"""Unit tests for the stream-processor PostgreSQL writer (db_writer.py).

The writer must batch telemetry readings, flush by size or interval, persist
anomalies promptly, and degrade gracefully (drop the batch, log, reconnect
later) when the database is down. All tests use a mocked connection factory:
no real PostgreSQL instance and no psycopg2 are required.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _telemetry(car_id="SF-16", **overrides):
    """A minimal telemetry object with every field the writer reads."""
    base = {
        "timestamp": "2026-06-07T12:00:00+00:00",
        "car_id": car_id,
        "team": "Scuderia Ferrari",
        "car_model": "SF-24",
        "speed_kmh": 290.0,
        "engine_temp_celsius": 110.0,
        "brake_temp_fl_celsius": 450.0,
        "brake_temp_fr_celsius": 450.0,
        "brake_temp_rl_celsius": 430.0,
        "brake_temp_rr_celsius": 430.0,
        "tire_temp_fl_celsius": 95.0,
        "tire_temp_fr_celsius": 95.0,
        "tire_temp_rl_celsius": 92.0,
        "tire_temp_rr_celsius": 92.0,
        "tire_wear_percent": 20.0,
        "fuel_remaining_kg": 50.0,
        "throttle_percent": 95.0,
        "gear": 7,
        "rpm": 11000,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _anomaly(car_id="SF-16"):
    return SimpleNamespace(
        timestamp=datetime(2026, 6, 7, 12, 0, 0),
        car_id=car_id,
        anomaly_type="brake_overheat_fl",
        severity="critical",
        message="brake FL overheating",
    )


def _mock_connection(session_id=42, existing_session=False):
    """A MagicMock psycopg2-like connection whose cursor answers the bootstrap.

    fetchone() is consumed by: circuit_id SELECT, session SELECT, then either
    the session INSERT RETURNING (fresh DB) or nothing (existing session).
    Later fetchone() calls (teams lookups in _ensure_cars) return team_id 1.
    """
    conn = MagicMock(name="connection")
    cursor = conn.cursor.return_value.__enter__.return_value
    if existing_session:
        bootstrap_rows = [(1,), (session_id,)]
    else:
        bootstrap_rows = [(1,), None, (session_id,)]
    rows = iter(bootstrap_rows)
    cursor.fetchone.side_effect = lambda: next(rows, (1,))
    return conn, cursor


def _writer(db_writer_mod, conn, batch_size=3):
    """A writer wired to a mocked connection; the flush thread is NOT started."""
    return db_writer_mod.TelemetryDBWriter(
        "postgresql://test:test@localhost/test",
        batch_size=batch_size,
        flush_interval=0.1,
        connection_factory=lambda: conn,
    )


# --------------------------------------------------------------------------- #
# Activation via l'environnement
# --------------------------------------------------------------------------- #

def test_from_env_disabled_by_default(db_writer_mod, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ENABLE_DB_WRITES", raising=False)
    assert db_writer_mod.TelemetryDBWriter.from_env() is None


def test_from_env_requires_both_variables(db_writer_mod, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:y@db/test")
    monkeypatch.delenv("ENABLE_DB_WRITES", raising=False)
    assert db_writer_mod.TelemetryDBWriter.from_env() is None

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ENABLE_DB_WRITES", "true")
    assert db_writer_mod.TelemetryDBWriter.from_env() is None


def test_from_env_enabled(db_writer_mod, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:y@db/test")
    monkeypatch.setenv("ENABLE_DB_WRITES", "true")
    monkeypatch.setattr(db_writer_mod, "PSYCOPG2_AVAILABLE", True)
    writer = db_writer_mod.TelemetryDBWriter.from_env()
    assert writer is not None
    assert writer.database_url == "postgresql://x:y@db/test"


# --------------------------------------------------------------------------- #
# Batching
# --------------------------------------------------------------------------- #

def test_buffers_until_batch_size(db_writer_mod):
    conn, _ = _mock_connection()
    writer = _writer(db_writer_mod, conn, batch_size=3)

    writer.add_reading(_telemetry())
    writer.add_reading(_telemetry())
    assert not writer._flush_event.is_set(), "must not flush below the batch size"

    writer.add_reading(_telemetry())
    assert writer._flush_event.is_set(), "a full buffer must request a flush"


def test_flush_writes_batch_with_session_id(db_writer_mod):
    conn, cursor = _mock_connection(session_id=42)
    writer = _writer(db_writer_mod, conn, batch_size=3)

    for _ in range(3):
        writer.add_reading(_telemetry())
    writer.flush()

    assert cursor.executemany.call_count == 1
    sql, rows = cursor.executemany.call_args[0]
    assert "telemetry_readings" in sql
    assert len(rows) == 3
    assert all(row[0] == 42 for row in rows), "session_id must prefix every row"
    conn.commit.assert_called()


def test_flush_without_data_is_a_noop(db_writer_mod):
    factory = MagicMock(name="factory")
    writer = db_writer_mod.TelemetryDBWriter(
        "postgresql://test:test@localhost/test", connection_factory=factory,
    )
    writer.flush()
    factory.assert_not_called()


def test_parent_car_rows_inserted_once(db_writer_mod):
    conn, cursor = _mock_connection()
    writer = _writer(db_writer_mod, conn, batch_size=2)

    writer.add_reading(_telemetry(car_id="SF-16"))
    writer.add_reading(_telemetry(car_id="SF-16"))
    writer.flush()
    writer.add_reading(_telemetry(car_id="SF-16"))
    writer.flush()

    car_inserts = [
        call for call in cursor.execute.call_args_list
        if "INSERT INTO cars" in call[0][0]
    ]
    assert len(car_inserts) == 1, "a known car must not be re-inserted"


def test_existing_session_is_reused(db_writer_mod):
    conn, cursor = _mock_connection(session_id=7, existing_session=True)
    writer = _writer(db_writer_mod, conn)

    writer.add_reading(_telemetry())
    writer.flush()

    assert writer._session_id == 7
    session_inserts = [
        call for call in cursor.execute.call_args_list
        if "INSERT INTO sessions" in call[0][0]
    ]
    assert session_inserts == []


# --------------------------------------------------------------------------- #
# Anomalies
# --------------------------------------------------------------------------- #

def test_anomaly_triggers_immediate_flush_request(db_writer_mod):
    conn, cursor = _mock_connection(session_id=42)
    writer = _writer(db_writer_mod, conn)

    writer.add_anomaly(_anomaly())
    assert writer._flush_event.is_set(), "anomalies must be flushed promptly"

    writer.flush()
    sql, rows = cursor.executemany.call_args[0]
    assert "anomalies" in sql
    assert rows == [(42, "SF-16", datetime(2026, 6, 7, 12, 0, 0),
                     "brake_overheat_fl", "critical", "brake FL overheating")]


# --------------------------------------------------------------------------- #
# Pannes de la base (le chemin critique ne doit jamais casser)
# --------------------------------------------------------------------------- #

def test_db_down_drops_batch_without_raising(db_writer_mod):
    factory = MagicMock(side_effect=ConnectionError("db is down"))
    writer = db_writer_mod.TelemetryDBWriter(
        "postgresql://test:test@localhost/test",
        batch_size=2,
        connection_factory=factory,
    )

    writer.add_reading(_telemetry())
    writer.add_anomaly(_anomaly())
    writer.flush()  # must not raise

    assert writer._readings == [], "the failed batch must be dropped"
    assert writer._anomalies == []

    # The writer retries the connection on the next flush.
    writer.add_reading(_telemetry())
    writer.flush()
    assert factory.call_count == 2


def test_failed_insert_resets_the_connection(db_writer_mod):
    good_conn, _ = _mock_connection()
    factory = MagicMock(return_value=good_conn)
    writer = db_writer_mod.TelemetryDBWriter(
        "postgresql://test:test@localhost/test",
        batch_size=10,
        connection_factory=factory,
    )

    writer.add_reading(_telemetry())
    writer.flush()  # first flush succeeds and opens the connection
    assert factory.call_count == 1

    cursor = good_conn.cursor.return_value.__enter__.return_value
    cursor.executemany.side_effect = RuntimeError("insert failed")
    writer.add_reading(_telemetry())
    writer.flush()  # must swallow the error

    good_conn.rollback.assert_called()
    good_conn.close.assert_called()
    assert writer._conn is None, "a failed flush must force a reconnect"

    cursor.executemany.side_effect = None
    writer.add_reading(_telemetry())
    writer.flush()
    assert factory.call_count == 2


def test_bad_reading_is_dropped_silently(db_writer_mod):
    conn, _ = _mock_connection()
    writer = _writer(db_writer_mod, conn)

    writer.add_reading(_telemetry(timestamp="not-a-timestamp"))  # must not raise
    assert writer._readings == []
