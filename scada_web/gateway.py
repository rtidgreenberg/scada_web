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
import rti.asyncio  # patches DataReader with take_async (WaitSet-backed)

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
        self._qos_provider: dds.QosProvider | None = None
        self._topics: dict[str, TopicRuntime] = {}
        self._reader_tasks: list[asyncio.Task] = []
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
        for topic_name, runtime in self._topics.items():
            task = asyncio.create_task(self._reader_loop(topic_name, runtime))
            self._reader_tasks.append(task)
        logger.info("dds_gateway_started participants=%d topics=%d",
                    len(self._participants), len(self._topics))

    async def stop(self) -> None:
        """Tear down all DDS entities."""
        self._running = False
        for task in self._reader_tasks:
            task.cancel()
        await asyncio.gather(*self._reader_tasks, return_exceptions=True)
        self._reader_tasks.clear()
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

        # Load QoS profiles if configured
        if self._config.qos_profiles:
            self._qos_provider = dds.QosProvider(self._config.qos_profiles)
            logger.info("qos_profiles_loaded xml=%s", self._config.qos_profiles)

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

            # Resolve QoS: from profile XML if configured, else defaults
            reader_qos = None
            if tc.qos_profile and self._qos_provider:
                reader_qos = self._qos_provider.datareader_qos_from_profile(
                    tc.qos_profile)
                logger.info("qos_applied topic=%s profile=%s", tc.name, tc.qos_profile)

            if tc.filter:
                cft = dds.DynamicData.ContentFilteredTopic(
                    topic,
                    f"{tc.name}_filtered",
                    dds.Filter(tc.filter.expression, tc.filter.parameters),
                )
                if reader_qos:
                    reader = dds.DynamicData.DataReader(subscriber, cft, reader_qos)
                else:
                    reader = dds.DynamicData.DataReader(subscriber, cft)
            else:
                if reader_qos:
                    reader = dds.DynamicData.DataReader(subscriber, topic, reader_qos)
                else:
                    reader = dds.DynamicData.DataReader(subscriber, topic)

            self._topics[tc.name] = TopicRuntime(config=tc, topic=topic, reader=reader)
            logger.info("reader_created topic=%s type=%s", tc.name, dtype.name)

    # ─── Internal: read loop ─────────────────────────────────────────────

    async def _reader_loop(self, topic_name: str, runtime: TopicRuntime) -> None:
        """Async generator loop — wakes only when data arrives (WaitSet-backed)."""
        reader = runtime.reader
        if reader is None:
            return
        try:
            async for data, info in reader.take_async():
                if not info.valid:
                    continue
                if self.on_sample:
                    self.on_sample(topic_name, data, info)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("reader_loop_error topic=%s", topic_name)

    # ─── Public query ────────────────────────────────────────────────────

    @property
    def topics(self) -> list[str]:
        """All configured topic names."""
        return list(self._topics.keys())

    def get_type(self, type_name: str) -> dds.DynamicType:
        """Public access to loaded types (for the REST type endpoint)."""
        return self._get_type(type_name)
