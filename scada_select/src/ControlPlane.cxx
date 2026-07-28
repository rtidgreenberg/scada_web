#include "ControlPlane.hpp"

namespace scada_select {

ControlPlane::ControlPlane(SelectionTable &table, MetadataRequestHandler on_metadata_request)
    : table_(table), on_metadata_request_(std::move(on_metadata_request)) {}

void ControlPlane::handle(const PLC::ValueRequest &request) {
    switch (request._d()) {
        case PLC::Command_t::ADD:
            table_.add(request.addRequest().uid);
            break;
        case PLC::Command_t::DELETE:
            table_.erase(request.uid());
            break;
        case PLC::Command_t::METADATA:
            if (on_metadata_request_) {
                on_metadata_request_(request.uid());
            }
            break;
        case PLC::Command_t::PERIOD:
            // period_ms == 0 restores the selector's startup default --
            // SelectionTable::set_period implements that, and deliberately
            // does not let 0 mean "full field rate".
            table_.set_period(request.periodRequest().period_ms);
            break;
    }
}

}  // namespace scada_select
