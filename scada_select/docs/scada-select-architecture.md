# scada_select — Selector Architecture

**Status:** Draft v0.1
**Date:** 2026-07-27
**Scope:** the Role 1 component — the `scada_select/` package.

The `scada_select/` package is the **scada-selector** component named throughout
[system-architecture.md](../../docs/system-architecture.md) (the docs use the hyphenated
service name; the directory uses the short form). It is the Level 2 selection
service: it absorbs the full field value stream with **compiled** types and
republishes only the tags scada-web has asked for, at no more than the rate
scada-web asked for.

Companions:
[system-architecture.md](../../docs/system-architecture.md) §1a (Role 1) for placement,
[scada-selector-implementation.md](scada-selector-implementation.md) for build
configuration and hot-path code that was **verified by building and running it**,
and [DD-026](../../docs/design-decisions.md#dd-026) / [DD-027](../../docs/design-decisions.md#dd-027)
for the two decisions that determine its shape.

---

## 1. Placement in the System

```
Level 0/1 (sim/)          Level 2 (scada_select/)      Level 2 (scada_web/)
┌──────────────────┐      ┌──────────────────────┐     ┌──────────────────┐
│ field_simulation │      │ SelectionTable       │     │ interest.py      │
│ plc_publisher    │─DDS─▶│  per-uid {period,    │─DDS▶│ gateway.py       │
│ plc_types        │      │   last_emitted}      │     │ server.py        │
└──────────────────┘      │ control ◀── request ─┼─────┤                  │
                          └──────────────────────┘     └──────────────────┘
       PLC::IdValue              PLC::SelectedValue         REST + WS
       PLC::MetaData ────────────(bypasses selector)───────▶
       PLC::ValueRequest ◀───────────────────────────────────
```

Three facts the diagram is meant to make hard to forget:

- **`MetaData` does not pass through the selector.** scada-web subscribes to it
  directly ([DD-024](../../docs/design-decisions.md#dd-024)); the selector has no metadata
  cache and no `MetaData` reader.
- **The type on the output topic is the type on the input topic.** `IdValue` in,
  `IdValue` out, on `PLC::SelectedValue`.
- **The control channel runs backwards**, from scada-web into the selector, and it
  is the only thing that changes the selector's behavior at runtime.

The selector is the only component in the system that sees the **untrimmed**
value stream. That is its whole reason to exist: everything downstream of it
reads `DynamicData`, which is affordable only on a stream that has already been
reduced ([system-architecture.md](../../docs/system-architecture.md) §1a).

---

## 2. Module Architecture

Planned layout. Nothing here is built yet — see §8.

```
scada_select/
├── CMakeLists.txt         rtiddsgen via ConnextDdsCodegen (impl notes §1)
├── idl/
│   └── PlcValue.idl       generated-from source; see §3.7 on duplication
├── config/
│   └── qos.xml            QoS profiles per §6 (optional; defaults work)
├── src/
│   ├── main.cxx           CLI, participant, wiring, signal handling
│   ├── SelectionTable.hpp per-uid state — pure C++, no DDS
│   ├── SelectionTable.cxx
│   ├── ControlPlane.hpp   ValueRequest reader → SelectionTable mutations
│   ├── ControlPlane.cxx
│   ├── DataPlane.hpp      IdValue reader → decimate → SelectedValue writer
│   └── DataPlane.cxx
└── test/
    └── test_selection_table.cxx   runs without the Connext runtime
```

### 2.1 Dependency Flow (acyclic)

```
SelectionTable        (pure C++: uid → {period_ms, last_emitted})
      ▲   ▲
      │   └──────────── DataPlane ────▶ (dds::sub, dds::pub)
      │                     ▲
      └── ControlPlane ─────┼──────────▶ (dds::sub)
                 ▲          │
                 └── main ──┘ ─────────▶ (dds::domain, dds::core::cond)
```

`SelectionTable` is deliberately DDS-free, for the same reason
[`interest.py`](../../scada_web/interest.py) is in scada-web: the decision logic is
the part worth unit-testing, and requiring a live domain to test it is what makes
people stop testing it. It holds no Connext type — `int32_t` keys, not
`PLC::UniqueId_t` samples.

This decomposition is also the discipline that keeps
[architecture-comparison.md](../../docs/architecture-comparison.md) §7's "revisit if the
type constraint relaxes" cheap: `SelectionTable` is the whole of the logic, and
it would move into a Routing Service Processor unchanged.

---

## 3. Key Design Decisions

### 3.1 Modern C++ API, and Compiled Types

**The API is the Connext Modern C++ API** — the `dds::` namespace reached through
`#include <dds/dds.hpp>`, linked as `RTIConnextDDS::cpp2_api`, generated with
`rtiddsgen -language C++11`. Not the Traditional C++ API (`ndds/ndds_cpp.h`,
`cpp_api`, `DDSDomainParticipant`), which is legacy and should not appear in this
component at all.

The name collision is worth stating once, because it causes real confusion: RTI
calls this API **"C++11"** because that was the language standard it required at
introduction. It is a *binding* choice, independent of the **language standard**,
which is **C++17** here per [DD-006](../../docs/design-decisions.md#dd-006)
(`set(CMAKE_CXX_STANDARD 17)`). So: Modern C++ API, C++17 language level, and
`LANG "C++11"` in the codegen call — all three are correct simultaneously.

What that buys, concretely, in a component whose whole job is a tight loop over
samples:

| Modern C++ | Traditional C++ | Why it matters here |
|---|---|---|
| `dds::sub::LoanedSamples<T>` from `take()`, RAII | `DDS_SampleSeq` + explicit `return_loan()` | The loan returns when the range leaves scope. A `continue` in the middle of the decimation loop (§4.3) cannot leak it — and that loop is nothing but early exits. |
| Range-`for` over samples | Index loop over paired data/info sequences | Data and `SampleInfo` travel together, so `s.info().valid()` cannot drift out of step with `s.data()`. |
| Exceptions | Return-code checks | No unchecked `DDS_ReturnCode_t` on the hot path. |
| Reference-counted entity handles | Manual `delete_*` factories | Participant/reader/writer teardown is scope-based; the signal handler only has to stop the dispatch loop. |
| Scoped enums (`PLC::Command_t::ADD`) | Unscoped `#define`-adjacent constants | The `switch` in §4.2 is exhaustively checkable. |
| Streaming QoS composition (`qos << Reliability::Reliable()`) | Struct field assignment | The QoS in §6 reads as the contract it is. |

Generated types are **plain aggregates with public data members** in this
binding — `s.data().uid`, not `s.data().uid()` — see §7 and impl notes §2. Much
RTI example code online shows the older accessor style and does not apply.

Everything in this doc's code, and everything in impl notes §3, is Modern C++;
the snippets in §3.4 and §4.3 were validated against the Connext 7.7.0 C++11 API
(§10).

**Types are compiled, not `DynamicData`** — `rtiddsgen` from
[`PlcValue.idl`](../../sim/PlcValue.idl), built by CMake
([DD-026](../../docs/design-decisions.md#dd-026), impl notes §1). The selector
subscribes to the high-rate topic, so the per-sample key check must be a struct
member load (`s.data().uid`) rather than a name lookup
(`dd.value<int32_t>("uid")`).

This is the **opposite** of scada-web's choice, and both are right: the selector
handles exactly one known type as fast as it can; scada-web handles types it was
never compiled against.

**Consequence:** an IDL change is a rebuild of this component. Accepted — the
selector reads two fields (`uid`, and nothing else on the hot path) and the model
is owned upstream.

**Consequence:** hosting inside Routing Service is ruled out, because its
built-in DDS adapter is DynamicData-based and offers no documented way to bind
generated types to a Processor's `TypedInput<T>`. The selector is therefore a
standalone executable that must supply its own configuration, lifecycle, logging,
and metrics.

### 3.2 Pure Selection — No Model Changes

Samples that pass through are the same type, unmodified. No enrichment, no JSON,
no union resolution, no limit evaluation, no correlation. Every one of those is
scada-web's ([system-architecture.md](../../docs/system-architecture.md) §7).

The v0.1 design had the selector emit an enriched `EnabledValue` carrying
`longName`/`hostname`/`limits`; [DD-024](../../docs/design-decisions.md#dd-024) moved that
out, which deleted a type, a cache, and a denormalization cost from this
component.

### 3.3 Selection Is Two-Dimensional: id **and** rate

[DD-027](../../docs/design-decisions.md#dd-027). State is per-uid, not a bare set:

```cpp
struct TagState {
    uint32_t period_ms {0};                                  // 0 = every sample
    std::chrono::steady_clock::time_point last_emitted {};
};
```

Four defaults, all reversible, all stated because each has a wrong-looking
alternative that seems obvious:

| Choice | Instead of | Why |
|---|---|---|
| **Decimate on arrival** | Timer-driven emit | O(1) per sample, no timers, and naturally correct when the source is slower than the requested rate. A timer spaces output more evenly but must hold samples and wake up — not worth it for display data. |
| **`steady_clock`** | The payload's `valueTime` | Source stamps may be irregular or skewed. The decimation decision is about *our* output cadence, not the field's. |
| **`period_ms == 0` = every sample** | `0` = never | An unset rate degrades to plain selection, not to silence. |
| **Latest sample wins** | Oldest, or aggregate | Display data: the freshest value is the useful one. Nothing is averaged — that would be a model change (§3.2). |

The rate axis is not a nicety. It is what keeps the volume reaching scada-web's
`DynamicData` reader small enough for that representation to be affordable, and
in particular it removes the per-sample burst cost of inbound **batching** —
Connext unpacks a batch and deserializes each sample individually, so batching
cuts network overhead while concentrating CPU into a spike.

### 3.4 Lifecycle Events Bypass the Rate Limit

A dispose or unregister must reach the display *now*, not at the next tick — a
tag going stale is exactly the event an operator must not see late. So instance
lifecycle notifications are forwarded unconditionally for any selected uid.

Invalid samples carry only the key, so recovering the uid requires
`reader.key_value(key_holder, info.instance_handle())` rather than a payload
read (the `key_of` helper in impl notes §3.1).

**Forward the transition as a writer-side lifecycle call, not as a `write()`.**
Impl notes §3.1 sketches it as `selected_writer.write(s.data(), s.info())` on an
invalid sample, which reads the payload of a sample that has none. The mapping to
use instead:

| Inbound instance state | Outbound call |
|---|---|
| `not_alive_disposed()` | `writer.dispose_instance(handle)` |
| `not_alive_no_writers()` | `writer.unregister_instance(handle)` |

```cpp
PLC::IdValue key_holder;
value_reader.key_value(key_holder, s.info().instance_handle());
const dds::core::InstanceHandle out = selected_writer.lookup_instance(key_holder);

if (s.info().state().instance_state()
        == dds::sub::status::InstanceState::not_alive_disposed()) {
    selected_writer.dispose_instance(out);
} else {
    selected_writer.unregister_instance(out);
}
```

This form was **validated against the Connext 7.7.0 C++11 API** (§10). Note that
it sidesteps the open question rather than answering it: because the uid is
recovered through `key_value()`, nothing here calls `data()` on an invalid
sample, so whether that access is legal never arises. Keep it that way.

**One edge to guard:** `lookup_instance()` returns nil if the *writer* has never
registered that instance — a uid enabled but disposed upstream before a single
sample was ever forwarded. Disposing a nil handle throws, so either check
`out != dds::core::InstanceHandle::nil()` and skip, or register first
(`selected_writer.register_instance(key_holder)`) and dispose the result. Skipping
is the better default: with no sample ever forwarded, scada-web has nothing
displayed to retract.

### 3.5 Control Before Data, One Thread

A single `WaitSet` with the control-plane condition attached **first**, so a tag
enabled in a batch is forwarded in the same dispatch pass rather than one pass
later. One thread owns all reader/writer access; there is no hand-off queue and
no lock, because there is nothing to hand off to.

This matches [DD-022](../../docs/design-decisions.md#dd-022)'s reasoning for the system:
the selector has one aggregate consumer and no connections, so the concurrency
question that dominates scada-web does not arise here at all.

The invariant to keep: **nothing blocking in either callback.** The callbacks
run on the dispatch thread, and blocking one stalls the other.

### 3.6 The Selector Holds No Durable State

`ValueRequest` is an unkeyed command stream, so the selection table is
reconstructed from commands and lost on restart. Two consequences, both already
recorded:

- **`RELIABLE` + `KEEP_ALL`** on the request channel is required, not optional
  ([DD-023](../../docs/design-decisions.md#dd-023)). Under `KEEP_LAST depth=1` a rapid
  `ADD(1) ADD(2) ADD(3)` burst can have unacknowledged samples replaced before
  delivery. Reliability guarantees the *last* sample arrives, not every sample.
  The failure is silent and load-dependent — tags simply never turn on, most
  likely when an operator opens a screen with many tags at once.
- **scada-web owns reconciliation** (SR-003): after a selector restart it
  re-drives the full active set. The selector does not ask; it just starts empty.

[OQ-17](../../docs/questions.md#oq-17) and [OQ-24](../../docs/questions.md#oq-24) would retire both by
making the request topic `@key uid` + `{enabled, period_ms}` +
`TRANSIENT_LOCAL`, which is idempotent and lets a restarted selector recover its
whole subscription set from the middleware. Adding `period_ms` did not take that
step, so **both consequences stand today.**

### 3.7 Configuration Is Flags, Not YAML

scada-web reads YAML because its topology is discovered and its views are
declarative. The selector's topology is **three entities, fixed forever**: one
`ValueRequest` reader, one `IdValue` reader, one `SelectedValue` writer. A config
file for that is ceremony.

So: CLI flags (`--domain`, `--value-topic`, `--selected-topic`,
`--request-topic`, `--qos-file`, `--verbosity`) with the topic names from
[system-architecture.md](../../docs/system-architecture.md) §4 as defaults, plus an optional
QoS provider XML for the profiles in §6.

**The IDL is copied into `idl/`, and that is a real duplication** of
[`sim/PlcValue.idl`](../../sim/PlcValue.idl). It is the residue of
[OQ-20](../../docs/questions.md#oq-20): the intended end state is one IDL with two automated
derivations — `rtiddsgen` for this component, `rtiddsgen -convertToXml` for the
types library scada-web loads — so nothing is hand-transcribed. Until that is
wired, prefer pointing `CMakeLists.txt` at `../sim/PlcValue.idl` over keeping a
second copy in sync by hand.

---

## 4. Data Flow

### 4.1 Startup Sequence

```
1. Parse flags; optionally load QoS XML
2. Create DomainParticipant (default domain 0)
3. Create Subscriber + Publisher
4. ValueRequest reader   — RELIABLE + KEEP_ALL      (DD-023)
5. IdValue reader        — matches the sim's writer QoS
6. SelectedValue writer  — mirrors IdValue QoS       (§6)
7. Attach ReadConditions to one WaitSet: control first, data second
8. dispatch() loop until SIGINT/SIGTERM
```

Start order versus scada-web and the sim does not matter. The selector starts
with an empty table and turns tags on as requests arrive; `IdValue` is `VOLATILE`
so there is no backlog to mis-handle on a late join.

### 4.2 Control-Plane Flow

```
scada-web: interest 0→1 for uid=5 at 250ms
    │
    ▼  write ValueRequest{uid=5, command=ADD, period_ms=250}
DDS (PLC::ValueRequest, RELIABLE + KEEP_ALL)
    │
    ▼  request_reader.take()  — DataState::any(), so lifecycle is visible too
ControlPlane
    │  ADD      → table[uid].period_ms = period_ms  (re-ADD updates the rate)
    │  DELETE   → table.erase(uid)
    │  METADATA → not this component's job (DD-024) — ignored, logged once
    ▼
SelectionTable
```

`ADD` on an already-enabled uid is a **rate update**, not an error, and not a
duplicate-enable. That is what makes the channel tolerable to drive from a
refcounting client.

`name` is redundant with `uid` here. It is retained for readable logs and for a
possible name-based lookup path ([OQ-13](../../docs/questions.md#oq-13)).

### 4.3 Data-Plane Flow (the hot path)

```
DDS (PLC::IdValue — full field stream, possibly batched)
    │
    ▼  value_reader.take()  → LoanedSamples<IdValue>   (RAII loan)
for each sample:
    │
    ├─ uid = info.valid() ? data().uid : key_of(reader, info)
    │
    ├─ table.find(uid) == end  ────────────────▶ drop (not selected)
    │
    ├─ !info.valid()  ─────────────────────────▶ forward lifecycle (§3.4)
    │                                             — never rate limited
    ├─ period_ms != 0 && now - last_emitted < period_ms ──▶ drop (too soon)
    │
    └─ last_emitted = now; selected_writer.write(data())
                                    │
                                    ▼
                          DDS (PLC::SelectedValue) ──▶ scada-web
```

`take()` returns `LoanedSamples<T>`, which is RAII — the loan returns when the
range leaves scope, so nothing may retain a reference past the loop body.

**What republishing costs.** `writer.write(sample.data())` is the right call but
it is not a zero-copy hand-off: the loan is a `const T&` into the reader cache,
so nothing is copied into application memory, but the writer still serializes
from that object. There is no supported way to move a reader loan into a writer,
FlatData has no "republish the received bytes unchanged" shortcut, and Zero Copy
helps each hop independently but does not bridge a forwarder. `IdValue` is on the
order of 100 bytes, so none of these is the lever — see impl notes §4.

**What republishing preserves.** The `@key uid` means instances map 1:1 between
`IdValue` and `SelectedValue`. The DDS `source_timestamp` is rewritten to the
selector's write time, but the payload's `valueTime` carries the field
acquisition time, so **no acquisition-time information is lost** — downstream
must read `valueTime`, not the sample's source timestamp, to display "as of".

---

## 5. State Model

The whole of the selector's state:

| State | Type | Lifetime | Bounded by |
|---|---|---|---|
| Selection table | `unordered_map<int32_t, TagState>` | Process | Tag count |
| Reader caches | Connext-owned | Per QoS | `History` depth × instances |

There is no metadata map, no per-client state, no connection state, and no
persistence. The selector cannot tell how many web clients exist, and must not
need to: it sees exactly one aggregate consumer, which is what makes per-client
refcounting scada-web's job ([system-architecture.md](../../docs/system-architecture.md)
§7).

---

## 6. Topic and QoS Contract

Types are in [`sim/PlcValue.idl`](../../sim/PlcValue.idl). Contracts in
[system-architecture.md](../../docs/system-architecture.md) §4.

| Topic | Role | Type | QoS |
|---|---|---|---|
| `PLC::ValueRequest` | Read (control in) | `ValueRequest` | **`RELIABLE` + `KEEP_ALL`** — required, [DD-023](../../docs/design-decisions.md#dd-023) |
| `PLC::IdValue` | Read (data in) | `IdValue` | `RELIABLE`, `VOLATILE`, matches the sim's writer |
| `PLC::SelectedValue` | Write (data out) | `IdValue` | Mirrors `IdValue` — `RELIABLE`, `VOLATILE` |
| `PLC::MetaData` | **Not used** | — | Read directly by scada-web ([DD-024](../../docs/design-decisions.md#dd-024)) |

Two QoS choices worth arguing rather than inheriting:

- **A shallow `KEEP_LAST` on the inbound `IdValue` reader is defensible** —
  arguably preferable — because the data plane discards most samples anyway
  (§3.3). Deep history on a stream that is about to be decimated buys cache
  pressure and nothing else. Depth is a tuning parameter; it is not a
  correctness question, because dropping stale values is the intended behavior.
- **The output writer should mirror the input, not "improve" it.** Adding
  `TRANSIENT_LOCAL` or deeper history on `SelectedValue` would change the
  semantics scada-web sees relative to reading `IdValue` directly, which would
  make the selector observable in the data model — a §3.2 violation.

If the output writer batches, note it interacts with §3.3: batching on an already
downrated stream adds latency for little bandwidth gain. Default to no batching
outbound.

---

## 7. Build and Run

Full, verified detail — including the three CMake details that cost time if
guessed — is in
[scada-selector-implementation.md](scada-selector-implementation.md) §1. In brief:

```bash
cmake -S scada_select -B scada_select/build \
  -DCONNEXTDDS_DIR=/home/rti/rti_connext_dds-7.7.0 \
  -DCONNEXTDDS_ARCH=x64Linux4gcc7.3.0 \
  -DBUILD_SHARED_LIBS=ON \
  -DCMAKE_BUILD_TYPE=Release
cmake --build scada_select/build -j

export LD_LIBRARY_PATH=/home/rti/rti_connext_dds-7.7.0/lib/x64Linux4gcc7.3.0
./scada_select/build/scada_selector --domain 0
```

Three traps, all verified against the local 7.7.0 install:
`connextdds_rtiddsgen_run`'s `VAR plc` yields `${plc_CXX11_SOURCES}` (not
`GENERATED_SOURCES_VAR`); `CONNEXTDDS_ARCH` is `x64Linux4gcc7.3.0` and the
`gcc8.5.0` directory under `resource/app/lib` holds bundled services, failing at
link rather than configure; and without `BUILD_SHARED_LIBS=ON`,
`FindRTIConnextDDS` resolves the static variant and fails with
`libnddscpp2_release_static-NOTFOUND`.

Generated C++11 types are **plain aggregates with public members**, so field
access is `sample.data().uid`, not `sample.data().uid()` — most RTI example code
online shows the older accessor style, which does not apply (impl notes §2).

The two lines that pin the API choice from §3.1 are in `CMakeLists.txt`:
`connextdds_rtiddsgen_run(... LANG "C++11" ...)` for generation, and
`target_link_libraries(scada_selector PRIVATE RTIConnextDDS::cpp2_api)` for the
link. `cpp2_api` is the Modern C++ library; `cpp_api` would be the Traditional
one, and the `nddscpp2` in the `libnddscpp2_release_static-NOTFOUND` failure above
is the same "2". Nothing in this component should link `cpp_api`.

---

## 8. Verification

The selector is **independently demonstrable with no web tier at all**, which per
[system-architecture.md](../../docs/system-architecture.md) §9 makes it the cheapest real
progress available in the project.

| Level | What | How |
|---|---|---|
| Unit | `SelectionTable` — add/delete/re-add, rate update, `period_ms=0`, decimation boundaries | No Connext runtime; clock injected so decimation is tested deterministically |
| Integration | Selection works | Run `sim/plc_publisher.py`; drive `ValueRequest` by hand; `rtiddsspy` on `PLC::SelectedValue` |
| Integration | Rate limiting works | Same, with `period_ms` set; measure observed output period against requested |
| Integration | Lifecycle passthrough | Dispose a `uid` upstream; confirm the notification arrives on `SelectedValue` **immediately**, not at the next tick |
| Performance | Selection cost | The relative comparison in impl notes §4: naive `s.data().uid` predicate versus instance-handle selection, same machine, realistic tag counts and rates |

Inject the clock in the unit tests. A `SelectionTable` that calls
`steady_clock::now()` internally is a table whose rate-limiting tests either
sleep or don't exist.

**Do not adopt instance-handle selection without measuring it.** With compiled
types the naive predicate is already a struct member load; the instance-handle
version adds a handle map to maintain and a per-instance take loop, and may well
be slower for a ~100-byte type. NFR-PERF-001 asks for a relative comparison,
which is all this needs to settle.

---

## 9. Open Questions and Future Work

Bearing on this component specifically:

| ID | Question | Effect here |
|---|---|---|
| [OQ-15](../../docs/questions.md#oq-15) | Language and DDS API for scada-selector? | Settled in practice: **Modern C++ API, C++17, compiled types** (§3.1, DD-026, DD-006) — the doc entry should be closed |
| [OQ-17](../../docs/questions.md#oq-17) | Keyed `ValueRequest`? | Would delete §3.6 entirely: idempotent requests, no reconciliation, no `KEEP_ALL` requirement |
| [OQ-24](../../docs/questions.md#oq-24) | Desired-state vs command stream? | Same as OQ-17; these should be decided together |
| [OQ-20](../../docs/questions.md#oq-20) | Single source of truth for types? | Decides whether `idl/` is a copy or a generated derivation (§3.7) |
| [OQ-18](../../docs/questions.md#oq-18) | `LIFESPAN` on `ValueRequest`? | Would bound how stale a replayed request can be |
| [OQ-22](../../docs/questions.md#oq-22) | Purdue zones via DDS Security? | The selector is the natural enforcement point if this stops being logical-only |

Future work, in rough order of value:

- **Observability.** Standalone hosting means no free Routing Service monitoring
  ([architecture-comparison.md](../../docs/architecture-comparison.md) §2). The metrics that
  matter are cheap and few: samples in, samples forwarded, samples dropped by
  rate limit, samples dropped as unselected, and table size. Per-uid counters if
  they stay off the hot path.
- **Admin surface.** Also forfeited with Routing Service. The selection table is
  the only mutable state, and it is already mutable over DDS, so read-only
  introspection is most of what is missing.
- **Instance-handle selection**, if and only if §8's measurement justifies it.
- **Alarm limit evaluation** is *not* future work here. It is a model change
  ([OQ-14](../../docs/questions.md#oq-14)) and §3.2 keeps it out.

---

## 10. Sources

- [system-architecture.md](../../docs/system-architecture.md) §1a, §2, §4, §7, §9 — roles, topology, contracts, build order
- [scada-selector-implementation.md](scada-selector-implementation.md) — CMake, generated type shape, verified selector core, rate control, what "efficient" buys
- [architecture-comparison.md](../../docs/architecture-comparison.md) — why Routing Service is not used
- [design-decisions.md](../../docs/design-decisions.md) — [DD-023](../../docs/design-decisions.md#dd-023), [DD-024](../../docs/design-decisions.md#dd-024), [DD-026](../../docs/design-decisions.md#dd-026), [DD-027](../../docs/design-decisions.md#dd-027)
- [sim/PlcValue.idl](../../sim/PlcValue.idl) — the type and command contract
- [scada-web-architecture.md](../../docs/scada-web-architecture.md) — the Role 2 counterpart
- [Connext 7.7.0 Modern C++ API reference](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/api/connext_dds/api_cpp2/index.html) — the `api_cpp2` tree is the Modern API; `api_cpp` is the Traditional one
- [`DataWriter` (Modern C++)](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/api/connext_dds/api_cpp2/classdds_1_1pub_1_1DataWriter.html) — `dispose_instance` / `unregister_instance` / `lookup_instance`
- **Validation:** the §3.4 lifecycle mapping and the §4.3 data-plane loop were checked against the Connext 7.7.0 C++11 API via Connext AI (`validate_modern_cpp_code`) and returned valid as written. Not the same as compiled-and-run — impl notes §3 is the verified-by-building material.
