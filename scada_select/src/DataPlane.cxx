#include "DataPlane.hpp"

namespace scada_select {

DataPlane::DataPlane(SelectionTable &table,
                      dds::sub::DataReader<PLC::IdValue> reader,
                      dds::pub::DataWriter<PLC::IdValue> writer)
    : table_(table), reader_(std::move(reader)), writer_(std::move(writer)) {}

void DataPlane::process() {
    const auto now = SelectionTable::Clock::now();

    for (const auto &s : reader_.take()) {
        PLC::IdValue key_holder;
        std::int32_t uid;

        if (s.info().valid()) {
            uid = s.data().uid;
        } else {
            // Invalid samples carry only the key -- recover uid via
            // key_value() rather than reading a payload that has none
            // (scada-select-architecture.md §3.4).
            reader_.key_value(key_holder, s.info().instance_handle());
            uid = key_holder.uid;
        }

        if (!table_.contains(uid)) {
            continue;  // not selected
        }

        if (!s.info().valid()) {
            // Lifecycle events are forwarded unconditionally -- never rate
            // limited (§3.4).
            forward_lifecycle(s.info(), key_holder);
            continue;
        }

        if (table_.should_forward(uid, now)) {
            writer_.write(s.data());
        }
    }
}

void DataPlane::forward_lifecycle(const dds::sub::SampleInfo &info,
                                   const PLC::IdValue &key_holder) {
    const dds::core::InstanceHandle out = writer_.lookup_instance(key_holder);
    if (out == dds::core::InstanceHandle::nil()) {
        // Never forwarded a sample for this uid -- nothing displayed to
        // retract, and disposing a nil handle throws (§3.4).
        return;
    }

    if (info.state().instance_state() ==
        dds::sub::status::InstanceState::not_alive_disposed()) {
        writer_.dispose_instance(out);
    } else {
        writer_.unregister_instance(out);
    }
}

}  // namespace scada_select
