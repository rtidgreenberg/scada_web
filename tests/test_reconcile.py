"""Unit tests for SR-003 reconciliation trigger logic (no DDS required).

Exercises server.py's `_on_publication_matched` directly against a fake
gateway and a real `InterestManager` -- no DomainParticipant, no license, no
selector process. CR-003: confirms the current-count-rising-from-zero
transition check (the only moment a write to a VOLATILE topic can land), and
that PERIOD is replayed before the ADD burst so no tag is briefly at the
wrong rate.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scada_web.server as server
from scada_web.interest import InterestManager


class _FakeGateway:
    """Records every write() call in order; no real DDS entities."""

    def __init__(self):
        self.calls: list[tuple[str, object]] = []

    def write(self, topic_name, sample):
        self.calls.append((topic_name, sample))


def _matched_status(current_count, current_count_change):
    return SimpleNamespace(current_count=current_count,
                           current_count_change=current_count_change)


class TestPublicationMatchedTrigger:
    """server._on_publication_matched is the SR-003 trigger added by CR-003."""

    def setup_method(self):
        self._orig_gateway = server._gateway
        self._orig_interest = server._interest
        self.gateway = _FakeGateway()
        server._gateway = self.gateway
        server._interest = InterestManager(
            on_add=server._send_add,
            on_delete=server._on_interest_delete,
            on_period=server._send_period,
            min_separation_ms=250,
        )

    def teardown_method(self):
        server._gateway = self._orig_gateway
        server._interest = self._orig_interest

    def test_ignores_other_topics(self):
        server._on_publication_matched("PLC::SomeOtherTopic", _matched_status(1, 1))
        assert self.gateway.calls == []

    def test_ignores_non_zero_transition(self):
        # current_count=3, change=1 -- already matched with 2, one more joined.
        # Not a restart: reconciling here would be a spurious, redundant replay.
        server._on_publication_matched(server.VALUE_REQUEST_TOPIC,
                                        _matched_status(3, 1))
        assert self.gateway.calls == []

    def test_ignores_zero_change(self):
        server._on_publication_matched(server.VALUE_REQUEST_TOPIC,
                                        _matched_status(1, 0))
        assert self.gateway.calls == []

    def test_zero_to_one_sends_period_with_no_active_uids(self):
        server._on_publication_matched(server.VALUE_REQUEST_TOPIC,
                                        _matched_status(1, 1))
        assert len(self.gateway.calls) == 1
        topic_name, sample = self.gateway.calls[0]
        assert topic_name == server.VALUE_REQUEST_TOPIC
        assert sample.periodRequest.period_ms == 250

    def test_reconcile_replays_period_before_active_uids(self):
        server._interest.client_subscribe("client-a", 10)
        server._interest.client_subscribe("client-a", 20)
        self.gateway.calls.clear()  # discard the ADD writes from subscribing

        server._on_publication_matched(server.VALUE_REQUEST_TOPIC,
                                        _matched_status(1, 1))

        assert len(self.gateway.calls) == 3
        _, period_sample = self.gateway.calls[0]
        assert period_sample.periodRequest.period_ms == 250
        add_uids = [sample.addRequest.uid for _, sample in self.gateway.calls[1:]]
        assert add_uids == [10, 20]
