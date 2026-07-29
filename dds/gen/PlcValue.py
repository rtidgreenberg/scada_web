
# WARNING: THIS FILE IS AUTO-GENERATED. DO NOT MODIFY.

# This file was generated from PlcValue.idl
# using RTI Code Generator (rtiddsgen) version 4.3.1.
# The rtiddsgen tool is part of the RTI Connext DDS distribution.
# For more information, type 'rtiddsgen -help' at a command shell
# or consult the Code Generator User's Manual.

from dataclasses import field
from typing import Union, Sequence, Optional
import rti.idl as idl
from enum import IntEnum
import sys
import os


PLC = idl.get_module("PLC")

PLC_MAX_STRING_VALUE_LENGTH = 32

PLC.MAX_STRING_VALUE_LENGTH = PLC_MAX_STRING_VALUE_LENGTH

PLC_MAX_HOSTNAME_LENGTH = 32

PLC.MAX_HOSTNAME_LENGTH = PLC_MAX_HOSTNAME_LENGTH

PLC_MAX_NAME_LENGTH = 32

PLC.MAX_NAME_LENGTH = PLC_MAX_NAME_LENGTH

PLC_FIELD_DOMAIN_ID = 15

PLC.FIELD_DOMAIN_ID = PLC_FIELD_DOMAIN_ID

PLC_PRESENTATION_DOMAIN_ID = 16

PLC.PRESENTATION_DOMAIN_ID = PLC_PRESENTATION_DOMAIN_ID

PLC_Hostname_t = str

PLC.Hostname_t = PLC_Hostname_t

PLC_Name_t = str

PLC.Name_t = PLC_Name_t

PLC_ValueTime_t = int

PLC.ValueTime_t = PLC_ValueTime_t

PLC_UniqueId_t = idl.int32

PLC.UniqueId_t = PLC_UniqueId_t

@idl.enum
class PLC_ValueKind_t(IntEnum):
    KIND_STRING = 0
    KIND_INT32 = 1
    KIND_INT64 = 2
    KIND_FLOAT32 = 3
    KIND_FLOAT64 = 4

PLC.ValueKind_t = PLC_ValueKind_t

@idl.union(
    type_annotations = [idl.type_name("PLC::Value_t"), ],
    member_annotations = {
        'stringValue': [idl.array([PLC.MAX_STRING_VALUE_LENGTH])],
    }
)
class PLC_Value_t:

    discriminator: PLC.ValueKind_t = PLC.ValueKind_t.KIND_STRING
    value: Union[Sequence[idl.char], idl.int32, int, idl.float32, float] = field(default_factory = idl.array_factory(idl.char, [PLC.MAX_STRING_VALUE_LENGTH]))

    stringValue: Sequence[idl.char] = idl.case(PLC.ValueKind_t.KIND_STRING)
    int32Value: idl.int32 = idl.case(PLC.ValueKind_t.KIND_INT32)
    int64Value: int = idl.case(PLC.ValueKind_t.KIND_INT64)
    float32Value: idl.float32 = idl.case(PLC.ValueKind_t.KIND_FLOAT32)
    float64Value: float = idl.case(PLC.ValueKind_t.KIND_FLOAT64)

PLC.Value_t = PLC_Value_t

@idl.struct(
    type_annotations = [idl.type_name("PLC::Limits_t"), ])
class PLC_Limits_t:
    redHigh: PLC.Value_t = field(default_factory = PLC.Value_t)
    redLow: PLC.Value_t = field(default_factory = PLC.Value_t)
    yellowHigh: PLC.Value_t = field(default_factory = PLC.Value_t)
    yellowLow: PLC.Value_t = field(default_factory = PLC.Value_t)
    greenHigh: PLC.Value_t = field(default_factory = PLC.Value_t)
    greenLow: PLC.Value_t = field(default_factory = PLC.Value_t)
    active: bool = False

PLC.Limits_t = PLC_Limits_t

PLC_MetaDataTopic = "PLC::MetaDataTopic"

PLC.MetaDataTopic = PLC_MetaDataTopic

@idl.struct(
    type_annotations = [idl.type_name("PLC::MetaData"), ],
    member_annotations = {
        'uid': [idl.key, ],
        'hostname': [idl.bound(PLC.MAX_HOSTNAME_LENGTH)],
        'longName': [idl.bound(PLC.MAX_NAME_LENGTH)],
    }
)
class PLC_MetaData:
    uid: idl.int32 = 0
    valueTime: int = 0
    hostname: str = ""
    limits: PLC.Limits_t = field(default_factory = PLC.Limits_t)
    longName: str = ""

PLC.MetaData = PLC_MetaData

PLC_IdValueTopic = "PLC::IdValueTopic"

PLC.IdValueTopic = PLC_IdValueTopic

@idl.struct(
    type_annotations = [idl.type_name("PLC::IdValue"), ],
    member_annotations = {
        'uid': [idl.key, ],
    }
)
class PLC_IdValue:
    uid: idl.int32 = 0
    valueTime: int = 0
    smoothedValue: PLC.Value_t = field(default_factory = PLC.Value_t)
    rawValue: PLC.Value_t = field(default_factory = PLC.Value_t)

PLC.IdValue = PLC_IdValue

PLC_SelectedValueTopic = "PLC::SelectedValueTopic"

PLC.SelectedValueTopic = PLC_SelectedValueTopic

PLC_SelectedMetaDataTopic = "PLC::SelectedMetaDataTopic"

PLC.SelectedMetaDataTopic = PLC_SelectedMetaDataTopic

@idl.enum
class PLC_Command_t(IntEnum):
    ADD = 0
    DELETE = 1
    METADATA = 2
    PERIOD = 3

PLC.Command_t = PLC_Command_t

@idl.struct(
    type_annotations = [idl.type_name("PLC::AddRequest_t"), ],
    member_annotations = {
        'name': [idl.bound(PLC.MAX_NAME_LENGTH)],
    }
)
class PLC_AddRequest_t:
    uid: idl.int32 = 0
    name: str = ""

PLC.AddRequest_t = PLC_AddRequest_t

@idl.struct(
    type_annotations = [idl.type_name("PLC::PeriodRequest_t"), ])
class PLC_PeriodRequest_t:
    period_ms: idl.uint32 = 0

PLC.PeriodRequest_t = PLC_PeriodRequest_t

PLC_ValueRequestTopic = "PLC::ValueRequestTopic"

PLC.ValueRequestTopic = PLC_ValueRequestTopic

@idl.union(
    type_annotations = [idl.type_name("PLC::ValueRequest"), ])
class PLC_ValueRequest:

    discriminator: PLC.Command_t = PLC.Command_t.ADD
    value: Union[PLC.AddRequest_t, idl.int32, PLC.PeriodRequest_t] = field(default_factory = PLC.AddRequest_t)

    addRequest: PLC.AddRequest_t = idl.case(PLC.Command_t.ADD)
    uid: idl.int32 = idl.case(PLC.Command_t.DELETE, PLC.Command_t.METADATA)
    periodRequest: PLC.PeriodRequest_t = idl.case(PLC.Command_t.PERIOD)

PLC.ValueRequest = PLC_ValueRequest
