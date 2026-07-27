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
[DD-028](../../docs/design-decisions.md#dd-028) /
[DD-029](../../docs/design-decisions.md#dd-029) for the four decisions that
determine its shape.

The two sides also have different **reliability** contracts — the field side is
`RELIABLE`, the web side is `BEST_EFFORT`, and inbound `ValueRequest` is the single
stated exception ([DD-029](../../docs/design-decisions.md#dd-029), §6).

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
[`PlcValue.idl`](../../dds/idl/PlcValue.idl), built by CMake
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

> **Necessary but no longer sufficient, under
> [DD-029](../../docs/design-decisions.md#dd-029).** The web side is
> `BEST_EFFORT`, so a forwarded dispose can be **dropped in transit — and unlike a
> value, it is never repeated.** Forwarding it immediately stops being a guarantee
> that scada-web ever learns the tag is gone. Two mitigations, and the first is
> required: **scada-web must treat sample absence as staleness** (no update within
> N expected periods ⇒ stale on the display), which ISA-101 practice wants
> regardless of transport. Cheap adjunct here: **write disposes two or three
> times**, since they are rare and tiny. Bypassing the rate limit is still correct
> — it is just no longer the whole story.

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

**And under [DD-029](../../docs/design-decisions.md#dd-029) that stays true on both
sides of the boundary — the title needs no further qualification.** An earlier draft
of this section had the selector re-originating `TRANSIENT_LOCAL` durability for the
forwarded catalogue, making its outbound writer cache the one durable thing in the
process. That does not survive the web side being `BEST_EFFORT`: **`TRANSIENT_LOCAL`
delivers historical samples to a late joiner only if both the writer and the reader
are `RELIABLE`** (verified against 7.7.0 — §10). A best-effort reader would get
nothing from a durable writer, so durability there would be decoration.

The catalogue is therefore **served on request** (§4.4), and what remains inside the
selector is one Connext-owned cache on the **field** side:

- **The store is Connext-owned, not application-owned.** A `RELIABLE` +
  `TRANSIENT_LOCAL` + `KEEP_LAST 1` reader on a `@key uid` topic holds exactly one
  sample per tag, which *is* the catalogue. There is no
  `unordered_map<int32_t, MetaData>` in this component, and adding one would be the
  actual violation of DD-024.
- **It is a copy, not a merge.** Nothing joins it to values (§3.2).
- **Restart recovery is the startup path.** The reader re-receives the catalogue
  from the sim — which is reliable and durable — so there is no separate recovery
  code and no window where the selector has forgotten the catalogue while running.

This is strictly simpler than the durable-writer design it replaces: one cache
instead of two, no durability on the web side, and no "empty catalogue during a
selector restart" window to reason about. What it costs is that scada-web must
**ask** rather than merely subscribe — and must retry until its map is populated,
which is the property a best-effort reply needs in order to be trustworthy.

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
[`dds/idl/PlcValue.idl`](../../dds/idl/PlcValue.idl). It is the residue of
[OQ-20](../../docs/questions.md#oq-20): the intended end state is one IDL with two automated
derivations — `rtiddsgen` for this component, `rtiddsgen -convertToXml` for the
types library scada-web loads — so nothing is hand-transcribed. Until that is
wired, prefer pointing `CMakeLists.txt` at `../dds/idl/PlcValue.idl` over keeping a
second copy in sync by hand.

### 3.8 The Real-Time Boundary

[DD-028](../../docs/design-decisions.md#dd-028). The selector is the conduit
between two zones with **different timing contracts**, and it is the only conduit:

| | Field side (hard real time) | Web side (soft real time) |
|---|---|---|
| Participants | sim L1 publishers, selector readers | selector writers, scada-web, browsers |
| Timing contract | Bounded, deterministic latency; a missed deadline is a **failure** | Latency is a *target*; a late or dropped display update is a **degradation** |
| **Reliability** | **`RELIABLE`** | **`BEST_EFFORT`** ([DD-029](../../docs/design-decisions.md#dd-029)) — except inbound `ValueRequest` |
| Data representation | Compiled types | `DynamicData`, then JSON |
| Transport | DDS/UDP, one plant network | DDS, then TCP/WebSocket to browsers |
| Volume | Full scan rate, batched | Selected uids, downrated (§3.3) |
| Failure appetite | None — this side runs the process | Tolerant — a browser can miss a frame |

**The invariant that makes the boundary real: nothing on the soft side may
back-pressure the hard side.** A boundary that propagates congestion upstream is
not a boundary; it is a coupling with a diagram drawn around it.

**`BEST_EFFORT` on the web side is what enforces this, and it enforces it by
construction.** A best-effort writer has no send window to exhaust, no
unacknowledged samples to retain, and no ACK to wait for, so there is no state in
which it blocks waiting for a slow consumer. The failure mode is not mitigated; it
is absent. Three rules remain, now as defense in depth rather than as the guarantee
itself:

1. **Outbound writers still use `KEEP_LAST`, never `KEEP_ALL`.** Under DD-029 this
   is belt-and-braces — it documents intent and it is what would keep the invariant
   if reliability were ever raised on this side. It mattered absolutely under the
   earlier `RELIABLE` design: a `RELIABLE` + `KEEP_ALL` writer whose resource
   limits fill **blocks in `write()`** on the dispatch thread, which stops draining
   the inbound reader, whose cache overflows — a stalled browser degrading
   field-side reception. Keep the rule; the reason it is cheap now is that
   `BEST_EFFORT` already removed the mechanism.
2. **`max_blocking_time` is short, and a timeout is a drop.** Log it, count it,
   continue. Never retry inside the dispatch callback — that converts one late
   sample into a stalled loop.
3. **`ASYNCHRONOUS_PUBLISH_MODE` with a `FlowController`** is no longer needed for
   isolation, only for burst shaping if measurement shows the send path intruding
   on the read path. Lower priority than it was.

**What `BEST_EFFORT` costs, stated plainly.** Loss on the web side is invisible to
the receiver: scada-web cannot infer what never arrived, so the selector must count
what it wrote. The sharper cost is §3.4's — **a lost dispose is never repeated**,
so "this tag went away" becomes an inference rather than an event, and scada-web
must treat sample absence as staleness. Whether a `BEST_EFFORT` reader's
`SampleLostStatus` reports useful gap information here is **unverified**; do not
design on it without checking.

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
4. Field side:  IdValue reader     — RELIABLE, matches the sim's writer QoS
                MetaData reader    — RELIABLE + TRANSIENT_LOCAL + KEEP_LAST 1
5. Web side:    ValueRequest reader   — RELIABLE + KEEP_ALL   (DD-023, the exception)
                SelectedValue writer  — BEST_EFFORT + VOLATILE + KEEP_LAST  (DD-029)
                SelectedMetaData writer
                                  — BEST_EFFORT + VOLATILE + KEEP_LAST 1
6. Attach ReadConditions to one WaitSet: control, then metadata, then data
7. dispatch() loop until SIGINT/SIGTERM
```

Start order versus the sim does not matter: the selector starts with an empty table
and turns tags on as requests arrive, `IdValue` is `VOLATILE` so there is no backlog
to mis-handle, and `MetaData` is `RELIABLE` + `TRANSIENT_LOCAL` on the field hop so
a selector that starts after the sim still receives the whole catalogue.

**Start order versus scada-web does matter, and only for the catalogue.** Because
the web side is `BEST_EFFORT` ([DD-029](../../docs/design-decisions.md#dd-029)), a
scada-web that starts after the selector receives no history — it gets values within
one publish period, since values are periodic, but the catalogue is written once and
will not come round again. That is what makes the catalogue request-driven (§4.4):
scada-web asks when it is ready, and retries until its map is populated.

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

**And under [DD-029](../../docs/design-decisions.md#dd-029) it is the *primary*
bootstrap path, not a fallback.** An earlier draft called it secondary, on the
assumption that `TRANSIENT_LOCAL` would deliver the catalogue to a late joiner
without asking. With the web side `BEST_EFFORT` that is not available — durable
delivery requires reliability on both ends — so this command is how the catalogue
gets across at all. It needs a sentinel `uid` meaning "all" to bootstrap (§4.4).

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
sim (once at startup, RELIABLE + TRANSIENT_LOCAL)
    │
    ▼  PLC::MetaData
metadata_reader.read()        ← read(), NOT take() — see below
    │                            the reader cache IS the catalogue (§3.6)
    ├─ on arrival: forward every uid, unmodified, unfiltered by the table
    │
    └─ on request: ValueRequest{command=METADATA, uid} → re-read that instance
       (or the sentinel uid meaning "all" → the whole catalogue)
    │
    ▼  selected_metadata_writer.write(data())
    │
    ▼  PLC::SelectedMetaData (BEST_EFFORT + VOLATILE — DD-029)
scada-web: uid→metadata map  (its own state, DD-024 unchanged)
           retries what it did not get
```

**The request path is the bootstrap path, not a fallback.** This inverts what an
earlier draft said, and the reason is
[DD-029](../../docs/design-decisions.md#dd-029): with the web side `BEST_EFFORT`,
durability cannot deliver the catalogue to a late-joining scada-web, so *asking* is
the only mechanism that works. Two properties make it sound:

- **The ask itself is reliable.** `ValueRequest` is the one `RELIABLE` channel on
  the web side (§6), so the request cannot be silently lost even though the reply
  can.
- **The requester knows what it asked for**, so a lost reply is detectable and
  re-askable. That is exactly what durability would *not* have given scada-web, and
  it is why request/reply beats the alternatives here (the
  `on_publication_matched()` republish trick races and is not a documented
  mechanism; periodic re-announce pays continuously for a startup problem).

**Bootstrapping needs a "give me everything" request.** A per-uid request cannot
bootstrap, because scada-web does not know the uid list until it *has* the
catalogue. So `Command_t::METADATA` needs a **sentinel `uid` meaning "all"** — a
semantic addition to an existing field, not an IDL change; no new field, no new
type. The concrete value (`-1` or `0`) is a contract detail for whoever implements
it first, and it should be written into
[system-architecture.md](../../docs/system-architecture.md) §4.1 when chosen.

Four further decisions in that short path:

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

**Durability is *not* carried across the boundary.** `RELIABLE` +
`TRANSIENT_LOCAL` + `KEEP_LAST 1` inbound, `BEST_EFFORT` + `VOLATILE` outbound
([DD-029](../../docs/design-decisions.md#dd-029)). Making the outbound topic durable
would be decoration: a best-effort reader receives no historical samples from a
durable writer, so the durability would cost cache and buy nothing. If the
request/reply bootstrap ever proves fiddly, the one-line alternative is to make this
single topic `RELIABLE` + `TRANSIENT_LOCAL` — a second stated exception, and RTI's
own suggested split of "catalogue reliable, live stream best-effort".

**Lifecycle transitions use the §3.4 path, with §3.4's new caveat.** A disposed tag
must retract from the catalogue, or scada-web's map keeps a tag the plant no longer
has. Same `dispose_instance` / `unregister_instance` mapping, same nil-handle guard,
and no rate limit — metadata has no rate limit to bypass. But a retraction can be
**lost** on a best-effort link and is never repeated, so the catalogue converges by
scada-web re-asking, not by the retraction being guaranteed. A periodic re-ask is
the cheapest way to bound how long a stale catalogue entry can survive.

---

## 5. State Model

The whole of the selector's state:

| State | Type | Lifetime | Bounded by |
|---|---|---|---|
| Selection table | `unordered_map<int32_t, TagState>` | Process | Tag count |
| Reader caches | Connext-owned | Per QoS | `History` depth × instances |
| `MetaData` reader cache | Connext-owned | Process | Tag count (`RELIABLE` + `TRANSIENT_LOCAL` + `KEEP_LAST 1`, keyed) — **load-bearing**, §4.4 |

The third row is new with [DD-028](../../docs/design-decisions.md#dd-028) and is the
reason §3.6's title changed from "no durable state" to "no *application* state". It
is a **field-side reader** cache, not an outbound durable writer: an earlier draft
had a fourth row for a `TRANSIENT_LOCAL` `SelectedMetaData` writer, which
[DD-029](../../docs/design-decisions.md#dd-029) removed — durability on a
best-effort link delivers nothing to a late joiner, so the catalogue is served on
request instead. One cache, on the reliable side, is the whole of it.

The distinction is not pedantry — it is the line that keeps DD-024 intact:

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

Types are in [`dds/idl/PlcValue.idl`](../../dds/idl/PlcValue.idl). Contracts in
[system-architecture.md](../../docs/system-architecture.md) §4.

**The two sides have different reliability contracts**
([DD-029](../../docs/design-decisions.md#dd-029)). The field side is reliable
because it runs the process; the web side is not, because it draws pictures of it.

| Side | Topic | Role | Type | Reliability | Durability | History |
|---|---|---|---|---|---|---|
| Field | `PLC::IdValue` | Read (data in) | `IdValue` | `RELIABLE` | `VOLATILE` | `KEEP_LAST`, shallow |
| Field | `PLC::MetaData` | Read (catalogue in) | `MetaData` | `RELIABLE` | **`TRANSIENT_LOCAL`** | `KEEP_LAST 1` |
| Web | `PLC::ValueRequest` | Read (control in) | `ValueRequest` | **`RELIABLE` + `KEEP_ALL`** — the exception | `VOLATILE` | `KEEP_ALL` |
| Web | `PLC::SelectedValue` | Write (data out) | `IdValue` | **`BEST_EFFORT`** | `VOLATILE` | `KEEP_LAST` |
| Web | `PLC::SelectedMetaData` | Write (catalogue out) | `MetaData` | **`BEST_EFFORT`** | `VOLATILE` | `KEEP_LAST 1` |

Four QoS choices worth arguing rather than inheriting:

- **`BEST_EFFORT` outbound is what makes §3.8's invariant structural.** A
  best-effort writer has no send window to exhaust, no unacknowledged samples to
  retain, and no ACK to wait for, so it cannot block on a slow consumer at all.
  `KEEP_LAST` stays as defense in depth and as a statement of intent, but it is no
  longer the thing carrying the guarantee.
- **`RELIABLE` + `KEEP_ALL` inbound on `ValueRequest` is the one exception, and it
  is safe.** Operator intent on an unkeyed command stream does not self-heal — a
  lost `ADD` means a tag silently never turns on
  ([DD-023](../../docs/design-decisions.md#dd-023)). A reliable *reader* also
  cannot block the dispatch thread; only writers block. The direction of the
  exception is what makes it free.
- **A shallow `KEEP_LAST` on the inbound `IdValue` reader is defensible** —
  arguably preferable — because the data plane discards most samples anyway
  (§3.3). Depth is tuning here; dropping stale values is intended. The inbound
  **`MetaData`** reader is the opposite case: its cache is load-bearing (§4.4), so
  `RELIABLE` + `TRANSIENT_LOCAL` + `KEEP_LAST 1` is required, and `read()` rather
  than `take()` keeps it populated.
- **The outbound side no longer mirrors the inbound, and that is the point.**
  Earlier drafts said each output should mirror its input; DD-029 deliberately
  breaks that for reliability and durability, because the two sides have different
  jobs. What still must not change is the **type** and the **field values** — that
  is what §3.2 protects, and QoS is not part of the data model.

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
| Integration | Late-joining scada-web | Start sim → selector → *then* the subscriber. Confirm the **negative** result first: with no request, the catalogue does **not** arrive (best-effort, no durability — DD-029). Then confirm the sentinel `METADATA` request delivers it in full |
| Integration | Catalogue bootstrap is retryable | Drop or ignore the first reply; confirm a second request repopulates. This is what makes a best-effort reply trustworthy (§4.4) |
| Integration | Selector restart | Kill and restart the selector with the sim running; confirm the field-side catalogue is re-read and a subscriber that re-asks converges |
| Integration | `METADATA` command | Send `Command_t::METADATA` for one uid; confirm exactly that instance is republished. Then the sentinel uid; confirm the whole catalogue (§4.2) |
| Integration | Lost dispose | Force loss of a forwarded dispose; confirm scada-web's **staleness timeout** catches it, since the retraction will not be repeated (§3.4) |
| **Boundary** | **No upstream backpressure** | Stall or SIGSTOP the `SelectedValue` subscriber under load; confirm field-side reception at the selector is **unchanged** — inbound rate and cache occupancy flat, drops attributed outbound. Under DD-029 this should pass trivially, since a best-effort writer cannot block; run it anyway, because it is what would catch reliability being raised on this side later |
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

**Write the catalogue-bootstrap tests first.** That is a change from the previous
draft, which put the backpressure test first — [DD-029](../../docs/design-decisions.md#dd-029)
demoted it, because `BEST_EFFORT` removes the mechanism it was hunting for rather
than merely constraining it. Keep it as a regression guard against reliability being
raised here later. The bootstrap path is now the fragile part: it is the one place
where the system depends on an application-level retry loop rather than on
middleware guarantees, and the failure — an empty or partial tag catalogue — is both
silent and easy to mistake for "no tags configured".

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
| [OQ-25](../../docs/questions.md#oq-25) | Keep the WIS polling surface on a shared reader? | Its recommended option A is now the only coherent one: `BEST_EFFORT` + `VOLATILE` + `KEEP_LAST 1` is a current-value stream, so take-once queue semantics have nothing to take from ([DD-029](../../docs/design-decisions.md#dd-029)) |
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
- **Per-key reliability classes** — post-PoC, and the implementation lands mostly
  here even though the roadmap entry lives with scada-web
  ([scada-web-architecture.md](../../scada_web/docs/scada-web-architecture.md)
  §9.1). Shape: `ValueRequest` gains a class per uid, the selector holds one
  outbound writer per class, and critical tags route to a `RELIABLE` topic while
  everything else stays best-effort. **The work is not the QoS line — it is
  isolating that writer so it cannot block the dispatch thread**, which is precisely
  the coupling [DD-029](../../docs/design-decisions.md#dd-029) removed by going
  best-effort. Read §3.8 before starting. A cheaper alternative to evaluate first is
  per-key gap detection with re-request over the still-reliable control channel,
  which needs no reliable data writer at all.
- **Instance-handle selection**, if and only if §8's measurement justifies it.
- **Alarm limit evaluation** is *not* future work here. It is a model change
  ([OQ-14](../../docs/questions.md#oq-14)) and §3.2 keeps it out.

---

## 10. Sources

- [system-architecture.md](../../docs/system-architecture.md) §1a, §2, §4, §7, §9 — roles, topology, contracts, build order
- [scada-selector-implementation.md](scada-selector-implementation.md) — CMake, generated type shape, verified selector core, rate control, what "efficient" buys
- [architecture-comparison.md](../../docs/architecture-comparison.md) — why Routing Service is not used
- [design-decisions.md](../../docs/design-decisions.md) — [DD-023](../../docs/design-decisions.md#dd-023), [DD-024](../../docs/design-decisions.md#dd-024), [DD-026](../../docs/design-decisions.md#dd-026), [DD-027](../../docs/design-decisions.md#dd-027), [DD-028](../../docs/design-decisions.md#dd-028), [DD-029](../../docs/design-decisions.md#dd-029)
- [Ensuring Information is Available to Late-Joining Applications](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/users_manual/users_manual/Ensuring_Information_is_Available_to_Lat.htm) and [KB: Why does my DataReader miss the first few samples?](https://community.rti.com/kb/why-does-my-dds-datareader-miss-first-few-samples) — **`TRANSIENT_LOCAL` late-joiner delivery requires `RELIABLE` on both writer and reader.** Verified via Connext AI; this is what makes the §4.4 catalogue request-driven rather than durable
- [dds/idl/PlcValue.idl](../../dds/idl/PlcValue.idl) — the type and command contract
- [scada-web-architecture.md](../../scada_web/docs/scada-web-architecture.md) — the Role 2 counterpart (colocated under `scada_web/docs/` in a parallel change)
- [Connext 7.7.0 Modern C++ API reference](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/api/connext_dds/api_cpp2/index.html) — the `api_cpp2` tree is the Modern API; `api_cpp` is the Traditional one
- [`DataWriter` (Modern C++)](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/api/connext_dds/api_cpp2/classdds_1_1pub_1_1DataWriter.html) — `dispose_instance` / `unregister_instance` / `lookup_instance`
- **Validation:** the §3.4 lifecycle mapping and the §4.3 data-plane loop were checked against the Connext 7.7.0 C++11 API via Connext AI (`validate_modern_cpp_code`) and returned valid as written. Not the same as compiled-and-run — impl notes §3 is the verified-by-building material.
