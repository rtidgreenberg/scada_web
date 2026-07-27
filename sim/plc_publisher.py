#!/usr/bin/env python3
"""Simulated PLC/RTU that publishes DDS samples of the PLC IDL module
(sim/PlcValue.idl) for the scada_web web gateway to expose to web clients.

Purdue-model placement: this script *is* the Level 1 (PLC/RTU) boundary. It
owns the field-device scan loop and is the only thing in the sim that talks
DDS; Level 0 (the simulated process) lives in field_simulation.py and knows
nothing about DDS, and the wire schema lives in plc_types.py and knows
nothing about either DDS entities or simulated values. Keeping those three
concerns in separate modules is deliberate, even in a small simulator, so
the architecture doesn't imply the field device, the network, and the data
model are one undifferentiated blob.

Publishing pattern, per the QoS-pattern comments already in the IDL:
  - MetaData: "Use State Data QoS pattern, only sent at startup, typically"
    -> published once per tag at startup, RELIABLE + TRANSIENT_LOCAL so a
       late-joining subscriber (e.g. scada_web itself, or a test client)
       still receives each tag's static description.
  - IdValue: "Use 1-many reliable QoS pattern ... reliability depends on
    whether all values update periodically or upon change"
    -> published periodically for every tag, RELIABLE + VOLATILE (the
       process moves on; a new subscriber gets the next scan, not history).

Usage:
    python3 sim/plc_publisher.py --domain-id 0 --period 1.0
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rti.connextdds as dds

from field_simulation import PLC_HOSTNAME, Tag, build_tags
from plc_types import build_plc_types, set_value_t

METADATA_TOPIC = "PLC::MetaData"
ID_VALUE_TOPIC = "PLC::IdValue"


def _now_ms() -> int:
    """valueTime convention used by this sim: milliseconds since Unix epoch."""
    return int(time.time() * 1000)


def _metadata_writer_qos(participant: dds.DomainParticipant) -> dds.DataWriterQos:
    qos = participant.default_datawriter_qos
    qos.reliability.kind = dds.ReliabilityKind.RELIABLE
    qos.durability.kind = dds.DurabilityKind.TRANSIENT_LOCAL
    qos.history.kind = dds.HistoryKind.KEEP_LAST
    qos.history.depth = 1
    return qos


def _id_value_writer_qos(participant: dds.DomainParticipant) -> dds.DataWriterQos:
    qos = participant.default_datawriter_qos
    qos.reliability.kind = dds.ReliabilityKind.RELIABLE
    qos.durability.kind = dds.DurabilityKind.VOLATILE
    qos.history.kind = dds.HistoryKind.KEEP_LAST
    qos.history.depth = 1
    return qos


def _write_metadata(
    writer: dds.DynamicData.DataWriter, metadata_type: dds.DynamicType, tag: Tag
) -> None:
    sample = dds.DynamicData(metadata_type)
    sample.set_int32("uid", tag.uid)
    sample.set_int64("valueTime", _now_ms())
    sample.set_string("hostname", PLC_HOSTNAME)
    sample.set_string("longName", tag.long_name)

    limits = tag.limits
    set_value_t(sample, "limits.redHigh", "float64", limits.red_high)
    set_value_t(sample, "limits.redLow", "float64", limits.red_low)
    set_value_t(sample, "limits.yellowHigh", "float64", limits.yellow_high)
    set_value_t(sample, "limits.yellowLow", "float64", limits.yellow_low)
    set_value_t(sample, "limits.greenHigh", "float64", limits.green_high)
    set_value_t(sample, "limits.greenLow", "float64", limits.green_low)
    sample.set_boolean("limits.active", limits.active)

    writer.write(sample)


def _write_id_value(
    writer: dds.DynamicData.DataWriter,
    id_value_type: dds.DynamicType,
    tag: Tag,
    t: float,
    previous_smoothed: float,
) -> float:
    raw = tag.raw_value(t)
    smoothed = tag.smoothed_value(t, raw, previous_smoothed)

    sample = dds.DynamicData(id_value_type)
    sample.set_int32("uid", tag.uid)
    sample.set_int64("valueTime", _now_ms())
    set_value_t(sample, "smoothedValue", "float64", smoothed)
    set_value_t(sample, "rawValue", "float64", raw)

    writer.write(sample)
    return smoothed


def run(domain_id: int, period_s: float, verbose: bool) -> None:
    tags = build_tags()
    types = build_plc_types()

    participant = dds.DomainParticipant(domain_id)
    publisher = dds.Publisher(participant)

    metadata_topic = dds.DynamicData.Topic(participant, METADATA_TOPIC, types.metadata)
    id_value_topic = dds.DynamicData.Topic(participant, ID_VALUE_TOPIC, types.id_value)

    metadata_writer = dds.DynamicData.DataWriter(
        publisher, metadata_topic, _metadata_writer_qos(participant)
    )
    id_value_writer = dds.DynamicData.DataWriter(
        publisher, id_value_topic, _id_value_writer_qos(participant)
    )

    print(
        f"PLC sim '{PLC_HOSTNAME}' publishing {len(tags)} tags on domain "
        f"{domain_id}: '{METADATA_TOPIC}' (once at startup) and "
        f"'{ID_VALUE_TOPIC}' (every {period_s}s)."
    )

    for tag in tags:
        _write_metadata(metadata_writer, types.metadata, tag)
        if verbose:
            print(f"  metadata: uid={tag.uid} name={tag.name}")

    smoothed_by_uid = {tag.uid: None for tag in tags}
    start = time.monotonic()
    try:
        while True:
            t = time.monotonic() - start
            for tag in tags:
                smoothed_by_uid[tag.uid] = _write_id_value(
                    id_value_writer, types.id_value, tag, t, smoothed_by_uid[tag.uid]
                )
                if verbose:
                    print(
                        f"  {tag.name}: raw={tag.raw_value(t):.2f} "
                        f"smoothed={smoothed_by_uid[tag.uid]:.2f} {tag.units}"
                    )
            time.sleep(period_s)
    except KeyboardInterrupt:
        print("\nStopping PLC sim.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain-id", type=int, default=0, help="DDS domain ID")
    parser.add_argument(
        "--period", type=float, default=1.0, help="IdValue publish period, seconds"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print each sample as it's published"
    )
    args = parser.parse_args()
    run(args.domain_id, args.period, args.verbose)


if __name__ == "__main__":
    main()
