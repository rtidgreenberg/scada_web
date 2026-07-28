"""View types — smaller web-facing dataclasses mapped from DDS generated types.

Each view defines its own `from_*` classmethods that map fields from the
full DDS type. This is the DD-053 pattern: mapping is Python code, not config.

The DDS generated types live in scada_web/gen/ (produced by rtiddsgen).
Until codegen is run, this module imports from plc_types (the sim stubs)
as a stand-in.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TagValue:
    """A single tag's current value — the minimal payload sent to web clients."""
    uid: int
    value: float
    timestamp: int

    # @classmethod
    # def from_idvalue(cls, s: PLC.IdValue) -> "TagValue":
    #     """Map from DDS IdValue to the web-facing view."""
    #     return cls(
    #         uid=s.uid,
    #         value=s.smoothedValue.float64Value,
    #         timestamp=s.valueTime,
    #     )


@dataclass(slots=True)
class TagMeta:
    """Tag metadata — static catalogue info sent once per tag."""
    uid: int
    name: str
    hostname: str
    timestamp: int

    # @classmethod
    # def from_metadata(cls, s: PLC.MetaData) -> "TagMeta":
    #     """Map from DDS MetaData to the web-facing view."""
    #     return cls(
    #         uid=s.uid,
    #         name=s.longName,
    #         hostname=s.hostname,
    #         timestamp=s.valueTime,
    #     )
