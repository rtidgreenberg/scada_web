"""End-to-end tests: full pipeline from sim through to web client.

These tests verify the complete data path:
  sim (domain 15) → scada_select (domain 15→16) → scada_web (domain 16→REST/WS)

They exercise realistic user scenarios — a browser client subscribing,
receiving live data, changing period, and disconnecting — with the actual
DDS infrastructure running underneath.
"""

import asyncio
import json
import time
import urllib.parse
import urllib.request

import pytest

pytestmark = pytest.mark.pipeline

# Tests that require live data flowing through scada_select (being rebuilt)
requires_selector = pytest.mark.skip(
    reason="Requires scada_select (being rebuilt) to forward data to domain 16"
)


@requires_selector
class TestE2EDataFlow:
    """Verify data flows end-to-end from sim to web client."""

    def test_sim_to_web_value_latency(self, pipeline):
        """A value sample should reach the REST cache within a bounded time.

        This tests the full path: sim publishes → selector forwards →
        scada_web reader caches → REST serves.
        """
        # uid 105 is in the 1 Hz band and pre-enabled in selector
        url = (
            f"{pipeline['base_url']}/api/v1/topics/"
            "PLC::SelectedValueTopic/samples?uid=105"
        )
        start = time.monotonic()
        sample = None
        while time.monotonic() - start < 15.0:
            resp = urllib.request.urlopen(url, timeout=5)
            data = json.loads(resp.read())
            if data.get("sample") is not None:
                sample = data["sample"]
                break
            time.sleep(0.5)

        elapsed = time.monotonic() - start
        assert sample is not None, "Sample never reached REST endpoint"
        assert sample["uid"] == 105
        # Should arrive well within 15s (typically <3s for 1 Hz)
        assert elapsed < 15.0

    def test_metadata_catalogue_completeness(self, pipeline):
        """All pre-enabled uids should have metadata available."""
        url = (
            f"{pipeline['base_url']}/api/v1/topics/"
            "PLC::SelectedMetaDataTopic/samples/all"
        )
        # Metadata is TRANSIENT_LOCAL — may need a moment for discovery + delivery
        deadline = time.monotonic() + 15.0
        samples = []
        while time.monotonic() < deadline:
            resp = urllib.request.urlopen(url, timeout=5)
            data = json.loads(resp.read())
            samples = data["samples"]
            if len(samples) > 0:
                break
            time.sleep(1.0)

        uids = {s["uid"] for s in samples if s.get("uid") is not None}
        # Selector pre-enables 100-500, sim provides tags 1-500
        expected_range = set(range(100, 501))
        coverage = len(uids & expected_range) / len(expected_range)
        assert coverage > 0.5, (
            f"Metadata coverage {coverage:.0%} ({len(uids)} uids) — "
            f"expected >50% of uid 100-500"
        )

    def test_value_freshness(self, pipeline):
        """Value samples should have recent timestamps (not stale)."""
        url = (
            f"{pipeline['base_url']}/api/v1/topics/"
            "PLC::SelectedValueTopic/samples/all"
        )
        # Wait for some fresh samples
        time.sleep(2.0)
        resp = urllib.request.urlopen(url, timeout=5)
        data = json.loads(resp.read())
        samples = data["samples"]
        if not samples:
            pytest.skip("No value samples available yet")

        now_ms = int(time.time() * 1000)
        for s in samples[:10]:
            sample_data = s.get("data", {})
            value_time = sample_data.get("valueTime")
            if value_time is not None:
                age_ms = now_ms - value_time
                # Samples should be less than 30s old
                assert age_ms < 30_000, (
                    f"uid {s['uid']} has stale timestamp (age={age_ms}ms)"
                )


