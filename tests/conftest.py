"""Shared fixtures for SCADA integration tests.

Provides process management for the three pipeline components:
  - sim (plc_publisher.py) — publishes on domain 15
  - scada_select (C++ binary) — bridges domain 15 → 16
  - scada_web (FastAPI server) — reads domain 16, serves REST + WS

Tests that need the full pipeline use the `pipeline` fixture which starts
all three in dependency order and tears them down after the test.
"""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Generator, List

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SIM_SCRIPT = REPO_ROOT / "scripts" / "start-sim.sh"
SELECTOR_SCRIPT = REPO_ROOT / "scripts" / "start-select.sh"
WEB_SCRIPT = REPO_ROOT / "scripts" / "start-web.sh"
SCADA_WEB_CONFIG = REPO_ROOT / "scada_web" / "config.yaml"
SCADA_WEB_HOST = "127.0.0.1"
SCADA_WEB_PORT = 8765  # Test port to avoid clashing with dev server


# ─── RTI license auto-detect (mirrors scripts/start-*.sh find_license) ───────
def _find_and_set_license() -> None:
    """Discover RTI license file the same way the start scripts do."""
    if os.environ.get("RTI_LICENSE_FILE"):
        return  # already set

    # Check NDDSHOME first
    nddshome = os.environ.get("NDDSHOME", "")
    if nddshome:
        candidate = Path(nddshome) / "rti_license.dat"
        if candidate.exists():
            os.environ["RTI_LICENSE_FILE"] = str(candidate)
            return

    # Scan well-known locations (newest version first)
    home = Path.home()
    candidates = sorted(home.glob("rti_connext_dds-*/rti_license.dat"), reverse=True)
    candidates += sorted(Path("/opt").glob("rti_connext_dds-*/rti_license.dat"), reverse=True)
    candidates.append(home / "rti_license.dat")

    for candidate in candidates:
        if candidate.exists():
            os.environ["RTI_LICENSE_FILE"] = str(candidate)
            return


_find_and_set_license()


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
    """Start a subprocess, capturing stdout/stderr for startup diagnostics."""
    merged_env = {**os.environ, **(env or {})}
    # Startup output goes to a temp file, not a PIPE. These fixtures are
    # long-lived and nothing drains the pipe during the session, so a PIPE fills
    # its 64 KiB buffer and then blocks the component mid-write -- which presents
    # as a component going silent, indistinguishable from a DDS stall. A file
    # never blocks the writer, and each component also has its own rotating log
    # under logs/ for anything past startup.
    log = tempfile.TemporaryFile()
    proc = subprocess.Popen(
        cmd,
        stdout=log,
        stderr=subprocess.STDOUT,
        cwd=cwd or REPO_ROOT,
        env=merged_env,
    )
    proc._startup_log = log  # type: ignore[attr-defined]  # for _drain_startup_log
    # Give it a moment to crash-check
    time.sleep(0.5)
    if proc.poll() is not None:
        raise RuntimeError(
            f"{label} exited immediately (rc={proc.returncode}):\n"
            f"{_drain_startup_log(proc)}"
        )
    return proc


def _drain_startup_log(proc: subprocess.Popen) -> str:
    """Read whatever the process has written so far. Never blocks."""
    log = getattr(proc, "_startup_log", None)
    if log is None:
        return ""
    log.seek(0)
    return log.read().decode(errors="replace")


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
    """Start the PLC simulator (publishes on domain 15) via start script."""
    proc = _start_process(
        ["bash", str(SIM_SCRIPT), "--domain-id", "15"],
        label="sim/plc_publisher",
    )
    # Allow time for MetaData (TRANSIENT_LOCAL) burst to complete
    time.sleep(2.0)
    yield proc
    _stop_process(proc, "sim/plc_publisher")


@pytest.fixture(scope="session")
def selector_process(sim_process) -> Generator[subprocess.Popen, None, None]:
    """Start scada_select (bridges domain 15 → 16) via start script.

    Depends on sim_process so the field domain has data when selector starts.
    """
    proc = _start_process(
        ["bash", str(SELECTOR_SCRIPT)],
        label="scada_select",
    )
    time.sleep(2.0)
    yield proc
    _stop_process(proc, "scada_select")


@pytest.fixture(scope="session")
def scada_web_process(selector_process) -> Generator[subprocess.Popen, None, None]:
    """Start the scada_web FastAPI server on the test port via start script.

    Depends on selector_process so the presentation domain is populated
    (sim → selector → domain 16 → scada_web readers).
    """
    proc = _start_process(
        [
            "bash", str(WEB_SCRIPT),
            "--config", str(SCADA_WEB_CONFIG),
            "--host", SCADA_WEB_HOST,
            "--port", str(SCADA_WEB_PORT),
        ],
        label="scada_web",
    )
    if not _wait_for_http(SCADA_WEB_HOST, SCADA_WEB_PORT):
        # Stop first, then read. This branch is reached precisely when the process
        # started but never became healthy -- i.e. it is still running -- so
        # reading its output before stopping it waits for an EOF that never comes.
        # That turned the most common startup failure (port still held, missing
        # license, QoS error) into an indefinite hang, and the RuntimeError below
        # was never raised.
        _stop_process(proc, "scada_web")
        raise RuntimeError(
            f"scada_web failed to become healthy:\n{_drain_startup_log(proc)}"
        )
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
