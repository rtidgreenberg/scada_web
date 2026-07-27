"""DynamicType schema for the PLC IDL module (sim/PlcValue.idl).

Builds the DDS wire types programmatically via the Connext Python API's
DynamicType builders (StructType, UnionType, EnumType, ...) rather than
generating code with rtiddsgen. This mirrors DD-002 in
docs/design-decisions.md ("Operate on DynamicData throughout; require no
generated type support code") and FR-DDS-007 (types constructible
programmatically, no build step per data model).

This module only describes the schema (Level 0/1 data model). It has no
knowledge of DDS entities (participants, topics, writers) and no knowledge
of simulated process values -- that separation of concerns is deliberate,
see the scada-sme agent's module-layout guidance.

The struct/union/enum shapes below are a direct, field-for-field
transcription of sim/PlcValue.idl. Where the IDL itself is unusual --
notably, stringValue is a fixed char array rather than a bounded string --
that is preserved verbatim rather than "corrected", because the wire
schema must match the real IDL exactly.
"""

import rti.connextdds as dds

MAX_STRING_VALUE_LENGTH = 32
MAX_HOSTNAME_LENGTH = 32
MAX_NAME_LENGTH = 32


def _build_value_kind_t() -> dds.EnumType:
    return dds.EnumType(
        "ValueKind_t",
        [
            dds.EnumMember("KIND_STRING", 0),
            dds.EnumMember("KIND_INT32", 1),
            dds.EnumMember("KIND_INT64", 2),
            dds.EnumMember("KIND_FLOAT32", 3),
            dds.EnumMember("KIND_FLOAT64", 4),
        ],
    )


def _build_value_t(value_kind_t: dds.EnumType) -> dds.UnionType:
    string_value_array = dds.ArrayType(dds.CharType(), MAX_STRING_VALUE_LENGTH)
    return dds.UnionType(
        "Value_t",
        value_kind_t,
        [
            dds.UnionMember("stringValue", string_value_array, 0),  # KIND_STRING
            dds.UnionMember("int32Value", dds.Int32Type(), 1),  # KIND_INT32
            dds.UnionMember("int64Value", dds.Int64Type(), 2),  # KIND_INT64
            dds.UnionMember("float32Value", dds.Float32Type(), 3),  # KIND_FLOAT32
            dds.UnionMember("float64Value", dds.Float64Type(), 4),  # KIND_FLOAT64
        ],
    )


def _build_limits_t(value_t: dds.UnionType) -> dds.StructType:
    return dds.StructType(
        "Limits_t",
        [
            dds.Member("redHigh", value_t),
            dds.Member("redLow", value_t),
            dds.Member("yellowHigh", value_t),
            dds.Member("yellowLow", value_t),
            dds.Member("greenHigh", value_t),
            dds.Member("greenLow", value_t),
            dds.Member("active", dds.BoolType()),
        ],
    )


def _build_metadata(limits_t: dds.StructType) -> dds.StructType:
    return dds.StructType(
        "MetaData",
        [
            dds.Member("uid", dds.Int32Type(), is_key=True),
            dds.Member("valueTime", dds.Int64Type()),
            dds.Member("hostname", dds.StringType(MAX_HOSTNAME_LENGTH)),
            dds.Member("limits", limits_t),
            dds.Member("longName", dds.StringType(MAX_NAME_LENGTH)),
        ],
    )


def _build_id_value(value_t: dds.UnionType) -> dds.StructType:
    return dds.StructType(
        "IdValue",
        [
            dds.Member("uid", dds.Int32Type(), is_key=True),
            dds.Member("valueTime", dds.Int64Type()),
            dds.Member("smoothedValue", value_t),
            dds.Member("rawValue", value_t),
        ],
    )


def _build_command_t() -> dds.EnumType:
    return dds.EnumType(
        "Command_t",
        [
            dds.EnumMember("ADD", 0),
            dds.EnumMember("DELETE", 1),
            dds.EnumMember("METADATA", 2),
        ],
    )


def _build_value_request(command_t: dds.EnumType) -> dds.StructType:
    return dds.StructType(
        "ValueRequest",
        [
            dds.Member("uid", dds.Int32Type()),
            dds.Member("name", dds.StringType(MAX_NAME_LENGTH)),
            dds.Member("command", command_t),
            # period_ms: max publish rate for this uid, 0 = every sample.
            # Applies to ADD; ignored for DELETE and METADATA.
            dds.Member("period_ms", dds.Uint32Type()),
        ],
    )


class PlcTypes:
    """Namespace holding the built DynamicTypes for the PLC module."""

    def __init__(self) -> None:
        self.value_kind_t = _build_value_kind_t()
        self.value_t = _build_value_t(self.value_kind_t)
        self.limits_t = _build_limits_t(self.value_t)
        self.metadata = _build_metadata(self.limits_t)
        self.id_value = _build_id_value(self.value_t)
        self.command_t = _build_command_t()
        self.value_request = _build_value_request(self.command_t)


def build_plc_types() -> PlcTypes:
    """Builds and returns the PLC module's DynamicTypes."""
    return PlcTypes()


def _set_char_array(data: dds.DynamicData, path: str, value: str) -> None:
    # stringValue is `char stringValue[MAX_STRING_VALUE_LENGTH]` in the IDL --
    # a fixed-size char array, not a bounded `string<N>`. DynamicData requires
    # the full array length on every set, so pad/truncate and NUL-terminate.
    if len(value) >= MAX_STRING_VALUE_LENGTH:
        raise ValueError(
            f"string value {value!r} exceeds MAX_STRING_VALUE_LENGTH "
            f"({MAX_STRING_VALUE_LENGTH})"
        )
    padded = value + "\0" * (MAX_STRING_VALUE_LENGTH - len(value))
    data.set_char_values(path, padded)


_VALUE_KIND_SETTERS = {
    "int32": lambda data, path, value: data.set_int32(path, int(value)),
    "int64": lambda data, path, value: data.set_int64(path, int(value)),
    "float32": lambda data, path, value: data.set_float32(path, float(value)),
    "float64": lambda data, path, value: data.set_float64(path, float(value)),
    "string": _set_char_array,
}

_VALUE_KIND_MEMBERS = {
    "string": "stringValue",
    "int32": "int32Value",
    "int64": "int64Value",
    "float32": "float32Value",
    "float64": "float64Value",
}


def set_value_t(sample: dds.DynamicData, member_path: str, kind: str, value) -> None:
    """Sets a `Value_t` union field at `member_path` (e.g. "rawValue" or
    "limits.redHigh") to `value`, selecting the union case named by `kind`
    (one of "string", "int32", "int64", "float32", "float64").

    Setting a union branch's member by its dotted path implicitly selects
    that branch as the active discriminator -- no separate discriminator
    assignment is required.
    """
    if kind not in _VALUE_KIND_SETTERS:
        raise ValueError(f"unknown Value_t kind: {kind!r}")
    field = f"{member_path}.{_VALUE_KIND_MEMBERS[kind]}"
    _VALUE_KIND_SETTERS[kind](sample, field, value)
