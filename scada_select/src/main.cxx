// scada-selector -- Role 1: selection and the hard-RT/soft-RT boundary
// (scada-select-architecture.md). Entity wiring, CLI, signal handling, and
// the WaitSet dispatch loop. All decision logic lives in SelectionTable,
// ControlPlane, DataPlane, and MetaDataPlane -- this file only wires them to
// DDS entities.
#include <chrono>
#include <csignal>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>

#include <dds/dds.hpp>

#include "Config.hpp"
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

// NOT_READ + any view state + ANY instance state.
//
// Deliberately not DataState::new_data(), which masks instance state to ALIVE
// and therefore hides every lifecycle event: a ReadCondition built on it never
// wakes for a dispose or unregister, and a read()/take() filtered by it never
// returns the invalid sample that carries one. Retractions would then reach
// scada-web only by accident -- when live data for some other instance happened
// to arrive in the same batch (§3.4, §4.4).
const dds::sub::status::DataState kUnreadAnyInstance(
    dds::sub::status::SampleState::not_read(),
    dds::sub::status::ViewState::any(),
    dds::sub::status::InstanceState::any());

// A pre-enabled range is PoC scaffolding (DD-039), not a production selection
// mechanism: cap it so a fat-fingered flag cannot ask for millions of entries.
constexpr std::int64_t kMaxUidRangeSize = 100000;

struct Options {
    // Both defaults are relative to scada_select/build, the directory the
    // binary is built and run from. A path read out of config.yaml is resolved
    // relative to the config file instead, so that file works from any cwd.
    std::string config_file = "../config.yaml";
    std::int32_t field_domain = PLC::FIELD_DOMAIN_ID;
    std::int32_t web_domain = PLC::PRESENTATION_DOMAIN_ID;
    std::string qos_file = "../../dds/qos/profiles.xml";
    // Topic names come from the IDL constants, never from string literals
    // here: dds/idl/PlcValue.idl is the single source of truth for the wire
    // contract, and these are the same constants scada-web's XML type library
    // is generated from (DD-043).
    std::string value_topic{PLC::IdValueTopic};
    std::string metadata_topic{PLC::MetaDataTopic};
    std::string selected_value_topic{PLC::SelectedValueTopic};
    std::string selected_metadata_topic{PLC::SelectedMetaDataTopic};
    std::string request_topic{PLC::ValueRequestTopic};
    // DD-039: PoC pre-enables a fixed uid range at startup instead of
    // waiting for a dynamic catalogue bootstrap.
    std::int32_t uid_range_low = 100;
    std::int32_t uid_range_high = 500;
    std::uint32_t default_min_separation_ms = 250;
    // 0 = errors only, 1 = startup banner and periodic counters, 2 = also log
    // every ValueRequest command as it is handled.
    int verbosity = 1;
};

// Which flags the operator actually typed, so config.yaml fills in only what
// the command line left alone (precedence: built-in < YAML < flag).
struct ParsedArgs {
    Options opts;
    std::set<std::string> seen;
};

void print_usage() {
    std::cerr
        << "scada_selector -- SCADA selection and the field/presentation boundary\n"
           "\n"
           "Usage: scada_selector [options]\n"
           "\n"
           "  --config PATH                   YAML startup defaults "
           "(default: ../config.yaml)\n"
           "  --field-domain ID               field domain "
           "(default: PLC::FIELD_DOMAIN_ID)\n"
           "  --web-domain ID                 presentation domain "
           "(default: PLC::PRESENTATION_DOMAIN_ID)\n"
           "  --qos-file PATH                 QoS profiles XML "
           "(default: ../../dds/qos/profiles.xml)\n"
           "  --value-topic NAME              field value topic\n"
           "  --metadata-topic NAME           field catalogue topic\n"
           "  --selected-topic NAME           forwarded value topic\n"
           "  --selected-metadata-topic NAME  forwarded catalogue topic\n"
           "  --request-topic NAME            inbound command topic\n"
           "  --uid-range-low N               first pre-enabled uid (DD-039)\n"
           "  --uid-range-high N              last pre-enabled uid, inclusive\n"
           "  --min-separation-ms MS          startup minimum separation per uid\n"
           "  --verbosity N                   0 errors, 1 default, 2 per-command\n"
           "  --help                          print this and exit\n"
           "\n"
           "Topic name defaults are the constants in dds/idl/PlcValue.idl.\n";
}

bool parse_int(const char *arg, std::int64_t &out) {
    char *end = nullptr;
    out = std::strtoll(arg, &end, 10);
    return end != arg && *end == '\0';
}

