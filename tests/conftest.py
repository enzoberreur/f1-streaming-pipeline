"""Shared pytest fixtures.

The service directories use hyphens (`stream-processor`, `sensor-simulator`),
which are not importable Python package names. We therefore load each `main.py`
explicitly from its file path under a unique module name so the unit tests can
exercise the real production code.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_module(relative_path: str, module_name: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def stream_processor_mod():
    """The stream-processor service module (anomaly detection + pit-stop logic)."""
    return _load_module("stream-processor/main.py", "f1_stream_processor")


@pytest.fixture(scope="session")
def simulator_mod():
    """The sensor-simulator service module (telemetry + anomaly generation)."""
    return _load_module("sensor-simulator/main.py", "f1_sensor_simulator")
