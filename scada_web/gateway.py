"""DDS gateway — manages participants, topics, and readers from YAML config.

Orchestrates the lifecycle:
  1. Load types from XML (generated from IDL via rtiddsgen -convertToXml)
  2. Create DomainParticipants from config
  3. Create Topics + DataReaders immediately (types are known, no discovery wait)
  4. Optionally create a DataWriter for ValueRequest (back-channel to selector)
  5. Forward received samples to the web layer via callbacks

This is the Level 2 (SCADA master) DDS boundary — it owns all DDS entities
and isolates the web server from DDS API details.

Types are loaded from XML at startup — NOT learned from wire discovery.
In SCADA the data model is commissioned infrastructure; it doesn't change at
runtime. This is simpler, faster to start, and doesn't depend on publishers
being up first.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

import rti.connextdds as dds

from .config import ScadaWebConfig, TopicConfig

logger = logging.getLogger(__name__)

# Callback type: (topic_name, sample_data, sample_info) → None
SampleCallback = Callable[[str, Any, Any], None]


@dataclass
class TopicRuntime:
    """Runtime state for a single subscribed topic."""
    config: TopicConfig
    topic: dds.DynamicData.Topic | None = None
    reader: dds.DynamicData.DataReader | None = None


class DdsGateway:
    """Manages DDS entities driven by YAML config and XML-loaded types.

    Lifecycle:
        gw = DdsGateway(config)
        gw.on_sample = my_callback
        await gw.start()   # loads types, creates participants + readers
        ...
        await gw.stop()    # tears down everything
    """

    def __init__(self, config: ScadaWebConfig):
        self._config = config
        self._participants: dict[str, dds.DomainParticipant] = {}
        self._provider: dds.QosProvider | None = None
        self._topics: dict[str, TopicRuntime] = {}
        self._poll_task: asyncio.Task | None = None
        self._running = False

        # Public callback — set before start()
        self.on_sample: SampleCallback | None = None

    # ─── Lifecycle ───────────────────────────────────────────────────────

    async def start(self) -> None:
        """Load XML types, create participants and readers, begin reading."""
        self._load_types()
        self._create_participants()
        self._create_readers()
        self._running = True
        self._poll_task = asyncio.create_task(self._read_loop())
        logger.info("dds_gateway_started participants=%d topics=%d",
                    len(self._participants), len(self._topics))

    async def stop(self) -> None:
        """Tear down all DDS entities."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        for dp in self._participants.values():
            dp.close()
        self._participants.clear()
        self._topics.clear()
        logger.info("dds_gateway_stopped")

    # ─── Internal: type loading ──────────────────────────────────────────

    def _load_types(self) -> None:
        """Load DynamicTypes from the XML type library."""
        xml_path = self._config.types_xml
        if not xml_path:
            raise RuntimeError("config must specify types.xml path")
        self._provider = dds.QosProvider(xml_path)
        logger.info("types_loaded xml=%s", xml_path)

    def _get_type(self, type_name: str) -> dds.DynamicType:
        """Look up a type from the loaded XML library."""
        return self._provider.type(type_name)

    # ─── Internal: participant + reader setup ────────────────────────────

    def _create_participants(self) -> None:
        for pc in self._config.participants:
            qos = dds.DomainParticipantQos()
            dp = dds.DomainParticipant(pc.domain, qos)
            self._participants[pc.name] = dp
            logger.info("participant_created name=%s domain=%d", pc.name, pc.domain)

    def _create_readers(self) -> None:
        """Create Topic + DataReader for each configured topic immediately."""
        for tc in self._config.topics:
            dp = self._participants[tc.participant]
            dtype = self._get_type(tc.type_name)

            topic = dds.DynamicData.Topic(dp, tc.name, dtype)
            subscriber = dds.Subscriber(dp)

            if tc.filter:
                cft = dds.DynamicData.ContentFilteredTopic(
                    topic,
                    f"{tc.name}_filtered",
                    dds.Filter(tc.filter.expression, tc.filter.parameters),
                )
                reader = dds.DynamicData.DataReader(subscriber, cft)
            else:
                reader = dds.DynamicData.DataReader(subscriber, topic)

            self._topics[tc.name] = TopicRuntime(config=tc, topic=topic, reader=reader)
            logger.info("reader_created topic=%s type=%s", tc.name, dtype.name)

    # ─── Internal: read loop ─────────────────────────────────────────────

    async def _read_loop(self) -> None:
        """Periodically take samples from all readers."""
        while self._running:
            for topic_name, runtime in self._topics.items():
                if runtime.reader is None:
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
    def topics(self) -> list[str]:
        """All configured topic names."""
        return list(self._topics.keys())

    def get_type(self, type_name: str) -> dds.DynamicType:
        """Public access to loaded types (for the REST type endpoint)."""
        return self._get_type(type_name)
