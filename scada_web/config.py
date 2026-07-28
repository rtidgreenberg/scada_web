"""YAML configuration loader for scada_web.

Declares DDS participants, topic subscriptions, QoS, type library path,
and mapping views in a single YAML file.

Types are loaded from an XML type library (generated from IDL via
`rtiddsgen -convertToXml`). Each topic entry specifies its type_name
so the gateway can create readers immediately at startup.

Config schema mirrors the pattern proven in act-sim-scope-infra's C++ router
(references/act-sim-scope-infra/router/config/) adapted for Python + the
presentation role (Role 2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ─── Data classes ────────────────────────────────────────────────────────────


@dataclass
class ParticipantConfig:
    """A DDS DomainParticipant declared in config."""
    name: str
    domain: int
    qos_xml: str | None = None  # optional QoS provider XML path
    wis_name: str | None = None  # name this participant carries in WIS URIs


@dataclass
class FilterConfig:
    """Content filter for a topic subscription."""
    expression: str
    parameters: list[str] = field(default_factory=list)


@dataclass
class WisReaderConfig:
    """WIS URI names for a subscribed topic's reader resource."""
    subscriber: str
    data_reader: str


@dataclass
class WisWriterConfig:
    """WIS URI names for a published topic's writer resource."""
    publisher: str
    data_writer: str


@dataclass
class TopicConfig:
    """A topic to subscribe to. Type is loaded from the XML library."""
    name: str
    participant: str  # references a ParticipantConfig.name
    type_name: str = ""  # fully-qualified type in XML, e.g. "PLC::MetaData"
    qos_profile: str | None = None
    filter: FilterConfig | None = None
    wis: WisReaderConfig | None = None


@dataclass
class WriterConfig:
    """A topic to publish. Backs a WIS data_writer resource."""
    name: str
    participant: str  # references a ParticipantConfig.name
    type_name: str = ""
    qos_profile: str | None = None
    wis: WisWriterConfig | None = None


@dataclass
class MappingFieldConfig:
    """Single field mapping: wire path → view name."""
    wire: str       # DynamicData field path, e.g. "smoothedValue.float64Value"
    view: str       # JSON output key, e.g. "value"
    transform: str | None = None  # optional: "union_scalar", "char_array_string"


@dataclass
class ViewConfig:
    """A view schema exposed to web clients for a given topic."""
    name: str
    topic: str  # references a TopicConfig.name
    fields: list[MappingFieldConfig] = field(default_factory=list)


@dataclass
class ServerConfig:
    """Web server settings."""
    host: str = "0.0.0.0"
    port: int = 8080
    websocket_path: str = "/ws"
    rest_prefix: str = "/api/v1"


@dataclass
class SelectionConfig:
    """Selection defaults for web-originated ValueRequest commands."""
    default_min_separation_ms: int = 250


@dataclass
class WisConfig:
    """RTI Web Integration Service compatibility surface.

    `application` is the name that appears in WIS resource URIs
    (/dds/rest1/applications/{application}/...) and must match what the browser
    client is configured with.

    `strict_websocket_connections` mirrors WIS's requirement that a connection
    name be reserved via POST /dds/v1/websocket_connections before the socket
    opens. Left False, an unreserved name is accepted, which avoids a confusing
    failure when the browser's POST is blocked; set True for WIS-strict behavior.
    """
    enabled: bool = True
    application: str = ""
    strict_websocket_connections: bool = False
    document_root: str | None = None  # static dir to serve, like WIS -documentRoot
    allow_origins: list[str] = field(default_factory=lambda: ["*"])


@dataclass
class ScadaWebConfig:
    """Root configuration for scada_web."""
    types_xml: str = ""  # path to XML type library (rtiddsgen -convertToXml output)
    qos_profiles: str = ""  # path to QoS profiles XML (dds/qos/profiles.xml)
    participants: list[ParticipantConfig] = field(default_factory=list)
    topics: list[TopicConfig] = field(default_factory=list)
    writers: list[WriterConfig] = field(default_factory=list)
    views: list[ViewConfig] = field(default_factory=list)
    selection: SelectionConfig = field(default_factory=SelectionConfig)
    wis: WisConfig = field(default_factory=WisConfig)
    server: ServerConfig = field(default_factory=ServerConfig)

    # --- convenience lookups ---

    def participant_by_name(self, name: str) -> ParticipantConfig:
        for p in self.participants:
            if p.name == name:
                return p
        raise KeyError(f"no participant named '{name}'")

    def topic_by_name(self, name: str) -> TopicConfig:
        for t in self.topics:
            if t.name == name:
                return t
        raise KeyError(f"no topic named '{name}'")

    def writer_by_name(self, name: str) -> WriterConfig:
        for w in self.writers:
            if w.name == name:
                return w
        raise KeyError(f"no writer named '{name}'")


# ─── Loader ──────────────────────────────────────────────────────────────────


def _parse_filter(raw: dict[str, Any] | None) -> FilterConfig | None:
    if raw is None:
        return None
    return FilterConfig(
        expression=raw["expression"],
        parameters=raw.get("parameters", []),
    )


def _parse_mapping_field(raw: dict[str, Any]) -> MappingFieldConfig:
    return MappingFieldConfig(
        wire=raw["wire"],
        view=raw["view"],
        transform=raw.get("transform"),
    )


