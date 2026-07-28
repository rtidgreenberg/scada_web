// scada-selector -- Role 1: selection and the hard-RT/soft-RT boundary
// (scada-select-architecture.md). Entity wiring, CLI, signal handling, and
// the WaitSet dispatch loop. All decision logic lives in SelectionTable,
// ControlPlane, DataPlane, and MetaDataPlane -- this file only wires them to
// DDS entities.
#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <thread>

#include <dds/dds.hpp>

#include "ControlPlane.hpp"
#include "DataPlane.hpp"
#include "MetaDataPlane.hpp"
#include "PlcValue.hpp"
#include "SelectionTable.hpp"

namespace {

// Signal handling must be async-signal-safe -- a plain flag, set and polled,
// nothing more (scada-select-architecture.md §3.5).
volatile std::sig_atomic_t g_running = 1;

void handle_signal(int) {
    g_running = 0;
}

struct Options {
    std::int32_t field_domain = PLC::FIELD_DOMAIN_ID;
    std::int32_t web_domain = PLC::PRESENTATION_DOMAIN_ID;
    std::string qos_file = "../dds/qos/profiles.xml";
    std::string value_topic = "PLC::IdValueTopic";
    std::string metadata_topic = "PLC::MetaDataTopic";
    std::string selected_value_topic = "PLC::SelectedValueTopic";
    std::string selected_metadata_topic = "PLC::SelectedMetaDataTopic";
    std::string request_topic = "PLC::ValueRequestTopic";
    // DD-039: PoC pre-enables a fixed uid range at startup instead of
    // waiting for a dynamic catalogue bootstrap.
    std::int32_t uid_range_low = 100;
    std::int32_t uid_range_high = 500;
    std::uint32_t default_min_separation_ms = 250;
};

bool parse_int(const char *arg, std::int64_t &out) {
    char *end = nullptr;
    out = std::strtoll(arg, &end, 10);
    return end != arg && *end == '\0';
}

Options parse_args(int argc, char **argv) {
    Options opts;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        const bool has_next = i + 1 < argc;
        std::int64_t value = 0;

        if (arg == "--field-domain" && has_next && parse_int(argv[++i], value)) {
            opts.field_domain = static_cast<std::int32_t>(value);
        } else if (arg == "--web-domain" && has_next && parse_int(argv[++i], value)) {
            opts.web_domain = static_cast<std::int32_t>(value);
        } else if (arg == "--qos-file" && has_next) {
            opts.qos_file = argv[++i];
        } else if (arg == "--uid-range-low" && has_next && parse_int(argv[++i], value)) {
            opts.uid_range_low = static_cast<std::int32_t>(value);
        } else if (arg == "--uid-range-high" && has_next && parse_int(argv[++i], value)) {
            opts.uid_range_high = static_cast<std::int32_t>(value);
        } else if (arg == "--min-separation-ms" && has_next && parse_int(argv[++i], value)) {
            opts.default_min_separation_ms = static_cast<std::uint32_t>(value);
        } else {
            std::cerr << "scada_selector: unrecognized or malformed argument: " << arg
                      << "\n";
            std::exit(EXIT_FAILURE);
        }
    }
    return opts;
}

}  // namespace