ParsedArgs parse_args(int argc, char **argv) {
    ParsedArgs parsed;
    Options &opts = parsed.opts;

    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        const bool has_next = i + 1 < argc;
        std::int64_t value = 0;

        if (arg == "--help" || arg == "-h") {
            print_usage();
            std::exit(EXIT_SUCCESS);
        } else if (arg == "--config" && has_next) {
            opts.config_file = argv[++i];
        } else if (arg == "--field-domain" && has_next && parse_int(argv[++i], value)) {
            opts.field_domain = static_cast<std::int32_t>(value);
        } else if (arg == "--web-domain" && has_next && parse_int(argv[++i], value)) {
            opts.web_domain = static_cast<std::int32_t>(value);
        } else if (arg == "--qos-file" && has_next) {
            opts.qos_file = argv[++i];
        } else if (arg == "--value-topic" && has_next) {
            opts.value_topic = argv[++i];
        } else if (arg == "--metadata-topic" && has_next) {
            opts.metadata_topic = argv[++i];
        } else if (arg == "--selected-topic" && has_next) {
            opts.selected_value_topic = argv[++i];
        } else if (arg == "--selected-metadata-topic" && has_next) {
            opts.selected_metadata_topic = argv[++i];
        } else if (arg == "--request-topic" && has_next) {
            opts.request_topic = argv[++i];
        } else if (arg == "--uid-range-low" && has_next && parse_int(argv[++i], value)) {
            opts.uid_range_low = static_cast<std::int32_t>(value);
        } else if (arg == "--uid-range-high" && has_next && parse_int(argv[++i], value)) {
            opts.uid_range_high = static_cast<std::int32_t>(value);
        } else if (arg == "--min-separation-ms" && has_next &&
                   parse_int(argv[++i], value)) {
            opts.default_min_separation_ms = static_cast<std::uint32_t>(value);
        } else if (arg == "--verbosity" && has_next && parse_int(argv[++i], value)) {
            opts.verbosity = static_cast<int>(value);
        } else {
            std::cerr << "scada_selector: unrecognized or malformed argument: " << arg
                      << "\n\n";
            print_usage();
            std::exit(EXIT_FAILURE);
        }
        parsed.seen.insert(arg);
    }
    return parsed;
}

// YAML supplies only what the command line did not.
void apply_file_config(ParsedArgs &parsed) {
    const bool explicit_config = parsed.seen.count("--config") != 0;
    const scada_select::FileConfig file =
        scada_select::load_file_config(parsed.opts.config_file, explicit_config);
    if (!file.found) {
        return;
    }

    Options &opts = parsed.opts;
    if (file.has_qos_profiles && parsed.seen.count("--qos-file") == 0) {
        opts.qos_file = file.qos_profiles;
    }
    if (file.has_min_separation && parsed.seen.count("--min-separation-ms") == 0) {
        opts.default_min_separation_ms = file.default_min_separation_ms;
    }
    if (file.has_uid_range_low && parsed.seen.count("--uid-range-low") == 0) {
        opts.uid_range_low = file.uid_range_low;
    }
    if (file.has_uid_range_high && parsed.seen.count("--uid-range-high") == 0) {
        opts.uid_range_high = file.uid_range_high;
    }
}

// Rejects configurations that would otherwise fail late, obscurely, or not at
// all: an inverted range silently selects nothing, and an unbounded one walks
// the int32 space building a hash node per uid.
void validate(const Options &opts) {
    if (opts.uid_range_low > opts.uid_range_high) {
        throw std::runtime_error(
            "uid range is inverted: low " + std::to_string(opts.uid_range_low) +
            " > high " + std::to_string(opts.uid_range_high));
    }
    const std::int64_t span = static_cast<std::int64_t>(opts.uid_range_high) -
                              static_cast<std::int64_t>(opts.uid_range_low) + 1;
    if (span > kMaxUidRangeSize) {
        throw std::runtime_error("uid range spans " + std::to_string(span) +
                                 " uids, more than the " +
                                 std::to_string(kMaxUidRangeSize) + " maximum");
    }
    if (opts.verbosity < 0) {
        throw std::runtime_error("verbosity must be >= 0");
    }
}

const char *command_name(PLC::Command_t command) {
    switch (command) {
        case PLC::Command_t::ADD:      return "ADD";
        case PLC::Command_t::DELETE:   return "DELETE";
        case PLC::Command_t::METADATA: return "METADATA";
        case PLC::Command_t::PERIOD:   return "PERIOD";
    }
    return "UNKNOWN";
}

