# scada_select

Role 1 — **selection**: which tags flow, and how often.

Standalone service in the Connext **Modern C++ API** (`dds::`, `cpp2_api`,
`rtiddsgen -language C++11`) at language level **C++17**, using **compiled** types
generated from
[`../sim/PlcValue.idl`](../sim/PlcValue.idl). Subscribes to the full
`PLC::IdValue` stream, forwards only the uids scada-web has requested on
`PLC::ValueRequest`, at no more than the requested rate, on `PLC::SelectedValue`.
Same type in, same type out — it makes no model changes.

**Status:** not started. Architecture and planned layout:
[docs/scada-select-architecture.md](docs/scada-select-architecture.md).
Verified build configuration and hot-path code:
[docs/scada-selector-implementation.md](docs/scada-selector-implementation.md).

The docs refer to this component as **scada-selector**; this directory uses the
short form.
