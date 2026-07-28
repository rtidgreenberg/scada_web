"""RTI Web Integration Service protocol compatibility — pure protocol layer.

This module knows the WIS wire contract and nothing about HTTP plumbing or DDS
entities: URI construction and resolution, the HELLO handshake, sample
envelopes, frame shapes, and the ValueRequest body translation. The FastAPI
routes that use it live in wis_routes.py.

The point of this layer is that UI/index.html — written against RTI Web
Integration Service 7.7 — runs against scada_web unchanged. Resource names in
the URIs are not invented here; they come from the `wis:` blocks in config.yaml,
so they stay owned by configuration exactly as they are in wis-config.xml.

Reference: docs/technical-requirements.md §2 (WIS baseline behavior).

Deliberately not implemented (see docs/wis-compatibility.md):
  sampleFormat=xml, maxWait long-poll, builtin topics, ACL / API keys,
  b_req streaming writes, PUT/DELETE on resource instances.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

REST_ROOT = "/dds/rest1"
CONTENT_TYPE = "application/dds-web+json"

# WIS 7.7 replies "HELLO OK:<text>" / "HELLO FAIL:<reason>" — a space, not the
# underscore the manual shows. UI/index.html matches on the "HELLO" prefix and
# treats any reply containing "fail" as a failure, so the exact text matters.
HELLO_OK = "HELLO OK:Handshake succeeded"
HELLO_FAIL_PREFIX = "HELLO FAIL:"

# Required HELLO headers. The OMG-DDS-API-Key value is accepted empty because
# scada_web implements no ACL — the same as WIS run without -aclFile.
HELLO_REQUIRED_HEADERS = ("Content-Type", "Accept", "OMG-DDS-API-Key", "Version")

# Error codes from the WIS error body contract (§2.2).
INVALID_INPUT = "INVALID_INPUT"
INVALID_OBJECT = "INVALID_OBJECT"
GENERIC_SERVICE_ERROR = "GENERIC_SERVICE_ERROR"


class WisError(Exception):
    """A WIS-shaped error carrying a code from the §2.2 contract."""

    def __init__(self, code: str, message: str, http_status: int = 422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status

    def body(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class HelloError(WisError):
    """The first WebSocket frame was not an acceptable HELLO."""

    def __init__(self, message: str):
        super().__init__(INVALID_INPUT, message, http_status=400)


# ─── Resource identity ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class WisResource:
    """A WIS resource URI bound to the gateway entity that backs it."""
    kind: str    # "reader" | "writer"
    uri: str
    topic: str   # gateway topic/writer key


def reader_uri(app: str, participant: str, subscriber: str,
               data_reader: str) -> str:
    return (f"{REST_ROOT}/applications/{app}"
            f"/domain_participants/{participant}"
            f"/subscribers/{subscriber}/data_readers/{data_reader}")


def writer_uri(app: str, participant: str, publisher: str,
               data_writer: str) -> str:
    return (f"{REST_ROOT}/applications/{app}"
            f"/domain_participants/{participant}"
            f"/publishers/{publisher}/data_writers/{data_writer}")


def normalize_uri(uri: str) -> str:
    """Canonicalize a client-supplied URI for registry lookup.

    Drops query/fragment, collapses repeated slashes, and strips the trailing
    slash. Names stay case-sensitive — WIS resource names are.
    """
    text = (uri or "").strip()
    for sep in ("?", "#"):
        if sep in text:
            text = text.split(sep, 1)[0]
    while "//" in text:
        text = text.replace("//", "/")
    if len(text) > 1:
        text = text.rstrip("/")
    return text


class WisRegistry:
    """Maps WIS resource URIs to the gateway entities behind them."""

    def __init__(self) -> None:
        self._by_uri: dict[str, WisResource] = {}

    def add(self, resource: WisResource) -> None:
        uri = normalize_uri(resource.uri)
        existing = self._by_uri.get(uri)
        if existing is not None:
            raise ValueError(
                f"duplicate WIS resource URI '{uri}' "
                f"(already bound to '{existing.topic}')")
        self._by_uri[uri] = WisResource(resource.kind, uri, resource.topic)

    def resolve(self, uri: str, kind: str | None = None) -> WisResource:
        """Look up a resource, raising a WIS-shaped 404 when it is unknown."""
        resource = self._by_uri.get(normalize_uri(uri))
        if resource is None:
            raise WisError(INVALID_OBJECT,
                           f"no such resource: '{normalize_uri(uri)}'",
                           http_status=404)
        if kind is not None and resource.kind != kind:
            raise WisError(INVALID_OBJECT,
                           f"resource '{resource.uri}' is a {resource.kind}, "
                           f"not a {kind}",
                           http_status=404)
        return resource

    @property
    def uris(self) -> list[str]:
        return sorted(self._by_uri)


def build_registry(config: Any) -> WisRegistry:
    """Build the URI registry from the `wis:` blocks in config."""
    registry = WisRegistry()
    app = config.wis.application

    for tc in config.topics:
        if tc.wis is None:
            continue
        participant = _wis_participant_name(config, tc.participant, tc.name)
        registry.add(WisResource(
            kind="reader",
            uri=reader_uri(app, participant, tc.wis.subscriber,
                           tc.wis.data_reader),
            topic=tc.name,
        ))

    for wc in config.writers:
        if wc.wis is None:
            continue
        participant = _wis_participant_name(config, wc.participant, wc.name)
        registry.add(WisResource(
            kind="writer",
            uri=writer_uri(app, participant, wc.wis.publisher,
                           wc.wis.data_writer),
            topic=wc.name,
        ))

    return registry


def _wis_participant_name(config: Any, participant: str, entity: str) -> str:
    pc = config.participant_by_name(participant)
    if not pc.wis_name:
        raise ValueError(
            f"'{entity}' declares a wis: block but participant "
            f"'{participant}' has no wis_name")
    return pc.wis_name


# ─── HELLO handshake ─────────────────────────────────────────────────────────


def parse_hello(frame: str) -> dict[str, str]:
    """Parse a WIS HELLO frame into its headers.

    The frame is not JSON: it is CRLF-delimited `Name:Value` lines terminated by
    a blank line. A leading bare `HELLO` line is tolerated — the manual presents
    the frame that way while the shipped JavaScript client sends headers only.

    Raises HelloError if the frame is not a HELLO or a required header is
    missing.
    """
    if frame is None:
        raise HelloError("expected a HELLO frame, got nothing")
    text = frame.strip()
    if not text:
        raise HelloError("expected a HELLO frame, got an empty frame")
    if text.startswith("{") or text.startswith("["):
        raise HelloError("expected a HELLO frame before any JSON frame")

    headers: dict[str, str] = {}
    for line in text.replace("\r\n", "\n").split("\n"):
        line = line.strip()
        if not line or line.upper() == "HELLO":
            continue
        if ":" not in line:
            raise HelloError(f"malformed HELLO header line: '{line}'")
        name, _, value = line.partition(":")
        headers[name.strip()] = value.strip()

    missing = [h for h in HELLO_REQUIRED_HEADERS if h not in headers]
    if missing:
        raise HelloError("missing required HELLO header(s): "
                         + ", ".join(missing))
    return headers


def hello_failure(reason: str) -> str:
    return HELLO_FAIL_PREFIX + reason


# ─── Sample envelopes and frames ─────────────────────────────────────────────


def _timestamp(value: Any) -> dict[str, int] | None:
    if value is None:
        return None
    try:
        return {"sec": int(value.sec), "nanosec": int(value.nanosec)}
    except Exception:
        return None


def _state_name(value: Any) -> str | None:
    """"InstanceState.ALIVE" → "ALIVE", matching WIS output."""
    if value is None:
        return None
    return str(value).rsplit(".", 1)[-1]


def read_sample_info(info: Any) -> dict[str, Any]:
    """Build the WIS `read_sample_info` object for a DDS SampleInfo."""
    state = getattr(info, "state", None)
    out: dict[str, Any] = {"valid_data": bool(getattr(info, "valid", True))}
    ts = _timestamp(getattr(info, "source_timestamp", None))
    if ts is not None:
        out["source_timestamp"] = ts
    for key, attr in (("instance_state", "instance_state"),
                      ("sample_state", "sample_state"),
                      ("view_state", "view_state")):
        name = _state_name(getattr(state, attr, None))
        if name is not None:
            out[key] = name
    return out


def sample_envelope(data_dict: dict[str, Any], info: Any) -> dict[str, Any]:
    """One entry of a `read_sample_seq`: read_sample_info alongside data."""
    return {"read_sample_info": read_sample_info(info), "data": data_dict}


def b_push_frame(bind_id: str, samples: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Server-initiated sample delivery for a bound reader."""
    return {
        "kind": "b_push",
        "bind_id": bind_id,
        "body": {"read_sample_seq": list(samples)},
    }


