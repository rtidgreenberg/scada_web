// ControlPlane -- turns PLC::ValueRequest commands into SelectionTable
// mutations (scada-select-architecture.md §4.2).
//
// Depends on SelectionTable directly. Depends on MetaDataPlane only through a
// callback for the METADATA command -- not a shared table -- per the
// acyclic dependency flow in scada-select-architecture.md §2.1.
#pragma once

#include <functional>

#include "PlcValue.hpp"
#include "SelectionTable.hpp"

namespace scada_select {

class ControlPlane {
public:
    // Invoked for Command_t::METADATA with the requested uid. Re-publishing
    // the metadata instance is the metadata plane's job, not this class's --
    // see scada-select-architecture.md §4.4.
    using MetadataRequestHandler = std::function<void(std::int32_t uid)>;

    ControlPlane(SelectionTable &table, MetadataRequestHandler on_metadata_request);

    // Process one ValueRequest sample. Only valid samples carry meaningful
    // commands -- ValueRequest has no @key, so instance lifecycle on this
    // topic is not selection intent and is ignored here.
    void handle(const PLC::ValueRequest &request);

private:
    SelectionTable &table_;
    MetadataRequestHandler on_metadata_request_;
};

}  // namespace scada_select
