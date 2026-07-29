"""Unit tests for the view-layer scalar conversion (no DDS required).

Constructs generated PLC.Value_t/Limits_t instances directly and checks the
scalarization in views.py — no DomainParticipant, no license, no pipeline.

CR-025: the KIND_STRING branch was unverified and unexercised (the sim only
ever publishes float64). This is the two-line regression test that closes it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dds.gen.PlcValue import PLC
from scada_web.views import _value_t_to_scalar, _limits_to_dict


class TestValueTToScalar:
    """Each PLC.ValueKind_t discriminator decodes to a plain Python scalar."""

    def test_kind_string_round_trips(self):
        # CR-025: unverified before this test — confirms rti.idl yields
        # one-character strings for a char[] array, not integers.
        v = PLC.Value_t(stringValue=list("hi"))
        assert _value_t_to_scalar(v) == "hi"

    def test_kind_string_strips_nul_padding(self):
        v = PLC.Value_t(stringValue=list("hi\0\0"))
        assert _value_t_to_scalar(v) == "hi"

    def test_kind_float64(self):
        v = PLC.Value_t(float64Value=1.5)
        assert _value_t_to_scalar(v) == 1.5

    def test_kind_float32(self):
        v = PLC.Value_t(float32Value=2.5)
        assert _value_t_to_scalar(v) == 2.5

    def test_kind_int32(self):
        v = PLC.Value_t(int32Value=7)
        assert _value_t_to_scalar(v) == 7

    def test_kind_int64(self):
        v = PLC.Value_t(int64Value=9)
        assert _value_t_to_scalar(v) == 9


class TestLimitsToDict:
    def test_scalarizes_all_members(self):
        lim = PLC.Limits_t(
            redHigh=PLC.Value_t(float64Value=100.0),
            redLow=PLC.Value_t(float64Value=0.0),
            yellowHigh=PLC.Value_t(float64Value=90.0),
            yellowLow=PLC.Value_t(float64Value=10.0),
            greenHigh=PLC.Value_t(float64Value=80.0),
            greenLow=PLC.Value_t(float64Value=20.0),
            active=True,
        )
        assert _limits_to_dict(lim) == {
            "redHigh": 100.0,
            "redLow": 0.0,
            "yellowHigh": 90.0,
            "yellowLow": 10.0,
            "greenHigh": 80.0,
            "greenLow": 20.0,
            "active": True,
        }
