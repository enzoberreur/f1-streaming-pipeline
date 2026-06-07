"""Unit tests for the F1 sensor simulator (grid build + anomaly injection)."""

import pytest


def test_build_championship_grid_has_twenty_cars(simulator_mod):
    grid = simulator_mod.build_championship_grid()
    assert len(grid) == 20                      # 10 teams x 2 cars
    assert len({c.team for c in grid}) == 10    # ten distinct teams
    assert len({c.car_id for c in grid}) == 20  # every car id is unique


def test_generate_anomaly_returns_known_pair(simulator_mod):
    sim = simulator_mod.AnomalySimulator()
    anomaly_type, severity = sim.generate_anomaly()
    assert anomaly_type in sim.anomaly_types
    assert severity in {"warning", "critical"}


def test_apply_brake_overheat_scales_temperatures(simulator_mod):
    sim = simulator_mod.AnomalySimulator()
    data = {
        "brake_temp_fl_celsius": 400.0,
        "brake_temp_fr_celsius": 400.0,
        "brake_temp_rl_celsius": 400.0,
        "brake_temp_rr_celsius": 400.0,
    }
    out = sim.apply_anomaly(dict(data), "brake_overheat", "critical")
    assert out["brake_temp_fl_celsius"] == pytest.approx(400.0 * 1.6)
    assert out["brake_temp_rr_celsius"] == pytest.approx(400.0 * 1.6)


def test_apply_tire_pressure_loss_drops_pressure(simulator_mod):
    sim = simulator_mod.AnomalySimulator()
    data = {
        "tire_pressure_fl_psi": 23.0,
        "tire_pressure_fr_psi": 23.0,
        "tire_pressure_rl_psi": 21.0,
        "tire_pressure_rr_psi": 21.0,
    }
    out = sim.apply_anomaly(dict(data), "tire_pressure_loss", "warning")
    assert out["tire_pressure_fl_psi"] == pytest.approx(23.0 * 0.7)


def test_should_trigger_anomaly_respects_probability(simulator_mod):
    never = simulator_mod.AnomalySimulator(anomaly_probability=0.0)
    always = simulator_mod.AnomalySimulator(anomaly_probability=1.0)
    assert never.should_trigger_anomaly() is False
    assert always.should_trigger_anomaly() is True


def test_int_from_env_parsing(simulator_mod, monkeypatch):
    monkeypatch.setenv("F1_TEST_INT", "42")
    assert simulator_mod._int_from_env("F1_TEST_INT", 7) == 42

    monkeypatch.setenv("F1_TEST_INT", "-5")  # non-positive is rejected -> default
    assert simulator_mod._int_from_env("F1_TEST_INT", 7) == 7

    monkeypatch.setenv("F1_TEST_INT", "not-a-number")  # unparseable -> default
    assert simulator_mod._int_from_env("F1_TEST_INT", 7) == 7

    monkeypatch.delenv("F1_TEST_INT", raising=False)  # unset -> default
    assert simulator_mod._int_from_env("F1_TEST_INT", 7) == 7