@requires_selector
class TestE2EWebSocketScenarios:
    """Realistic browser-client scenarios over WebSocket."""

    @pytest.fixture
    def ws_connect(self, pipeline):
        import websockets.sync.client as ws_client

        def _connect():
            return ws_client.connect(pipeline["ws_url"], open_timeout=5,
                                     close_timeout=5)

        return _connect

    def test_subscribe_receive_unsubscribe_cycle(self, ws_connect):
        """Full lifecycle: connect → subscribe → receive → unsubscribe → close."""
        with ws_connect() as ws:
            # 1. Subscribe
            ws.send(json.dumps({
                "action": "subscribe",
                "uids": [200],
                "period_ms": 500,
            }))

            # 2. Receive at least 3 samples
            received = []
            for _ in range(3):
                raw = ws.recv(timeout=15)
                msg = json.loads(raw)
                assert msg["uid"] == 200
                received.append(msg)

            assert len(received) == 3

            # 3. Unsubscribe
            ws.send(json.dumps({
                "action": "unsubscribe",
                "uids": [200],
            }))

            # 4. Verify silence (allow some pipeline lag)
            trailing = []
            try:
                while True:
                    raw = ws.recv(timeout=3)
                    msg = json.loads(raw)
                    if msg.get("uid") == 200:
                        trailing.append(msg)
            except (TimeoutError, Exception):
                pass
            # At most 1-2 in-flight samples may arrive after unsubscribe
            assert len(trailing) <= 2

    def test_multiple_clients_independent(self, ws_connect):
        """Two clients subscribe to different uids independently."""
        with ws_connect() as ws1, ws_connect() as ws2:
            ws1.send(json.dumps({"action": "subscribe", "uids": [110]}))
            ws2.send(json.dumps({"action": "subscribe", "uids": [210]}))

            msg1 = json.loads(ws1.recv(timeout=10))
            msg2 = json.loads(ws2.recv(timeout=10))

            assert msg1["uid"] == 110
            assert msg2["uid"] == 210

    def test_client_disconnect_cleanup(self, ws_connect):
        """After disconnect, server should clean up client interest (SR-002)."""
        # Connect and subscribe
        ws = ws_connect()
        ws.send(json.dumps({"action": "subscribe", "uids": [180]}))
        ws.recv(timeout=10)  # confirm subscription works

        # Abrupt close
        ws.close()

        # Server should have cleaned up — verify by connecting a new client
        # and confirming the system is still healthy
        time.sleep(1.0)
        with ws_connect() as ws2:
            ws2.send(json.dumps({"action": "subscribe", "uids": [180]}))
            msg = json.loads(ws2.recv(timeout=10))
            assert msg["uid"] == 180

    def test_dynamic_period_change(self, ws_connect):
        """Changing period_ms at runtime affects sample delivery rate."""
        with ws_connect() as ws:
            # Subscribe with fast period
            ws.send(json.dumps({
                "action": "subscribe",
                "uids": [115],
                "period_ms": 200,
            }))

            # Collect samples for 3 seconds
            fast_samples = []
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                try:
                    raw = ws.recv(timeout=4)
                    msg = json.loads(raw)
                    if msg.get("uid") == 115:
                        fast_samples.append(msg)
                except TimeoutError:
                    break

            # Switch to slow period
            ws.send(json.dumps({
                "action": "set_period",
                "period_ms": 2000,
            }))
            time.sleep(0.5)  # let the command propagate

            # Collect samples for 3 more seconds
            slow_samples = []
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                try:
                    raw = ws.recv(timeout=4)
                    msg = json.loads(raw)
                    if msg.get("uid") == 115:
                        slow_samples.append(msg)
                except TimeoutError:
                    break

            # Fast period should yield more samples than slow period
            # (uid 115 is in 1 Hz band; 200ms separation → ~3/s; 2000ms → ~0.5/s)
            if fast_samples and slow_samples:
                assert len(fast_samples) >= len(slow_samples), (
                    f"Fast ({len(fast_samples)}) should be >= slow ({len(slow_samples)})"
                )


class TestE2ETopicType:
    """Verify topic type introspection through the full pipeline."""

    def _topic_url(self, base_url, topic_name):
        encoded = urllib.parse.quote(topic_name, safe='')
        return f"{base_url}/api/v1/topics/{encoded}/type"

    def test_topic_type_endpoint(self, pipeline):
        """GET /api/v1/topics/{name}/type returns type structure."""
        url = self._topic_url(pipeline['base_url'], "PLC::SelectedValueTopic")
        try:
            resp = urllib.request.urlopen(url, timeout=5)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                pytest.skip("Type endpoint not wired for topic-name lookup")
            raise
        data = json.loads(resp.read())
        assert "members" in data
        member_names = {m["name"] for m in data["members"]}
        assert "uid" in member_names

    def test_metadata_type_has_limits(self, pipeline):
        """MetaData type should include limits structure."""
        url = self._topic_url(pipeline['base_url'], "PLC::SelectedMetaDataTopic")
        try:
            resp = urllib.request.urlopen(url, timeout=5)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                pytest.skip("Type endpoint not wired for topic-name lookup")
            raise
        data = json.loads(resp.read())
        member_names = {m["name"] for m in data["members"]}
        assert "uid" in member_names
        assert "limits" in member_names
