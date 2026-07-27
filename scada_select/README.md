# scada_select

Role 1 — **selection** (which tags flow, and how often) and **the system
boundary** (the only conduit between the hard-real-time field side and the
soft-real-time presentation side).

Standalone service in the Connext **Modern C++ API** (`dds::`, `cpp2_api`,
`rtiddsgen -language C++11`) at language level **C++17**, using **compiled** types
generated from
[`../sim/PlcValue.idl`](../sim/PlcValue.idl). Subscribes to the full
`PLC::IdValue` stream, forwards only the uids scada-web has requested on
`PLC::ValueRequest`, at no more than the requested rate, on `PLC::SelectedValue`.
Also forwards `PLC::MetaData` unmodified to `PLC::SelectedMetaData` so that nothing
else has to cross the boundary. Same types in, same types out — it makes no model
changes, and holds no metadata map.

No soft-real-time congestion may reach the field side: outbound writers are
`KEEP_LAST`, never `KEEP_ALL`. That is the one invariant to preserve when editing
this component — see the architecture doc §3.8.

**Status:** not started. Architecture and planned layout:
[docs/scada-select-architecture.md](docs/scada-select-architecture.md).
Verified build configuration and hot-path code:
[docs/scada-selector-implementation.md](docs/scada-selector-implementation.md).

The docs refer to this component as **scada-selector**; this directory uses the
short form.
