"""View types — smaller web-facing dataclasses mapped from DDS generated types.

Each view defines `from_*` classmethods that map fields from the full DDS
generated type to a slim web-facing shape (DD-053). This is Python code,
not config — typed attribute access with IDE completion and import-time
validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .gen.PlcValue import PLC


def _value_t_to_scalar(v: PLC.Value_t) -> Any:
    """Extract the scalar from a Value_t union."""
    kind = v.discriminator
    if kind == PLC.ValueKind_t.KIND_FLOAT64:
        return v.float64Value
    elif kind == PLC.ValueKind_t.KIND_FLOAT32:
        return float(v.float32Value)
    elif kind == PLC.ValueKind_t.KIND_INT32:
        return int(v.int32Value)
    elif kind == PLC.ValueKind_t.KIND_INT64:
        return int(v.int64Value)
    elif kind == PLC.ValueKind_t.KIND_STRING:
        # char[N] comes as a list of chars — join and strip NUL padding
        chars = v.stringValue
        return "".join(chars).split("\0", 1)[0]
    return None


def _limits_to_dict(lim: PLC.Limits_t) -> dict[str, Any]:
    """Convert Limits_t to a browser-friendly dict."""
    return {
        "redHigh": _value_t_to_scalar(lim.redHigh),
        "redLow": _value_t_to_scalar(lim.redLow),
        "yellowHigh": _value_t_to_scalar(lim.yellowHigh),
        "yellowLow": _value_t_to_scalar(lim.yellowLow),
        "greenHigh": _value_t_to_scalar(lim.greenHigh),
        "greenLow": _value_t_to_scalar(lim.greenLow),
        "active": lim.active,
    }


@dataclass
class TagValue:
    """A single tag's current value — the minimal payload sent to web clients."""
    uid: int
    value: Any
    raw_value: Any
    timestamp: int

    @classmethod
    def from_idvalue(cls, s: PLC.IdValue) -> "TagValue":
        """Map from generated PLC::IdValue to the web-facing view."""
        return cls(
            uid=int(s.uid),
            value=_value_t_to_scalar(s.smoothedValue),
            raw_value=_value_t_to_scalar(s.rawValue),
            timestamp=int(s.valueTime),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "valueTime": self.timestamp,
            "smoothedValue": self.value,
            "rawValue": self.raw_value,
        }


@dataclass
class TagMeta:
    """Tag metadata — static catalogue info sent once per tag."""
    uid: int
    name: str
    hostname: str
    limits: dict[str, Any]
    timestamp: int

    @classmethod
    def from_metadata(cls, s: PLC.MetaData) -> "TagMeta":
        """Map from generated PLC::MetaData to the web-facing view."""
        return cls(
            uid=int(s.uid),
            name=s.longName,
            hostname=s.hostname,
            limits=_limits_to_dict(s.limits),
            timestamp=int(s.valueTime),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "valueTime": self.timestamp,
            "hostname": self.hostname,
            "longName": self.name,
            "limits": self.limits,
        }
