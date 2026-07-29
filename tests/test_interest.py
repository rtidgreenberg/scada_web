"""Unit tests for the InterestManager (no DDS required).

Verifies refcounting, ADD/DELETE callbacks, period updates, and
client disconnect cleanup — all in-process, fast, no infrastructure.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scada_web.interest import InterestManager


class TestInterestRefcounting:
    """SR-001: ADD on 0→1, DELETE on 1→0."""

    def test_first_subscribe_fires_add(self):
        adds = []
        mgr = InterestManager(on_add=lambda uid: adds.append(uid))
        mgr.client_subscribe("c1", 10)
        assert adds == [10]

    def test_second_subscribe_no_add(self):
        adds = []
        mgr = InterestManager(on_add=lambda uid: adds.append(uid))
        mgr.client_subscribe("c1", 10)
        mgr.client_subscribe("c2", 10)
        assert len(adds) == 1  # only the first triggers ADD

    def test_last_unsubscribe_fires_delete(self):
        deletes = []
        mgr = InterestManager(on_delete=lambda uid: deletes.append(uid))
        mgr.client_subscribe("c1", 10)
        mgr.client_unsubscribe("c1", 10)
        assert deletes == [10]

    def test_partial_unsubscribe_no_delete(self):
        deletes = []
        mgr = InterestManager(on_delete=lambda uid: deletes.append(uid))
        mgr.client_subscribe("c1", 10)
        mgr.client_subscribe("c2", 10)
        mgr.client_unsubscribe("c1", 10)
        assert deletes == []  # refcount still > 0

    def test_duplicate_subscribe_idempotent(self):
        adds = []
        mgr = InterestManager(on_add=lambda uid: adds.append(uid))
        mgr.client_subscribe("c1", 10)
        mgr.client_subscribe("c1", 10)  # same client, same uid
        assert len(adds) == 1


class TestInterestDisconnect:
    """SR-002: abrupt disconnect decrements the client's full interest set."""

    def test_disconnect_cleans_all_uids(self):
        deletes = []
        mgr = InterestManager(on_delete=lambda uid: deletes.append(uid))
        mgr.client_subscribe("c1", 10)
        mgr.client_subscribe("c1", 20)
        mgr.client_subscribe("c1", 30)
        mgr.client_disconnect("c1")
        assert set(deletes) == {10, 20, 30}

    def test_disconnect_preserves_other_clients(self):
        deletes = []
        mgr = InterestManager(on_delete=lambda uid: deletes.append(uid))
        mgr.client_subscribe("c1", 10)
        mgr.client_subscribe("c2", 10)
        mgr.client_disconnect("c1")
        assert deletes == []  # c2 still holds uid 10


class TestInterestPeriod:
    """Minimum separation updates fire a dedicated PERIOD callback once,
    regardless of how many uids (if any) are active (CR-011, closes CR-004).
    """

    def test_set_min_separation_fires_period_once(self):
        periods = []
        mgr = InterestManager(on_period=lambda ms: periods.append(ms))
        mgr.client_subscribe("c1", 10)
        mgr.client_subscribe("c1", 20)
        mgr.set_min_separation(500)
        assert periods == [500]  # one PERIOD, not one per active uid

    def test_set_min_separation_fires_with_no_active_uids(self):
        # CR-004: a separation change with nothing subscribed must still
        # reach the wire.
        periods = []
        mgr = InterestManager(on_period=lambda ms: periods.append(ms))
        mgr.set_min_separation(500)
        assert periods == [500]

    def test_set_min_separation_does_not_refire_add(self):
        adds = []
        mgr = InterestManager(on_add=lambda uid: adds.append(uid))
        mgr.client_subscribe("c1", 10)
        adds.clear()
        mgr.set_min_separation(500)
        assert adds == []  # ADD is not how PERIOD changes propagate anymore

    def test_set_same_period_noop(self):
        periods = []
        mgr = InterestManager(
            on_period=lambda ms: periods.append(ms),
            min_separation_ms=250,
        )
        mgr.client_subscribe("c1", 10)
        mgr.set_min_separation(250)  # same as current
        assert periods == []

    def test_negative_period_raises(self):
        mgr = InterestManager()
        with pytest.raises(ValueError):
            mgr.set_min_separation(-1)


class TestInterestIsInterested:
    """SR-004: per-client demux query."""

    def test_interested_after_subscribe(self):
        mgr = InterestManager()
        mgr.client_subscribe("c1", 10)
        assert mgr.is_interested("c1", 10) is True

    def test_not_interested_other_uid(self):
        mgr = InterestManager()
        mgr.client_subscribe("c1", 10)
        assert mgr.is_interested("c1", 99) is False

    def test_not_interested_after_unsubscribe(self):
        mgr = InterestManager()
        mgr.client_subscribe("c1", 10)
        mgr.client_unsubscribe("c1", 10)
        assert mgr.is_interested("c1", 10) is False

    def test_not_interested_unknown_client(self):
        mgr = InterestManager()
        assert mgr.is_interested("unknown", 10) is False
