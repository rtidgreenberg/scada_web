#include "MetaDataPlane.hpp"

namespace scada_select {

MetaDataPlane::MetaDataPlane(dds::sub::DataReader<PLC::MetaData> reader,
                              dds::pub::DataWriter<PLC::MetaData> writer)
    : reader_(std::move(reader)), writer_(std::move(writer)) {}

void MetaDataPlane::process() {
    // NOT_READ, any instance state -- forward each metadata sample exactly once
    // while leaving it in the cache (§4.4). Not DataState::new_data(), whose
    // ALIVE instance-state mask would filter out the invalid samples that carry
    // dispose and unregister, making the retraction path below unreachable.
    const dds::sub::status::DataState unread_any_instance(
        dds::sub::status::SampleState::not_read(),
        dds::sub::status::ViewState::any(),
        dds::sub::status::InstanceState::any());

    auto samples = reader_.select().state(unread_any_instance).read();

    for (const auto &s : samples) {
        if (s.info().valid()) {
            try_write(s.data());
            continue;
        }

        // A disposed/unregistered tag must retract from the catalogue too,
        // or scada-web's map keeps a tag the plant no longer has (§4.4).
        PLC::MetaData key_holder;
        reader_.key_value(key_holder, s.info().instance_handle());
        const dds::core::InstanceHandle out = writer_.lookup_instance(key_holder);
        if (out == dds::core::InstanceHandle::nil()) {
            continue;  // never forwarded -- nothing to retract
        }

        try {
            if (s.info().state().instance_state() ==
                dds::sub::status::InstanceState::not_alive_disposed()) {
                writer_.dispose_instance(out);
            } else {
                writer_.unregister_instance(out);
            }
        } catch (const dds::core::TimeoutError &) {
            ++write_timeouts_;
        }
    }
}

void MetaDataPlane::handle_metadata_request(std::int32_t uid) {
    PLC::MetaData key_holder;
    key_holder.uid = uid;

    const dds::core::InstanceHandle handle = reader_.lookup_instance(key_holder);
    if (handle == dds::core::InstanceHandle::nil()) {
        return;  // uid not (yet) in the catalogue
    }

    for (const auto &s : reader_.select().instance(handle).read()) {
        if (s.info().valid()) {
            try_write(s.data());
        }
    }
}

void MetaDataPlane::try_write(const PLC::MetaData &sample) {
    try {
        writer_.write(sample);
    } catch (const dds::core::TimeoutError &) {
        // §3.8 rule 2: log and count, never retry on the dispatch thread.
        // scada-web can re-ask for a catalogue entry it did not get.
        ++write_timeouts_;
    }
}

}  // namespace scada_select
