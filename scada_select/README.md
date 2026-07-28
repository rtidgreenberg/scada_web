# scada_select

Role 1 — **selection** (which tags flow, and how often) and **the system
boundary** (the only conduit between the hard-real-time field side and the
soft-real-time presentation side).

Standalone service in the Connext **Modern C++ API** (`dds::`, `cpp2_api`,
`rtiddsgen -language C++11`) at language level **C++17**, using **compiled** types
generated from
[`dds/idl/PlcValue.idl`](../dds/idl/PlcValue.idl). Subscribes to the full
`PLC::IdValue` stream, forwards only the uids scada-web has requested on
`PLC::ValueRequest`, at no more than the requested rate, on `PLC::SelectedValue`.
Also forwards `PLC::MetaData` unmodified to `PLC::SelectedMetaData` so that nothing
else has to cross the boundary. Same types in, same types out — it makes no model
changes, and holds no metadata map.

**Both sides are `RELIABLE`; what differs is the timing contract, not the
reliability kind** ([DD-029](../docs/design-decisions.md#dd-029)). The presentation
topics are `RELIABLE` + `TRANSIENT_LOCAL` + `KEEP_LAST 1` so a late-joining
scada-web receives the latest value and the whole catalogue per uid; inbound
`PLC::ValueRequest` adds `KEEP_ALL`, because operator intent is a command queue and
does not self-heal. Two invariants to preserve when editing this component
(architecture doc §3.8, §6):

- No soft-real-time congestion may reach the field side. With a `RELIABLE` output
  this is **maintained, not structural**: outbound `KEEP_LAST` (never `KEEP_ALL`)
  plus an explicitly unlimited reliable send window are what prevent it, and a short
  `max_blocking_time` with a counted, never-retried timeout is the backstop. A
  nonzero write-timeout count means one of those has been broken.
- The tag catalogue crosses by **durability**, which is sound only because both ends
  are `RELIABLE`. `Command_t::METADATA` re-reads a single uid on demand; it is not
  the bootstrap path, and there is no sentinel "all" uid.

**Status:** implemented and integration-tested (sim → selector → presentation
domain); `SelectionTable` has unit tests, the DDS planes do not yet.
Architecture: [docs/scada-select-architecture.md](docs/scada-select-architecture.md).
Verified build configuration and hot-path code:
[docs/scada-selector-implementation.md](docs/scada-selector-implementation.md).

Build and run (defaults assume this working directory):

```sh
mkdir -p build && cd build
cmake .. && make          # fetches yaml-cpp 0.8.0 if no system copy is present
./scada_selector --help
```

The docs refer to this component as **scada-selector**; this directory uses the
short form.
