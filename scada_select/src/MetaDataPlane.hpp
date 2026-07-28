// MetaDataPlane -- forwards the field-side PLC::MetaData catalogue,
// unmodified and unfiltered by selection, to PLC::SelectedMetaData
// (scada-select-architecture.md §4.4).
//
// Uses read(), never take(): the reader cache IS the catalogue, and taking
// would empty it, breaking both restart recovery and the METADATA command.
#pragma once

#include <cstdint>

#include <dds/dds.hpp>

#include "PlcValue.hpp"

namespace scada_select {

class MetaDataPlane {
public:
    MetaDataPlane(dds::sub::DataReader<PLC::MetaData> reader,
                  dds::pub::DataWriter<PLC::MetaData> writer);

    // Forward every newly-arrived metadata sample, unmodified. Runs at
    // startup and whenever the sim publishes/disposes a tag -- not a
    // per-sample hot path, so simplicity is preferred over cleverness here.
    void process();

    // Service Command_t::METADATA for one uid (§4.2): re-read that instance
    // from the field-side reader cache and republish it. No sentinel "all"
    // uid in the PoC (DD-039) -- the configured uid range is forwarded
    // unconditionally by process() as it arrives from the sim, so a full
    // bootstrap request is not needed yet.
    void handle_metadata_request(std::int32_t uid);

    // Outbound writes dropped after hitting the writer's max_blocking_time
    // (§3.8). main() reports the count.
    std::uint64_t write_timeouts() const { return write_timeouts_; }

private:
    // Write one catalogue sample, counting rather than propagating a timeout.
    void try_write(const PLC::MetaData &sample);

    dds::sub::DataReader<PLC::MetaData> reader_;
    dds::pub::DataWriter<PLC::MetaData> writer_;
    std::uint64_t write_timeouts_{0};
};

}  // namespace scada_select
