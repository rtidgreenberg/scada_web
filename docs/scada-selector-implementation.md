# scada-selector — Implementation Notes

**Status:** Draft v0.1 — build configuration and hot-path patterns
**Date:** 2026-07-27
**Scope:** how compiled types are wired into scada-selector's readers and writers.

Companion to [system-architecture.md](system-architecture.md) §1a (Role 1) and
[DD-026](design-decisions.md#dd-026) (compiled types, standalone).

> Everything in §1–§3 was **verified by building and running it** against the
> local Connext 7.7.0 install, not taken from documentation. §4 is documented
> behavior with sources.

---

## 1. Build integration

Generate types from `PlcValue.idl` at build time with RTI's own CMake modules —
not a hand-rolled `add_custom_command`.

```cmake
cmake_minimum_required(VERSION 3.16)
project(scada_selector LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)          # DD-006
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CONNEXTDDS_DIR AND DEFINED ENV{NDDSHOME})
    set(CONNEXTDDS_DIR "$ENV{NDDSHOME}")
endif()
list(APPEND CMAKE_MODULE_PATH "${CONNEXTDDS_DIR}/resource/cmake")

find_package(RTIConnextDDS 7.7.0 REQUIRED COMPONENTS core)
include(ConnextDdsCodegen)

connextdds_rtiddsgen_run(
    IDL_FILE         "${CMAKE_CURRENT_SOURCE_DIR}/idl/PlcValue.idl"
    LANG             "C++11"
    OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/generated"
    VAR              plc
)

add_executable(scada_selector
    src/main.cxx
    ${plc_CXX11_SOURCES}
    ${plc_CXX11_HEADERS}
)
target_include_directories(scada_selector PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated")
target_link_libraries(scada_selector PRIVATE RTIConnextDDS::cpp2_api)
```

Configure with:

```bash
cmake -S . -B build \
  -DCONNEXTDDS_DIR=/home/rti/rti_connext_dds-7.7.0 \
  -DCONNEXTDDS_ARCH=x64Linux4gcc7.3.0 \
  -DBUILD_SHARED_LIBS=ON \
  -DCMAKE_BUILD_TYPE=Release
```

Three details that cost time if guessed:

- **`VAR plc` produces `${plc_CXX11_SOURCES}` / `${plc_CXX11_HEADERS}`.** The
  helper takes a single `VAR` prefix and appends `_<LANG>_SOURCES`, with `+`
  replaced by `X` (`C++11` → `CXX11`). It is *not* `GENERATED_SOURCES_VAR`.
- **`CONNEXTDDS_ARCH` is `x64Linux4gcc7.3.0`** — the core libraries under
  `lib/`. The `x64Linux4gcc8.5.0` directory that also exists in this install is
  under `resource/app/lib` and holds the bundled *services*, not the core API.
  Using it fails at link, not at configure.
- **`BUILD_SHARED_LIBS=ON`** — without it `FindRTIConnextDDS` resolves the static
  variant and fails with `libnddscpp2_release_static-NOTFOUND`.

At runtime, `LD_LIBRARY_PATH` must include
`${CONNEXTDDS_DIR}/lib/x64Linux4gcc7.3.0`.

---

## 2. Generated type shape — public members, not accessors

**rtiddsgen 4.7.0 generates plain aggregate structs with public data members**
for C++11:

```cpp
struct NDDSUSERDllExport IdValue {
    int32_t uid {};
    int64_t valueTime {};
    ::PLC::Value_t smoothedValue {};
    ::PLC::Value_t rawValue {};

    IdValue();
    IdValue(int32_t uid_, int64_t valueTime_,
            const ::PLC::Value_t &smoothedValue_, const ::PLC::Value_t &rawValue_);
};
```

So field access is `sample.data().uid`, **not** `sample.data().uid()`. Much
existing RTI example code and documentation shows the getter/setter style from
the older codegen, which does not apply here. `Command_t` becomes a scoped
`enum class`.

This is the concrete reason compiled types are faster than `DynamicData` for this
component: `s.data().uid` is a struct member load resolved at compile time, where
`dd.value<int32_t>("uid")` is a member lookup by name on every sample.

---

## 3. The selector core

Verified to compile, link, and run. Two readers, one writer, WaitSet-driven, with
control processed before data so a tag enabled in a batch is forwarded in the same
pass.

```cpp
#include <unordered_set>
#include <dds/dds.hpp>
#include "PlcValue.hpp"

dds::domain::DomainParticipant participant(0);
dds::sub::Subscriber subscriber(participant);
dds::pub::Publisher  publisher(participant);

// Control plane. RELIABLE + KEEP_ALL — DD-023.
dds::topic::Topic<PLC::ValueRequest> request_topic(participant, "PLC::ValueRequest");
dds::sub::qos::DataReaderQos request_qos = subscriber.default_datareader_qos();
request_qos << dds::core::policy::Reliability::Reliable()
            << dds::core::policy::History::KeepAll();
dds::sub::DataReader<PLC::ValueRequest> request_reader(subscriber, request_topic, request_qos);

// Data plane. Same type in and out — Role 1 makes no model changes.
dds::topic::Topic<PLC::IdValue> value_topic(participant, "PLC::IdValue");
dds::topic::Topic<PLC::IdValue> selected_topic(participant, "PLC::SelectedValue");
dds::sub::DataReader<PLC::IdValue> value_reader(subscriber, value_topic);
dds::pub::DataWriter<PLC::IdValue> selected_writer(publisher, selected_topic);

std::unordered_set<int32_t> enabled;

dds::sub::cond::ReadCondition request_ready(
    request_reader, dds::sub::status::DataState::any(),
    [&]() {
        for (const auto &s : request_reader.take()) {
            if (!s.info().valid()) continue;
            const PLC::ValueRequest &r = s.data();
            switch (r.command) {
                case PLC::Command_t::ADD:      enabled.insert(r.uid); break;
                case PLC::Command_t::DELETE:   enabled.erase(r.uid);  break;
                case PLC::Command_t::METADATA: /* separate path */    break;
            }
        }
    });

dds::sub::cond::ReadCondition value_ready(
    value_reader, dds::sub::status::DataState::new_data(),
    [&]() {
        for (const auto &s : value_reader.take()) {
            if (!s.info().valid()) continue;
            if (enabled.count(s.data().uid)) {
                selected_writer.write(s.data());
            }
        }
    });

dds::core::cond::WaitSet waitset;
waitset += request_ready;   // control first
waitset += value_ready;

while (running) {
    waitset.dispatch(dds::core::Duration::from_millisecs(100));
}
```

`reader.take()` returns `LoanedSamples<T>`, which is RAII — the loan returns when
the range goes out of scope. Do not retain references into it past that point.

---

## 4. What "efficient" actually buys here

Documented behavior, and mostly a list of things **not** to reach for. Sources in §5.

**`writer.write(sample.data())` is the right call, but it is not a zero-copy
hand-off.** The loan gives a `const T&` into the reader cache, so nothing is
copied into application memory — but the writer still serializes from that object
into its own path. There is no supported way to transfer a reader loan into a
writer.

**FlatData does not give a serialized-buffer passthrough.** It is worth
considering when payloads are large and only a few fields are read, but the typed
API has no documented "take the received bytes and republish them unchanged"
shortcut — a FlatData forwarder still reads a typed sample and writes a typed
sample. `IdValue` is on the order of 100 bytes, so this is not the lever.

**Zero Copy does not bridge the forwarder.** It can help the inbound hop and the
outbound hop independently, but the selector is still a subscriber on one and a
publisher on the other; there is no automatic path from an incoming shared-memory
sample to an outgoing one.

**Instance-based selection is the real optimization, if one is needed.** Because
`IdValue` is keyed on `uid`, `SampleInfo::instance_handle()` identifies the tag
with no payload access, and:

- `reader.lookup_instance(key_holder)` → handle for a known `uid`
- `reader.select().instance(handle).take()` → take one instance
- `reader.select().next_instance(prev).take()` → walk instances
- `reader.key_value(key_holder, handle)` → recover the key from a handle

Holding a set of *enabled instance handles* lets the decision be made from
`SampleInfo` alone.

**Benchmark before adopting it.** With compiled types the naive `s.data().uid`
check is already a struct member load. The instance-handle version adds a handle
map to maintain and a per-instance take loop, and may well be slower for a small
type. The measurement to run: naive predicate versus instance selection, at
realistic tag counts and rates, on the same machine — a relative comparison, which
is all NFR-PERF-001 asks for anyway.

---

## 5. Sources

- [`ConnextDdsCodegen.cmake`](file:///home/rti/rti_connext_dds-7.7.0/resource/cmake/ConnextDdsCodegen.cmake) — local install; `VAR` semantics read from the function body
- [`FindRTIConnextDDS.cmake`](file:///home/rti/rti_connext_dds-7.7.0/resource/cmake/FindRTIConnextDDS.cmake) — local install
- [DataReader (Modern C++)](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/api/connext_dds/api_cpp2/classdds_1_1sub_1_1DataReader.html)
- [LoanedSamples](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/api/connext_dds/api_cpp2/classdds_1_1sub_1_1LoanedSamples.html)
- [Loaning and Returning Data and SampleInfo Sequences](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/users_manual/users_manual/Loaning_and_Returning_Data_and_SampleInf.htm)
- [Using FlatData Language Binding](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/users_manual/users_manual/SendingLDFlatDataUseheading.htm)
- [Building Applications — Notes for All Platforms](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/platform_notes/platform_notes/BuildingApplications.htm)