int run(const Options &opts) {
    std::signal(SIGINT, handle_signal);
    std::signal(SIGTERM, handle_signal);

    dds::domain::DomainParticipant field_participant(opts.field_domain);
    dds::domain::DomainParticipant presentation_participant(opts.web_domain);

    dds::sub::Subscriber field_subscriber(field_participant);
    dds::sub::Subscriber presentation_subscriber(presentation_participant);
    dds::pub::Publisher presentation_publisher(presentation_participant);

    // Connext's exceptions for a bad QoS URL carry an empty what(), so name the
    // file here or the operator gets "fatal:" and nothing else. The Connext
    // ERROR lines above it say what went wrong; this says what was being loaded.
    const std::string qos_url = "file://" + opts.qos_file;
    auto qos_provider = [&]() {
        try {
            return dds::core::QosProvider(qos_url);
        } catch (const std::exception &) {
            throw std::runtime_error("cannot load QoS profiles from " + qos_url);
        }
    }();

    // --- Field side (hard real time) ---
    dds::topic::Topic<PLC::IdValue> value_topic(field_participant, opts.value_topic);
    dds::sub::DataReader<PLC::IdValue> value_reader(
        field_subscriber, value_topic, qos_provider.datareader_qos("field::idvalue"));

    dds::topic::Topic<PLC::MetaData> metadata_topic(field_participant,
                                                      opts.metadata_topic);
    dds::sub::DataReader<PLC::MetaData> metadata_reader(
        field_subscriber, metadata_topic,
        qos_provider.datareader_qos("field::metadata"));

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

    scada_select::MetaDataPlane metadata_plane(metadata_reader,
                                                selected_metadata_writer);
    scada_select::DataPlane data_plane(table, value_reader, selected_value_writer);
    scada_select::ControlPlane control_plane(
        table, [&metadata_plane](std::int32_t uid) {
            metadata_plane.handle_metadata_request(uid);
        });

    if (opts.verbosity >= 1) {
        std::cerr << "scada_selector: field domain " << opts.field_domain
                  << ", web domain " << opts.web_domain << ", uid range ["
                  << opts.uid_range_low << ", " << opts.uid_range_high
                  << "], min separation " << opts.default_min_separation_ms << "ms\n";
    }

    // Both the phase-1 drain and the request ReadCondition run this, so the
    // two paths cannot drift apart.
    const auto drain_requests = [&]() {
        for (const auto &s : request_reader.take()) {
            if (!s.info().valid()) {
                continue;  // ValueRequest is unkeyed; lifecycle is not intent
            }
            if (opts.verbosity >= 2) {
                std::cerr << "scada_selector: command "
                          << command_name(s.data()._d()) << "\n";
            }
            control_plane.handle(s.data());
        }
    };

    // --- WaitSet, order: control, metadata, data (§4.1) ---
    dds::sub::cond::ReadCondition request_ready(
        request_reader, dds::sub::status::DataState::any(), drain_requests);

    dds::sub::cond::ReadCondition metadata_ready(
        metadata_reader, kUnreadAnyInstance, [&]() { metadata_plane.process(); });

    dds::sub::cond::ReadCondition value_ready(
        value_reader, kUnreadAnyInstance, [&]() { data_plane.process(); });

    dds::core::cond::WaitSet waitset;
    waitset += request_ready;
    waitset += metadata_ready;
    waitset += value_ready;

    std::int64_t reported_replaced = 0;
    std::uint64_t reported_write_timeouts = 0;

    while (g_running) {
        // Phase 1: drain control explicitly, before dispatch (DD-041).
        // WaitSet::dispatch() does not guarantee handler order when multiple
        // conditions trigger together, so this makes control-before-data
        // deterministic regardless of that.
        drain_requests();

        // Phase 2: dispatch metadata and data (+ any control that arrived
        // mid-phase-1, via request_ready above -- harmless, since taking an
        // already-drained reader is a no-op).
        waitset.dispatch(dds::core::Duration::from_millisecs(100));

        if (opts.verbosity < 1) {
            continue;
        }

        // DD-042: make it visible when the selector cannot keep up with the
        // field stream. replaced_dropped_sample_count is the counter that
        // actually moves here -- KEEP_LAST replacement of a still-unread
        // sample is neither a lost sample nor a rejected one, so
        // sample_lost_status alone reports nothing. Keep both: SAMPLE_LOST
        // still catches writer-side loss, which this counter does not see.
        const std::int64_t replaced = value_reader.extensions()
                                          .datareader_cache_status()
                                          .replaced_dropped_sample_count();
        if (replaced > reported_replaced) {
            std::cerr << "scada_selector: " << (replaced - reported_replaced)
                      << " unread field IdValue sample(s) overwritten before the "
                         "selector read them (total "
                      << replaced << ")\n";
            reported_replaced = replaced;
        }

        const auto lost = value_reader.sample_lost_status();
        if (lost.total_count_change() > 0) {
            std::cerr << "scada_selector: " << lost.total_count_change()
                      << " sample(s) lost on field IdValue reader (total "
                      << lost.total_count() << ")\n";
        }

        // §3.8 rule 2: an outbound write that hits max_blocking_time is a
        // logged drop. The planes count them; this is where they surface.
        const std::uint64_t timeouts =
            data_plane.write_timeouts() + metadata_plane.write_timeouts();
        if (timeouts > reported_write_timeouts) {
            std::cerr << "scada_selector: " << (timeouts - reported_write_timeouts)
                      << " presentation write(s) timed out and were dropped (total "
                      << timeouts << ")\n";
            reported_write_timeouts = timeouts;
        }
    }

    if (opts.verbosity >= 1) {
        std::cerr << "scada_selector: shutting down\n";
    }
    return EXIT_SUCCESS;
}

}  // namespace

int main(int argc, char **argv) {
    // Every DDS entity constructor below can throw, and so can a bad QoS
    // profile name or an unparseable config file. Without this the operator
    // gets std::terminate and a core dump instead of the reason (§3.5).
    try {
        ParsedArgs parsed = parse_args(argc, argv);
        apply_file_config(parsed);
        validate(parsed.opts);
        return run(parsed.opts);
    } catch (const std::exception &e) {
        std::cerr << "scada_selector: fatal: " << e.what() << "\n";
        return EXIT_FAILURE;
    }
}