def error_frame(kind: str, error: WisError, *, request_id: str | None = None,
                bind_id: str | None = None) -> dict[str, Any]:
    """An error reply frame. Bind and request families reply only on error."""
    frame: dict[str, Any] = {
        "kind": kind,
        "return_code": error.code,
        "message": error.message,
    }
    if request_id is not None:
        frame["id"] = request_id
    if bind_id is not None:
        frame["bind_id"] = bind_id
    return frame


# ─── ValueRequest body translation ───────────────────────────────────────────

COMMAND_NAMES = ("ADD", "DELETE", "METADATA", "PERIOD")


def _command_name(raw: Any) -> str:
    """Accept a command as its enum name or its ordinal."""
    if isinstance(raw, bool):
        raise WisError(INVALID_INPUT, f"invalid command: {raw!r}")
    if isinstance(raw, int):
        if not 0 <= raw < len(COMMAND_NAMES):
            raise WisError(INVALID_INPUT, f"command ordinal out of range: {raw}")
        return COMMAND_NAMES[raw]
    if isinstance(raw, str):
        name = raw.strip().upper()
        if name in COMMAND_NAMES:
            return name
        raise WisError(INVALID_INPUT, f"unknown command: '{raw}'")
    raise WisError(INVALID_INPUT, "command is required")