def _parse_wis_reader(raw: dict[str, Any] | None,
                      topic: str) -> WisReaderConfig | None:
    if raw is None:
        return None
    missing = [k for k in ("subscriber", "data_reader") if not raw.get(k)]
    if missing:
        raise ValueError(
            f"topic '{topic}' wis: block requires {', '.join(missing)}")
    return WisReaderConfig(subscriber=raw["subscriber"],
                           data_reader=raw["data_reader"])


def _parse_wis_writer(raw: dict[str, Any] | None,
                      writer: str) -> WisWriterConfig | None:
    if raw is None:
        return None
    missing = [k for k in ("publisher", "data_writer") if not raw.get(k)]
    if missing:
        raise ValueError(
            f"writer '{writer}' wis: block requires {', '.join(missing)}")
    return WisWriterConfig(publisher=raw["publisher"],
                           data_writer=raw["data_writer"])


def load_config(path: str | Path) -> ScadaWebConfig:
    """Load and validate a scada_web YAML config file."""
    path = Path(path)
    with open(path) as f:
        raw = yaml.safe_load(f)

    cfg = ScadaWebConfig()

    # Participants
    for name, p in raw.get("participants", {}).items():
        cfg.participants.append(ParticipantConfig(
            name=name,
            domain=int(p["domain"]),
            qos_xml=p.get("qos_xml"),
            wis_name=p.get("wis_name"),
        ))

    # Types
    types_section = raw.get("types", {})
    cfg.types_xml = types_section.get("xml", "")

    # QoS profiles
    cfg.qos_profiles = raw.get("qos_profiles", "")

    # Topics
    for t in raw.get("topics", []):
        cfg.topics.append(TopicConfig(
            name=t["name"],
            participant=t["participant"],
            type_name=t.get("type", t["name"]),
            qos_profile=t.get("qos_profile"),
            filter=_parse_filter(t.get("filter")),
            wis=_parse_wis_reader(t.get("wis"), t["name"]),
        ))

    # Writers
    for w in raw.get("writers", []):
        cfg.writers.append(WriterConfig(
            name=w["name"],
            participant=w["participant"],
            type_name=w.get("type", w["name"]),
            qos_profile=w.get("qos_profile"),
            wis=_parse_wis_writer(w.get("wis"), w["name"]),
        ))

    # Views
    for v in raw.get("views", []):
        fields = [_parse_mapping_field(f) for f in v.get("fields", [])]
        cfg.views.append(ViewConfig(
            name=v["name"],
            topic=v["topic"],
            fields=fields,
        ))

    # Selection defaults
    selection = raw.get("selection", {})
    cfg.selection = SelectionConfig(
        default_min_separation_ms=int(
            selection.get("default_min_separation_ms", 250)
        ),
    )

    # WIS compatibility surface
    if "wis" in raw:
        w = raw["wis"] or {}
        cfg.wis = WisConfig(
            enabled=bool(w.get("enabled", True)),
            application=w.get("application", ""),
            strict_websocket_connections=bool(
                w.get("strict_websocket_connections", False)),
            document_root=w.get("document_root"),
            allow_origins=list(w.get("allow_origins", ["*"])),
        )

    # Server
    if "server" in raw:
        s = raw["server"]
        cfg.server = ServerConfig(
            host=s.get("host", "0.0.0.0"),
            port=int(s.get("port", 8080)),
            websocket_path=s.get("websocket_path", "/ws"),
            rest_prefix=s.get("rest_prefix", "/api/v1"),
        )

    _validate(cfg)
    return cfg


def _validate(cfg: ScadaWebConfig) -> None:
    """Cross-reference validation (participant refs exist, etc.)."""
    if not cfg.types_xml:
        raise ValueError("config must specify types.xml path")
    if cfg.selection.default_min_separation_ms < 0:
        raise ValueError("selection.default_min_separation_ms must be >= 0")
    if cfg.topics and not cfg.qos_profiles:
        raise ValueError("config must specify qos_profiles when topics are declared")
    participant_names = {p.name for p in cfg.participants}
    for t in cfg.topics:
        if t.participant not in participant_names:
            raise ValueError(
                f"topic '{t.name}' references unknown participant '{t.participant}'")
        if not t.qos_profile:
            raise ValueError(f"topic '{t.name}' must specify qos_profile")
    topic_names = {t.name for t in cfg.topics}
    for v in cfg.views:
        if v.topic not in topic_names:
            raise ValueError(
                f"view '{v.name}' references unknown topic '{v.topic}'")

    if cfg.writers and not cfg.qos_profiles:
        raise ValueError("config must specify qos_profiles when writers are declared")
    seen_writers: set[str] = set()
    for w in cfg.writers:
        if w.name in seen_writers:
            raise ValueError(f"duplicate writer '{w.name}'")
        seen_writers.add(w.name)
        if w.participant not in participant_names:
            raise ValueError(
                f"writer '{w.name}' references unknown participant "
                f"'{w.participant}'")
        if not w.qos_profile:
            raise ValueError(f"writer '{w.name}' must specify qos_profile")

    # WIS: any entity exposing a wis: block needs a named application and a
    # participant wis_name, or its URI cannot be built.
    if cfg.wis.enabled:
        exposed = [t for t in cfg.topics if t.wis] + [
            w for w in cfg.writers if w.wis]
        if exposed and not cfg.wis.application:
            raise ValueError(
                "wis.application is required when topics or writers declare "
                "a wis: block")
        for entity in exposed:
            pc = cfg.participant_by_name(entity.participant)
            if not pc.wis_name:
                raise ValueError(
                    f"'{entity.name}' declares a wis: block but participant "
                    f"'{entity.participant}' has no wis_name")