int main(int argc, char **argv) {
    const Options opts = parse_args(argc, argv);

    std::signal(SIGINT, handle_signal);
    std::signal(SIGTERM, handle_signal);

    dds::domain::DomainParticipant field_participant(opts.field_domain);
    dds::domain::DomainParticipant presentation_participant(opts.web_domain);

    dds::sub::Subscriber field_subscriber(field_participant);
    dds::sub::Subscriber presentation_subscriber(presentation_participant);
    dds::pub::Publisher presentation_publisher(presentation_participant);

    dds::core::QosProvider qos_provider("file://" + opts.qos_file);

    // --- Field side (hard real time) ---
    dds::topic::Topic<PLC::IdValue> value_topic(field_participant, opts.value_topic);
    dds::sub::DataReader<PLC::IdValue> value_reader(
        field_subscriber, value_topic, qos_provider.datareader_qos("field::idvalue"));

    dds::topic::Topic<PLC::MetaData> metadata_topic(field_participant,
                                                      opts.metadata_topic);
    dds::sub::DataReader<PLC::MetaData> metadata_reader(
        field_subscriber, metadata_topic, qos_provider.datareader_qos("field::metadata"));

    // --- Web side (soft real time) ---
    dds::topic::Topic<PLC::ValueRequest> request_topic(presentation_participant,
                                                         opts.request_topic);
    dds::sub::DataReader<PLC::ValueRequest> request_reader(
        presentation_subscriber, request_topic,
        qos_provider.datareader_qos("presentation::value_request"));

    dds::topic::Topic<PLC::IdValue> selected_value_topic(presentation_participant,
                                                           opts.selected_value_topic);
    dds::pub::DataWriter<PLC::IdValue> selected_value_writer(
        presentation_publisher, selected_value_topic,
        qos_provider.datawriter_qos("presentation::selected_value"));

    dds::topic::Topic<PLC::MetaData> selected_metadata_topic(
        presentation_participant, opts.selected_metadata_topic);
    dds::pub::DataWriter<PLC::MetaData> selected_metadata_writer(
        presentation_publisher, selected_metadata_topic,
        qos_provider.datawriter_qos("presentation::selected_metadata"));

    // --- Decision logic (DDS-free) and planes ---
    scada_select::SelectionTable table(opts.default_min_separation_ms);
    table.add_range(opts.uid_range_low, opts.uid_range_high);  // DD-039

    scada_select::MetaDataPlane metadata_plane(metadata_reader, selected_metadata_writer);
    scada_select::DataPlane data_plane(table, value_reader, selected_value_writer);
    scada_select::ControlPlane control_plane(
        table, [&metadata_plane](std::int32_t uid) {
            metadata_plane.handle_metadata_request(uid);
        });

    std::cerr << "scada_selector: field domain " << opts.field_domain
              << ", web domain " << opts.web_domain << ", uid range ["
              << opts.uid_range_low << ", " << opts.uid_range_high
              << "], min separation " << opts.default_min_separation_ms << "ms\n";

    // --- WaitSet, order: control, metadata, data (§4.1) ---
    dds::sub::cond::ReadCondition request_ready(
        request_reader, dds::sub::status::DataState::any(), [&]() {
            for (const auto &s : request_reader.take()) {
                if (s.info().valid()) {
                    control_plane.handle(s.data());
                }
            }
        });

    dds::sub::cond::ReadCondition metadata_ready(
        metadata_reader, dds::sub::status::DataState::new_data(),
        [&]() { metadata_plane.process(); });

    dds::sub::cond::ReadCondition value_ready(
        value_reader, dds::sub::status::DataState::new_data(),
        [&]() { data_plane.process(); });

    dds::core::cond::WaitSet waitset;
    waitset += request_ready;
    waitset += metadata_ready;
    waitset += value_ready;

    while (g_running) {
        // Phase 1: drain control explicitly, before dispatch (DD-041).
        // WaitSet::dispatch() does not guarantee handler order when multiple
        // conditions trigger together, so this makes control-before-data
        // deterministic regardless of that.
        for (const auto &s : request_reader.take()) {
            if (s.info().valid()) {
                control_plane.handle(s.data());
            }
        }

        // Phase 2: dispatch metadata and data (+ any control that arrived
        // mid-phase-1, via request_ready above -- harmless, since taking an
        // already-drained reader is a no-op).
        waitset.dispatch(dds::core::Duration::from_millisecs(100));

        // DD-042: make inbound cache overflow visible rather than silent.
        const auto lost = value_reader.sample_lost_status();
        if (lost.total_count_change() > 0) {
            std::cerr << "scada_selector: " << lost.total_count_change()
                      << " sample(s) lost on field IdValue reader (total "
                      << lost.total_count() << ")\n";
        }
    }

    std::cerr << "scada_selector: shutting down\n";
    return 0;
}
