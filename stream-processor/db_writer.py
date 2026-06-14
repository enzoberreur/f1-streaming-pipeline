#!/usr/bin/env python3
"""
Ferrari F1 Stream Processor - Persistance PostgreSQL
Ecrit les lectures de télémétrie et les anomalies dans le schéma opérationnel
(sql/ddl/01_operational_schema.sql) sans jamais bloquer le chemin critique.

Activé uniquement si DATABASE_URL est défini ET ENABLE_DB_WRITES=true.
Les lectures sont mises en tampon puis insérées par lots (executemany) depuis
un thread dédié; les anomalies déclenchent un flush immédiat. Toute erreur DB
est loguée puis ignorée: le lot en échec est abandonné et compté dans une
métrique Prometheus, le traitement temps réel n'est jamais interrompu.
"""

import logging
import os
import threading
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# psycopg2 est optionnel: sans lui, la persistance est simplement désactivée
try:
    import psycopg2
    PSYCOPG2_AVAILABLE = True
except ImportError:
    psycopg2 = None
    PSYCOPG2_AVAILABLE = False

# Métriques Prometheus (registre par défaut, partagé avec main.py)
try:
    from prometheus_client import Counter

    db_rows_written = Counter(
        'ferrari_db_rows_written_total',
        'Nombre de lignes persistées dans PostgreSQL',
        ['table']
    )

    db_rows_dropped = Counter(
        'ferrari_db_rows_dropped_total',
        'Nombre de lignes abandonnées suite à une erreur DB',
        ['table']
    )
except ImportError:  # pragma: no cover - prometheus_client est une dépendance du service
    db_rows_written = None
    db_rows_dropped = None


# ============================================================================
# REQUÊTES SQL (schéma opérationnel, voir sql/ddl/01_operational_schema.sql)
# ============================================================================

INSERT_READING_SQL = """
    INSERT INTO telemetry_readings (
        session_id, car_id, recorded_at, speed_kmh, engine_temp_c, brake_temp_c,
        tire_temp_c, tire_wear_percent, fuel_remaining_kg, throttle_percent,
        brake_percent, gear, rpm
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

INSERT_ANOMALY_SQL = """
    INSERT INTO anomalies (
        session_id, car_id, recorded_at, anomaly_type, severity, description
    ) VALUES (%s, %s, %s, %s, %s, %s)
"""


def _env_flag(name: str, default: str = "false") -> bool:
    """Interprète une variable d'environnement booléenne."""
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _parse_timestamp(value: str) -> datetime:
    """Parse un timestamp ISO 8601 (même convention que l'AnomalyDetector)."""
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def _count_written(table: str, count: int) -> None:
    if db_rows_written is not None and count:
        db_rows_written.labels(table=table).inc(count)


def _count_dropped(table: str, count: int = 1) -> None:
    if db_rows_dropped is not None and count:
        db_rows_dropped.labels(table=table).inc(count)


# ============================================================================
# WRITER POSTGRESQL
# ============================================================================

