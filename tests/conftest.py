"""Shared fixtures for SCADA integration tests.

Provides process management for the three pipeline components:
  - sim (plc_publisher.py) — publishes on domain 15
  - scada_select (C++ binary) — bridges domain 15 → 16
  - scada_web (FastAPI server) — reads domain 16, serves REST + WS

Tests that need the full pipeline use the `pipeline` fixture which starts
all three in dependency order and tears them down after the test.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Generator, List, Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SIM_SCRIPT = REPO_ROOT / "sim" / "plc_publisher.py"
SELECTOR_BIN = REPO_ROOT / "scada_select" / "build" / "scada_selector"
SCADA_WEB_CONFIG = REPO_ROOT / "scada_web" / "config.yaml"
SCADA_WEB_HOST = "127.0.0.1"
SCADA_WEB_PORT = 8765  # Test port to avoid clashing with dev server

# RTI Connext license — auto-detect if not already set in env
_LICENSE_CANDIDATES = [
    Path.home() / "rti_connext_dds-7.7.0" / "rti_license.dat",
    Path.home() / "rti_connext_dds-7.6.0" / "rti_license.dat",
    Path.home() / "rti_connext_dds-7.3.1" / "rti_license.dat",
    Path.home() / "rti_license.dat",
]


def _find_license() -> Optional[str]:
    if os.environ.get("RTI_LICENSE_FILE"):
        return os.environ["RTI_LICENSE_FILE"]
    for candidate in _LICENSE_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    return None


RTI_LICENSE_FILE = _find_license()


def _wait_for_http(host: str, port: int, path: str = "/health",
                   timeout: float = 15.0) -> bool:
    """Poll until HTTP endpoint responds 200 or timeout expires."""
    import urllib.request
    import urllib.error

    deadline = time.monotonic() + timeout
    url = f"http://{host}:{port}{path}"
    while time.monotonic() < deadline:
        try:
            resp = urllib.request.urlopen(url, timeout=2)
            if resp.status == 200:
                return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.3)
    return False


def _start_process(cmd: List[str], label: str, env=None,
                   cwd=None) -> subprocess.Popen:
    """Start a subprocess, capturing stdout/stderr for diagnostics."""
    merged_env = {**os.environ, **(env or {})}
    if RTI_LICENSE_FILE:
        merged_env.setdefault("RTI_LICENSE_FILE", RTI_LICENSE_FILE)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=cwd or REPO_ROOT,
        env=merged_env,
    )
    # Give it a moment to crash-check
    time.sleep(0.5)
    if proc.poll() is not None:
        output = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
        raise RuntimeError(
            f"{label} exited immediately (rc={proc.returncode}):\n{output}"
        )
    return proc


def _stop_process(proc: subprocess.Popen, label: str, timeout: float = 5.0):
    """Gracefully stop a subprocess (SIGTERM then SIGKILL)."""
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)


@pytest.fixture(scope="session")
def sim_process() -> Generator[subprocess.Popen, None, None]:
    """Start the PLC simulator (publishes on domain 15)."""
    proc = _start_process(
        ["python3", str(SIM_SCRIPT), "--domain-id", "15"],
        label="sim/plc_publisher",
    )
    # Allow time for MetaData (TRANSIENT_LOCAL) burst to complete
    time.sleep(2.0)
    yield proc
    _stop_process(proc, "sim/plc_publisher")


@pytest.fixture(scope="session")
def selector_process(sim_process) -> Generator[subprocess.Popen, None, None]:
    """Start scada_select (bridges domain 15 → 16).

    Depends on sim_process so the field domain has data when selector starts.
    """
    if not SELECTOR_BIN.exists():
        pytest.skip(f"scada_selector binary not found at {SELECTOR_BIN}")
    config_file = REPO_ROOT / "scada_select" / "config.yaml"
    proc = _start_process(
        [str(SELECTOR_BIN), "--config", str(config_file)],
        label="scada_select",
        cwd=REPO_ROOT / "scada_select" / "build",
    )
    time.sleep(2.0)
    yield proc
    _stop_process(proc, "scada_select")


@pytest.fixture(scope="session")
def scada_web_process(selector_process) -> Generator[subprocess.Popen, None, None]:
    """Start the scada_web FastAPI server on the test port.

    Depends on selector_process so the presentation domain is populated
    (sim → selector → domain 16 → scada_web readers).
    """
    proc = _start_process(
        [
            "python3", "-m", "scada_web",
            "--config", str(SCADA_WEB_CONFIG),
            "--host", SCADA_WEB_HOST,
            "--port", str(SCADA_WEB_PORT),
        ],
        label="scada_web",
    )
    if not _wait_for_http(SCADA_WEB_HOST, SCADA_WEB_PORT):
        output = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
        _stop_process(proc, "scada_web")
        raise RuntimeError(f"scada_web failed to become healthy:\n{output}")
    yield proc
    _stop_process(proc, "scada_web")


@pytest.fixture(scope="session")
def pipeline(scada_web_process):
    """Convenience fixture — ensures the full pipeline is running.

    Returns a dict with connection details for tests to use.
    """
    return {
        "base_url": f"http://{SCADA_WEB_HOST}:{SCADA_WEB_PORT}",
        "ws_url": f"ws://{SCADA_WEB_HOST}:{SCADA_WEB_PORT}/ws",
        "host": SCADA_WEB_HOST,
        "port": SCADA_WEB_PORT,
    }
