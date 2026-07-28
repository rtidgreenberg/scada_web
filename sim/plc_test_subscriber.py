#!/usr/bin/env python3
"""Test subscriber for plc_publisher.py's `PLC::IdValue` topic.

Plain DDS test client (no Purdue-model role of its own) used to eyeball what
plc_publisher.py is putting on the wire without standing up the full
scada_web gateway. Every tag publishes on its own schedule (2 Hz down to
every 10 s, see plc_publisher.py's module docstring) so printing every
sample as it arrives is noisy; this subscriber instead rate-limits *console
output* per uid to at most once every RATE_LIMIT_S seconds, independent of
each tag's actual publish rate. Samples are still taken off the reader as
they arrive -- only the printing is throttled -- so no reader-side queue
build-up occurs for fast tags.

Usage:
    python3 sim/plc_test_subscriber.py --domain-id 15
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rti.connextdds as dds

from field_simulation import build_tags
from plc_types import build_plc_types, get_value_t

ID_VALUE_TOPIC = "PLC::IdValueTopic"
QOS_PROFILES_XML = str(Path(__file__).resolve().parent.parent / "dds" / "qos" / "profiles.xml")

RATE_LIMIT_S = 5.0
POLL_PERIOD_S = 0.1
RATE_REPORT_PERIOD_S = 4.0


def _id_value_reader_qos() -> dds.DataReaderQos:
    provider = dds.QosProvider(QOS_PROFILES_XML)
    return provider.datareader_qos_from_profile("field::idvalue")


def run(domain_id: int) -> None:
    tag_names = {tag.uid: tag.name for tag in build_tags()}
    types = build_plc_types()

    participant = dds.DomainParticipant(domain_id)
    subscriber = dds.Subscriber(participant)

    id_value_topic = dds.DynamicData.Topic(participant, ID_VALUE_TOPIC, types.id_value)
    id_value_reader = dds.DynamicData.DataReader(
        subscriber, id_value_topic, _id_value_reader_qos()
    )

    print(
        f"Listening for '{ID_VALUE_TOPIC}' on domain {domain_id}, printing at "
        f"most once every {RATE_LIMIT_S:.0f}s per uid (Ctrl+C to stop)."
    )

    last_printed: dict = {}

    sample_count = 0
    last_rate_report = time.monotonic()

    try:
        while True:
            for sample, info in id_value_reader.take():
                if not info.valid:
                    continue

                sample_count += 1

                uid = sample["uid"]
                now = time.monotonic()
                if now - last_printed.get(uid, float("-inf")) < RATE_LIMIT_S:
                    continue
                last_printed[uid] = now

                _, raw = get_value_t(sample, "rawValue")
                _, smoothed = get_value_t(sample, "smoothedValue")
                name = tag_names.get(uid, "?")
                print(
                    f"  uid={uid:<4} {name:<20} raw={raw:.2f} smoothed={smoothed:.2f} "
                    f"valueTime={sample['valueTime']}"
                )

            now = time.monotonic()
            elapsed = now - last_rate_report
            if elapsed >= RATE_REPORT_PERIOD_S:
                rate = sample_count / elapsed
                print(f"[rate] {rate:.1f} samples/s (avg over last {elapsed:.1f}s)")
                sample_count = 0
                last_rate_report = now

            time.sleep(POLL_PERIOD_S)
    except KeyboardInterrupt:
        print("\nStopping test subscriber.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain-id", type=int, default=15,
                        help="DDS domain ID (default: PLC::FIELD_DOMAIN_ID)")
    args = parser.parse_args()
    run(args.domain_id)


if __name__ == "__main__":
    main()