class TelemetryDBWriter:
    """Écriture par lots vers le schéma opérationnel PostgreSQL.

    Le chemin critique (add_reading / add_anomaly) ne fait que mettre en
    tampon en mémoire; toutes les I/O se font dans un thread d'arrière-plan.
    """

    BATCH_SIZE = 100
    FLUSH_INTERVAL_SECONDS = 5.0

    # Lignes parentes de démo créées de manière idempotente au démarrage
    DEMO_CIRCUIT = ("Monza", "Italy", 5.793, 53)
    DEMO_SESSION_TYPE = "race"

    def __init__(
        self,
        database_url: str,
        batch_size: int = BATCH_SIZE,
        flush_interval: float = FLUSH_INTERVAL_SECONDS,
        connection_factory: Optional[Callable] = None,
    ):
        if connection_factory is None and not PSYCOPG2_AVAILABLE:
            raise RuntimeError("psycopg2 n'est pas installé; persistance impossible")

        self.database_url = database_url
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._connection_factory = connection_factory or self._default_connection_factory

        self._conn = None
        self._session_id: Optional[int] = None
        self._known_cars: set = set()

        # Tampons protégés par verrou (remplis par le chemin critique)
        self._lock = threading.Lock()
        self._readings: List[Tuple] = []
        self._anomalies: List[Tuple] = []
        self._pending_cars: Dict[str, Tuple[str, str]] = {}  # car_id -> (team, modèle)

        self._flush_event = threading.Event()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ #
    # Cycle de vie
    # ------------------------------------------------------------------ #

    @classmethod
    def from_env(cls) -> Optional["TelemetryDBWriter"]:
        """Construit un writer depuis l'environnement, ou None si désactivé."""
        database_url = os.getenv("DATABASE_URL")
        if not database_url or not _env_flag("ENABLE_DB_WRITES"):
            logger.info("Persistance PostgreSQL désactivée (DATABASE_URL + ENABLE_DB_WRITES=true requis)")
            return None
        if not PSYCOPG2_AVAILABLE:
            logger.warning("ENABLE_DB_WRITES=true mais psycopg2 n'est pas installé; persistance désactivée")
            return None
        return cls(database_url)

    def start(self) -> None:
        """Démarre le thread de flush en arrière-plan."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="db-writer", daemon=True)
        self._thread.start()
        logger.info(
            "Persistance PostgreSQL activée (batch=%s, intervalle=%ss)",
            self.batch_size, self.flush_interval,
        )

    def stop(self) -> None:
        """Arrête le thread et tente un dernier flush."""
        self._stop_event.set()
        self._flush_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self.flush_interval + 5)
            self._thread = None
        self.flush()
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def _run(self) -> None:
        """Boucle du thread: flush toutes les N secondes ou sur signal."""
        while not self._stop_event.is_set():
            self._flush_event.wait(timeout=self.flush_interval)
            self._flush_event.clear()
            self.flush()

    # ------------------------------------------------------------------ #
    # Chemin critique (jamais d'I/O, jamais d'exception propagée)
    # ------------------------------------------------------------------ #

    def add_reading(self, telemetry) -> None:
        """Met en tampon une lecture de télémétrie (session_id ajouté au flush)."""
        try:
            row = (
                telemetry.car_id,
                _parse_timestamp(telemetry.timestamp),
                telemetry.speed_kmh,
                telemetry.engine_temp_celsius,
                (telemetry.brake_temp_fl_celsius + telemetry.brake_temp_fr_celsius +
                 telemetry.brake_temp_rl_celsius + telemetry.brake_temp_rr_celsius) / 4,
                (telemetry.tire_temp_fl_celsius + telemetry.tire_temp_fr_celsius +
                 telemetry.tire_temp_rl_celsius + telemetry.tire_temp_rr_celsius) / 4,
                telemetry.tire_wear_percent,
                telemetry.fuel_remaining_kg,
                telemetry.throttle_percent,
                None,  # brake_percent: le flux expose une pression (bar), pas un pourcentage
                telemetry.gear,
                telemetry.rpm,
            )
            with self._lock:
                if telemetry.car_id not in self._known_cars:
                    self._pending_cars[telemetry.car_id] = (telemetry.team, telemetry.car_model)
                self._readings.append(row)
                buffered = len(self._readings)
            if buffered >= self.batch_size:
                self._flush_event.set()
        except Exception as exc:
            _count_dropped('telemetry_readings')
            logger.debug("Lecture télémétrie non persistée: %s", exc)

    def add_anomaly(self, anomaly) -> None:
        """Met en tampon une anomalie et déclenche un flush immédiat."""
        try:
            row = (
                anomaly.car_id,
                anomaly.timestamp,
                anomaly.anomaly_type,
                anomaly.severity,
                anomaly.message,
            )
            with self._lock:
                self._anomalies.append(row)
            self._flush_event.set()
        except Exception as exc:
            _count_dropped('anomalies')
            logger.debug("Anomalie non persistée: %s", exc)

    # ------------------------------------------------------------------ #
    # Écriture (thread d'arrière-plan)
    # ------------------------------------------------------------------ #

    def flush(self) -> None:
        """Vide les tampons vers PostgreSQL; en cas d'erreur le lot est abandonné."""
        with self._lock:
            readings, self._readings = self._readings, []
            anomalies, self._anomalies = self._anomalies, []
            pending_cars, self._pending_cars = self._pending_cars, {}

        if not (readings or anomalies or pending_cars):
            return

        try:
            conn = self._ensure_connection()
            with conn.cursor() as cur:
                self._ensure_cars(cur, pending_cars)
                if readings:
                    cur.executemany(
                        INSERT_READING_SQL,
                        [(self._session_id,) + row for row in readings],
                    )
                if anomalies:
                    cur.executemany(
                        INSERT_ANOMALY_SQL,
                        [(self._session_id,) + row for row in anomalies],
                    )
            conn.commit()
            with self._lock:
                self._known_cars.update(pending_cars)
            _count_written('telemetry_readings', len(readings))
            _count_written('anomalies', len(anomalies))
        except Exception as exc:
            self._handle_failure(exc, len(readings), len(anomalies))

    def _default_connection_factory(self):
        return psycopg2.connect(self.database_url)

    def _ensure_connection(self):
        """Ouvre la connexion (lazy) et prépare la session de démo."""
        if self._conn is None:
            self._conn = self._connection_factory()
            self._bootstrap()
        return self._conn

    def _bootstrap(self) -> None:
        """Crée de manière idempotente le circuit et la session de démo."""
        name, country, length_km, total_laps = self.DEMO_CIRCUIT
        with self._conn.cursor() as cur:
            # circuits n'a pas de contrainte UNIQUE sur name: INSERT ... WHERE NOT EXISTS
            cur.execute(
                "INSERT INTO circuits (name, country, length_km, total_laps) "
                "SELECT %s, %s, %s, %s "
                "WHERE NOT EXISTS (SELECT 1 FROM circuits WHERE name = %s)",
                (name, country, length_km, total_laps, name),
            )
            cur.execute(
                "SELECT circuit_id FROM circuits WHERE name = %s ORDER BY circuit_id LIMIT 1",
                (name,),
            )
            circuit_id = cur.fetchone()[0]

            cur.execute(
                "SELECT session_id FROM sessions "
                "WHERE circuit_id = %s AND session_type = %s "
                "ORDER BY session_id LIMIT 1",
                (circuit_id, self.DEMO_SESSION_TYPE),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    "INSERT INTO sessions (circuit_id, session_type, start_time) "
                    "VALUES (%s, %s, NOW()) RETURNING session_id",
                    (circuit_id, self.DEMO_SESSION_TYPE),
                )
                row = cur.fetchone()
            self._session_id = row[0]
        self._conn.commit()
        logger.info("Session opérationnelle prête (session_id=%s)", self._session_id)

    def _ensure_cars(self, cur, pending_cars: Dict[str, Tuple[str, str]]) -> None:
        """Crée les lignes parentes teams/cars manquantes (ON CONFLICT DO NOTHING)."""
        for car_id, (team_name, car_model) in pending_cars.items():
            cur.execute(
                "INSERT INTO teams (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
                (team_name,),
            )
            cur.execute("SELECT team_id FROM teams WHERE name = %s", (team_name,))
            team_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO cars (car_id, team_id, chassis) VALUES (%s, %s, %s) "
                "ON CONFLICT (car_id) DO NOTHING",
                (car_id, team_id, car_model),
            )

    def _handle_failure(self, exc: Exception, readings_count: int, anomalies_count: int) -> None:
        """Abandonne le lot en échec, compte les pertes et force une reconnexion."""
        logger.warning(
            "Écriture PostgreSQL échouée (%s lectures, %s anomalies abandonnées): %s",
            readings_count, anomalies_count, exc,
        )
        _count_dropped('telemetry_readings', readings_count)
        _count_dropped('anomalies', anomalies_count)
        if self._conn is not None:
            try:
                self._conn.rollback()
            except Exception:
                pass
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