def _require_uid(body: dict[str, Any]) -> int:
    if "uid" not in body:
        raise WisError(INVALID_INPUT, "uid is required")
    try:
        return int(body["uid"])
    except (TypeError, ValueError):
        raise WisError(INVALID_INPUT, f"invalid uid: {body['uid']!r}") from None


def _period_ms(body: dict[str, Any]) -> int:
    raw = body.get("period_ms", 0)
    if raw is None:
        return 0
    try:
        period = int(raw)
    except (TypeError, ValueError):
        raise WisError(INVALID_INPUT,
                       f"invalid period_ms: {raw!r}") from None
    if period < 0:
        raise WisError(INVALID_INPUT, "period_ms must be >= 0")
    return period


@dataclass(frozen=True)
class ValueRequestIntent:
    """What a ValueRequest asks for, independent of its wire encoding.

    scada_web needs the intent — not just the samples to publish — because with
    no selector deployed it must apply the selection itself to decide what to
    push to that client.
    """
    command: Optional[str]          # ADD | DELETE | METADATA | PERIOD
    uid: Optional[int] = None
    period_ms: Optional[int] = None


def translate_value_request(
        body: Any) -> Tuple[ValueRequestIntent, List[Dict[str, Any]]]:
    """Translate a ValueRequest write body into its intent and wire samples.

    UI/index.html predates the Command_t-discriminated union and still posts the
    old flat struct `{uid, name, command, period_ms}`. Keeping the UI unchanged
    means translating here. Bodies already in union shape (an explicit
    `$discriminator`, or an `addRequest`/`periodRequest` branch) pass through.

    An ADD carrying a nonzero period_ms yields *two* samples — PERIOD then ADD —
    because minimum separation is global in the union API while the flat struct
    carried it per request. PERIOD goes first so the rate is in effect before the
    uid begins forwarding.

    The returned dicts are fed to DynamicData.from_json(), which is the only way
    to select DELETE vs METADATA: both share the `uid` member, and assigning that
    member always picks DELETE (the first case).
    """
    if not isinstance(body, dict):
        raise WisError(INVALID_INPUT, "write body must be a JSON object")

    # Already union-shaped: publish as given, and recover the intent when the
    # discriminator states it plainly.
    if "$discriminator" in body or "addRequest" in body or "periodRequest" in body:
        return _passthrough_intent(body), [body]

    command = _command_name(body.get("command"))

    if command == "ADD":
        uid = _require_uid(body)
        name = body.get("name") or ""
        if not isinstance(name, str):
            raise WisError(INVALID_INPUT, f"invalid name: {name!r}")
        samples: List[Dict[str, Any]] = []
        period = _period_ms(body)
        if period > 0:
            samples.append(_period_sample(period))
        samples.append({
            "$discriminator": "ADD",
            "addRequest": {"uid": uid, "name": name},
        })
        return ValueRequestIntent("ADD", uid=uid, period_ms=period or None), samples

    if command in ("DELETE", "METADATA"):
        uid = _require_uid(body)
        return (ValueRequestIntent(command, uid=uid),
                [{"$discriminator": command, "uid": uid}])

    # PERIOD
    period = _period_ms(body)
    return ValueRequestIntent("PERIOD", period_ms=period), [_period_sample(period)]


def _passthrough_intent(body: Dict[str, Any]) -> ValueRequestIntent:
    """Best-effort intent for a body already in union shape."""
    add = body.get("addRequest")
    if isinstance(add, dict):
        uid = add.get("uid")
        return ValueRequestIntent("ADD",
                                  uid=int(uid) if uid is not None else None)
    period = body.get("periodRequest")
    if isinstance(period, dict):
        ms = period.get("period_ms")
        return ValueRequestIntent("PERIOD",
                                  period_ms=int(ms) if ms is not None else None)
    disc = body.get("$discriminator")
    if disc in ("DELETE", "METADATA"):
        uid = body.get("uid")
        return ValueRequestIntent(disc,
                                  uid=int(uid) if uid is not None else None)
    return ValueRequestIntent(None)


def _period_sample(period_ms: int) -> dict[str, Any]:
    return {
        "$discriminator": "PERIOD",
        "periodRequest": {"period_ms": period_ms},
    }
