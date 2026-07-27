# scada_web — System Architecture

**Status:** Draft v0.1
**Date:** 2026-07-27
**Scope:** the whole deliverable — four components, not just the web gateway.

[technical-requirements.md](technical-requirements.md) specifies **scada-web**
alone. This document places it in the system and defines the contracts between
components. Where the TRD's §4 layer diagram describes the *inside* of
scada-web, this describes the *outside*.

> **Hosting:** both scada-selector and scada-web are **standalone C++ services**;
> Routing Service is not used. Role 1 is settled by the compiled-types requirement
> ([DD-026](design-decisions.md#dd-026)); Role 2 awaits sign-off on
> [OQ-23](questions.md#oq-23), analyzed in
> [architecture-comparison.md](architecture-comparison.md). The topic contracts in
> §4 hold either way.

---

## 1. Components

| # | Component | Purdue level | Language | Status |
|---|---|---|---|---|
| 1 | **scada-sim** — simulated field process + PLC/RTU | 0–1 | Python | Exists ([sim/](../sim/)) |
| 2 | **scada-selector** — key-based selection | 2 | C++ standalone, **compiled types** ([DD-026](design-decisions.md#dd-026)) | Not started |
| 3 | **scada-web** — web gateway + mapping engine | 2 | C++ standalone, **DynamicData** ([DD-002](design-decisions.md#dd-002)) | Not started |
| 4 | **browser interface** — HMI | 2 | Web — [OQ-16](questions.md#oq-16) | Not started |

Per the [scada-sme](../.github/agents/scada-sme.agent.md) guidance on ISA-95
level separation, no component reaches across a level boundary: the browser never
speaks DDS, and scada-web never speaks to the simulated process.

---

## 1a. Roles

Two roles carry the system. Stating them precisely matters, because the boundary
between them was drawn in the wrong place in v0.1 (see §6.2).

### Role 1 — selection: "which tags flow, and how often"

**Component: scada-selector.** Receives requested ids **and rates**, and gates the
value stream on both. **Pure selection: it does not touch the data model.**
Samples that pass through are byte-for-byte the same type that went in.

- Input: the subscription request topic (uid, enabled, rate), `IdValue`
- Output: `IdValue` on a selected topic — **same type, different topic name**
- State: per-uid `{enabled, period, last_emitted}`
- Not its job: JSON, HTTP, view schemas, correlation, alarm logic

Selection has **two dimensions**, and the rate axis matters as much as the id
axis ([DD-027](design-decisions.md#dd-027)): it is what keeps the volume reaching
scada-web's `DynamicData` reader small enough for that representation to be
affordable. Batched small samples are measurably expensive to receive as
`DynamicData` — Connext unpacks a batch and deserializes each sample
individually, so batching cuts network overhead but concentrates per-sample cost
into a burst. Downrating removes the burst before any `DynamicData` reader sees it.

### Role 2 — presentation: "what the web sees, and how"

**Component: scada-web.** Two responsibilities that travel together because both
are about the boundary between DDS and the web:

- **Model transformation** — project the wire model down to a slimmer view
  schema: rename, flatten, drop, unit-convert, resolve unions to scalars.
- **Protocol conversion** — DynamicData ⇄ JSON, REST, WebSocket.

- Input: filtered `IdValue`, plus `MetaData` for descriptions (§6.2)
- Output: JSON over REST/WebSocket
- State: per-client interest, uid→metadata map
- Not its job: deciding which uids exist in the system

### The distinction that is easy to blur

Both roles "filter", but at different levels, and conflating them is how the web
tier ends up with a DataReader per client:

- **scada-selector does system-level selection** — which uids enter the pipeline at
  all, once, for everyone.
- **scada-web does per-client routing** — which of those already-flowing samples
  go to which connected client (SR-004).

The first is a DDS concern and belongs upstream. The second is a connection
concern and can only be done where the connections are.

### Architecture recommendation per role

| Role | Component | Host | Types | Why |
|---|---|---|---|---|
| Selection | scada-selector | **Standalone C++** | **Compiled** (rtiddsgen from `PlcValue.idl`) | High-rate stream: the key check must be a struct field access, not a name lookup. Rules out a Routing Service Processor, whose built-in DDS adapter is DynamicData-based ([DD-026](design-decisions.md#dd-026)). |
| Presentation | scada-web | **Standalone C++** | **DynamicData** ([DD-002](design-decisions.md#dd-002)) | Must handle types it has never seen. REST reads are DataReader semantics — state masks, SQL filters, long-poll WaitSets — which Routing Service has no request/reply primitive to serve. |

**The two roles have deliberately opposite type strategies**, and each is right
for its role: Role 1 handles one known type as fast as possible; Role 2 handles
arbitrary types it was never compiled against. One IDL, two automated
derivations — `rtiddsgen` for the selector, `rtiddsgen -convertToXml` for the XML
types library scada-web loads at runtime — so nothing is hand-transcribed and
nothing drifts ([OQ-20](questions.md#oq-20)).

**Routing Service is therefore not used.** A real loss — its remote
administration and monitoring were the strongest argument for involving it, and
both components must now supply their own. It follows from two independent
requirements: compiled types for Role 1, DataReader read semantics for Role 2.

Full analysis in [architecture-comparison.md](architecture-comparison.md);
tracked as [OQ-23](questions.md#oq-23). Build configuration and hot-path patterns
for Role 1 are in
[scada-selector-implementation.md](scada-selector-implementation.md), verified by
building and running against the local 7.7.0 install.

**Considered and rejected for Role 1: no code at all.** Routing Service supports
content filters on inputs, and remote administration supports `UPDATE` on an
Input — so the enable set could in principle be a dynamically rewritten filter
expression. It collapses past a few dozen tags: the expression becomes
`uid = 1 OR uid = 2 OR ...`, rewritten on every operator action, with expression
length limits and re-evaluation cost. A hash-set lookup on a compiled key field is
simpler and bounded.

---

## 2. Topology

```
  ┌──────────────────────────────────────── Level 0/1 ─────┐
  │  scada-sim                                             │
  │    field_simulation.py   (Level 0 — process, no DDS)   │
  │    plc_publisher.py      (Level 1 — scan loop, DDS)    │
  └────────────────┬───────────────────────────────────────┘
                   │
      PLC::MetaData  (@key uid · RELIABLE · TRANSIENT_LOCAL · once at startup)
      PLC::IdValue   (@key uid · RELIABLE · VOLATILE · periodic)
                   │
                   ▼
  ┌──────────────────────────────────────── Level 2 ───────┐
  │  scada-selector   ROLE 1: select by id AND rate        │
  │    • compiled types — absorbs the batched full stream  │
  │    • per-uid {enabled, period, last_emitted}           │
  │    • republishes — same type, unmodified, downrated    │
  └────────┬──────────────────────────────────▲────────────┘
           │                                  │
   PLC::SelectedValue                  subscription request
   (IdValue type, selected + downrated)  (uid · enabled · period_ms)
           │                                  │
           │        ┌── PLC::MetaData ────────┼── (direct, TRANSIENT_LOCAL)
           ▼        ▼                         │
  ┌──────────────────────────────────────────┴────────────┐
  │  scada-web         ROLE 2: presentation                │
  │    • readers on SelectedValue + MetaData; one writer   │
  │      on ValueRequest — fixed, small entity set         │
  │    • uid→metadata map: tag catalogue + view lookup     │
  │    • refcounts uid interest across clients             │
  │    • mapping engine: wire type → slim view schema      │
  └────────────────┬──────────────────────────────────────┘
                   │  REST + WebSocket (JSON)
                   ▼
  ┌───────────────────────────────────────────────────────┐
  │  browser interface — mimic, trends, alarm banner       │
  └───────────────────────────────────────────────────────┘
```

---

## 3. Why scada-selector exists

**It moves per-client data selection out of the web tier and into DDS, where it
happens once for all clients.**

Without it, scada-web would give each web client its own content-filtered
DataReader so that clients only receive the tags they asked for. That is the
expensive design, and the cost is not primarily threads:

- **DDS entity explosion.** 100 clients with different tag selections means 100
  readers, 100 sets of discovery traffic, and 100 queues.
- **Repeated filter evaluation.** A content filter is evaluated per sample per
  reader inside the middleware. Ten readers interested in overlapping tags
  evaluate overlapping predicates ten times.
- **Churn.** An operator opening a mimic screen creates and destroys readers,
  which means discovery churn on every navigation.

With scada-selector, scada-web holds **one** reader and **one** writer regardless
of client count. Selection is expressed as data (`ValueRequest`) rather than as
DDS entities. See [DD-020](design-decisions.md#dd-020).

---

## 4. Topic contracts

### 4.1 Subscription request — scada-web → scada-selector

Current type in [sim/PlcValue.idl](../sim/PlcValue.idl), with `period_ms` added
for [DD-027](design-decisions.md#dd-027):

```idl
enum Command_t { ADD, DELETE, METADATA };

struct ValueRequest {
    UniqueId_t     uid;         // long
    Name_t         name;        // string<32>
    Command_t      command;
    unsigned long  period_ms;   // 0 = every sample
};
```

| Command | Meaning | `period_ms` |
|---|---|---|
| `ADD` | Enable `uid` on the output topic | Max publish rate for this uid; `0` = every sample. Re-sending `ADD` for an already-enabled uid **updates its rate**. |
| `DELETE` | Disable `uid` | Ignored |
| `METADATA` | Re-publish `MetaData` for `uid` | Ignored |

Instance lifecycle notifications (dispose/unregister) are **not** rate limited —
see [scada-selector-implementation.md](scada-selector-implementation.md) §3.1.

> **Still open: whether this should be keyed desired state instead of a command
> stream.** [OQ-17](questions.md#oq-17) and [OQ-24](questions.md#oq-24) recommend
> `@key uid` with `{enabled, period_ms}` and `TRANSIENT_LOCAL` durability, which
> would be idempotent and let a restarted selector recover its whole subscription
> set from the middleware. Adding `period_ms` did not take that step, so **both
> consequences still stand**: [DD-023](design-decisions.md#dd-023)'s
> `RELIABLE + KEEP_ALL` remains required, and SR-003 reconciliation remains
> required. Deciding those two questions is what would retire them.

**`ValueRequest` has no `@key`, so it is a single-instance command stream. Its
QoS must be `RELIABLE` + `KEEP_ALL`.** With `KEEP_LAST depth=1` — the QoS the sim
uses for its other topics — a rapid `ADD(1) ADD(2) ADD(3)` sequence can have
unacknowledged samples replaced before delivery, because `KEEP_LAST` permits the
writer to discard history. Reliability guarantees the *last* sample arrives, not
every sample. The failure is silent and load-dependent: tags simply never turn
on, most likely when an operator opens a screen with many tags at once. See
[DD-023](design-decisions.md#dd-023).

`name` is redundant with `uid` for `ADD`/`DELETE`. Retained for
human-readable logging, and potentially for name-based lookup when a client knows
a tag name but not its uid — see [OQ-13](questions.md#oq-13).

### 4.2 `PLC::SelectedValue` — scada-selector → scada-web

**No new type.** The filtered stream reuses the existing `IdValue` type on a
different topic name. Role 1 is selection, so the type that comes out is the type
that went in.

This is a change from v0.1, which defined an enriched `EnabledValue` carrying
`longName`, `hostname`, and `limits` alongside the value. See §6.2 for why that
moved; [DD-024](design-decisions.md#dd-024) records the decision.

Consequences worth noting, because they are all simplifications:

- **No type to keep in sync** across components. This shrinks
  [OQ-20](questions.md#oq-20) to almost nothing — there is no `EnabledValue`
  definition to duplicate or drift.
- **No denormalization.** v0.1 repeated static metadata on every sample; that
  cost is gone.
- **A Routing Service route can express it directly** — input topic `IdValue`,
  output topic `SelectedValue`, same registered type — which is what makes the
  Processor recommendation in §1a clean.

### 4.3 `PLC::MetaData` — read directly by scada-web

scada-web subscribes to `MetaData` itself rather than receiving it second-hand.
`TRANSIENT_LOCAL` means a late-joining scada-web still gets every tag's
description, so the uid→metadata map is populated regardless of start order.

That map serves two purposes at once, which is the main argument for this
placement (§6.2): the **tag catalogue** scada-web needs anyway for name-based
lookup ([OQ-13](questions.md#oq-13)), and **view enrichment** for the mapping
engine.

### 4.4 Unchanged

`PLC::MetaData` and `PLC::IdValue` keep the QoS the sim already uses:
`TRANSIENT_LOCAL` for MetaData, `VOLATILE` for IdValue because the process moves on.

---

## 5. scada-web's remaining state

The filter app removes DDS entity churn but introduces one piece of state in
scada-web that must be right:

**Interest refcounting.** Clients A and B both display tag `uid=5`. A closes its
screen. scada-web must **not** send `DELETE(5)` — B is still watching. So
scada-web maintains a per-uid refcount across all connected clients, sending
`ADD` on 0→1 and `DELETE` on 1→0.

This is a small amount of code and a well-known source of bugs. Requirements:

- **SR-001** scada-web MUST refcount uid interest across clients, enabling a uid
  on the 0→1 transition and disabling it on 1→0.
- **SR-001a** Interest is **not just a count** — it carries a rate
  ([DD-027](design-decisions.md#dd-027)). Two clients watching one tag at 1 Hz
  and 10 Hz means the selector must be told the **fastest** requested rate, so
  the aggregate is `max(rate)` over interested clients, recomputed whenever a
  client joins, leaves, or changes rate. scada-web MAY decimate further per client
  from that shared stream. Getting this wrong is silent: the slow client is fine
  and the fast one is merely sluggish, so it will not show up in a smoke test.
- **SR-002** Abrupt client disconnection MUST decrement that client's interest and
  recompute the aggregate rate. A dropped TCP connection is the normal case, not
  the exceptional one.
- **SR-003** scada-web MUST reconcile its full interest set after scada-selector
  restarts, since the selector's state is in-memory and does not survive.
  Detect via liveliness on `SelectedValue` and re-send the current set.
  **This requirement disappears** if the subscription topic becomes keyed desired
  state with `TRANSIENT_LOCAL` durability (§4.1) — the middleware replays the set
  and no reconciliation protocol is needed.
- **SR-004** Because the output topic carries the **union** of all clients'
  interests ([OQ-12](questions.md#oq-12)), scada-web MUST demultiplex per client
  and MUST NOT forward a sample to a client that did not request its uid. This is
  a per-client set membership test, not a DDS filter.

SR-003 is the one most likely to be missed. Its symptom is a permanently blank
display after a filter restart, with no error anywhere.

---

## 6. Consequences for the mapping engine

Two findings that change the TRD's §6 priorities. Both come from the actual IDL
rather than from speculation, which is why they were not visible when the TRD was
drafted.

### 6.1 Unions are the central case, not an edge case

Every value in this data model is a `Value_t` — a union discriminated on
`ValueKind_t` over string, int32, int64, float32, float64. `IdValue` has two of
them; `Limits_t` has six.

So the mapping engine's **primary** job here is projecting a discriminated union
to a JSON scalar: `smoothedValue` → `72.4`. FR-XF-005 (unions and
discriminators) was written as a completeness requirement; it is in fact the
first thing the engine must do, and it must work before anything else is
demonstrable. Raised to P1 in the TRD.

Two IDL details the engine must handle concretely:

- **`stringValue` is `char[32]`, not `string<32>`.** A char array serializes to
  JSON as an array of single-character strings, which is not what any client
  wants. The mapping engine needs an explicit char-array→string decode, with
  NUL-trimming. [sim/plc_types.py](../sim/plc_types.py) already documents this
  and works around it on the publish side; the view needs the inverse. This is a
  concrete instance of FR-TYPE-005.
- **`KIND_FLOAT32` is declared as IDL `double`.** Preserved deliberately in the
  sim to match the real IDL. Consequence: float32 and float64 are
  indistinguishable on the wire, so a view must not claim to report which one it
  received. Worth noting in the published view schema rather than silently
  papering over.

### 6.2 Correlation: reference-data lookup, not a join

A useful HMI view is `{tag, value, units, limits, alarm_state}` — spanning
`IdValue` (value) and `MetaData` (longName, limits), correlated on `uid`. That
looked like the `latest_value` join of FR-XF-022, the feature
[OQ-4](questions.md#oq-4) recommended deferring.

**v0.1 put that correlation in scada-selector** as enrichment
([DD-021](design-decisions.md#dd-021)), to keep join out of the engine. The role
clarification in §1a shows that was the wrong boundary: enrichment is data-model
work, and it makes the model *fatter*, while Role 2's job is to make it *slimmer*.
Fattening in one component so the next can slim it is incoherent, and it put
model concerns in a component whose role is selection.

**Corrected placement:** scada-web subscribes to `MetaData` directly and holds the
uid→metadata map. See [DD-024](design-decisions.md#dd-024).

The decisive argument is that **scada-web needs this map anyway.** It is the tag
catalogue required for name-based lookup ([OQ-13](questions.md#oq-13)). Under the
v0.1 design scada-web would have held the catalogue *and* received the same
metadata repeated on every value sample — the same data twice, one copy
denormalized.

**This is not a general join, and should not be built as one.** It is a narrower
mechanism worth naming separately:

| | Reference-data lookup | General join (FR-XF-022) |
|---|---|---|
| Source | A keyed, slowly-changing topic | Any stream |
| Correlation | Single key, exact match | Declared key expression |
| Time semantics | None — latest known value | Windows, staleness policy |
| Direction | Read-only context | Participates in the view both ways |
| State | One map, bounded by tag count | Per-key cache with eviction |

`MetaData` is `TRANSIENT_LOCAL` and written once at startup, so "latest known
value" is unambiguous and the map is bounded by tag count. That is a materially
easier problem than FR-XF-022, and it keeps OQ-4's answer intact: **general join
stays out of the v1 engine.** The DSL gains a `<lookup>` construct — see
[mapping-dsl.md](mapping-dsl.md) §3.8 — rather than multi-`<input>` support.

**Revisit if** a correlation appears that needs time semantics or a non-static
source. That is a real join and reopens OQ-4.

---

## 7. Component responsibilities

Kept explicit so behavior does not drift into whichever component is being
edited.

| Concern | Role | Owner | Not |
|---|---|---|---|
| Process simulation | — | scada-sim L0 | — |
| Tag scan and publish | — | scada-sim L1 | — |
| Which tags flow at all | 1 | **scada-selector** | scada-web (would mean a reader per client) |
| Data model changes of any kind | 2 | **scada-web** | scada-selector — Role 1 is selection only |
| uid→metadata lookup | 2 | **scada-web** | scada-selector (§6.2, corrected in DD-024) |
| Wire type → slim view schema | 2 | **scada-web** | — |
| DynamicData ⇄ JSON | 2 | **scada-web** | — |
| Per-client interest refcount | 2 | **scada-web** | scada-selector (it sees one aggregate consumer) |
| Per-client demux | 2 | **scada-web** | — |
| Tag catalogue / name lookup | 2 | **scada-web** | — same map as the view lookup |
| Alarm state machine | Unresolved — [OQ-14](questions.md#oq-14) | — see below |
| Trends / historian | Unresolved — [OQ-21](questions.md#oq-21) | — |
| Purdue zone enforcement | Logical only — [OQ-22](questions.md#oq-22) | Not enforced by DDS Security in the PoC |

**Alarm evaluation placement is unresolved.** `Limits_t` carries six thresholds
plus an `active` flag, so limit comparison could live in the filter (once, for
all clients), in the mapping engine (as a `<compute>` — the TRD's worked example
does exactly this), or in the browser. ISA-18.2 wants a real state machine
(Normal → Unacknowledged → Acknowledged → RTN) with deadbands, not a boolean
flip, and none of the three is an obviously right home for that. See
[OQ-14](questions.md#oq-14), which in turn depends on
[OQ-19](questions.md#oq-19): comparing a value against a limit means comparing two
`Value_t` unions whose discriminators may differ, and the promotion rules for that
are undefined today.

---

## 8. Threading, resolved

**The threading question is settled, but not solely by scada-selector.** Two
independent things resolve it, and it is worth separating them because the first
is often mistaken for the whole answer.

1. **scada-selector removes the per-client DDS cost** — no reader per client, no
   repeated filter evaluation, no discovery churn. This was the serious resource
   problem, and it is genuinely solved: scada-web's DDS entity count is now fixed
   and small.

2. **But it does not reduce connection count.** N browser clients are still N
   WebSocket sockets, and thread-per-connection still means N threads. The filter
   app does not touch that axis at all.

What actually retires the concern is that **the original 10,000-connection target
was the wrong requirement for this system.** It imported a web-scale assumption
into a plant-control context. The client population here is Level 2 operator
consoles and HMI displays — tens, plausibly low hundreds, not thousands.
Thread-per-connection is comfortable at that scale.

Taken together, [DD-009](design-decisions.md#dd-009) (async I/O) can be closed
rather than merely deferred, and [DD-019](design-decisions.md#dd-019)'s
thread-per-connection choice is now justified on the merits rather than as a
prototype shortcut. See [DD-022](design-decisions.md#dd-022).

One invariant survives regardless, from DD-019: **keep blocking DDS calls off the
mapping and serialization path.** Cheap now, expensive to retrofit.

---

## 9. Build order

Dependency-driven. The sim already exists, which means the filter can be built
and tested against real data immediately.

| Step | Work | Verifiable by |
|---|---|---|
| 1 | `rtiddsgen` C++ types from `PlcValue.idl`; topic name for `SelectedValue` (§4.2) | Compiles; resolves [OQ-12](questions.md#oq-12) |
| 2 | **scada-selector**: enable set, republish. No model changes | `rtiddsspy` on `SelectedValue` while driving `ValueRequest` by hand |
| 3 | **scada-web** engine (TRD §12 P1) — union→scalar projection first | Mapping CLI over JSON fixtures |
| 4 | **scada-web** DDS + web surface, incl. `MetaData` map and `<lookup>` | End-to-end to a test client |
| 5 | **browser**: tag table + trend (mimic is separate — [OQ-16](questions.md#oq-16)) | The demo |

Step 2 is independently demonstrable with no web tier at all, which makes it the
cheapest real progress available — and it shrank further under
[DD-024](design-decisions.md#dd-024), since the selector no longer caches or
merges metadata. Step 3 needs no DDS and no network. The two can proceed in
parallel.

Note that step 1 is now a build step rather than a design decision: there is no
new type to define, only generated code and a topic name
([DD-026](design-decisions.md#dd-026)).

---

## 10. Open questions raised by this document

| ID | Question | Priority |
|---|---|---|
| [OQ-12](questions.md#oq-12) | Shared union output topic, or one per client/session? | BLOCKING |
| [OQ-15](questions.md#oq-15) | What language and DDS API for scada-selector? | HIGH |
| [OQ-19](questions.md#oq-19) | Union comparison and promotion rules? | HIGH |
| [OQ-14](questions.md#oq-14) | Where does alarm limit evaluation and state live? | HIGH |
| [OQ-13](questions.md#oq-13) | Is name-based tag lookup required, or is `uid` sufficient? | MEDIUM |
| [OQ-16](questions.md#oq-16) | What stack for the browser interface? | MEDIUM |
| [OQ-17](questions.md#oq-17) | Should `ValueRequest` be keyed on `uid`? | MEDIUM |
| [OQ-20](questions.md#oq-20) | Single source of truth for `SelectedValue`? | MEDIUM |
| [OQ-21](questions.md#oq-21) | Are trends and a historian in scope? | MEDIUM |
| [OQ-18](questions.md#oq-18) | Should `ValueRequest` carry a `LIFESPAN`? | LOW |
| [OQ-22](questions.md#oq-22) | Enforce Purdue zones with DDS Security, or logically only? | LOW |
