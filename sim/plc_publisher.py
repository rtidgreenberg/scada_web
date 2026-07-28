#!/usr/bin/env python3
"""Simulated PLC/RTU that publishes DDS samples of the PLC IDL module
(dds/idl/PlcValue.idl) for the scada_web web gateway to expose to web clients.

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
        -> published periodically for every tag using the field-domain IdValue
             writer profile from dds/qos/profiles.xml.

Each tag publishes IdValue on its own schedule rather than a single shared
period: field_simulation.publish_period_s(uid) assigns uid 1-100 to 2 Hz,
101-200 to 1 Hz, 201-300 to every 5 s, and 301-500 to every 10 s. A min-heap
keyed on each tag's next-due time drives the scan loop so 500 independently
rated tags are serviced without polling every tag every tick.

Usage:
    python3 sim/plc_publisher.py --domain-id 0
"""

import argparse
import heapq
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rti.connextdds as dds

from field_simulation import PLC_HOSTNAME, Tag, build_tags, publish_period_s
from plc_types import build_plc_types, set_value_t

METADATA_TOPIC = "PLC::MetaDataTopic"
ID_VALUE_TOPIC = "PLC::IdValueTopic"

QOS_PROFILES_XML = str(Path(__file__).resolve().parent.parent / "dds" / "qos" / "profiles.xml")


def _now_ms() -> int:
    """valueTime convention used by this sim: milliseconds since Unix epoch."""
    return int(time.time() * 1000)


def _metadata_writer_qos() -> dds.DataWriterQos:
    provider = dds.QosProvider(QOS_PROFILES_XML)
    return provider.datawriter_qos_from_profile("field::metadata")


def _id_value_writer_qos() -> dds.DataWriterQos:
    provider = dds.QosProvider(QOS_PROFILES_XML)
    return provider.datawriter_qos_from_profile("field::idvalue")


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


def run(domain_id: int, verbose: bool) -> None:
    tags = build_tags()
    tags_by_uid = {tag.uid: tag for tag in tags}
    types = build_plc_types()

    participant = dds.DomainParticipant(domain_id)
    publisher = dds.Publisher(participant)

    metadata_topic = dds.DynamicData.Topic(participant, METADATA_TOPIC, types.metadata)
    id_value_topic = dds.DynamicData.Topic(participant, ID_VALUE_TOPIC, types.id_value)

    metadata_writer = dds.DynamicData.DataWriter(
        publisher, metadata_topic, _metadata_writer_qos()
    )
    id_value_writer = dds.DynamicData.DataWriter(
        publisher, id_value_topic, _id_value_writer_qos()
    )

    print(
        f"PLC sim '{PLC_HOSTNAME}' publishing {len(tags)} tags on domain "
        f"{domain_id}: '{METADATA_TOPIC}' (once at startup) and "
        f"'{ID_VALUE_TOPIC}' (per-tag rate: uid 1-100 @ 2 Hz, 101-200 @ 1 Hz, "
        f"201-300 every 5s, 301-500 every 10s)."
    )

    for tag in tags:
        _write_metadata(metadata_writer, types.metadata, tag)
        if verbose:
            print(f"  metadata: uid={tag.uid} name={tag.name}")

    smoothed_by_uid = {tag.uid: None for tag in tags}
    start = time.monotonic()

    # Min-heap of (next_due_time, uid, period_s); each entry is rescheduled
    # by period_s (not relative to `now`) on every publish, so a tag's cadence
    # does not drift from processing time spent on other tags.
    schedule: list = []
    for tag in tags:
        period = publish_period_s(tag.uid)
        heapq.heappush(schedule, (start + period, tag.uid, period))

    try:
        while True:
            due_time, uid, period = schedule[0]
            sleep_for = due_time - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)
            heapq.heappop(schedule)

            tag = tags_by_uid[uid]
            t = time.monotonic() - start
            smoothed_by_uid[uid] = _write_id_value(
                id_value_writer, types.id_value, tag, t, smoothed_by_uid[uid]
            )
            if verbose:
                print(
                    f"  {tag.name}: raw={tag.raw_value(t):.2f} "
                    f"smoothed={smoothed_by_uid[uid]:.2f} {tag.units}"
                )

            heapq.heappush(schedule, (due_time + period, uid, period))
    except KeyboardInterrupt:
        print("\nStopping PLC sim.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain-id", type=int, default=0, help="DDS domain ID")
    parser.add_argument(
        "--verbose", action="store_true", help="Print each sample as it's published"
    )
    args = parser.parse_args()
    run(args.domain_id, args.verbose)


if __name__ == "__main__":
    main()
