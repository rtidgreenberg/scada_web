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

It is also **the system boundary**: the only component with DDS endpoints on both
the hard-real-time field side and the soft-real-time presentation side
([DD-028](design-decisions.md#dd-028)). That is why `MetaData` passes through it —
forwarded unmodified on its own topic, not merged into values.

- Input: the subscription request topic (uid, enabled, rate), `IdValue`, `MetaData`
- Output: `IdValue` on a selected topic and `MetaData` on a selected topic —
  **same types, different topic names**
- State: per-uid `{enabled, period, last_emitted}`, plus one field-side reader cache
  that holds the tag catalogue and answers `METADATA` requests
  ([DD-029](design-decisions.md#dd-029))
- Not its job: JSON, HTTP, view schemas, correlation, alarm logic, and — still —
  any uid→metadata *map*; it forwards metadata without interpreting it

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
[scada-selector-implementation.md](../scada_select/docs/scada-selector-implementation.md), verified by
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
  │  scada-sim                              HARD REAL TIME │
  │    field_simulation.py   (Level 0 — process, no DDS)   │
  │    plc_publisher.py      (Level 1 — scan loop, DDS)    │
  └────────────────┬───────────────────────────────────────┘
                   │
      PLC::MetaData  (@key uid · RELIABLE · TRANSIENT_LOCAL · once at startup)
      PLC::IdValue   (@key uid · RELIABLE · VOLATILE · periodic)
                   │                          ┌─────────────────────┐
                   │                          │  DDS DOMAIN 0       │
                   │                          │  (field)            │
                   ▼                          └─────────────────────┘
  ┌──────────────────────────────────────── Level 2 ───────┐
  │  scada-selector   ROLE 1: select by id AND rate        │
  │                   + THE SYSTEM BOUNDARY (DD-028)       │
  │    • compiled types — absorbs the batched full stream  │
  │    • per-uid {enabled, period, last_emitted}           │
  │    • republishes — same types, unmodified, downrated   │
  │    • forwards MetaData unmodified; serves the whole    │
  │      catalogue on METADATA request (no durability out) │
  │    • TWO DomainParticipants: field (0) and web (1)     │
  │      (DD-044)                                          │
  └════════┬═════════════════════════════════▲═════════════┘
    ═══════╪══════ hard RT ─│─ soft RT ══════╪═══════════════  ← the boundary
           │                                  │
   PLC::SelectedValue                  subscription request
   (IdValue · BEST_EFFORT · VOLATILE)    (uid · enabled · period_ms)
   PLC::SelectedMetaData                 (RELIABLE + KEEP_ALL — the
   (MetaData · BEST_EFFORT · on request)  one exception, DD-023/DD-029)
           │                                  │
           │                          ┌─────────────────────┐
           │                          │  DDS DOMAIN 1       │
           │                          │  (web)              │
           ▼                          └─────────────────────┘
  ┌──────────────────────────────────────────┴────────────┐
  │  scada-web         ROLE 2: presentation                │
  │    • readers on SelectedValue + SelectedMetaData; one  │
  │      writer on ValueRequest — fixed, small entity set  │
  │    • NO field-side endpoint — nothing on domain 0,     │
  │      not even discovery traffic (DD-044)               │
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

**Everything above the double line is hard real time; everything below is soft
real time; the selector is the only component in both zones**
([DD-028](design-decisions.md#dd-028)). The load-bearing consequence is directional:
soft-side congestion must never back-pressure the hard side.

**Domain isolation ([DD-044](design-decisions.md#dd-044)):** domain 0 (field)
carries sim↔selector traffic only; domain 1 (web) carries selector↔scada-web
traffic only. The selector bridges the two via separate participants. A
misconfigured scada-web cannot reach field topics — the middleware refuses the
match. Discovery traffic on each domain is minimal and scoped to the components
that belong there.

**The two zones also have different reliability contracts**
([DD-029](design-decisions.md#dd-029)): the field side is `RELIABLE`, the web side
is **`BEST_EFFORT`**, and inbound `ValueRequest` is the single stated exception —
operator intent on an unkeyed command stream does not self-heal, and a reliable
*reader* cannot block anything. Best-effort output is also what makes the
no-backpressure invariant structural rather than a matter of QoS discipline: a
best-effort writer has no send window to exhaust and cannot block on a slow
consumer. Detail in
[scada-select-architecture.md](../scada_select/docs/scada-select-architecture.md)
§3.8 and §6.

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

Current type in [dds/idl/PlcValue.idl](../dds/idl/PlcValue.idl), with `period_ms` added
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
see [scada-selector-implementation.md](../scada_select/docs/scada-selector-implementation.md) §3.1.

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

### 4.3 `PLC::MetaData` → `PLC::SelectedMetaData` — forwarded by scada-selector

> **Changed by [DD-028](design-decisions.md#dd-028).** This section previously read
> "read directly by scada-web". Metadata now crosses the boundary through the
> selector so that the selector can be the *only* thing that does. The **ownership**
> argument below is unchanged — scada-web still holds the map and does all the
> correlation.

The selector reads `MetaData` on the field side and republishes it unmodified as
`PLC::SelectedMetaData` on the web side. Type in = type out, exactly as for values;
no merge into `SelectedValue` (that was DD-021, withdrawn by DD-024 and not
reopened).

| | Field side | Web side |
|---|---|---|
| Topic | `PLC::MetaData` | `PLC::SelectedMetaData` |
| Type | `MetaData` | `MetaData` — same |
| QoS | `RELIABLE` · `TRANSIENT_LOCAL` · `KEEP_LAST 1` | **`BEST_EFFORT` · `VOLATILE`** · `KEEP_LAST 1` ([DD-029](design-decisions.md#dd-029)) |
| Written by | scada-sim, once per tag at startup | scada-selector, on receipt **and on `METADATA` request** |
| Late joiner gets history? | Yes — durability | **No** — request it |

Three properties worth stating because they are easy to get wrong:

- **The whole catalogue crosses, unfiltered by the selection table.** scada-web's
  map *is* the tag catalogue, needed to answer "what tags exist" and to resolve a
  name to a uid ([OQ-13](questions.md#oq-13)) *before* anything is selected.
  Filtering it would deadlock discovery: a client cannot ask for a tag it cannot
  see. The volume argument for filtering does not apply — `MetaData` is written once
  per tag.
- **Durability is not carried across the boundary — the catalogue is requested.**
  `TRANSIENT_LOCAL` delivers history to a late joiner only when **both** the writer
  and the reader are `RELIABLE` (verified against 7.7.0), and the web side is
  `BEST_EFFORT` ([DD-029](design-decisions.md#dd-029)). So a late-joining scada-web
  gets no catalogue by subscribing; it asks, over the one channel that is still
  reliable, and retries until its map is populated. Values need no equivalent
  because they are periodic — a late joiner waits at most one publish period.
- **`Command_t::METADATA` is therefore the bootstrap path, not a fallback.** The
  selector services it by rewriting instances from its field-side reader cache. It
  needs a **sentinel `uid` meaning "all"** to bootstrap, since scada-web cannot ask
  per-uid for a catalogue it does not yet have — a semantic addition to the existing
  field, not an IDL change. Fix the concrete value (`-1` or `0`) in §4.1 when it is
  chosen.

The map still serves two purposes at once, which was always the main argument for
scada-web owning it (§6.2): the **tag catalogue** for name-based lookup, and **view
enrichment** for the mapping engine. Where the bytes come from does not change who
interprets them.

`scada_web/config.yaml` still subscribes to `PLC::MetaData` directly today, because
the selector does not exist yet and the PoC works. It switches to
`PLC::SelectedMetaData` when the selector lands.

### 4.4 Unchanged

**On the field side**, `PLC::MetaData` and `PLC::IdValue` keep the QoS the sim
already uses: `RELIABLE` throughout, `TRANSIENT_LOCAL` for MetaData, `VOLATILE` for
IdValue because the process moves on.

**On the web side, the selector does not mirror them** — it writes `BEST_EFFORT` +
`VOLATILE` + `KEEP_LAST` ([DD-029](design-decisions.md#dd-029)). Outbound history
stays `KEEP_LAST` and never `KEEP_ALL`, which under the earlier reliable design was
what stopped a slow web consumer from blocking the dispatch thread and stalling
field-side reception; with best-effort output it is defense in depth, since such a
writer cannot block at all. The types and field values are untouched either way —
QoS is not part of the data model, which is what keeps this consistent with Role 1
being pure selection.

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

**Corrected placement:** scada-web holds the uid→metadata map. See
[DD-024](design-decisions.md#dd-024). It receives `MetaData` *through the selector*
rather than directly ([DD-028](design-decisions.md#dd-028), §4.3) — a transport
change that leaves this placement argument untouched, since it is about who
interprets metadata, not about which hop delivers it.

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
| Hard-RT ↔ soft-RT boundary | 1 | **scada-selector** | Anyone else — a second conduit is not a boundary ([DD-028](design-decisions.md#dd-028)) |
| Metadata *transport* across the boundary | 1 | **scada-selector** | scada-web reading the field topic directly (DD-028) |
| Isolating the field side from soft-RT backpressure | 1 | **scada-selector** | — `KEEP_LAST` outbound is what enforces it |
| Data model changes of any kind | 2 | **scada-web** | scada-selector — Role 1 is selection only |
| uid→metadata lookup and the map itself | 2 | **scada-web** | scada-selector (§6.2, DD-024 — unchanged by DD-028, which moved transport only) |
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
| 2 | **scada-selector**: enable set, republish, **metadata passthrough**. No model changes | `rtiddsspy` on `SelectedValue` and `SelectedMetaData` while driving `ValueRequest` by hand |
| 2a | **scada-selector**: the boundary invariant — stall a web-side subscriber, confirm field-side reception is unaffected | Measured, not assumed ([DD-028](design-decisions.md#dd-028)) |
| 3 | **scada-web** engine (TRD §12 P1) — union→scalar projection first | Mapping CLI over JSON fixtures |
| 4 | **scada-web** DDS + web surface, incl. `MetaData` map and `<lookup>`; repoint config at `SelectedMetaData` | End-to-end to a test client |
| 5 | **browser**: tag table + trend (mimic is separate — [OQ-16](questions.md#oq-16)) | The demo |

Step 2 is independently demonstrable with no web tier at all, which makes it the
cheapest real progress available — and it shrank further under
[DD-024](design-decisions.md#dd-024), since the selector no longer caches or
merges metadata. Adding metadata passthrough under
[DD-028](design-decisions.md#dd-028) grows it back slightly, but not by much: it is
a second reader, a second writer, and `read()` instead of `take()`, with no
correlation and no map. Step 3 needs no DDS and no network. The two can proceed in
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
