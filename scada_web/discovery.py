"""Wire type learning from DDS builtin discovery.

Implements the same pattern as act-sim-scope-infra's DiscoveryDispatcher +
TypeResolver (C++) and type_discovery_spike.py (Python proof): read the
COMPLETE TypeObject inline from SEDP builtin discovery data, register it
per topic (first-learned-wins), and gate entity creation on type availability.

No local IDL/XML is needed — the publishing application's SEDP announcement
carries the full type inline for small types (spike-proven for Connext 7.7).

Threading model: a single asyncio task polls the builtin readers; type
registrations are communicated via callbacks to the gateway layer.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable

import rti.connextdds as dds

logger = logging.getLogger(__name__)

# Type alias for the callback fired when a new topic's type is learned.
TypeLearnedCallback = Callable[[str, dds.DynamicType], None]


@dataclass
class TypeResolver:
    """Thread-safe registry of wire-learned DynamicTypes, keyed by topic name.

    Mirrors references/act-sim-scope-infra/router/src/core/TypeResolver.hpp:
    first-learned-wins per topic — a later (possibly different) type object
    for the same topic is ignored.
    """

    _types: dict[str, dds.DynamicType] = field(default_factory=dict)

    def register(self, topic_name: str, dtype: dds.DynamicType) -> bool:
        """Register a discovered type. Returns True if this was the first."""
        if topic_name in self._types:
            return False
        self._types[topic_name] = dtype
        logger.info("type_learned topic=%s type=%s", topic_name, dtype.name)
        return True

    def has_type(self, topic_name: str) -> bool:
        return topic_name in self._types

    def get_type(self, topic_name: str) -> dds.DynamicType:
        """Returns the learned type or raises KeyError."""
        if topic_name not in self._types:
            raise KeyError(
                f"no wire-learned type for topic '{topic_name}' "
                "(types come from discovery, not local IDL)")
        return self._types[topic_name]

    @property
    def known_topics(self) -> list[str]:
        return list(self._types.keys())


class DiscoveryMonitor:
    """Monitors builtin discovery readers and learns types from endpoints.

    Attaches to a DomainParticipant's builtin publication_reader and
    subscription_reader, polling for new endpoints. When an endpoint's
    inline type object is available (data.type), registers it in the
    TypeResolver and fires the on_type_learned callback.

    Usage:
        resolver = TypeResolver()
        monitor = DiscoveryMonitor(participant, resolver, on_type_learned=callback)
        await monitor.run()  # runs until cancelled
    """

    def __init__(
        self,
        participant: dds.DomainParticipant,
        resolver: TypeResolver,
        on_type_learned: TypeLearnedCallback | None = None,
        poll_period_s: float = 0.25,
        topics_of_interest: set[str] | None = None,
    ):
        self._participant = participant
        self._resolver = resolver
        self._on_type_learned = on_type_learned
        self._poll_period_s = poll_period_s
        self._topics_of_interest = topics_of_interest  # None = learn all
        self._running = False

    async def run(self) -> None:
        """Poll builtin readers until cancelled. Call via asyncio.create_task."""
        self._running = True
        pub_reader = self._participant.publication_reader
        sub_reader = self._participant.subscription_reader

        logger.info("discovery_monitor_started domain=%d topics=%s",
                    self._participant.domain_id,
                    self._topics_of_interest or "ALL")

        while self._running:
            self._process_publications(pub_reader)
            self._process_subscriptions(sub_reader)
            await asyncio.sleep(self._poll_period_s)

    def stop(self) -> None:
        self._running = False

    def _should_learn(self, topic_name: str) -> bool:
        """Check if this topic is one we care about."""
        if self._topics_of_interest is None:
            return True
        return topic_name in self._topics_of_interest

    def _process_publications(self, reader) -> None:
        """Read publication builtin data and learn types from writers."""
        for data, info in reader.read():
            if not info.valid:
                continue
            topic_name = data.topic_name
            if not self._should_learn(topic_name):
                continue
            if self._resolver.has_type(topic_name):
                continue
            try:
                dtype = data.type
            except Exception:
                dtype = None
            if dtype is None:
                logger.debug("type_not_inline topic=%s (from publication)",
                             topic_name)
                continue
            if self._resolver.register(topic_name, dtype):
                self._fire_callback(topic_name, dtype)

    def _process_subscriptions(self, reader) -> None:
        """Read subscription builtin data and learn types from readers."""
        for data, info in reader.read():
            if not info.valid:
                continue
            topic_name = data.topic_name
            if not self._should_learn(topic_name):
                continue
            if self._resolver.has_type(topic_name):
                continue
            try:
                dtype = data.type
            except Exception:
                dtype = None
            if dtype is None:
                logger.debug("type_not_inline topic=%s (from subscription)",
                             topic_name)
                continue
            if self._resolver.register(topic_name, dtype):
                self._fire_callback(topic_name, dtype)

    def _fire_callback(self, topic_name: str, dtype: dds.DynamicType) -> None:
        if self._on_type_learned:
            try:
                self._on_type_learned(topic_name, dtype)
            except Exception:
                logger.exception("on_type_learned callback failed topic=%s",
                                 topic_name)
