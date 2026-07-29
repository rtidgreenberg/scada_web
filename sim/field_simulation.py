"""Simulated field process + Level 1 PLC tag definitions for the sim.

This module owns the Purdue Level 0 (physical process) and Level 1
(PLC scan/sampling) concerns: what tags exist, their engineering units and
alarm limits, and how their values evolve over time. It has no knowledge of
DDS -- see plc_publisher.py for the Level 1->2 publication path -- so the
process model can be tested or swapped independently of the transport.

The tag set is a synthetic rate/load-test population: 500 tags, uid 1-500,
each a noisy sine wave with no particular real-world meaning. Each tag's
IdValue publish rate is driven by `publish_period_s`, a Level 1 scan-rate
grouping keyed on uid:
  - uid 1-100:   2 Hz   (0.5 s)
  - uid 101-200: 1 Hz   (1.0 s)
  - uid 201-300: every 5 s
  - uid 301-500: every 10 s
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


# (low_uid, high_uid, period_s) bands, checked in order. Covers uid 1-500.
_RATE_BANDS = (
    (1, 100, 0.5),      # 2 Hz
    (101, 200, 1.0),    # 1 Hz
    (201, 300, 5.0),    # every 5 s
    (301, 500, 10.0),   # every 10 s
)

TAG_COUNT = 500


def publish_period_s(uid: int) -> float:
    """Returns the IdValue publish period, in seconds, for `uid`, per the
    rate distribution documented in this module's docstring.
    """
    for low, high, period in _RATE_BANDS:
        if low <= uid <= high:
            return period
    raise ValueError(f"uid {uid} is outside the simulated rate bands (1-{TAG_COUNT})")


def build_tags() -> List[Tag]:
    """Builds the simulated tag list: TAG_COUNT synthetic tags (uid 1-500),
    each a noisy sine wave whose shape varies by uid so tags are visibly
    distinct, but with no real-world process meaning (Level 0/1 model).
    """
    tags = []
    for uid in range(1, TAG_COUNT + 1):
        sine_period_s = 30 + (uid % 47)
        phase = (uid % 12) * (math.pi / 6)
        tags.append(
            Tag(
                uid=uid,
                name=f"SIM_TAG_{uid:03d}",
                long_name=f"Simulated Tag {uid:03d}",
                units="eng",
                limits=Limits(
                    red_low=0, yellow_low=10, green_low=20,
                    green_high=80, yellow_high=90, red_high=100,
                ),
                value_fn=_noisy(
                    _sine(mean=50, amplitude=40, period_s=sine_period_s, phase=phase),
                    1.0,
                ),
            )
        )
    return tags
