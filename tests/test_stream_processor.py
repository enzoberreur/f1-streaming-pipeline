"""Unit tests for the F1 stream processor.

Covers the three pieces of pure business logic the processor relies on:
the sliding TimeWindow, the AnomalyDetector, and the PitStopStrategyCalculator,
plus the end-to-end `process_message` entry point.
"""

from datetime import datetime, timedelta

import pytest


def _telemetry_dict(**overrides):
    """A complete, valid telemetry payload. Override individual fields as needed."""
    base = {
        "timestamp": "2026-06-07T12:00:00+00:00",
        "car_id": "SF-16",
        "team": "Scuderia Ferrari",
        "driver": "Charles Leclerc",
        "car_number": 16,
        "car_model": "SF-24",
        "lap": 10,
        "speed_kmh": 290.0,
        "rpm": 11000,
        "gear": 7,
        "throttle_percent": 95.0,
        "engine_temp_celsius": 110.0,
        "brake_pressure_bar": 120.0,
        "brake_temp_fl_celsius": 450.0,
        "brake_temp_fr_celsius": 450.0,
        "brake_temp_rl_celsius": 430.0,
        "brake_temp_rr_celsius": 430.0,
        "tire_compound": "SOFT",
        "tire_temp_fl_celsius": 95.0,
        "tire_temp_fr_celsius": 95.0,
        "tire_temp_rl_celsius": 92.0,
        "tire_temp_rr_celsius": 92.0,
        "tire_pressure_fl_psi": 23.0,
        "tire_pressure_fr_psi": 23.0,
        "tire_pressure_rl_psi": 21.0,
        "tire_pressure_rr_psi": 21.0,
        "tire_wear_percent": 20.0,
        "drs_status": "closed",
        "ers_power_kw": 120.0,
        "fuel_remaining_kg": 50.0,
        "track_temp_celsius": 40.0,
        "air_temp_celsius": 28.0,
        "humidity_percent": 45.0,
        "lap_time_seconds": 80.0,
        "stint_health_score": 90.0,
        "pit_window_probability": 0.1,
        "surface_condition": "dry",
        "strategy_recommendation": "hold",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# TimeWindow
# --------------------------------------------------------------------------- #

def test_timewindow_all_above_threshold(stream_processor_mod):
    tw = stream_processor_mod.TimeWindow(duration_seconds=2.0)
    t0 = datetime(2026, 6, 7, 12, 0, 0)
    tw.add(t0, 1000.0)
    tw.add(t0 + timedelta(seconds=1), 1010.0)
    assert tw.all_above_threshold(950.0) is True
    assert tw.all_above_threshold(1005.0) is False


def test_timewindow_evicts_old_samples(stream_processor_mod):
    tw = stream_processor_mod.TimeWindow(duration_seconds=2.0)
    t0 = datetime(2026, 6, 7, 12, 0, 0)
    tw.add(t0, 500.0)
    tw.add(t0 + timedelta(seconds=5), 1000.0)  # 5s later: the old sample falls out
    assert tw.all_above_threshold(950.0) is True
    assert tw.get_average() == 1000.0


def test_timewindow_get_duration(stream_processor_mod):
    tw = stream_processor_mod.TimeWindow(duration_seconds=10.0)
    t0 = datetime(2026, 6, 7, 12, 0, 0)
    tw.add(t0, 1.0)
    tw.add(t0 + timedelta(seconds=3), 2.0)
    assert tw.get_duration() == pytest.approx(3.0)


# --------------------------------------------------------------------------- #
# AnomalyDetector
# --------------------------------------------------------------------------- #

def test_no_anomaly_under_normal_conditions(stream_processor_mod):
    detector = stream_processor_mod.AnomalyDetector()
    data = stream_processor_mod.TelemetryData(**_telemetry_dict())
    assert detector.detect(data) == []


def test_brake_overheat_detected_when_sustained(stream_processor_mod):
    detector = stream_processor_mod.AnomalyDetector()
    hot = 1000.0  # above BRAKE_TEMP_CRITICAL (950)

    def hot_reading(second):
        return stream_processor_mod.TelemetryData(**_telemetry_dict(
            timestamp=f"2026-06-07T12:00:0{second}+00:00",
            brake_temp_fl_celsius=hot, brake_temp_fr_celsius=hot,
            brake_temp_rl_celsius=hot, brake_temp_rr_celsius=hot,
        ))

    # A single hot reading is not yet "sustained" over the detection window.
    assert detector.detect(hot_reading(0)) == []

    # Keep the brakes hot; once the window spans the full 2s, it must fire.
    anomalies = []
    for second in (1, 2, 3):
        anomalies = detector.detect(hot_reading(second))
        if anomalies:
            break

    assert anomalies, "expected a sustained brake overheat anomaly"
    assert all(a.severity == "critical" for a in anomalies)
    assert any(a.anomaly_type.startswith("brake_overheat") for a in anomalies)


# --------------------------------------------------------------------------- #
# PitStopStrategyCalculator
# --------------------------------------------------------------------------- #

def test_brake_degradation_bounds(stream_processor_mod):
    calc = stream_processor_mod.PitStopStrategyCalculator()
    cool = stream_processor_mod.TelemetryData(**_telemetry_dict(
        brake_temp_fl_celsius=250, brake_temp_fr_celsius=250,
        brake_temp_rl_celsius=250, brake_temp_rr_celsius=250,
    ))
    hot = stream_processor_mod.TelemetryData(**_telemetry_dict(
        brake_temp_fl_celsius=950, brake_temp_fr_celsius=950,
        brake_temp_rl_celsius=950, brake_temp_rr_celsius=950,
    ))
    assert calc._calculate_brake_degradation(cool) == pytest.approx(0.0)
    assert calc._calculate_brake_degradation(hot) == pytest.approx(100.0)


def test_pitstop_low_urgency_when_fresh(stream_processor_mod):
    calc = stream_processor_mod.PitStopStrategyCalculator()
    data = stream_processor_mod.TelemetryData(**_telemetry_dict(
        tire_wear_percent=5.0,
        brake_temp_fl_celsius=300, brake_temp_fr_celsius=300,
        brake_temp_rl_celsius=300, brake_temp_rr_celsius=300,
    ))
    rec = calc.calculate_score(data, anomalies=[])
    assert 0 <= rec.score <= 100
    assert rec.urgency == "low"


def test_pitstop_escalates_with_degradation(stream_processor_mod):
    """Worn tyres + dropping pace + hot brakes should push urgency to the top tier."""
    calc = stream_processor_mod.PitStopStrategyCalculator()

    # 10 healthy, fast laps to seed the speed-loss baseline
    for _ in range(10):
        calc.calculate_score(stream_processor_mod.TelemetryData(**_telemetry_dict(
            speed_kmh=300.0, tire_wear_percent=10.0,
            brake_temp_fl_celsius=300, brake_temp_fr_celsius=300,
            brake_temp_rl_celsius=300, brake_temp_rr_celsius=300,
        )), [])

    # 10 degraded, slow laps
    rec = None
    for _ in range(10):
        rec = calc.calculate_score(stream_processor_mod.TelemetryData(**_telemetry_dict(
            speed_kmh=150.0, tire_wear_percent=100.0,
            brake_temp_fl_celsius=950, brake_temp_fr_celsius=950,
            brake_temp_rl_celsius=950, brake_temp_rr_celsius=950,
        )), [])

    assert rec.score >= 75
    assert rec.urgency in {"high", "critical"}


# --------------------------------------------------------------------------- #
# StreamProcessor.process_message (end-to-end)
# --------------------------------------------------------------------------- #

def test_process_message_returns_pitstop(stream_processor_mod):
    processor = stream_processor_mod.StreamProcessor()
    result = processor.process_message(_telemetry_dict())
    assert result["status"] == "processed"
    assert result["team"] == "Scuderia Ferrari"
    assert "pitstop" in result
    assert 0 <= result["pitstop"]["score"] <= 100


def test_process_message_ignores_unknown_fields(stream_processor_mod):
    processor = stream_processor_mod.StreamProcessor()
    payload = _telemetry_dict(unexpected_field="should be dropped silently")
    result = processor.process_message(payload)  # must not raise
    assert result["status"] == "processed"
