"""Integration tests for scada_web (FastAPI server + DDS gateway).

These tests exercise the REST API and WebSocket interface with the full
DDS pipeline running underneath (sim → selector → scada_web). They verify
that scada_web correctly:
  - Reports health and lists topics
  - Serves samples from the DDS reader cache
  - Accepts WebSocket subscribe commands and pushes live data
  - Honors unsubscribe and disconnects cleanly
"""

import json
import time
import urllib.request
import urllib.error

import pytest
import websockets

# Mark all tests in this module as requiring the full pipeline
pytestmark = pytest.mark.pipeline


class TestHealthAndTopics:
    """REST API: /health, /api/v1/topics"""

    def test_health_returns_ok(self, pipeline):
        url = f"{pipeline['base_url']}/health"
        resp = urllib.request.urlopen(url, timeout=5)
        data = json.loads(resp.read())
        assert data["status"] == "ok"
        assert "topics" in data

    def test_topics_lists_expected_names(self, pipeline):
        url = f"{pipeline['base_url']}/api/v1/topics"
        resp = urllib.request.urlopen(url, timeout=5)
        data = json.loads(resp.read())
        topic_names = data["topics"]
        # scada_web subscribes to these on domain 16
        assert "PLC::SelectedMetaDataTopic" in topic_names
        assert "PLC::SelectedValueTopic" in topic_names


class TestRestSamples:
    """REST API: /api/v1/topics/{name}/samples"""

    def test_metadata_samples_available(self, pipeline):
        """MetaData is TRANSIENT_LOCAL — samples should be in cache."""
        url = (
            f"{pipeline['base_url']}/api/v1/topics/"
            "PLC::SelectedMetaDataTopic/samples/all"
        )
        resp = urllib.request.urlopen(url, timeout=5)
        data = json.loads(resp.read())
        samples = data["samples"]
        # Selector pre-enables uid 100-500, so we expect metadata samples
        assert len(samples) > 0, "Expected metadata samples in reader cache"
        # Each sample should have a uid
        for s in samples[:5]:
            assert "uid" in s

    def test_value_samples_arrive(self, pipeline):
        """IdValue samples are periodic — poll until at least one appears."""
        url = (
            f"{pipeline['base_url']}/api/v1/topics/"
            "PLC::SelectedValueTopic/samples/all"
        )
        deadline = time.monotonic() + 10.0
        samples = []
        while time.monotonic() < deadline:
            resp = urllib.request.urlopen(url, timeout=5)
            data = json.loads(resp.read())
            samples = data["samples"]
            if len(samples) > 0:
                break
            time.sleep(0.5)
        assert len(samples) > 0, "No value samples received within 10s"

    def test_single_sample_by_uid(self, pipeline):
        """GET /topics/{name}/samples?uid=N returns that specific uid."""
        uid = 150  # within selector's pre-enabled range (100-500)
        url = (
            f"{pipeline['base_url']}/api/v1/topics/"
            f"PLC::SelectedValueTopic/samples?uid={uid}"
        )
        # Wait for the periodic sample to arrive
        deadline = time.monotonic() + 10.0
        sample = None
        while time.monotonic() < deadline:
            resp = urllib.request.urlopen(url, timeout=5)
            data = json.loads(resp.read())
            if data.get("sample") is not None:
                sample = data["sample"]
                break
            time.sleep(0.5)
        assert sample is not None, f"No sample for uid {uid} within 10s"
        assert sample["uid"] == uid

    def test_unknown_topic_returns_404(self, pipeline):
        url = f"{pipeline['base_url']}/api/v1/topics/NonExistent/samples"
        try:
            urllib.request.urlopen(url, timeout=5)
            pytest.fail("Expected 404")
        except urllib.error.HTTPError as e:
            assert e.code == 404


class TestWebSocket:
    """WebSocket: /ws subscribe/unsubscribe/push"""

    @pytest.fixture
    def ws_connect(self, pipeline):
        """Provide a context manager that connects to the WebSocket."""
        import websockets.sync.client as ws_client

        def _connect():
            return ws_client.connect(pipeline["ws_url"], open_timeout=5,
                                     close_timeout=5)

        return _connect

    def test_subscribe_receives_samples(self, ws_connect):
        """Subscribe to a uid and verify samples are pushed."""
        with ws_connect() as ws:
            # Subscribe to uid 150 (selector pre-enabled, 1 Hz band)
            ws.send(json.dumps({
                "action": "subscribe",
                "uids": [150],
            }))
            # Wait for at least one pushed sample
            raw = ws.recv(timeout=10)
            msg = json.loads(raw)
            assert msg["uid"] == 150
            assert "data" in msg
            assert msg["topic"] == "PLC::SelectedValueTopic"

    def test_subscribe_multiple_uids(self, ws_connect):
        """Subscribe to multiple uids and verify samples arrive for each."""
        target_uids = {120, 130, 140}
        with ws_connect() as ws:
            ws.send(json.dumps({
                "action": "subscribe",
                "uids": list(target_uids),
            }))
            received_uids = set()
            deadline = time.monotonic() + 12.0
            while time.monotonic() < deadline and received_uids != target_uids:
                try:
                    raw = ws.recv(timeout=5)
                    msg = json.loads(raw)
                    if msg.get("uid") in target_uids:
                        received_uids.add(msg["uid"])
                except TimeoutError:
                    break
            assert received_uids == target_uids, (
                f"Missing uids: {target_uids - received_uids}"
            )

    def test_unsubscribe_stops_samples(self, ws_connect):
        """After unsubscribing, no more samples for that uid should arrive."""
        with ws_connect() as ws:
            ws.send(json.dumps({
                "action": "subscribe",
                "uids": [160],
            }))
            # Get one sample to confirm subscription works
            raw = ws.recv(timeout=10)
            assert json.loads(raw)["uid"] == 160

            # Unsubscribe
            ws.send(json.dumps({
                "action": "unsubscribe",
                "uids": [160],
            }))
            # Drain for 3 seconds — should get nothing for uid 160
            got_after_unsub = False
            try:
                while True:
                    raw = ws.recv(timeout=3)
                    msg = json.loads(raw)
                    if msg.get("uid") == 160:
                        got_after_unsub = True
                        break
            except TimeoutError:
                pass                      # silence, as intended
            except websockets.ConnectionClosed as exc:
                pytest.fail(f"connection closed during assert-silence window: {exc}")
            assert not got_after_unsub, "Received sample for uid 160 after unsubscribe"

    def test_set_period_accepted(self, ws_connect):
        """set_period command should be accepted without error."""
        with ws_connect() as ws:
            ws.send(json.dumps({
                "action": "set_period",
                "period_ms": 500,
            }))
            # Subscribe to verify the connection is still alive
            ws.send(json.dumps({
                "action": "subscribe",
                "uids": [170],
            }))
            raw = ws.recv(timeout=10)
            msg = json.loads(raw)
            assert msg["uid"] == 170
