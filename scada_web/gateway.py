"""DDS gateway — manages participants, topics, and readers from YAML config.

Orchestrates the lifecycle:
  1. Create DomainParticipants from config
  2. Start DiscoveryMonitor to learn types from wire
  3. Once a topic's type is learned, create the DynamicData DataReader
  4. Optionally create a DataWriter for ValueRequest (back-channel to selector)
  5. Forward received samples to the web layer via callbacks

This is the Level 2 (SCADA master) DDS boundary — it owns all DDS entities
and isolates the web server from DDS API details.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

import rti.connextdds as dds

from .config import ScadaWebConfig, TopicConfig, FilterConfig
from .discovery import DiscoveryMonitor, TypeResolver

logger = logging.getLogger(__name__)

# Callback type: (topic_name, sample_dict, sample_info) → None
SampleCallback = Callable[[str, Any, Any], None]


@dataclass
class TopicRuntime:
    """Runtime state for a single subscribed topic."""
    config: TopicConfig
    topic: dds.DynamicData.Topic | None = None
    reader: dds.DynamicData.DataReader | None = None
    ready: bool = False


class DdsGateway:
    """Manages DDS entities driven by YAML config and wire-learned types.

    Lifecycle:
        gw = DdsGateway(config)
        gw.on_sample = my_callback
        await gw.start()   # creates participants, starts discovery, creates readers
        ...
        await gw.stop()    # tears down everything
    """

    def __init__(self, config: ScadaWebConfig):
        self._config = config
        self._participants: dict[str, dds.DomainParticipant] = {}
        self._monitors: list[DiscoveryMonitor] = []
        self._monitor_tasks: list[asyncio.Task] = []
        self._resolver = TypeResolver()
        self._topics: dict[str, TopicRuntime] = {}
        self._poll_task: asyncio.Task | None = None
        self._running = False

        # Public callback — set before start()
        self.on_sample: SampleCallback | None = None

    # ─── Lifecycle ───────────────────────────────────────────────────────

    async def start(self) -> None:
        """Create DDS participants, start discovery, begin reading."""
        self._create_participants()
        self._init_topic_runtimes()
        self._start_discovery()
        self._running = True
        self._poll_task = asyncio.create_task(self._read_loop())
        logger.info("dds_gateway_started participants=%d topics=%d",
                    len(self._participants), len(self._topics))

    async def stop(self) -> None:
        """Tear down all DDS entities."""
        self._running = False
        for m in self._monitors:
            m.stop()
        for t in self._monitor_tasks:
            t.cancel()
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        # Close participants (closes all child entities)
        for dp in self._participants.values():
            dp.close()
        self._participants.clear()
        self._topics.clear()
        logger.info("dds_gateway_stopped")

    # ─── Internal: participant + topic setup ─────────────────────────────

    def _create_participants(self) -> None:
        for pc in self._config.participants:
            qos = dds.DomainParticipantQos()
            dp = dds.DomainParticipant(pc.domain, qos)
            self._participants[pc.name] = dp
            logger.info("participant_created name=%s domain=%d", pc.name, pc.domain)

    def _init_topic_runtimes(self) -> None:
        for tc in self._config.topics:
            self._topics[tc.name] = TopicRuntime(config=tc)

    def _start_discovery(self) -> None:
        """Start a DiscoveryMonitor per participant, filtered to configured topics."""
        # Build the set of topics each participant needs to learn
        participant_topics: dict[str, set[str]] = {}
        for tc in self._config.topics:
            participant_topics.setdefault(tc.participant, set()).add(tc.name)

        for pname, topic_names in participant_topics.items():
            dp = self._participants[pname]
            monitor = DiscoveryMonitor(
                participant=dp,
                resolver=self._resolver,
                on_type_learned=self._on_type_learned,
                topics_of_interest=topic_names,
            )
            self._monitors.append(monitor)
            task = asyncio.create_task(monitor.run())
            self._monitor_tasks.append(task)

    def _on_type_learned(self, topic_name: str, dtype: dds.DynamicType) -> None:
        """Callback from discovery — create the reader for this topic now."""
        if topic_name not in self._topics:
            return
        runtime = self._topics[topic_name]
        if runtime.ready:
            return
        try:
            self._create_reader(runtime, dtype)
            runtime.ready = True
            logger.info("topic_ready name=%s type=%s", topic_name, dtype.name)
        except Exception:
            logger.exception("reader_creation_failed topic=%s", topic_name)

    def _create_reader(self, runtime: TopicRuntime, dtype: dds.DynamicType) -> None:
        """Create Topic + DataReader (+ optional CFT) from wire-learned type."""
        tc = runtime.config
        dp = self._participants[tc.participant]

        topic = dds.DynamicData.Topic(dp, tc.name, dtype)
        runtime.topic = topic

        subscriber = dds.Subscriber(dp)

        # Content filter from config
        if tc.filter:
            cft = dds.DynamicData.ContentFilteredTopic(
                topic,
                f"{tc.name}_filtered",
                dds.Filter(tc.filter.expression, tc.filter.parameters),
            )
            reader = dds.DynamicData.DataReader(subscriber, cft)
        else:
            reader = dds.DynamicData.DataReader(subscriber, topic)

        runtime.reader = reader

    # ─── Internal: read loop ─────────────────────────────────────────────

    async def _read_loop(self) -> None:
        """Periodically take samples from all ready readers."""
        while self._running:
            for topic_name, runtime in self._topics.items():
                if not runtime.ready or runtime.reader is None:
                    continue
                try:
                    samples = runtime.reader.take()
                    for data, info in samples:
                        if not info.valid:
                            continue
                        if self.on_sample:
                            self.on_sample(topic_name, data, info)
                except Exception:
                    logger.exception("read_error topic=%s", topic_name)
            await asyncio.sleep(0.05)  # 50ms poll — fast enough for HMI

    # ─── Public query ────────────────────────────────────────────────────

    @property
    def ready_topics(self) -> list[str]:
        """Topics whose types have been learned and readers are active."""
        return [name for name, rt in self._topics.items() if rt.ready]

    @property
    def pending_topics(self) -> list[str]:
        """Topics still waiting for type discovery."""
        return [name for name, rt in self._topics.items() if not rt.ready]

    @property
    def resolver(self) -> TypeResolver:
        return self._resolver
