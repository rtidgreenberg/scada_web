// DataPlane -- the hot path: PLC::IdValue reader -> decimate -> PLC::IdValue
// (SelectedValue topic) writer (scada-select-architecture.md §4.3).
//
// Same type in and out -- Role 1 makes no model changes (DD-024). Decimates
// on arrival using SelectionTable; lifecycle events (dispose/unregister)
// bypass the rate limit unconditionally (§3.4).
#pragma once

#include <cstdint>

#include <dds/dds.hpp>

#include "PlcValue.hpp"
#include "SelectionTable.hpp"

namespace scada_select {

class DataPlane {
public:
    DataPlane(SelectionTable &table,
              dds::sub::DataReader<PLC::IdValue> reader,
              dds::pub::DataWriter<PLC::IdValue> writer);

    // Drain and process all newly-available samples on the value reader.
    // Must not block -- runs on the WaitSet dispatch thread (§3.5).
    void process();

    // Outbound writes dropped after hitting the writer's max_blocking_time.
    // Loss on the web side is invisible to the receiver, so the selector has
    // to count what it failed to write (§3.8).
    std::uint64_t write_timeouts() const { return write_timeouts_; }

private:
    void forward_lifecycle(const dds::sub::SampleInfo &info,
                            const PLC::IdValue &key_holder);

    SelectionTable &table_;
    dds::sub::DataReader<PLC::IdValue> reader_;
    dds::pub::DataWriter<PLC::IdValue> writer_;
    std::uint64_t write_timeouts_{0};
};

}  // namespace scada_select
