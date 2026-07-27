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
    python3 sim/plc_test_subscriber.py --domain-id 0
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rti.connextdds as dds

from field_simulation import build_tags
from plc_types import build_plc_types, get_value_t

ID_VALUE_TOPIC = "PLC::IdValue"

RATE_LIMIT_S = 5.0
POLL_PERIOD_S = 0.1


def _id_value_reader_qos(participant: dds.DomainParticipant) -> dds.DataReaderQos:
    # Matches plc_publisher.py's writer QoS so it's compatible/reliable.
    qos = participant.default_datareader_qos
    qos.reliability.kind = dds.ReliabilityKind.RELIABLE
    qos.durability.kind = dds.DurabilityKind.VOLATILE
    qos.history.kind = dds.HistoryKind.KEEP_LAST
    qos.history.depth = 1
    return qos


def run(domain_id: int) -> None:
    tag_names = {tag.uid: tag.name for tag in build_tags()}
    types = build_plc_types()

    participant = dds.DomainParticipant(domain_id)
    subscriber = dds.Subscriber(participant)

    id_value_topic = dds.DynamicData.Topic(participant, ID_VALUE_TOPIC, types.id_value)
    id_value_reader = dds.DynamicData.DataReader(
        subscriber, id_value_topic, _id_value_reader_qos(participant)
    )

    print(
        f"Listening for '{ID_VALUE_TOPIC}' on domain {domain_id}, printing at "
        f"most once every {RATE_LIMIT_S:.0f}s per uid (Ctrl+C to stop)."
    )

    last_printed: dict = {}

    try:
        while True:
            for sample, info in id_value_reader.take():
                if not info.valid:
                    continue

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

            time.sleep(POLL_PERIOD_S)
    except KeyboardInterrupt:
        print("\nStopping test subscriber.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain-id", type=int, default=0, help="DDS domain ID")
    args = parser.parse_args()
    run(args.domain_id)


if __name__ == "__main__":
    main()
