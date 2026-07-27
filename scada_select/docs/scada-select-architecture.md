# scada_select — Selector Architecture

**Status:** Draft v0.1
**Date:** 2026-07-27
**Scope:** the Role 1 component — the `scada_select/` package.

The `scada_select/` package is the **scada-selector** component named throughout
[system-architecture.md](../../docs/system-architecture.md) (the docs use the hyphenated
service name; the directory uses the short form). It has two jobs, and the second
is the reason the first is placed here:

1. **Selection.** Absorb the full field stream with **compiled** types and
   republish only the tags scada-web asked for, at no more than the rate it asked
   for.
2. **Boundary.** Be the *only* conduit between the **hard real-time** field side
   and the **soft real-time** presentation side. Every topic that crosses that
   line crosses it here ([DD-028](../../docs/design-decisions.md#dd-028)).

Companions:
[system-architecture.md](../../docs/system-architecture.md) §1a (Role 1) for placement,
[scada-selector-implementation.md](scada-selector-implementation.md) for build
configuration and hot-path code that was **verified by building and running it**,
and [DD-026](../../docs/design-decisions.md#dd-026) /
[DD-027](../../docs/design-decisions.md#dd-027) /
[DD-028](../../docs/design-decisions.md#dd-028) for the three decisions that
determine its shape.

---

## 1. Placement in the System

```
        HARD REAL TIME                  │        SOFT REAL TIME
        (field side)                    │        (presentation side)
                                        │
Level 0/1 (sim/)          Level 2 (scada_select/)      Level 2 (scada_web/)
┌──────────────────┐      ┌─────────────┼────────┐     ┌──────────────────┐
│ field_simulation │      │ SelectionTable        │     │ interest.py      │
│ plc_publisher    │─DDS─▶│  per-uid {period,     │─DDS▶│ gateway.py       │
│ plc_types        │      │   last_emitted}       │     │ server.py        │
└──────────────────┘      │ metadata passthrough  │     │                  │
                          │ control ◀─── request ─┼─────┤                  │
                          └─────────────┼────────┘     └──────────────────┘
  PLC::IdValue  ─────────▶              │  ──▶ PLC::SelectedValue
  PLC::MetaData ─────────▶              │  ──▶ PLC::SelectedMetaData
                                        │  ◀── PLC::ValueRequest      REST + WS
                                        │
                              the boundary is this process
```

Four facts the diagram is meant to make hard to forget:

- **Nothing crosses the boundary except through this process.** scada-web has no
  endpoint on the field side — no reader, no participant, no discovery traffic
  ([DD-028](../../docs/design-decisions.md#dd-028)).
- **`MetaData` passes through, unmodified, on its own topic.** The selector
  forwards it to `PLC::SelectedMetaData`; it does **not** merge it into values
  (§4.4). scada-web still owns the uid→metadata map and all correlation
  ([DD-024](../../docs/design-decisions.md#dd-024) is unchanged on that point).
- **The type on each output topic is the type on its input topic.** `IdValue` in,
  `IdValue` out; `MetaData` in, `MetaData` out.
- **The control channel runs backwards**, from scada-web into the selector, and it
  is the only thing that changes the selector's behavior at runtime. It originates
  on the soft side, which is why §3.8's backpressure rule exists.

The selector is the only component that sees the **untrimmed** field stream.
Everything downstream of it reads `DynamicData`, which is affordable only on a
stream that has already been reduced
([system-architecture.md](../../docs/system-architecture.md) §1a).

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
│   ├── DataPlane.cxx
│   ├── MetaDataPlane.hpp  MetaData reader → SelectedMetaData writer (§4.4)
│   └── MetaDataPlane.cxx
└── test/
    └── test_selection_table.cxx   runs without the Connext runtime
```

The three planes are separate translation units because they have **three
different rate and criticality profiles** — the data plane runs per sample, the
metadata plane runs at startup and on request, the control plane runs on operator
action. Only the data plane is on a path where per-sample cost matters.

### 2.1 Dependency Flow (acyclic)

```
SelectionTable        (pure C++: uid → {period_ms, last_emitted})
      ▲   ▲
      │   └──────────── DataPlane ────▶ (dds::sub, dds::pub)
      │                     ▲
      └── ControlPlane ─────┤──────────▶ (dds::sub)
                 ▲          │
                 │      MetaDataPlane ─▶ (dds::sub, dds::pub)
                 │          ▲
                 └── main ──┘ ─────────▶ (dds::domain, dds::core::cond)
```

`MetaDataPlane` does not depend on `SelectionTable` — metadata is forwarded for
**all** tags, not just selected ones (§4.4). It takes a dependency on
`ControlPlane` only for the `METADATA` re-publish command, and that is a callback,
not a shared table.

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

**Forwarding `MetaData` does not violate this, and it is worth being precise about
why**, because it looks like a return to the design DD-024 rejected. What DD-024
rejected was *merging* metadata into value samples — an enriched `EnabledValue`
that made the model fatter so the next component could slim it. Forwarding
`MetaData` unmodified on its own topic is a different operation: two topics in,
two topics out, no field of either touched, and no correlation performed. The
selector still cannot answer "what is tag 5 called" — it never reads `longName`.

The test to apply: **does the selector look at any field other than the key?** For
values it reads `uid` and nothing else; for metadata it reads `uid` and nothing
else. That is transport, not presentation.

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

### 3.6 The Selector Holds No Application State — but It Now Re-originates Durability

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

**Metadata forwarding adds one exception, and it is the only durable thing in the
process.** Because `MetaData` is `TRANSIENT_LOCAL` on the field side and scada-web
may join late, the forwarded topic must also be `TRANSIENT_LOCAL` — which makes
the selector's writer the **durability re-origin** for everything downstream of
the boundary (§4.4). Three points that keep this from becoming state creep:

- **The store is Connext-owned, not application-owned.** A `KEEP_LAST depth=1`
  writer on a `@key uid` topic holds exactly one sample per tag, which *is* the
  catalogue. There is no `unordered_map<int32_t, MetaData>` in this component, and
  adding one would be the actual violation of DD-024.
- **It is a copy, not a merge.** Nothing joins it to values (§3.2).
- **It does not survive restart, and does not need to.** `TRANSIENT_LOCAL` dies
  with the writer; on restart the selector's own `TRANSIENT_LOCAL` reader receives
  the catalogue again from the sim and republishes it. The recovery path is the
  startup path, so there is no separate recovery code.

The cost of that last point: **during a selector restart, a late-joining scada-web
sees an empty catalogue** until the field-side historical samples arrive and are
forwarded — two DDS hops instead of one. Values behave the same way but matter
less, being `VOLATILE` and continuously republished. scada-web's map update is
keyed by uid and therefore idempotent, so re-delivery is harmless; what it must
not do is treat "catalogue empty" as "no tags exist".

### 3.7 Configuration Is Flags, Not YAML

scada-web reads YAML because its topology is discovered and its views are
declarative. The selector's topology is **five entities, fixed forever**: readers
on `IdValue`, `MetaData`, and `ValueRequest`; writers on `SelectedValue` and
`SelectedMetaData`. A config file for that is ceremony.

So: CLI flags (`--field-domain`, `--web-domain`, `--value-topic`,
`--selected-topic`, `--metadata-topic`, `--selected-metadata-topic`,
`--request-topic`, `--qos-file`, `--verbosity`) with the topic names from
[system-architecture.md](../../docs/system-architecture.md) §4 as defaults, plus an optional
QoS provider XML for the profiles in §6. Two domain flags rather than one because
of §3.8; setting both to the same value is the single-domain deployment.

**The IDL is copied into `idl/`, and that is a real duplication** of
[`sim/PlcValue.idl`](../../sim/PlcValue.idl). It is the residue of
[OQ-20](../../docs/questions.md#oq-20): the intended end state is one IDL with two automated
derivations — `rtiddsgen` for this component, `rtiddsgen -convertToXml` for the
types library scada-web loads — so nothing is hand-transcribed. Until that is
wired, prefer pointing `CMakeLists.txt` at `../sim/PlcValue.idl` over keeping a
second copy in sync by hand.

### 3.8 The Real-Time Boundary

[DD-028](../../docs/design-decisions.md#dd-028). The selector is the conduit
between two zones with **different timing contracts**, and it is the only conduit:

| | Field side (hard real time) | Web side (soft real time) |
|---|---|---|
| Participants | sim L1 publishers, selector readers | selector writers, scada-web, browsers |
| Timing contract | Bounded, deterministic latency; a missed deadline is a **failure** | Latency is a *target*; a late or dropped display update is a **degradation** |
| Data representation | Compiled types | `DynamicData`, then JSON |
| Transport | DDS/UDP, one plant network | DDS, then TCP/WebSocket to browsers |
| Volume | Full scan rate, batched | Selected uids, downrated (§3.3) |
| Failure appetite | None — this side runs the process | Tolerant — a browser can miss a frame |

**The invariant that makes the boundary real: nothing on the soft side may
back-pressure the hard side.** A boundary that propagates congestion upstream is
not a boundary; it is a coupling with a diagram drawn around it. Three concrete
rules follow, in decreasing order of how badly they bite:

1. **Outbound writers use `KEEP_LAST`, never `KEEP_ALL`.** This is the load-bearing
   one. A `RELIABLE` + `KEEP_ALL` writer whose resource limits fill up will
   **block in `write()`** for up to `max_blocking_time` — on the dispatch thread,
   which then stops draining the inbound reader, whose cache then overflows. A
   stalled browser client would degrade field-side reception. With `KEEP_LAST`,
   history-full overwrites the oldest sample instead of blocking, so a slow
   consumer costs *its own* data and nothing else. `KEEP_ALL` is correct on the
   inbound `ValueRequest` reader ([DD-023](../../docs/design-decisions.md#dd-023))
   and wrong on both outbound writers; the asymmetry is deliberate.
2. **`max_blocking_time` is short, and a timeout is a drop.** Log it, count it,
   continue. Never retry inside the dispatch callback — that converts one late
   sample into a stalled loop.
3. **Consider `ASYNCHRONOUS_PUBLISH_MODE` with a `FlowController`** on the
   outbound writers, which moves serialization and send off the dispatch thread
   and shapes bursts. Not required for the PoC — it adds a queue whose bounds
   become another thing to get right — but it is the standard answer if
   measurement shows the send path intruding on the read path.

**Dropping under congestion is policy here, not failure.** §3.3 already drops
deliberately (rate limiting), so the same disposition under a different trigger
needs no new semantics: a display shows the latest value it received, and the
selector's contract downstream is "latest, at most this often", never "all".

**What the boundary buys beyond timing:**

- **Discovery isolation.** This is the concrete win, and it is bigger than the
  metadata path itself. Before this decision scada-web read `MetaData` directly,
  which meant it joined the field-side domain, which put its discovery traffic,
  its restarts, and its per-client churn on the control network. Now the field
  side sees exactly one subscriber — the selector — with a fixed, small,
  never-changing endpoint set.
- **[OQ-22](../../docs/questions.md#oq-22) becomes structurally answerable.** Its
  option (b) — "separate DDS domains per level with a deliberate bridge as the
  conduit" — was already the recommended cheap step, and it was *impossible* while
  scada-web had a foot in the field domain. The conduit is now an actual component
  rather than an assumption, which is exactly the distinction the
  [scada-sme](../../.github/agents/scada-sme.agent.md) IEC 62443 guidance draws.
- **One place to audit.** Every sample crossing zones passes through five
  entities in one process.

**Two domains or one?** Two participants — one per side — is the deployment this
design is for, and it is what `--field-domain` / `--web-domain` express. A single
domain still works and is the right PoC default, because the boundary is enforced
by *topology* (only the selector has endpoints on both sides) before it is
enforced by domain IDs. Tracked as [OQ-26](../../docs/questions.md#oq-26). Two
notes on the two-domain case:

- **A `WaitSet` may hold conditions from entities on different participants**, so
  §3.5's single-threaded dispatch loop survives domain separation unchanged. Each
  participant brings its own discovery and receive threads, which is the cost.
- **Distinct topic names are kept even though two domains would permit reuse.**
  `PLC::SelectedValue` and `PLC::SelectedMetaData` stay distinct from
  `PLC::IdValue` and `PLC::MetaData` so that single-domain deployment works,
  `rtiddsspy` output is unambiguous about which side of the boundary a sample was
  captured on, and a misconfigured domain flag fails loudly rather than
  short-circuiting the selector.

---

## 4. Data Flow

### 4.1 Startup Sequence

```
1. Parse flags; optionally load QoS XML
2. Create field-side participant   (--field-domain)
   Create web-side participant     (--web-domain; same value = one domain)
3. Create a Subscriber + Publisher per side
4. Field side:  IdValue reader     — matches the sim's writer QoS
                MetaData reader    — RELIABLE + TRANSIENT_LOCAL + KEEP_LAST 1
5. Web side:    ValueRequest reader   — RELIABLE + KEEP_ALL         (DD-023)
                SelectedValue writer  — RELIABLE + VOLATILE + KEEP_LAST  (§3.8)
                SelectedMetaData writer
                                  — RELIABLE + TRANSIENT_LOCAL + KEEP_LAST 1
6. Attach ReadConditions to one WaitSet: control, then metadata, then data
7. dispatch() loop until SIGINT/SIGTERM
```

Start order versus scada-web and the sim does not matter, and the two topics reach
that conclusion by different routes. The selector starts with an empty table and
turns tags on as requests arrive; `IdValue` is `VOLATILE`, so there is no backlog
to mis-handle on a late join. `MetaData` is `TRANSIENT_LOCAL` on both hops, so a
selector that starts after the sim still receives the whole catalogue, and a
scada-web that starts after the selector still receives it too (§4.4).

**Order within the WaitSet: control, metadata, data.** Control first for the
reason in §3.5. Metadata before data is a weaker preference — it means a tag's
description is available downstream no later than its first value, which spares
scada-web a "value for an unknown uid" transient it would otherwise have to hold.

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
    │  METADATA → re-publish MetaData for uid       (§4.4 — now implemented here)
    ▼
SelectionTable
```

`ADD` on an already-enabled uid is a **rate update**, not an error, and not a
duplicate-enable. That is what makes the channel tolerable to drive from a
refcounting client.

**`METADATA` finally has an owner.** The IDL has carried
`Command_t::METADATA` — "re-publish `MetaData` for `uid`" — since before this
component existed, and under DD-024 the selector had no metadata path, so the
command was dead: nothing could service it. Now that metadata crosses the
boundary here, this is the only component that *can* service it, and it does so by
re-reading its own reader cache and rewriting one instance (§4.4).

This is not the primary recovery path — `TRANSIENT_LOCAL` on the forwarded topic
already gives a late-joining scada-web the full catalogue with no request at all.
It is the in-band path for a scada-web that lost its map **without** recreating its
DDS entities, where durability alone would not redeliver.

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

### 4.4 Metadata-Plane Flow

```
sim (once at startup, TRANSIENT_LOCAL)
    │
    ▼  PLC::MetaData
metadata_reader.read()        ← read(), NOT take() — see below
    │
    │  forward every uid, unmodified, unfiltered by the selection table
    ▼
selected_metadata_writer.write(data())
    │
    ▼  PLC::SelectedMetaData (TRANSIENT_LOCAL — the durability re-origin, §3.6)
scada-web: uid→metadata map  (its own state, DD-024 unchanged)
```

Four decisions in that short path:

**The whole catalogue crosses, not just selected uids.** Filtering metadata by the
selection table would be the intuitive symmetry with §3.3, and it is wrong:
scada-web's map *is* the tag catalogue, needed to answer "what tags exist" and to
resolve a name to a uid ([OQ-13](../../docs/questions.md#oq-13)) **before** anything
is selected. Filtering it would make the catalogue depend on what is currently on
screen — a bootstrapping deadlock, since a client cannot ask for a tag it cannot
discover. The volume argument for filtering does not apply either: `MetaData` is
written once per tag at startup, so the full catalogue is a few hundred bytes ×
tag count, once.

**`read()`, not `take()`.** The value plane takes (§4.3); the metadata plane must
not, and the asymmetry has two reasons. Taking would consume the sample, leaving
nothing to answer a `METADATA` command from (§4.2), and it would empty the reader
cache that makes restart recovery free (§3.6). Use `NOT_READ` sample state to
forward each metadata sample exactly once while leaving it in the cache:

```cpp
auto samples = metadata_reader.select()
        .state(dds::sub::status::DataState::new_data())   // NOT_READ, ALIVE
        .read();
for (const auto &s : samples) {
    if (s.info().valid()) {
        selected_metadata_writer.write(s.data());
    }
}
```

**Durability is mirrored, not upgraded.** `TRANSIENT_LOCAL` in, `TRANSIENT_LOCAL`
out, `KEEP_LAST depth=1` on a keyed topic both sides. Anything stronger
(`TRANSIENT`, `PERSISTENT`) would make the selector a store, which is a different
component; anything weaker breaks late-joining scada-web, which is the whole point
of the topic being durable in the first place.

**Lifecycle transitions use the §3.4 path.** A disposed tag must retract from the
catalogue, or scada-web's map keeps a tag the plant no longer has. Same
`dispose_instance` / `unregister_instance` mapping, same nil-handle guard, and no
rate limit — metadata has no rate limit to bypass.

---

## 5. State Model

The whole of the selector's state:

| State | Type | Lifetime | Bounded by |
|---|---|---|---|
| Selection table | `unordered_map<int32_t, TagState>` | Process | Tag count |
| Reader caches | Connext-owned | Per QoS | `History` depth × instances |
| `MetaData` reader cache | Connext-owned | Process | Tag count (`KEEP_LAST 1`, keyed) — load-bearing, §4.4 |
| `SelectedMetaData` writer cache | Connext-owned | Process | Tag count (`KEEP_LAST 1`, keyed) — the durability re-origin, §3.6 |

The last two rows are new with [DD-028](../../docs/design-decisions.md#dd-028) and
are the reason §3.6's title changed from "no durable state" to "no *application*
state". The distinction is not pedantry — it is the line that keeps DD-024 intact:

**There is no `unordered_map<int32_t, MetaData>` in this component.** The catalogue
lives in middleware caches the selector configures but does not interpret. It
holds no metadata *map*, no per-client state, no connection state, and nothing
persistent. It cannot tell how many web clients exist, and must not need to: it
sees exactly one aggregate consumer, which is what makes per-client refcounting
scada-web's job ([system-architecture.md](../../docs/system-architecture.md) §7).

If a future requirement forces an application-level metadata structure here —
indexing by name, say — that is the signal to re-read DD-024 before writing it,
because it means presentation work has drifted across the boundary.

---

## 6. Topic and QoS Contract

Types are in [`sim/PlcValue.idl`](../../sim/PlcValue.idl). Contracts in
[system-architecture.md](../../docs/system-architecture.md) §4.

| Side | Topic | Role | Type | QoS |
|---|---|---|---|---|
| Field | `PLC::IdValue` | Read (data in) | `IdValue` | `RELIABLE`, `VOLATILE`, matches the sim's writer |
| Field | `PLC::MetaData` | Read (catalogue in) | `MetaData` | `RELIABLE`, **`TRANSIENT_LOCAL`**, `KEEP_LAST 1` — durability required or a late-starting selector misses the catalogue |
| Web | `PLC::ValueRequest` | Read (control in) | `ValueRequest` | **`RELIABLE` + `KEEP_ALL`** — required, [DD-023](../../docs/design-decisions.md#dd-023) |
| Web | `PLC::SelectedValue` | Write (data out) | `IdValue` | `RELIABLE`, `VOLATILE`, **`KEEP_LAST`** — never `KEEP_ALL` (§3.8) |
| Web | `PLC::SelectedMetaData` | Write (catalogue out) | `MetaData` | `RELIABLE`, **`TRANSIENT_LOCAL`**, `KEEP_LAST 1` — the durability re-origin (§3.6) |

Three QoS choices worth arguing rather than inheriting:

- **`KEEP_LAST` on both outbound writers is a correctness requirement, not
  tuning.** It is what stops soft-side congestion from blocking the dispatch
  thread and reaching the field side — the §3.8 invariant, and the single most
  consequential QoS line in this component.
- **A shallow `KEEP_LAST` on the inbound `IdValue` reader is defensible** —
  arguably preferable — because the data plane discards most samples anyway
  (§3.3). Deep history on a stream that is about to be decimated buys cache
  pressure and nothing else. Depth is a tuning parameter here; dropping stale
  values is the intended behavior. The inbound **`MetaData`** reader is the
  opposite case: its cache is load-bearing (§4.4), so `TRANSIENT_LOCAL` +
  `KEEP_LAST 1` per instance is required, and `read()` rather than `take()` keeps
  it populated.
- **Each output mirrors its input rather than "improving" it.** Deepening history
  on `SelectedValue`, or upgrading `SelectedMetaData` to `TRANSIENT`, would change
  the semantics scada-web sees relative to reading the field topics directly —
  making the selector observable in the data model, a §3.2 violation. Mirroring is
  what lets §8's tests substitute one for the other.

If the output writer batches, note it interacts with §3.3: batching on an already
downrated stream adds latency for little bandwidth gain, and on the boundary it
also enlarges the burst a soft-side consumer must absorb. Default to no batching
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
| Integration | Catalogue crosses the boundary | `rtiddsspy` on `PLC::SelectedMetaData` with the sim running: every tag present, unfiltered by the selection table (§4.4) |
| Integration | Late-joining scada-web | Start sim → selector → *then* the subscriber; confirm the full catalogue still arrives (durability re-origination, §3.6) |
| Integration | Selector restart | Kill and restart the selector with the sim running; confirm a subscriber that stayed up re-receives the catalogue and the map converges |
| Integration | `METADATA` command | Send `Command_t::METADATA` for one uid; confirm exactly that instance is republished (§4.2) |
| **Boundary** | **No upstream backpressure** | Stall or SIGSTOP the `SelectedValue` subscriber under load; confirm field-side reception at the selector is **unchanged** — inbound rate and cache occupancy flat, drops attributed outbound. This is the §3.8 invariant, and it is the one test that would catch a `KEEP_ALL` slipping into an output writer |
| Boundary | No field-side endpoints from scada-web | `rtiddsspy` on the field domain with scada-web running: only the selector appears as a subscriber |
| Performance | Selection cost | The relative comparison in impl notes §4: naive `s.data().uid` predicate versus instance-handle selection, same machine, realistic tag counts and rates |

Inject the clock in the unit tests. A `SelectionTable` that calls
`steady_clock::now()` internally is a table whose rate-limiting tests either
sleep or don't exist.

**Do not adopt instance-handle selection without measuring it.** With compiled
types the naive predicate is already a struct member load; the instance-handle
version adds a handle map to maintain and a per-instance take loop, and may well
be slower for a ~100-byte type. NFR-PERF-001 asks for a relative comparison,
which is all this needs to settle.

**The backpressure test is the one to write first**, ahead of anything about
rates. Every other row above fails visibly; that one fails as a *coupling* that
only appears under load, on the side of the system where a missed deadline is a
failure rather than a dropped frame. A boundary that has never been tested with a
stalled consumer is an assumption.

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
| [OQ-26](../../docs/questions.md#oq-26) | One DDS domain or two across the boundary? | Decides whether `--field-domain` and `--web-domain` differ in deployment (§3.8) |
| [OQ-22](../../docs/questions.md#oq-22) | Purdue zones via DDS Security? | Now structurally reachable: DD-028 makes the conduit a real component, so option (b) — a domain per level — is available (§3.8). The selector is the enforcement point |

Future work, in rough order of value:

- **Observability.** Standalone hosting means no free Routing Service monitoring
  ([architecture-comparison.md](../../docs/architecture-comparison.md) §2). The metrics that
  matter are cheap and few: samples in, samples forwarded, samples dropped by
  rate limit, samples dropped as unselected, and table size. Per-uid counters if
  they stay off the hot path.
  **Add two for the boundary:** outbound writes that hit `max_blocking_time`, and
  outbound samples lost to `KEEP_LAST` overwrite. Those two are how a soft-side
  consumer problem becomes visible *as* a soft-side problem instead of as
  mysterious field-side jitter.
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
- [design-decisions.md](../../docs/design-decisions.md) — [DD-023](../../docs/design-decisions.md#dd-023), [DD-024](../../docs/design-decisions.md#dd-024), [DD-026](../../docs/design-decisions.md#dd-026), [DD-027](../../docs/design-decisions.md#dd-027), [DD-028](../../docs/design-decisions.md#dd-028)
- [sim/PlcValue.idl](../../sim/PlcValue.idl) — the type and command contract
- [scada-web-architecture.md](../../scada_web/docs/scada-web-architecture.md) — the Role 2 counterpart (colocated under `scada_web/docs/` in a parallel change)
- [Connext 7.7.0 Modern C++ API reference](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/api/connext_dds/api_cpp2/index.html) — the `api_cpp2` tree is the Modern API; `api_cpp` is the Traditional one
- [`DataWriter` (Modern C++)](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/api/connext_dds/api_cpp2/classdds_1_1pub_1_1DataWriter.html) — `dispose_instance` / `unregister_instance` / `lookup_instance`
- **Validation:** the §3.4 lifecycle mapping and the §4.3 data-plane loop were checked against the Connext 7.7.0 C++11 API via Connext AI (`validate_modern_cpp_code`) and returned valid as written. Not the same as compiled-and-run — impl notes §3 is the verified-by-building material.
