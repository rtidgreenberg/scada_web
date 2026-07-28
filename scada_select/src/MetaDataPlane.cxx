#include "MetaDataPlane.hpp"

namespace scada_select {

MetaDataPlane::MetaDataPlane(dds::sub::DataReader<PLC::MetaData> reader,
                              dds::pub::DataWriter<PLC::MetaData> writer)
    : reader_(std::move(reader)), writer_(std::move(writer)) {}

void MetaDataPlane::process() {
    // NOT_READ, ALIVE -- forward each metadata sample exactly once while
    // leaving it in the cache (§4.4).
    auto samples =
        reader_.select().state(dds::sub::status::DataState::new_data()).read();

    for (const auto &s : samples) {
        if (s.info().valid()) {
            writer_.write(s.data());
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

        if (s.info().state().instance_state() ==
            dds::sub::status::InstanceState::not_alive_disposed()) {
            writer_.dispose_instance(out);
        } else {
            writer_.unregister_instance(out);
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
            writer_.write(s.data());
        }
    }
}

}  // namespace scada_select
