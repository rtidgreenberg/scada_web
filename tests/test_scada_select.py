"""Integration tests for scada_select (C++ SCADA selector).

Verifies that scada_select correctly:
  - Forwards selected tags from domain 15 to domain 16
  - Respects the pre-enabled uid range (100-500 per config.yaml)
  - Responds to ValueRequest ADD/DELETE commands
  - Applies minimum separation (rate-limiting) on the output
  - Publishes SelectedMetaData as TRANSIENT_LOCAL

These tests use the sim as the field-domain data source and a Python
DDS subscriber on domain 16 as the verification point.
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sim"))

pytestmark = pytest.mark.pipeline


@pytest.fixture(scope="module")
def presentation_subscriber():
    """Subscribe to SelectedValueTopic and SelectedMetaDataTopic on domain 16."""
    try:
        import rti.connextdds as dds
    except ImportError:
        pytest.skip("rti.connextdds not available")

    from plc_types import build_plc_types

    types = build_plc_types()
    participant = dds.DomainParticipant(16)

    selected_value_topic = dds.DynamicData.Topic(
        participant, "PLC::SelectedValueTopic", types.id_value
    )
    selected_meta_topic = dds.DynamicData.Topic(
        participant, "PLC::SelectedMetaDataTopic", types.metadata
    )

    # MetaData: TRANSIENT_LOCAL for late-join
    meta_qos = dds.DataReaderQos()
    meta_qos.reliability.kind = dds.ReliabilityKind.RELIABLE
    meta_qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
    meta_reader = dds.DynamicData.DataReader(
        participant.implicit_subscriber, selected_meta_topic, meta_qos
    )

    value_reader = dds.DynamicData.DataReader(
        participant.implicit_subscriber, selected_value_topic
    )

    yield {
        "participant": participant,
        "meta_reader": meta_reader,
        "value_reader": value_reader,
        "types": types,
    }

    participant.close()


class TestSelectorForwarding:
    """Verify scada_select forwards the correct data to domain 16."""

    def test_selected_metadata_available(self, selector_process,
                                         presentation_subscriber):
        """SelectedMetaData should be available via TRANSIENT_LOCAL."""
        reader = presentation_subscriber["meta_reader"]
        time.sleep(2.0)
        samples = reader.read()
        valid = [s for s in samples if s.info.valid]
        assert len(valid) > 0, "No SelectedMetaData received on domain 16"

    def test_selected_metadata_uid_range(self, selector_process,
                                         presentation_subscriber):
        """Metadata forwards all tags from the sim (catalogue data).

        Unlike IdValue, metadata is forwarded for the full tag set — the
        uid_range_low/high config only gates periodic value forwarding.
        """
        reader = presentation_subscriber["meta_reader"]
        time.sleep(2.0)
        samples = reader.read()
        valid = [s for s in samples if s.info.valid]
        uids = {s.data["uid"] for s in valid}
        # Should have metadata for the tags the sim publishes (1-500)
        assert len(uids) > 50, f"Expected many metadata uids, got {len(uids)}"

    def test_selected_values_flow(self, selector_process,
                                  presentation_subscriber):
        """SelectedValueTopic should receive periodic value samples."""
        reader = presentation_subscriber["value_reader"]
        time.sleep(5.0)
        samples = reader.take()
        valid = [s for s in samples if s.info.valid]
        assert len(valid) > 0, "No SelectedValue samples on domain 16 within 5s"

    def test_selected_values_only_enabled_uids(self, selector_process,
                                               presentation_subscriber):
        """Value samples should only contain pre-enabled uids."""
        reader = presentation_subscriber["value_reader"]
        time.sleep(5.0)
        samples = reader.take()
        valid = [s for s in samples if s.info.valid]
        for s in valid:
            uid = s.data["uid"]
            assert 100 <= uid <= 500, f"Unexpected uid {uid} in SelectedValue"


class TestSelectorValueRequest:
    """Verify scada_select responds to ValueRequest commands."""

    @pytest.fixture
    def request_writer(self, presentation_subscriber):
        """Create a ValueRequest writer on domain 16."""
        try:
            import rti.connextdds as dds
        except ImportError:
            pytest.skip("rti.connextdds not available")

        types = presentation_subscriber["types"]
        participant = presentation_subscriber["participant"]

        # The selector already owns this topic on domain 16 — find it via
        # discovery rather than trying to create a duplicate.
        request_topic = dds.DynamicData.Topic(
            participant, "PLC::ValueRequestTopic", types.value_request
        )
        writer = dds.DynamicData.DataWriter(
            participant.implicit_publisher, request_topic
        )
        time.sleep(1.0)  # Allow discovery
        yield writer

    def test_add_request_enables_uid(self, selector_process,
                                     presentation_subscriber,
                                     request_writer):
        """Sending ADD for uid 50 (outside default range) should start forwarding."""
        import rti.connextdds as dds

        types = presentation_subscriber["types"]
        # uid 50 is below the pre-enabled range (100-500)
        sample = dds.DynamicData(types.value_request)
        sample["addRequest.uid"] = 50
        sample["addRequest.name"] = ""
        request_writer.write(sample)

        # Wait for samples on the presentation domain
        reader = presentation_subscriber["value_reader"]
        time.sleep(5.0)
        samples = reader.take()
        valid = [s for s in samples if s.info.valid]
        uids = {s.data["uid"] for s in valid}
        assert 50 in uids, f"uid 50 not found after ADD request (got: {uids})"

    def test_min_separation_limits_rate(self, selector_process,
                                       presentation_subscriber,
                                       request_writer):
        """PERIOD command should rate-limit forwarded samples."""
        import rti.connextdds as dds

        types = presentation_subscriber["types"]
        # Set a large separation (2000ms) for uid 110 (2 Hz source = 500ms)
        sample = dds.DynamicData(types.value_request)
        sample["periodRequest.period_ms"] = 2000
        request_writer.write(sample)

        # Collect samples for uid 110 over 6 seconds
        reader = presentation_subscriber["value_reader"]
        time.sleep(1.0)
        reader.take()  # flush old samples
        time.sleep(6.0)
        samples = reader.take()
        valid = [s for s in samples if s.info.valid and s.data["uid"] == 110]
        # At 2000ms separation, 6s window should yield ~3 samples (not 12)
        assert len(valid) <= 5, (
            f"Expected <=5 samples with 2s separation, got {len(valid)}"
        )
