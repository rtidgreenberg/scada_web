"""Simulated field process + Level 1 PLC tag definitions for the sim.

This module owns the Purdue Level 0 (physical process) and Level 1
(PLC scan/sampling) concerns: what tags exist, their engineering units and
alarm limits, and how their values evolve over time. It has no knowledge of
DDS -- see plc_publisher.py for the Level 1->2 publication path -- so the
process model can be tested or swapped independently of the transport.

Tag naming follows <AREA>_<EQUIPMENT>_<MEASUREMENT>_<SUFFIX>, e.g.
WTP1_PMP01_FLOW_PV, per the scada-sme tag/point database convention.
"""

import math
import random
from dataclasses import dataclass
from typing import Callable, List


@dataclass
class Limits:
    """Engineering-unit alarm limits, mirroring PLC::Limits_t."""

    red_low: float
    yellow_low: float
    green_low: float
    green_high: float
    yellow_high: float
    red_high: float
    active: bool = True


@dataclass
class Tag:
    """A single simulated PLC point (Level 0/1 process value)."""

    uid: int
    name: str
    long_name: str
    units: str
    limits: Limits
    # value_fn(t_seconds) -> raw process value in engineering units.
    value_fn: Callable[[float], float]
    noise_stddev: float = 0.0

    def raw_value(self, t: float) -> float:
        return self.value_fn(t)

    def smoothed_value(self, t: float, raw: float, previous_smoothed: float) -> float:
        # Simple first-order (exponential) filter, as a real PLC scan-rate
        # smoothing pass would apply before publishing "smoothedValue".
        alpha = 0.3
        if previous_smoothed is None:
            return raw
        return previous_smoothed + alpha * (raw - previous_smoothed)


PLC_HOSTNAME = "plc-wtp1-01"


def _sine(mean: float, amplitude: float, period_s: float, phase: float = 0.0):
    def fn(t: float) -> float:
        return mean + amplitude * math.sin(2 * math.pi * t / period_s + phase)

    return fn


def _noisy(fn, stddev: float):
    def wrapped(t: float) -> float:
        return fn(t) + random.gauss(0.0, stddev)

    return wrapped


def build_tags() -> List[Tag]:
    """Builds the simulated tag list (Level 0/1 process model)."""
    return [
        Tag(
            uid=101,
            name="WTP1_PMP01_FLOW_PV",
            long_name="WTP1 Pump 01 Discharge Flow",
            units="gpm",
            limits=Limits(
                red_low=0, yellow_low=50, green_low=100,
                green_high=400, yellow_high=450, red_high=500,
            ),
            value_fn=_noisy(_sine(mean=250, amplitude=60, period_s=180), 3.0),
        ),
        Tag(
            uid=102,
            name="WTP1_TK02_LVL_PV",
            long_name="WTP1 Tank 02 Level",
            units="%",
            limits=Limits(
                red_low=5, yellow_low=15, green_low=25,
                green_high=85, yellow_high=92, red_high=97,
            ),
            value_fn=_noisy(_sine(mean=60, amplitude=20, period_s=600), 0.4),
        ),
        Tag(
            uid=103,
            name="WTP1_TK02_PRESS_PV",
            long_name="WTP1 Tank 02 Discharge Pressure",
            units="psi",
            limits=Limits(
                red_low=10, yellow_low=20, green_low=30,
                green_high=80, yellow_high=90, red_high=100,
            ),
            value_fn=_noisy(_sine(mean=55, amplitude=8, period_s=240), 0.8),
        ),
        Tag(
            uid=104,
            name="WTP1_LINE1_TEMP_PV",
            long_name="WTP1 Line 1 Process Temperature",
            units="degF",
            limits=Limits(
                red_low=40, yellow_low=50, green_low=60,
                green_high=90, yellow_high=95, red_high=100,
            ),
            value_fn=_noisy(_sine(mean=72, amplitude=5, period_s=900), 0.2),
        ),
        Tag(
            uid=105,
            name="WTP1_VLV01_POS_PV",
            long_name="WTP1 Valve 01 Position Feedback",
            units="% open",
            limits=Limits(
                red_low=0, yellow_low=5, green_low=10,
                green_high=95, yellow_high=98, red_high=100,
                active=True,
            ),
            value_fn=_noisy(_sine(mean=50, amplitude=45, period_s=120), 1.0),
        ),
    ]
