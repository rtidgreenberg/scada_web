"""Integration tests for the simulation layer (sim/).

Tests the field_simulation process model and the plc_publisher DDS output
independently of the downstream pipeline. Verifies:
  - Tag generation produces the expected 500 tags with correct rate bands
  - Value functions produce bounded, non-constant output
  - The publisher can start and produce DDS samples on domain 15
  - MetaData samples are published once (TRANSIENT_LOCAL burst)
  - IdValue samples flow at the expected rates per uid band
"""

import sys
import time
from pathlib import Path

import pytest

# Add sim/ to path so we can import its modules directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sim"))

from field_simulation import (
    build_tags,
    publish_period_s,
    TAG_COUNT,
)

# Band coverage is asserted by observing live traffic, so the observation window
# has to be at least as long as the slowest band's period. plc_publisher seeds
# every tag's first due time at `start + period`, so all tags in a band share a
# due time and publish as one synchronized burst once per period rather than
# trickling across it -- a window shorter than the period therefore misses the
# band entirely for part of every cycle rather than merely seeing fewer samples.
# At 5s against the 10s band this test was a coin flip: it passed standalone
# (fixture sleeps happened to straddle the burst) and failed in the full suite,
# where the phase depends on how long the preceding modules took.
#
# Derived from publish_period_s rather than hardcoded so it tracks _RATE_BANDS.
SLOWEST_PERIOD_S = max(publish_period_s(uid) for uid in range(1, TAG_COUNT + 1))
BAND_OBSERVE_S = SLOWEST_PERIOD_S + 2.0  # margin for scheduling + DDS delivery


class TestFieldSimulation:
    """Unit-level tests for the process model (no DDS required)."""

    def test_build_tags_count(self):
        tags = build_tags()
        assert len(tags) == TAG_COUNT
        assert tags[0].uid == 1
        assert tags[-1].uid == TAG_COUNT

    def test_uid_rate_bands(self):
        """Each uid band maps to the documented publish period."""
        assert publish_period_s(1) == 0.5
        assert publish_period_s(100) == 0.5
        assert publish_period_s(101) == 1.0
        assert publish_period_s(200) == 1.0
        assert publish_period_s(201) == 5.0
        assert publish_period_s(300) == 5.0
        assert publish_period_s(301) == 10.0
        assert publish_period_s(500) == 10.0

    def test_uid_out_of_range_raises(self):
        with pytest.raises(ValueError):
            publish_period_s(0)
        with pytest.raises(ValueError):
            publish_period_s(501)

    def test_tag_value_bounded(self):
        """Tag values should be roughly within engineering limits."""
        tags = build_tags()
        tag = tags[0]  # uid=1, mean=50, amplitude=40
        values = [tag.raw_value(t) for t in range(0, 100)]
        # With noise stddev=1 and amplitude=40, values stay near 10-90
        assert all(-5 < v < 105 for v in values)

    def test_tag_value_varies_over_time(self):
        """Values should not be constant — the sine wave evolves."""
        tags = build_tags()
        tag = tags[0]
        values = {round(tag.raw_value(t), 2) for t in range(0, 60)}
        assert len(values) > 10, "Value should vary over time (sine wave)"

    def test_smoothed_value_tracks_raw(self):
        """Exponential smoothing should follow the raw signal."""
        tags = build_tags()
        tag = tags[0]
        smoothed = None
        for t in range(100):
            raw = tag.raw_value(t)
            smoothed = tag.smoothed_value(t, raw, smoothed)
        # After 100 samples, smoothed should be close to raw
        final_raw = tag.raw_value(99)
        assert abs(smoothed - final_raw) < 20

    def test_limits_structure(self):
        tags = build_tags()
        for tag in tags[:5]:
            lim = tag.limits
            assert lim.red_low <= lim.yellow_low <= lim.green_low
            assert lim.green_high <= lim.yellow_high <= lim.red_high
            assert lim.active is True


class TestPlcPublisherDDS:
    """Integration tests verifying plc_publisher outputs DDS samples.

    These require the RTI Connext Python library (rti.connextdds) and the
    PLC type definitions to be available.
    """

    @pytest.fixture(scope="class")
    def dds_subscriber(self):
        """Create a test subscriber on domain 15 to verify publisher output."""
        try:
            import rti.connextdds as dds
        except ImportError:
            pytest.skip("rti.connextdds not available")

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from dds.gen.PlcValue import PLC

        participant = dds.DomainParticipant(15)

        metadata_topic = dds.Topic(participant, "PLC::MetaDataTopic", PLC.MetaData)
        idvalue_topic = dds.Topic(participant, "PLC::IdValueTopic", PLC.IdValue)

        # Reliable + TRANSIENT_LOCAL for metadata (late-join)
        meta_qos = dds.DataReaderQos()
        meta_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
        meta_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
        meta_reader = dds.DataReader(
            participant.implicit_subscriber, metadata_topic, meta_qos
        )

        value_reader = dds.DataReader(
            participant.implicit_subscriber, idvalue_topic
        )

        yield {
            "participant": participant,
            "meta_reader": meta_reader,
            "value_reader": value_reader,
        }

        participant.close()

    def test_metadata_received(self, sim_process, dds_subscriber):
        """Verify MetaData samples are received (TRANSIENT_LOCAL burst)."""
        reader = dds_subscriber["meta_reader"]
        # sim_process fixture already waited 2s for the burst
        time.sleep(1.0)
        samples = reader.read()
        valid = [s for s in samples if s.info.valid]
        assert len(valid) > 0, "No MetaData samples received from publisher"
        # Check structure of first sample
        sample = valid[0].data
        uid = sample.uid
        assert 1 <= uid <= TAG_COUNT

    def test_idvalue_samples_flow(self, sim_process, dds_subscriber):
        """Verify periodic IdValue samples arrive over a window."""
        reader = dds_subscriber["value_reader"]
        time.sleep(3.0)  # Wait for a few publish cycles
        samples = reader.take()
        valid = [s for s in samples if s.info.valid]
        assert len(valid) > 0, "No IdValue samples received within 3s"
        # Verify uid field exists and is in range
        for s in valid[:10]:
            uid = s.data.uid
            assert 1 <= uid <= TAG_COUNT

    def test_idvalue_covers_multiple_bands(self, sim_process, dds_subscriber):
        """Samples should arrive from both fast and slow uid bands."""
        reader = dds_subscriber["value_reader"]
        time.sleep(BAND_OBSERVE_S)  # must exceed SLOWEST_PERIOD_S — see above
        samples = reader.take()
        valid = [s for s in samples if s.info.valid]

        uids = {s.data.uid for s in valid}
        fast_uids = {u for u in uids if u <= 100}
        slow_uids = {u for u in uids if u > 300}

        # Assert the precondition before the property, so an undelivering
        # pipeline reports as itself rather than as a missing band.
        assert valid, (
            f"no IdValue samples at all in {BAND_OBSERVE_S:.0f}s — "
            "publisher not delivering"
        )
        assert fast_uids, (
            f"no samples from fast band (uid 1-100) in {BAND_OBSERVE_S:.0f}s; "
            f"saw {len(uids)} uid(s): {sorted(uids)[:10]}"
        )
        assert slow_uids, (
            f"no samples from slow band (uid 301-{TAG_COUNT}) in "
            f"{BAND_OBSERVE_S:.0f}s (band period {SLOWEST_PERIOD_S:.0f}s); "
            f"saw {len(uids)} uid(s): {sorted(uids)[:10]}"
        )
