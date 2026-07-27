# scada_web — Open Questions Register

**Status:** Living document — this is the canonical register.
**Last updated:** 2026-07-27

Questions raised anywhere (TRD, code review, spike, meeting) are recorded here.
[technical-requirements.md](technical-requirements.md) §11.2 defers to this file;
where the two disagree, this file wins.

---

## Workflow

```
  issue surfaces
        │
        ▼
  ┌───────────┐   logged here with an OQ- id, owner, and what it blocks
  │   OPEN    │
  └─────┬─────┘
        │  gather options + evidence (spike, doc dig, ask RTI)
        ▼
  ┌───────────┐   options written up below; a recommendation is stated
  │  READY    │
  └─────┬─────┘
        │  decide
        ▼
  ┌───────────┐   a DD- entry is written in design-decisions.md,
  │  ANSWERED │   this entry links to it and stops being edited
  └───────────┘
```

Rules that keep this useful:

1. **One question per entry.** If it has an "and" in it, split it.
2. **Every entry has an owner and a blocks field.** A question that blocks
   nothing and belongs to nobody is a note, not a question — put it in §5.
3. **Answering a question means writing a DD- entry.** The resolution lives in
   [design-decisions.md](design-decisions.md); this file only points at it.
   Never record the rationale in both places.
4. **Do not delete or renumber.** IDs are referenced from the TRD and from
   commit messages. Move to §4 with a status instead.
5. **A question that has been ready for a decision through two working
   sessions gets escalated** — either decided, or explicitly deferred with a
   trigger condition. Silent lingering is the failure mode.

**Statuses:** `OPEN` · `READY` (options assembled, awaiting decision) ·
`ANSWERED` (→ DD-) · `DEFERRED` (with a stated trigger) · `MOOT` (no longer
applies).

**Priority:** `BLOCKING` (work stops) · `HIGH` (drives design now) ·
`MEDIUM` · `LOW`.

---

## 1. Index

**Scope note (2026-07-27):** the project is a **prototype PoC** — no target
hardware, no embeddable library ([DD-018](design-decisions.md#dd-018)). This
retired OQ-9 and OQ-10, downgraded OQ-1 and OQ-5, and deferred OQ-7 and OQ-8.
Priorities below are relative to *the PoC*, not to an eventual product.

| ID | Question | Status | Priority | Owner | Blocks |
|---|---|---|---|---|---|
| [OQ-23](#oq-23) | Standalone, RS Adapter + Processor, or hybrid? | Role 1 ANSWERED → [DD-026](design-decisions.md#dd-026); Role 2 READY | MEDIUM | DG | scada-web structure |
| [OQ-12](#oq-12) | Shared union output topic, or one per client? | DECIDED | BLOCKING | DG | scada-selector design, step 1 |
| [OQ-11](#oq-11) | What must the PoC demonstrate to count as a success? | DECIDED | BLOCKING | DG | Judging the outcome |
| [OQ-15](#oq-15) | What language and DDS API for scada-selector? | SUPERSEDED | — | — | → [OQ-23](#oq-23) |
| [OQ-6](#oq-6) | Bespoke expression grammar or restricted CEL? | DEFERRED | HIGH | — | mapping-dsl §4/§5, P1 |
| [OQ-19](#oq-19) | Union comparison and promotion rules? | DEFERRED | HIGH | — | OQ-6 spike, OQ-14 |
| [OQ-24](#oq-24) | `ValueRequest`: deltas or full desired state? | DECIDED | HIGH | DG | DD-023, SR-003, OQ-17 |
| [OQ-25](#oq-25) | Per-client read semantics on a shared reader — keep WIS polling at all? | DECIDED | HIGH | DG | FR-REST-003, read path |
| [OQ-14](#oq-14) | Where does alarm limit evaluation and state live? | DECIDED | HIGH | DG | Browser + filter scope |
| [OQ-13](#oq-13) | Is name-based tag lookup required, or is `uid` enough? | DECIDED | MEDIUM | DG | `ValueRequest` handling |
| [OQ-16](#oq-16) | What stack for the browser interface? | OPEN | MEDIUM | — | Browser work, step 5 |
| [OQ-17](#oq-17) | Should `ValueRequest` be keyed on `uid`? | DECIDED | MEDIUM | DG | IDL revision window |
| [OQ-20](#oq-20) | Single source of truth for types across components? | ANSWERED | — | — | → [DD-026](design-decisions.md#dd-026) |
| [OQ-21](#oq-21) | Are trends and a historian in scope? | DECIDED | MEDIUM | DG | Browser scope |
| [OQ-3](#oq-3) | Is `/dds/rest1` wire compatibility required? | DECIDED | MEDIUM | DG | Web surface design |
| [OQ-1](#oq-1) | RTI licensing/support position on reimplementing WIS | OPEN | MEDIUM | DG | Productization, not the PoC |
| [OQ-26](#oq-26) | One DDS domain across the RT boundary, or two? | OPEN | MEDIUM | DG | Selector deployment, OQ-22 |
| [OQ-27](#oq-27) | Should `ValueRequest` be keyed + `TRANSIENT_LOCAL` for phase 0? | SUPERSEDED by [DD-034](design-decisions.md#dd-034)/[DD-036](design-decisions.md#dd-036) | HIGH | DG | Control plane design, SR-003 |
| [OQ-28](#oq-28) | `METADATA` sentinel uid: magic value or new enum? | DEFERRED → [DD-039](design-decisions.md#dd-039) | MEDIUM | DG | IDL contract, catalogue bootstrap |
| [OQ-29](#oq-29) | `char stringValue[32]` vs `string<32>` in the IDL | DECIDED → [DD-040](design-decisions.md#dd-040) | HIGH | DG | Type correctness, Python/C++ interop |
| [OQ-30](#oq-30) | Does the selector need an ACK/feedback channel? | DEFERRED | MEDIUM | DG | Command reliability guarantee |
| [OQ-31](#oq-31) | Is WaitSet dispatch order guaranteed for simultaneous conditions? | DECIDED → [DD-041](design-decisions.md#dd-041) | MEDIUM | DG | Control-before-data invariant |
| [OQ-32](#oq-32) | Should inbound `IdValue` reader be `BEST_EFFORT`? | DECIDED → [DD-042](design-decisions.md#dd-042) | MEDIUM | DG | Field-side backpressure on selector stall |
| [OQ-33](#oq-33) | How is reader-cache overflow made observable? | ANSWERED → [DD-042](design-decisions.md#dd-042) | LOW | DG | Silent data loss, observability |
| [OQ-34](#oq-34) | Single IDL source with build-system enforcement? | DECIDED → [DD-043](design-decisions.md#dd-043) | MEDIUM | DG | Type duplication between sim/ and scada_select/ |
| [OQ-35](#oq-35) | Config YAML references non-existent `instantaneousValue` — fix or rename IDL? | OPEN | BLOCKING | DG | Gateway startup crash |
| [OQ-36](#oq-36) | `_ws_clients` dict concurrent mutation in async event loop | OPEN | HIGH | DG | Runtime correctness |
| [OQ-37](#oq-37) | PoC reader QoS: match the sim's RELIABLE/TRANSIENT_LOCAL, or skip metadata? | OPEN | HIGH | DG | MetaData never arrives at gateway |
| [OQ-38](#oq-38) | No `PlcValue.xml` committed — require `rtiddsgen` or commit generated file? | OPEN | HIGH | DG | Repo unrunnable without manual step |
| [OQ-39](#oq-39) | Poll loop vs WaitSet for the Python gateway read path | OPEN | MEDIUM | DG | CPU waste, scalability |
| [OQ-40](#oq-40) | Gateway testability: module globals + deprecated FastAPI events | OPEN | MEDIUM | DG | Test isolation |
| [OQ-41](#oq-41) | Programmatic types (sim) vs XML types (gateway) — interop validated? | OPEN | MEDIUM | DG | End-to-end correctness |
| [OQ-42](#oq-42) | Test strategy: what tests does the PoC need? | OPEN | MEDIUM | DG | Regression visibility |
| [OQ-18](#oq-18) | Should `ValueRequest` carry a `LIFESPAN`? | OPEN | LOW | — | Nothing; cheap later |
| [OQ-22](#oq-22) | Enforce Purdue zones with DDS Security, or logically only? | OPEN — now structurally reachable via [DD-028](design-decisions.md#dd-028) | LOW | — | Deployment claims |
| [OQ-4](#oq-4) | Is cross-topic join in the PoC? | ANSWERED | — | — | → DD-021 |
| [OQ-5](#oq-5) | Which HTTP stack? | READY | LOW | — | P3 |
| [OQ-2](#oq-2) | Must we mechanically ingest Routing Service assignment configs? | DEFERRED | LOW | — | FR-XF-053 scope |
| [OQ-7](#oq-7) | How to re-authenticate a long-lived WebSocket? | DEFERRED | LOW | — | Post-PoC |
| [OQ-8](#oq-8) | Multi-instance / horizontal scaling story? | DEFERRED | LOW | — | Post-PoC |
| [OQ-9](#oq-9) | Is the embeddable library a v1 requirement or v2? | ANSWERED | — | — | → DD-018 |
| [OQ-10](#oq-10) | What is the reference hardware for §7.1 targets? | MOOT | — | — | → DD-018 |

**Scope note (2026-07-27, second revision):** the deliverable is four
components — scada-sim, scada-selector, scada-web, browser
([system-architecture.md](system-architecture.md),
[DD-020](design-decisions.md#dd-020)). This **answered OQ-4** by relocating the
join, **downgraded OQ-5** to near-irrelevant, and raised OQ-12…15.

**Scope note (2026-07-27, third revision):** `scada-filter` renamed
**`scada-selector`**, and it must use **compiled IDL types** for high-rate topics.
That ruled out a Routing Service Processor and settled Role 1 of OQ-23 as
standalone ([DD-026](design-decisions.md#dd-026)); **Routing Service is not used
anywhere.** It also **answered OQ-20**. Separately,
[DD-024](design-decisions.md#dd-024) moved metadata correlation from the selector
to scada-web, so the selector is now pure selection — any text below describing it
as enriching or caching metadata is superseded.

**Scope note (2026-07-27, fourth revision):** scada-selector is now the **sole
conduit between the hard-real-time field side and the soft-real-time presentation
side**, and `MetaData` is forwarded *through* it rather than read directly by
scada-web ([DD-028](design-decisions.md#dd-028)). This amends DD-024's transport
path only — metadata *ownership* stays with scada-web. It raised **OQ-26** and made
**OQ-22** structurally reachable: its recommended option (b), a domain per level
with a deliberate bridge, was impossible while scada-web held a field-side
endpoint. Any text below implying scada-web subscribes to `PLC::MetaData` directly
is superseded.

**Scope note (2026-07-27, fifth revision):** the **web side is `BEST_EFFORT`**
([DD-029](design-decisions.md#dd-029)). `PLC::ValueRequest` is the single stated
exception and keeps `RELIABLE` + `KEEP_ALL`, so [DD-023](design-decisions.md#dd-023)
stands and [OQ-17](#oq-17)/[OQ-24](#oq-24) remain optional rather than forced. Two
consequences below: **[OQ-25](#oq-25)'s option A is now the only coherent choice** —
a best-effort current-value stream has nothing for take-once semantics to take — and
the tag catalogue can no longer arrive by durability, since `TRANSIENT_LOCAL`
requires `RELIABLE` on both ends, so it is **requested** over the reliable control
channel instead.

---

## 2. Questions

Ordered by ID, not priority — the index above is the single source of truth for
status and priority, so it is not repeated here.

### OQ-1
**What is RTI's licensing and support position on reimplementing WIS behavior and
reusing the Routing Service transformation plugin interface?**

- **Status:** OPEN · **Priority:** MEDIUM · **Owner:** DG
- **Blocks:** Productization. Does **not** block the PoC.
- **Raised:** 2026-07-27 (TRD RISK-7) · **Downgraded:** 2026-07-27 (PoC scoping)

**Downgraded from BLOCKING.** An internal prototype that never fronts a
production domain does not raise the question with any urgency. It becomes
blocking again the moment anyone proposes deploying this or showing it outside
the organization — which, per RISK-9, is exactly the drift to watch for.

**Context.** We consume only documented public APIs (Connext Modern C++, XTypes)
and reimplement a documented protocol surface. We do not link WIS or Routing
Service binaries at runtime (NFR-PORT-004). But WIS is a licensed RTI product,
and modeling our plugin ABI on `rti::routing::transf::TransformationPlugin`
(FR-XF-052) means reusing an RTI-authored interface shape.

**What we need to know.**
1. Any contractual restriction on building a functional substitute for a
   licensed component we hold a license to.
2. Whether reusing the transformation plugin interface shape is acceptable, and
   whether existing RS plugin binaries may be loaded by our process.
3. Whether RTI support obligations change for a deployment where our service,
   not WIS, is the web boundary.

**Why it isn't blocking today.** Everything in P0 is spikes and documents. The
decision is needed before P1 code lands.

---

### OQ-3
**Is strict `/dds/rest1` wire compatibility required, or may we ship only
`/api/v1`?**

- **Status:** DECIDED · **Priority:** MEDIUM · **Owner:** DG
- **Blocks:** Web surface design (P3); TRD §5.1 and §5.5
- **Raised:** 2026-07-27 · **Downgraded:** 2026-07-27 (PoC scoping)
- **Decision:** 2026-07-27 — [DD-038](design-decisions.md#dd-038). **Option A: match WIS `/dds/rest1` surface.** Initial
  development will use WIS as the gateway; next phase swaps scada-web in behind
  the same API. This means the browser client is built against the WIS wire
  format and scada-web must be compatible when it replaces WIS.

**Recommendation for the PoC: option B — `/api/v1` only.** PoC framing largely
settles this. Building a compatibility surface plus a differential conformance
suite is a large fraction of the total effort and proves nothing about the
mapping thesis. Ship `/api/v1`, keep WIS as an ad-hoc oracle (NFR-TEST-006), and
revisit compatibility if the PoC leads to a product. That also withdraws
[DD-015](design-decisions.md#dd-015).

**Context.** This is the largest single cost driver in the TRD. Compatibility
means implementing the full WIS surface *and* building a differential
conformance suite against the real 7.7.0 binary, *and* carrying WIS quirks
(XML-default `sampleFormat`, bare `204`s, `404` on take failure) behind a
compatibility flag forever.

**Options.**

| | Option | Cost | Consequence |
|---|---|---|---|
| A | Full compat: `/dds/rest1` + `/api/v1` | High — §5.1 in full, plus the differential suite | Existing WIS clients migrate with a base-URL change. Six DIV- divergences must be flag-gated. |
| B | `/api/v1` only | Low — no compat surface, no differential suite | Every existing WIS client must be rewritten. We lose the strongest correctness oracle we have. |
| C | `/api/v1` + a thin `/dds/rest1` shim covering only the routes real clients use | Medium | Needs an inventory of what clients actually call. Partial compat that looks total is a support trap. |

**What would settle it.** An inventory of existing WIS clients in our
deployments and whether any are third-party or otherwise not ours to rewrite.
If the answer is "none, all first-party" → B. If any are external → A.

**Note.** Even under B, keep the differential suite as a *development* tool. The
WIS binary is installed locally and is the only authoritative oracle for
behavior the manual leaves ambiguous (RISK-5). Losing compatibility as a
*product* requirement need not mean losing it as a *test* technique.

---

## 3. Open

### OQ-2
**Do we need to mechanically ingest existing Routing Service Assignment
Transformation configurations, or is a documented migration path enough?**

- **Status:** DEFERRED · **Priority:** LOW · **Owner:** —
- **Blocks:** FR-XF-053 / `scada-web-mapc import-rs` scope
- **Raised:** 2026-07-27 · **Deferred:** 2026-07-27
- **Trigger to reopen:** the PoC succeeds and migration of real configurations
  is on the table.

Depends entirely on how many such configurations exist in the field. Note that
DD-003 flips the meaning of the mapping direction attributes, so translation is
not a copy-paste — it is a real rewrite, which is the argument for tooling. If
the count is under roughly a dozen, hand migration plus a documented table is
cheaper than a translator.

**Action:** count them before designing anything.

---

### OQ-4
**Is joining across topics (FR-XF-022) in the PoC?**

- **Status:** ANSWERED — **no, relocated** · **Resolved:** 2026-07-27
- **Resolution:** [DD-021](design-decisions.md#dd-021)

**Answered, and the answer inverted the reasoning below.** The real IDL showed
that the natural HMI view — `{tag, value, units, limits, alarm_state}` — spans
`IdValue` and `MetaData` correlated on `uid`, which is exactly the
`latest_value` join this entry recommended cutting. **The one feature planned for
deferral turned out to be required by the primary use case.**

Rather than reinstate it in the engine, scada-selector performs the enrichment: it
already holds per-uid state for the enabled set, and `MetaData` is
`TRANSIENT_LOCAL` so it reliably has every description. Join stays out of the v1
mapping engine and the view still works.

Worth recording as a lesson: the deferral recommendation below was reasonable on
the information available and wrong on the information that arrived. It was made
before any concrete data model existed — which is an argument for looking at real
types earlier, not for deferring less.

The analysis below is preserved as written.

**Context.** Join is the single largest driver of state in the transformation
engine. Without it, a mapping is a pure function of one input sample and the
engine needs no memory at all. With it, we need a per-key latest-value cache
with its own eviction policy, memory bound, and staleness semantics — and the
`unmapped_policy` interaction when a counterpart has not arrived yet.

It is also the feature most likely to be genuinely required, since the whole
point of a view is to not look like the wire.

**Recommendation:** defer to v2, but *design the plan representation so join can
be added without reshaping it* — i.e. allow multiple `<input>` elements in the
schema from day one and reject more than one at compile time in v1. Retiring
this risk cheaply is worth more than the feature.

---

### OQ-5
**Which HTTP stack?**

- **Status:** READY · **Priority:** LOW · **Owner:** —
- **Blocks:** P3
- **Raised:** 2026-07-27 · **Reframed:** 2026-07-27 (PoC scoping, then DD-022)

**Now near-irrelevant.** [DD-022](design-decisions.md#dd-022) closed the
threading question on the merits — the client population is operator consoles,
tens to low hundreds, so connection scaling is not a differentiator between
stacks. **Take option A (Boost.Beast)** unless the spike hits an obstacle. This
no longer warrants comparative evaluation.

**Earlier reframing, preserved:**

1. **NFR-MAINT-002 is withdrawn** with the embeddable library (TRD §8.1). The
   rule against external dependencies in public headers was the main argument
   against option C, so **C is now viable**.
2. **NFR-PERF-003's 10,000-connection target is [Post-PoC]**, so the criterion
   that would have decided this — connection scaling — no longer applies. Per
   [DD-019](design-decisions.md#dd-019) the PoC uses the simplest workable
   concurrency model.

So the PoC criterion is now **time-to-working-WebSocket**, not scalability.
That points at **A (Boost.Beast)**: mature, good WebSocket support, no HTTP/2
but the PoC does not need HTTP/2. Option B is clearly wrong for a prototype —
hand-writing an HTTP/2 state machine is the opposite of what a PoC should spend
its time on.

**Candidates.**

| | Stack | For | Against |
|---|---|---|---|
| A | Boost.Beast | Mature, widely deployed, good WebSocket support, Asio underneath | No HTTP/2. Header-heavy, slow builds. Asio async style is verbose. |
| B | nghttp2 + hand-written layer | Real HTTP/2, full control over the connection model | Substantially more work; we own the HTTP state machine and its bugs. |
| C | A vendored async framework (e.g. userver, drogon, seastar) | Batteries included | Large dependency; opinionated threading that may fight Connext's; licensing review needed. |

**Decision criteria for the PoC, in order.** (1) Time to a working WebSocket
push path. (2) Whether its threading model composes with Connext's notification
model without a thread per endpoint — still worth checking, because getting this
wrong is expensive to unwind later even if the PoC never stresses it.
(3) Build weight.

**Action.** Timeboxed spike: one DDS reader pushing to one browser over
WebSocket, on option A. If that lands quickly, stop looking. Defer the
connection-scaling comparison to the post-PoC decision, when a reference
platform exists to measure it on.

---

### OQ-6
**Bespoke expression grammar, or a restricted profile of an existing language?**

- **Status:** DEFERRED · **Priority:** HIGH · **Owner:** —
- **Blocks:** [mapping-dsl.md](mapping-dsl.md) §4 and §5 finalization; P3
- **Deferred:** 2026-07-27 — POC uses `DynamicData.to_json()` directly; no
  expression language or mapping engine needed. Revisit when mapping/transform
  layer is built.
- **Raised:** 2026-07-27

**Context.** DD-011 already fixes the *requirements*: total, statically typed
against XTypes, no I/O, bounded memory, not Turing-complete. This question is
only about which implementation satisfies them.

**Candidates.**

| | Option | For | Against |
|---|---|---|---|
| A | CEL (Common Expression Language) | Specified; total by design; has a type checker; C++ implementation exists | Type system is CEL's, not XTypes' — needs a bridge for enums, unions, optionals, fixed-width ints. Dependency. |
| B | Bespoke grammar | Types are XTypes natively; we control the cost model exactly; no dependency | We own a parser, a type checker, and their fuzzing surface. |
| C | JSONPath / jq subset | Familiar to web developers | jq is Turing-complete; a safe subset is ill-defined. Poor fit for typed numerics. |

**Leaning A**, on the grounds that "we wrote our own expression language" is a
recurring source of long-term maintenance cost, and CEL's totality guarantee is
exactly the hard requirement in DD-011. The deciding factor is whether the
CEL↔XTypes bridge for enums, unions, optionals, and 64-bit integers is cleaner
than a bespoke checker.

**Action (P0 spike).** Bridge CEL to a `DynamicData` sample with a type
containing an enum, a union, an optional, an `int64`, and a bounded sequence.
If the bridge needs special-casing per XTypes construct, that is the signal for B.

---

### OQ-7
**How do we authenticate and authorize a long-lived WebSocket after `HELLO`?**

- **Status:** DEFERRED · **Priority:** LOW · **Owner:** —
- **Blocks:** Post-PoC
- **Raised:** 2026-07-27 · **Deferred:** 2026-07-27
- **Trigger to reopen:** any deployment beyond a demo, or the full authz model
  (DD-013) being built.

**Retained despite deferral because of sub-question (3) below** — it has an
architectural consequence that is cheap now and expensive later, so honor it in
the PoC even without an answer to the rest: **a bind must hold a reference to its
principal, not a snapshot of its permissions.**

**Context.** WIS authenticates once, in the `HELLO` frame, and never again.
A SCADA WebSocket may stay open for weeks; a JWT lives for minutes. So either
tokens are irrelevant after connect (a real security hole — a revoked principal
keeps streaming), or we need a protocol extension beyond WIS.

**Sub-questions.**
1. Is a token-refresh frame acceptable, given it diverges from the WIS protocol?
2. On expiry with no refresh: close the connection, or downgrade to
   read-only, or suspend delivery until refreshed?
3. Does an authorization *policy* change (not a token change) have to take
   effect on already-established binds? Presumably yes — that is the
   revocation path. Which means binds must be re-evaluated on policy reload,
   interacting with FR-CFG-005 hot reload.

**Note:** (3) is the one with architectural consequences and it is easy to miss.
A bind must hold a reference to its principal, not a snapshot of its permissions.

---

### OQ-8
**What is the multi-instance and horizontal scaling story?**

- **Status:** DEFERRED · **Priority:** LOW · **Owner:** —
- **Blocks:** Post-PoC
- **Raised:** 2026-07-27 · **Deferred:** 2026-07-27
- **Trigger to reopen:** a reference platform exists and absolute scaling
  targets are set (OQ-10).

Stateless REST scales trivially behind a load balancer. Bound WebSocket readers
are per-instance state, and joined views (OQ-4) hold a cache. Options: sticky
routing by connection; sticky by application/topic partition; or shared state in
an external store. Note that each instance is also a DDS participant, so N
instances means N participants and N sets of matched endpoints — this has
discovery and bandwidth cost on the DDS side that a stateless-web-tier mental
model overlooks.

**Depends on OQ-4:** if join is out of v1, the only per-instance state is bind
registration, and sticky-by-connection is sufficient and nearly free.

---

### OQ-9
**Is the embeddable library (§8.1) a v1 requirement or v2?**

- **Status:** ANSWERED — **no, neither** · **Resolved:** 2026-07-27
- **Resolution:** [DD-018](design-decisions.md#dd-018)

Answered by scope direction: there is no embeddable-library requirement. TRD
§8.1 is withdrawn and FR-LIB-001…005 removed. This also withdrew NFR-MAINT-002,
which reopened [OQ-5](#oq-5) to dependency options previously ruled out — the
question resolved *and* loosened a constraint, which is worth noting because the
second effect is easy to miss when a requirement is dropped.

---

### OQ-10
**What is the reference hardware for the §7.1 performance targets?**

- **Status:** MOOT for the PoC · **Resolved:** 2026-07-27
- **Resolution:** [DD-018](design-decisions.md#dd-018)

There is no target hardware, so absolute performance targets and the CI
regression gate are [Post-PoC]. TRD §7.1 was rewritten to state *relative* and
*shape* requirements only, which are machine-independent and therefore still
meaningful. **Reopens** if the PoC leads to a product — at which point a named
runner class or dedicated benchmark host is needed before any absolute number is
written down.

---

### OQ-11
**What must the PoC demonstrate to count as a success?**

- **Status:** DECIDED · **Priority:** BLOCKING · **Owner:** DG
- **Blocks:** Judging the outcome; secondarily the P3 scope
- **Raised:** 2026-07-27 (PoC scoping)
- **Decision:** 2026-07-27 — [DD-030](design-decisions.md#dd-030). The POC demonstrates:
  1. GUI sends select commands (add/remove tag UIDs)
  2. scada-selector publishes selected values + metadata
  3. GUI displays those selected values in real time
  4. Configuration is YAML, as simple as possible

  No mapping engine, no expression language, no write-through, no round-trip
  correctness proofs. Success = the read path works end-to-end with real DDS
  data flowing from sim → scada-selector → scada-web → browser.

**Context.** A prototype without a stated success criterion cannot fail, which
means it also cannot succeed — it just ends when attention moves on. This is
the most important question in this file and the cheapest to answer.

The TRD now assumes the criterion is the **mapping thesis**: a browser client
consuming and writing through a view that exists in no IDL (§12 P3). That
assumption drove the P1/P2 inversion and [DD-019](design-decisions.md#dd-019).
It should be confirmed rather than inherited from my reading.

**Candidate criteria — which ones count?**

| | Criterion | If in scope, requires |
|---|---|---|
| A | A non-trivial mapped view works end to end, read path only | Engine + DDS + REST or WS read |
| B | Writes work through the view, with correct instance semantics | All of A, plus inbound mapping and §6.5 — roughly doubles the engine work |
| C | Round-trip correctness is demonstrated, not just demoed | Property-based test suite (NFR-TEST-002) |
| D | The declarative DSL is usable by a non-programmer | A real user attempting a real mapping unaided |
| E | The cost shape is acceptable | Microbenchmarks (NFR-PERF-002) |
| F | It scales | A reference platform — not available, out of scope |

**Recommendation: A + B + C.** B is what distinguishes this from a read-only
dashboard gateway and is where the hard problems are (invertibility, key
semantics) — a read-only PoC would skip precisely the parts most likely to be
infeasible, which is the wrong risk to defer. C is what makes the result
evidence rather than an anecdote. D is valuable but needs a person and a
schedule. E is cheap; include it if it is free.

**Note:** if the answer is A only, then DD-004 and DD-005 lose most of their
force and the engine gets substantially smaller. That is a legitimate choice, but
it should be a choice.

---

### OQ-12
**Does scada-selector publish one shared output topic carrying the union of all
clients' requested uids, or one topic/partition per client?**

- **Status:** DECIDED · **Priority:** BLOCKING · **Owner:** DG
- **Blocks:** scada-selector design; `SelectedValue` definition (build step 1)
- **Raised:** 2026-07-27 ([system-architecture.md](system-architecture.md) §5)
- **Decision:** 2026-07-27 — [DD-031](design-decisions.md#dd-031). **Option A (one shared output topic).** Initial POC
  targets a single client, so the question is moot for now. scada-web will implement
  per-client demux in the future if multiple clients are needed.

**Context.** [DD-020](design-decisions.md#dd-020) moves selection into
scada-selector, but does not say what granularity it publishes at. This is the
first thing that has to be decided, because everything downstream depends on it.

| | Option | Consequence |
|---|---|---|
| A | **One shared topic**, union of all requested uids | scada-web holds one reader. It must demultiplex per client (SR-004) — a cheap set-membership test, but real code, and the *only* thing preventing client A from seeing client B's tags. |
| B | **One topic or partition per client/session** | No demux in scada-web. But entity count now scales with client count inside scada-selector — the problem is relocated, not solved, which defeats the point of DD-020. |

**Recommendation: A.** It is the only option consistent with DD-020's rationale.
B recreates the per-client entity explosion one component to the left.

**But note what A implies, because it is a security property, not just a
performance one:** the output topic carries every tag any client has asked for, so
per-client scoping exists *only* because scada-web enforces it in software. A demux
bug leaks other clients' tags. If tag-level access control is ever required
(NFR-SEC-003), that enforcement point is the one that matters, and it is in the
web tier rather than in DDS. Worth deciding deliberately rather than discovering.

**Sub-question:** under A, should scada-selector use DDS partitions to give coarse
grouping (e.g. per plant area) even if not per client? That would reduce
scada-web's demux volume without per-client entities.

---

### OQ-13
**Is name-based tag lookup required, or is `uid` sufficient?**

- **Status:** DECIDED · **Priority:** MEDIUM · **Owner:** DG
- **Blocks:** `ValueRequest` handling in scada-selector; browser tag-selection UX
- **Raised:** 2026-07-27
- **Decision:** 2026-07-27 — [DD-032](design-decisions.md#dd-032). `uid`-only for POC. Name-based lookup deferred to
  future implementation roadmap.

**Context.** `ValueRequest` carries both `uid` and `name`, but `ADD`/`DELETE` only
need `uid`. So `name` is either (a) redundant, kept for readable logging, or (b) an
alternative lookup key for a client that knows a tag's name but not its numeric id.

If (b), scada-selector needs a name→uid index built from `MetaData.longName`, and
must define behavior for an unknown or ambiguous name — `MetaData.longName` is not
declared unique, so ambiguity is possible.

This also bears on how the browser lets an operator pick tags. Selecting by
numeric uid is not a usable HMI affordance; selecting by name is. So *something*
must resolve names — the question is which component does it. A third option is
that scada-web exposes a tag catalogue built from `MetaData` and the browser
resolves names before ever sending a `uid`, which keeps scada-selector simple.

**Leaning:** catalogue in scada-web, `uid`-only in `ValueRequest`, `name` kept for
logging. Confirm before building either side.

---

### OQ-14
**Where does alarm limit evaluation and alarm state live?**

- **Status:** DECIDED · **Priority:** HIGH · **Owner:** DG
- **Blocks:** scada-selector scope; browser scope; mapping engine `<compute>` usage
- **Raised:** 2026-07-27 ([system-architecture.md](system-architecture.md) §7)
- **Decision:** 2026-07-27 — [DD-033](design-decisions.md#dd-033). Out of scope for POC. Alarm/limit evaluation is future
  roadmap for scada-selector.

**Context.** `Limits_t` carries six thresholds (red/yellow/green high and low) plus
an `active` flag. Something must compare values against them. Three candidate
homes, none obviously right:

| | Where | For | Against |
|---|---|---|---|
| A | scada-selector | Evaluated once for all clients; consistent across displays | Puts supervisory logic in a component whose job is selection |
| B | scada-web mapping engine, as `<compute>` | Declarative; the TRD's worked example does exactly this | Per-client re-evaluation; expression language must handle union-typed comparisons |
| C | Browser | Simple; no server state | Every client re-implements it; inconsistent between clients; no server-side alarm history |

**The harder half of the question is state, not evaluation.** ISA-18.2 wants
Normal → Unacknowledged → Acknowledged → RTN with deadbands and priorities — a
state machine with memory, and acknowledgement is an *operator action* that must
be shared across clients. If operator A acknowledges an alarm, operator B must see
it acknowledged. That is server-side shared state, which rules out C for anything
beyond a single-operator demo, and means whichever component owns it needs a
write path from the browser.

**Note:** limit comparison over `Value_t` means comparing union-typed values,
which is a non-trivial case for the expression language. Promoted to its own
entry — see [OQ-19](#oq-19), which must be answered before this one can be
implemented whichever component wins.

**Recommendation:** for the PoC, evaluate limits in scada-selector (option A) and
emit a simple severity level on `SelectedValue`; treat the full ISA-18.2 state
machine as explicitly out of scope and say so, rather than implementing a boolean
and calling it alarms. Confirm — this expands `SelectedValue` and scada-selector's
remit.

---

### OQ-15
**What language and DDS API for scada-selector?**

- **Status:** SUPERSEDED by [OQ-23](#oq-23) · **Superseded:** 2026-07-27
- **Raised:** 2026-07-27

**Superseded, and the answer is one this entry did not consider.** OQ-23's
recommendation is that scada-selector be a **Routing Service Processor** — none of
the three options below. Its job is multi-input correlation with state, which is
what Processors exist for, and RS then supplies config, lifecycle, remote admin,
and monitoring. Option C below (Routing Service) was rejected for the wrong reason:
I evaluated *Routing Service with a transformation plugin*, which genuinely is an
awkward fit, and did not consider a **Processor**, which is multi-input and
supports `update()`. The "don't pick C without a spike" warning was right about
transformations and wrong about processors.

The `SelectedValue` drift concern ([OQ-20](#oq-20)) survives and gets easier: a
C++ Processor and a C++ scada-web can share the same type-loading path.

**Original analysis, preserved:**

**Context.** The sim is Python; scada-web is modern C++. scada-selector could be
either, and the choice is not obvious.

| | Option | For | Against |
|---|---|---|---|
| A | Modern C++ | Matches scada-web; shares type-handling and DynamicData code; production-plausible | Slower to write; the component is mostly bookkeeping, which C++ is not fastest at |
| B | Python | Fastest to a working filter; consistent with the sim; the logic is a dict and a set | Second runtime to deploy; per-sample Python on the data path |
| C | Routing Service + a transformation plugin | Least new code; RTI already does topic-to-topic republishing | Selection driven by a live command topic is not what RS transformations are built for; awkward fit; drags in [OQ-1](#oq-1) |

**Leaning B for the PoC, A if it outlives the PoC.** scada-selector's logic is a set
of enabled uids, a dict of cached metadata, and a republish loop — that is a
short Python program, and it is on the critical path as the earliest independently
demonstrable component (system-architecture §9). At SCADA scan rates (the sim
publishes at 1 Hz) Python is nowhere near a bottleneck.

**The argument against B worth weighing:** if scada-selector is Python, the
`EnabledValue` type is defined twice — once in the sim's builder style and once in
scada-web's C++ — and they can drift. Promoted to its own entry, since the fix is
a system-wide choice rather than a note on this one: see [OQ-20](#oq-20).

**Do not pick C without a spike.** Bending Routing Service to do command-driven
dynamic selection is likely to cost more than the ~200 lines it replaces.

---

### OQ-16
**What stack for the browser interface?**

- **Status:** OPEN · **Priority:** MEDIUM · **Owner:** —
- **Blocks:** Browser work (build step 5)
- **Raised:** 2026-07-27

**Context.** The browser interface is one of the four named deliverables and its
stack is currently just "TBD" in
[system-architecture.md](system-architecture.md) §1. Nothing tracked it, which is
how a deliverable quietly becomes an afterthought.

ISA-101 requirements shape this more than usual: high-performance HMI means a
grayscale/muted mimic with saturated color reserved for abnormal states, state
shown by shape *and* fill rather than color alone (accessibility), and trends plus
an alarm banner as first-class elements rather than bolt-ons. A mimic diagram is
essentially interactive vector graphics bound to live tag values.

**Candidates.** Plain SVG + vanilla TypeScript (no framework, direct WebSocket
binding — mimics are SVG anyway); React or similar with an SVG mimic; or a
canvas-based renderer if tag counts get high enough that per-element DOM updates
hurt.

**Leaning:** SVG plus a thin TypeScript layer, no framework. A mimic is a static
drawing with a few hundred bound attributes; frameworks solve a problem this does
not have, and direct binding keeps the update path obvious. Revisit if the alarm
banner and trend components turn out to want real component structure.

**Sub-question:** does the PoC need a *drawn* mimic at all, or is a tag table plus
one trend enough to demonstrate the mapping thesis? A hand-drawn mimic is
substantial art effort that proves nothing about the gateway. Recommend a table
plus trend for the PoC and treat the mimic as separate.

---

### OQ-17
**Should `ValueRequest` be keyed on `uid`?**

- **Status:** DECIDED · **Priority:** MEDIUM · **Owner:** DG
- **Blocks:** IDL revision window — cheap now, disruptive later
- **Raised:** 2026-07-27 (latent in [DD-023](design-decisions.md#dd-023))
- **Decision:** 2026-07-27 — [DD-034](design-decisions.md#dd-034). **Option (a): leave unkeyed, `KEEP_ALL`.** No IDL
  change. Commands queue in order. Keyed desired-state model (b) is future
  consideration if restart recovery becomes needed.

**Context.** `ValueRequest` currently has no `@key`, making it a single-instance
command stream, which is why DD-023 requires `KEEP_ALL`. Adding `@key uid` would
give each tag its own instance and change the QoS calculus.

**Why it is not obviously right.** With `@key uid` and `KEEP_LAST depth=1`, an
`ADD(5)` followed quickly by `DELETE(5)` would have the DELETE replace the ADD on
the same instance. That happens to produce the correct end state — but only by
luck, because the two commands are not actually idempotent replacements for one
another in general, and the `METADATA` command is not a state at all. A keyed
topic models "the desired state of uid 5", whereas the current type models "a
command about uid 5". Those are different designs and the enum mixes them:
`ADD`/`DELETE` are state-like, `METADATA` is a request.

**Options.** (a) Leave unkeyed, use `KEEP_ALL` per DD-023 — no IDL change, works.
(b) Key on `uid` and split `METADATA` onto its own request topic, so the keyed
topic is genuinely "desired enable state". Cleaner model, touches the IDL and the
sim. (c) Key on `uid` and keep the enum as-is — tempting and probably subtly wrong.

**Recommendation:** (a) for the PoC. Consider (b) if the IDL opens for other
reasons; do not adopt (c). Whichever way, note that a keyed "desired state" topic
with `TRANSIENT_LOCAL` durability would let a restarted scada-selector recover its
enable set from the middleware instead of needing reconciliation
(system-architecture SR-003) — which is a genuine architectural argument for (b)
worth weighing against the churn.

---

### OQ-18
**Should `ValueRequest` carry a `LIFESPAN` QoS?**

- **Status:** OPEN · **Priority:** LOW · **Owner:** —
- **Blocks:** Nothing — cheap to add later
- **Raised:** 2026-07-27 (noted undecided in [DD-023](design-decisions.md#dd-023))

`KEEP_ALL` means commands queue rather than being dropped. If scada-selector is down
or slow, commands accumulate and then all execute at once when it recovers —
including requests from clients that have since disconnected. A `LIFESPAN` would
expire stale commands.

Interacts with interest refcounting (SR-001…004): scada-web's refcount is the real
source of truth for what should be enabled, so stale queued commands are not just
wasteful but can disagree with it. Arguably reconciliation after reconnect
(SR-003) is the better fix and `LIFESPAN` is redundant. Recorded so it is a
decision rather than an omission.

---

### OQ-19
**How are union-typed values compared, and what are the promotion rules?**

- **Status:** DEFERRED · **Priority:** HIGH · **Owner:** —
- **Blocks:** [OQ-6](#oq-6) expression-language spike; [OQ-14](#oq-14) alarm evaluation
- **Raised:** 2026-07-27 (was a note inside OQ-14)
- **Deferred:** 2026-07-27 — depends on OQ-6; both are post-POC (mapping engine
  roadmap).

**Context.** Every value in the data model is a `Value_t` union over string,
int32, int64, float32 (declared `double`), and float64. Alarm limits are *also*
`Value_t`. So the core alarm operation is comparing one union against another, and
the two may carry different discriminators.

**Questions that need answers, not defaults:**

1. What happens comparing `KIND_INT64` against `KIND_FLOAT64`? Promote to double
   and accept precision loss above 2^53, or refuse?
2. What does comparing `KIND_STRING` against a numeric limit mean? Presumably an
   error — but the engine must define which error and what
   `on_error` does with it.
3. Are `KIND_FLOAT32` and `KIND_FLOAT64` interchangeable? On the wire they are
   both `double` (see FR-XF-005), so a strict discriminator check would reject a
   comparison that is actually well-defined.
4. Does the expression language expose the discriminator itself, so a mapping can
   branch on `ValueKind_t`? Almost certainly needed, and it means the type checker
   must handle a value whose static type is a union.

**Why HIGH.** This lands on both the OQ-6 language choice and OQ-14 alarm
placement, and it is exactly the kind of semantics that gets decided implicitly by
whatever the first implementation happens to do. Answer it in the P0 spike. It is
also the concrete test of whether a restricted CEL profile can bridge to XTypes
cleanly — unions are the hard part of that bridge, and this system is made of them.

---

### OQ-20
**What is the single source of truth for the `SelectedValue` type across
components?**

- **Status:** **ANSWERED** · **Resolved:** 2026-07-27
- **Resolution:** [DD-026](design-decisions.md#dd-026), with [DD-024](design-decisions.md#dd-024)
- **Raised:** 2026-07-27 (was a note inside OQ-15)

**Answered by two decisions that between them removed the problem rather than
solving it.**

1. **DD-024 withdrew the enriched type.** `SelectedValue` reuses `IdValue` on a
   different topic name, so there is no second type definition to keep in sync.
2. **DD-026 fixed the derivation path.** One IDL, two *automated* derivations —
   `rtiddsgen` for the selector's compiled C++ types, `rtiddsgen -convertToXml`
   for the XML types library scada-web loads at runtime (DD-007). Neither is
   hand-written, so neither can drift.

The residual item is a build-system concern, not a design question: **both
derivations must be wired into the build** so a change to `PlcValue.idl`
regenerates both. If they are run by hand, drift returns through the back door.

Worth noting the sim is still the exception — [sim/plc_types.py](../sim/plc_types.py)
hand-transcribes the IDL into DynamicType builder calls. That is deliberate and
documented in its docstring, and it is now the *only* hand-transcription left. If
the Connext Python API can load XML types, the sim could consume the same
generated XML and the duplication would be gone entirely.

**Original analysis, preserved:**

**Context.** `SelectedValue` is written by scada-selector and read by scada-web. If
those are different languages, the type gets defined twice and can drift — and a
drifted type fails at *runtime* as a type-mismatch on endpoint matching, not at
build time.

The sim already shows the shape of this problem: [sim/PlcValue.idl](../sim/PlcValue.idl)
is the nominal source of truth, but [sim/plc_types.py](../sim/plc_types.py)
hand-transcribes it into DynamicType builder calls, with a docstring noting the
transcription is deliberate and field-for-field. That is careful and correct today,
and it is exactly the kind of duplication that silently rots.

**Options.** (a) IDL as source of truth, `rtiddsgen -convertToXml`, both components
load the XML types library at runtime — consistent with DD-007 and FR-DDS-007, and
scada-web needs XML type loading anyway. (b) IDL plus generated code per language.
(c) Keep hand-transcribing and add a test that asserts the two definitions agree.

**Leaning (a).** It removes the duplication rather than policing it, and scada-web
already requires runtime XML type loading, so the machinery is not extra work.
Note this would also let the sim drop its hand-built builders — worth checking
whether the Connext Python API can load XML types as readily.

---

### OQ-21
**Are trends and a historian in scope?**

- **Status:** DECIDED · **Priority:** MEDIUM · **Owner:** DG
- **Blocks:** Browser scope; possibly a fifth component
- **Raised:** 2026-07-27
- **Decision:** 2026-07-27 — [DD-035](design-decisions.md#dd-035). **Option (b): client-side trend buffer.** Browser
  keeps last N minutes in memory from the WebSocket stream. No server-side
  historian. Real historian (option c) is out of scope.

**Context.** I marked historian and trends "out of scope" in
[system-architecture.md](system-architecture.md) §7 on my own authority, which
was a scope call I should not have made silently — flagging it rather than leaving
it buried in a table.

The case for including *something*: the [scada-sme](../.github/agents/scada-sme.agent.md)
guidance treats trending as a first-class HMI element, not an add-on, and an
operator display showing only instantaneous values is not recognizably a SCADA
HMI. A trend also exercises the gateway differently from a live value — it implies
either client-side buffering of the WebSocket stream or a server-side query API,
and the latter would be a genuinely new capability rather than a UI feature.

**Options.** (a) Out of scope entirely — live values only. (b) Client-side trend
buffer in the browser: keeps the last N minutes in memory, no server changes, no
persistence. (c) Real historian as a fifth component, with a query path through
scada-web.

**Recommendation: (b).** It gives a recognizable HMI and costs nothing on the
server side, since the browser is already receiving the stream. (c) is a separate
project — Level 3 in Purdue terms — and would pull scada-web into query-API
territory that has nothing to do with the mapping thesis.

---

### OQ-22
**Does the PoC enforce Purdue zone separation with DDS Security, or only
logically?**

- **Status:** OPEN · **Priority:** LOW · **Owner:** —
- **Blocks:** Nothing in the PoC; matters for any real deployment claim
- **Raised:** 2026-07-27

**Context.** The [scada-sme](../.github/agents/scada-sme.agent.md) guidance is
explicit that IEC 62443 zones and conduits should be *architecturally* real, not
just drawn on a diagram — default-deny between zones, explicit conduits. Today the
four components would share one DDS domain with no authentication between them, so
Level 1 and Level 2 separation exists only as a module boundary.

For the PoC this is defensible: the separation is real in code structure, which is
what the architecture is meant to demonstrate. But it should be **stated** rather
than left to be inferred, because "we modeled Purdue levels" and "we enforced
Purdue levels" are different claims and only the first is true.

**Options.** (a) Logical separation only, documented as such. (b) Separate DDS
domains per level with a deliberate bridge as the conduit. (c) Connext Security
Plugins with per-level permissions.

**Recommendation: (a) for the PoC, documented explicitly** — and note that (b) is
the cheap intermediate step if separation ever needs to be more than a claim,
since domain separation costs almost nothing and makes the conduit an actual
component rather than an assumption. (c) is already [Post-PoC] per NFR-TEST-007.

> **Update (2026-07-27, [DD-028](design-decisions.md#dd-028)).** Option (b) is now
> *reachable*, which it was not when this was written. The blocker was never the
> domain IDs — it was that scada-web read `PLC::MetaData` directly and therefore
> held a field-side endpoint, so no bridge could be the only conduit. Metadata now
> passes through scada-selector, which makes the conduit "an actual component
> rather than an assumption" in the exact sense this entry asked for. What remains
> open here is narrower: whether the PoC *runs* two domains
> ([OQ-26](#oq-26)) and whether Security Plugins are involved (c). The
> zone-boundary claim itself is no longer only logical — it is enforced by
> topology.

---

### OQ-23
**Standalone service, Routing Service Adapter + Processor, or a hybrid?**

- **Status:** **ANSWERED for Role 1** (→ [DD-026](design-decisions.md#dd-026)); READY for Role 2 · **Priority:** MEDIUM · **Owner:** DG
- **Blocks:** scada-web structure only; supersedes [OQ-15](#oq-15)
- **Raised:** 2026-07-27 · **Partly resolved:** 2026-07-27
- **Full analysis:** [architecture-comparison.md](architecture-comparison.md)

> **Role 1 is settled, and not as recommended below.** The requirement that
> scada-selector use **compiled IDL types** for high-rate topics rules out a
> Routing Service Processor outright: the built-in DDS adapter is
> DynamicData-based, with no documented way to bind generated types to a
> Processor's `TypedInput<T>`. **scada-selector is standalone**
> ([DD-026](design-decisions.md#dd-026)).
>
> **Role 2 is unchanged and still recommended: scada-web standalone.** The
> analysis below for *why not an Adapter* (§3.1 of the comparison — REST reads are
> DataReader semantics) is untouched and is the part that still needs sign-off.
>
> Net: Routing Service is not used anywhere. Its free admin and monitoring were
> the strongest reason to involve it, and that is now a cost both components carry.

**Context.** Prompted by [RTI_REST_Adapter_Proposal.md](RTI_REST_Adapter_Proposal.md),
which argues for hosting a WIS-like REST/WebSocket interface as a Routing Service
Adapter. The comparison evaluates that against the standalone assumption in the
TRD and finds a third option the proposal does not consider.

| | Option | Verdict |
|---|---|---|
| A | Standalone service (TRD's current assumption) | Acceptable fallback |
| B | RS Adapter + Processor, one process | **Not recommended** |
| C | scada-selector as an RS **Processor**; scada-web standalone | **Recommended** |

**Why C.** The two components have opposite fits to the Routing Service model, and
treating this as one system-wide decision hides that.

- **scada-selector is a textbook Processor** — three inputs (`IdValue`, `MetaData`,
  `ValueRequest`), one output, holding a per-uid enable set and metadata cache.
  Multi-input correlation with state is exactly what Processors are for, `update()`
  is supported on them, and RS supplies config, lifecycle, remote admin, and
  monitoring for free. This answers OQ-15.
- **scada-web fits it poorly.** Routing Service has no request/reply primitive, so
  an HTTP `GET` has nothing to read from and the adapter must rebuild a cache —
  and FR-REST-003's `sampleStateMask`, `viewStateMask`, `instanceStateMask`, and
  `filterExpression` **are DataReader semantics**. Option B reimplements, less
  correctly, the component that already solves the read path. In a standalone
  service a REST GET is a `take()` with a QueryCondition.

**Two findings worth surfacing.**

1. **[DD-020](design-decisions.md#dd-020) accidentally improved B's case.** Moving
   selection into scada-selector means scada-web holds one reader and one writer
   forever, which removes the dynamic-entity requirement that adapters handle
   worst. B is more viable than it would have been a week ago — just still not
   viable enough.
2. **The proposal's own §11 criteria point to standalone for scada-web.** It says
   prefer a standalone app when you want a tailored API and are not already running
   RS for other bridging. We aren't, and [OQ-3](#oq-3) leans toward a tailored
   `/api/v1`. Its recommendation is conditional in exactly the way that matters
   here, so this is agreement with the proposal rather than a rejection of it.

**The one thing that could invalidate C:** deployment licensing for an RS host
running our Processor plugin. RS ships with Connext Professional and is installed
locally, but this needs confirming — folds into [OQ-1](#oq-1).

**If C is rejected, take A, not B.** B's free infrastructure is real but buys the
wrong things: an admin plane and metrics, paid for by reimplementing sample-state
tracking and DDS SQL filtering, plus the proposal's own 1–2 week budget just to
prove the thread hand-off model — spent on plumbing rather than on the mapping
thesis.

**Not affected either way:** the mapping engine, plan compiler, key semantics, and
round-trip tests. [DD-010](design-decisions.md#dd-010) keeps the engine
independent of HTTP and DDS, which is what makes this decision reversible and
TRD §12 P1 valid regardless.

---

### OQ-24
**Does `ValueRequest` carry incremental deltas or a full desired-state set?**

- **Status:** DECIDED · **Priority:** HIGH · **Owner:** DG
- **Blocks:** `ValueRequest` semantics; interacts with [DD-023](design-decisions.md#dd-023), SR-003, [OQ-17](#oq-17)
- **Raised:** 2026-07-27 (second axis of [DD-025](design-decisions.md#dd-025))
- **Decision:** 2026-07-27 — [DD-036](design-decisions.md#dd-036). **Option A (deltas).** `ADD`/`DELETE` per current IDL.
  Single-client POC has no restart/reconciliation concerns. Keyed or
  desired-state model can be revisited for multi-client robustness later.

**Context.** DD-025 settled the *transport* — the in-band DDS topic. This is the
*semantics*, and it is orthogonal: both models work over that transport.

| | Model | Shape |
|---|---|---|
| A | **Deltas** (today's IDL) | `ADD(5)`, `DELETE(5)` — one uid per sample |
| B | **Desired state** | "the complete set of enabled uids is {1,5,17}" — one sample carries the whole set |

**The case for B is stronger than it first appears.** scada-web already holds the
authoritative interest refcount (SR-001), so it always *knows* the full desired
set. Publishing it makes the message idempotent, which removes three problems at
once:

- **SR-003 reconciliation disappears.** A restarted filter receives the next
  desired-state sample and is immediately correct. No restart detection, no
  re-send protocol. This is the requirement I flagged as most likely to be
  forgotten, with a blank-display-and-no-error symptom.
- **[DD-023](design-decisions.md#dd-023) relaxes.** A lost sample stops being
  fatal, because the next one carries the full truth. `KEEP_LAST depth=1` becomes
  *correct* rather than dangerous — the latest state is exactly what a
  desired-state topic wants.
- **Ordering and duplicate-delivery concerns vanish.** No `ADD`/`DELETE` race.

**The case for A.** It is what the IDL already says, so B means an IDL change
(a `sequence<UniqueId_t>`, bounded — and the bound then caps total enabled tags,
which is a real design constraint to pick deliberately). Deltas are also cheaper
per message when one tag changes, though at operator rates that is irrelevant.

**Interaction with [OQ-17](#oq-17).** A third shape: keep one uid per sample but
`@key` it and carry a boolean `enabled`, making each uid its own instance of a
desired-state topic. With `TRANSIENT_LOCAL` a restarted filter recovers the whole
set from the middleware — SR-003 solved by QoS rather than by protocol. This is
the same insight OQ-17 reached from the keying direction, and it is arguably the
cleanest of the three because it keeps messages small *and* idempotent.

**Recommendation: the keyed variant**, if the IDL is open to revision — it gets
B's idempotence without an unbounded sequence, and `METADATA` moves to its own
request topic since it is a request, not a state. Otherwise A with `KEEP_ALL` per
DD-023, which works and is what the current IDL supports.

---

### OQ-25
**With one shared DataReader, what do per-client read semantics mean — and should
we keep the WIS polling surface at all?**

- **Status:** DECIDED · **Priority:** HIGH · **Owner:** DG
- **Blocks:** FR-REST-003; scada-web read path design (P3)
- **Raised:** 2026-07-27, clarifying
  [architecture-comparison.md](architecture-comparison.md) §3.1
- **Decision:** 2026-07-27 — [DD-037](design-decisions.md#dd-037). **Option A (latest-value + WebSocket push).** POC is
  single client; no WIS polling surface, no per-client state. Multi-client
  concerns deferred.

**Context.** FR-REST-003 inherits WIS's read surface: `removeFromReaderCache`
(read vs take), `sampleStateMask` (READ / NOT_READ), `viewStateMask` (NEW /
NOT_NEW), `instanceStateMask`, `filterExpression`, `maxSamples`, `maxWait`.

Those are **per-DataReader** semantics. WIS makes them per-client because in the
WEDDS model each client creates its own DataReader.
**[DD-020](design-decisions.md#dd-020) removed that** — scada-web holds one shared
reader on `SelectedValue`, which is the entire point of the selector.

**The inconsistency.** On a shared reader, three of those parameters are wrong or
meaningless per client, in *any* hosting arrangement:

| Parameter | On a shared reader |
|---|---|
| `removeFromReaderCache=true` (take) | **Unsafe** — one client consuming removes the sample for every other client |
| `sampleStateMask` | Means "read by the gateway", not "read by this client" |
| `viewStateMask` | "First seen by the gateway" — a client connecting later sees NOT_NEW for instances that are new *to it* |
| `instanceStateMask` | **Fine** — a property of the instance, correctly shared |
| `filterExpression` | **Fine** — per-client QueryConditions on one reader are supported and cheap |
| `maxSamples`, `maxWait` | **Fine** — per-query and per-WaitSet |

So FR-REST-003 as written is not implementable per-client on this architecture.
It was inherited from the WIS baseline (TRD §2.2) before DD-020 existed.

**Options.**

| | Option | Consequence |
|---|---|---|
| A | **Drop the polling surface.** Reads become latest-value lookups; change notification is WebSocket push. `read()` never `take()`, `KEEP_LAST depth=1`. | Cleanest fit. The DDS reader cache *is* the latest-value store, shared safely across clients. Diverges from WIS — fine if [OQ-3](#oq-3) resolves to `/api/v1` only. |
| B | **Synthesize per-client state** in scada-web: per-client read/view tracking layered over the shared reader. | Preserves the WIS surface, but reimplements per-client what DDS does per-reader — the exact work we criticized Option B of OQ-23 for. |
| C | **Reader per client.** | Reverses DD-020 and reintroduces the entity explosion the selector exists to prevent. Rejected. |

**Recommendation: A.** This is a SCADA HMI — an operator display wants "the current
value of these tags" plus "tell me when it changes". That is latest-value plus
push. Take-once queue semantics are an artifact of WIS's polling model, and
`KEEP_LAST depth=1` with `read()` is both the correct DDS idiom for current-value
data and safe to share across clients. It also matches how the sim publishes
(`IdValue` is `VOLATILE`, `KEEP_LAST depth=1` — current value, not a log).

**If A is chosen, FR-REST-003 must be rewritten**, not just annotated: keep
`filterExpression`, `maxSamples`, `maxWait`, and `instanceStateMask`; drop
`removeFromReaderCache`, `sampleStateMask`, and `viewStateMask` with a note that
they are meaningless without a per-client reader.

**Note:** this weakens — but does not overturn — the §3.1 argument in the
comparison. The surviving claim is that the reader cache is a queryable,
instance-indexed store which a standalone service keeps and an RS Adapter throws
away. That holds under option A here just as much as under B.

> **Update (2026-07-27, [DD-029](design-decisions.md#dd-029)).** Option A is now
> effectively forced. The web side is `BEST_EFFORT` + `VOLATILE` + `KEEP_LAST 1`,
> which *is* a current-value stream: there is no history to poll through and
> take-once semantics have nothing to take. `removeFromReaderCache`,
> `sampleStateMask`, and `viewStateMask` were already meaningless on a shared
> reader; they are now meaningless on the transport as well. Option B
> (synthesizing per-client state) would additionally have to synthesize
> completeness the transport never promised. **This entry is ready to be closed as
> A** — the remaining work is rewriting FR-REST-003, as described above.

---

### OQ-26
**Does the PoC run one DDS domain across the real-time boundary, or two?**

- **Status:** OPEN · **Priority:** MEDIUM · **Owner:** DG
- **Blocks:** Nothing in the code — scada-selector takes `--field-domain` and
  `--web-domain` regardless. Blocks the *deployment* story and part of
  [OQ-22](#oq-22)
- **Raised:** 2026-07-27, by [DD-028](design-decisions.md#dd-028)

**Context.** DD-028 makes scada-selector the sole conduit between the hard-real-time
field side and the soft-real-time presentation side. The boundary is enforced by
**topology** — only the selector has endpoints on both sides — which works within a
single domain. Running a domain per side adds enforcement by **configuration**: a
misconfigured scada-web then *cannot* reach field topics, rather than merely not
being pointed at them.

The selector is built for either. Two participants, two domain flags, one WaitSet
(conditions from entities on different participants may share one), and topic names
that stay distinct across the boundary so a single-domain deployment works
unchanged.

**Options.**

| | Option | Consequence |
|---|---|---|
| A | **One domain** (`--field-domain == --web-domain`) | Simplest; matches the sim and the current `scada_web/config.yaml`. The boundary is real but rests on nobody creating a field-side reader in scada-web. One participant. |
| B | **Two domains**, selector bridges | Enforced by configuration, not just discipline. Field-side discovery contains exactly one subscriber. Costs a second participant with its own discovery and receive threads, and a second QoS block to keep consistent. |
| C | **One domain, two partitions** | Cheaper than B, and partitions are a *matching* filter rather than an isolation boundary — a participant that names the partition still joins. Weaker than B for the zone claim, more machinery than A. |

**Recommendation: A for the PoC, with B as the documented deployment shape.** The
work that makes B possible is already done — it is the DD-028 topology plus two
flags — so B costs nothing to *reach* later and the PoC gains nothing from paying
for a second participant now. What matters is that the claim be stated precisely:
under A, zone separation is enforced by topology and one config file; under B, by
the middleware.

**Decide when** a demo needs to make a security or zoning claim to an outside
audience, or when the sim moves to separate hardware from the web tier — either
makes B the honest default. Discard C unless partitions are already being used for
something else.

---

### OQ-27
**Should `ValueRequest` be keyed on `uid` with `TRANSIENT_LOCAL` durability for phase 0?**

- **Status:** SUPERSEDED · **Priority:** HIGH · **Owner:** DG
- **Blocks:** Control plane design, SR-003 reconciliation, OQ-17, OQ-24
- **Raised:** 2026-07-27 (architecture review of scada-select)
- **Superseded:** 2026-07-27 — already decided by [DD-034](design-decisions.md#dd-034)
  (unkeyed) and [DD-036](design-decisions.md#dd-036) (deltas). Additionally,
  [DD-039](design-decisions.md#dd-039) (preset uid range) removes the bootstrap
  concern that motivated this question.

**Context.** The current design uses an unkeyed command stream with `RELIABLE` +
`KEEP_ALL`. This makes the selector stateless across restarts (the table is lost
and must be reconciled by scada-web via SR-003). Three consequences:

1. **Unbounded queue growth.** `KEEP_ALL` on the request reader has no resource
   limit stated — if scada-web sends faster than the selector processes, the queue
   grows without bound.
2. **Reconciliation complexity.** scada-web must track its full outbound command set
   and re-drive it on selector restart. This is the entire SR-003 code path.
3. **No introspection.** The selector cannot answer "what is my current state?" to a
   monitoring tool — it has no durable truth, only the residue of processed commands.

OQ-17 and OQ-24 already raise this but frame it as optional. The question here is
sharper: **is the cost of the unkeyed design acceptable for phase 0, or does it
complicate the PoC enough to justify doing it right now?**

**Options.**

| | Option | Consequence |
|---|---|---|
| A | **Keep unkeyed, phase 0** | Accept SR-003, accept unbounded queue risk, ship faster. Retrofit keyed requests later (wire protocol change). |
| B | **Keyed `{@key uid, enabled, period_ms}` + `TRANSIENT_LOCAL`** now | Deletes SR-003, deletes KEEP_ALL hazard, selector recovers its table from middleware on restart. IDL change now. |
| C | **Keyed but `VOLATILE`** | Idempotent writes (re-ADD is safe), but no restart recovery — still need SR-003 or equivalent. Half the benefit. |

**Recommendation: B.** The IDL is not yet shipped. The wire protocol is not yet
frozen. The SR-003 reconciliation code is the single most complex interaction
between scada-web and the selector, and deleting it simplifies both sides. The cost
is one IDL revision now, which costs nothing because the IDL is already in flux.

---

### OQ-28
**Should the "give me all metadata" request use a sentinel uid value, or a new enum?**

- **Status:** OPEN · **Priority:** MEDIUM · **Owner:** DG
- **Blocks:** IDL contract, catalogue bootstrap path (scada-select §4.4)
- **Raised:** 2026-07-27 (architecture review of scada-select)

**Context.** The catalogue bootstrap requires scada-web to ask "send me all
metadata" because durability cannot deliver it on a best-effort link (DD-029). The
current plan uses a magic `uid` value (-1 or 0) to mean "all" — an in-band signal
that constrains the uid space and requires every component to know the convention.

**Options.**

| | Option | Consequence |
|---|---|---|
| A | **Sentinel uid** (e.g., `-1` or `0`) | No IDL change; convention documented in system-architecture.md. Risk: collision with real uid values; every consumer must check. |
| B | **New enum value `METADATA_ALL`** in `Command_t` | IDL change; clean separation of "one uid" vs "all uids". The `uid` field is ignored when `command == METADATA_ALL`. |
| C | **Separate topic for catalogue requests** | Over-engineered for one command variant; rejected. |

**Recommendation: B.** It is a one-line IDL addition (`METADATA_ALL` in the enum),
costs nothing at this stage, and removes the ambiguity permanently.

---

### OQ-29
**Should `Value_t`'s string arm be `char stringValue[32]` or `string<32>`?**

- **Status:** DECIDED · **Priority:** HIGH · **Owner:** DG
- **Blocks:** Type correctness, Python/C++ interop, field_simulation encoding
- **Raised:** 2026-07-27 (architecture review of scada-select)
- **Decision:** 2026-07-27 — [DD-040](design-decisions.md#dd-040). **Option A: keep `char[32]`.**
  Fixed memory allocation is a deliberate real-time constraint for the exercise.

**Context.** The IDL currently defines the string arm of `Value_t` as:
```idl
char stringValue[MAX_STRING_VALUE_LENGTH];  // fixed char array
```

This is a **fixed-size char array**, not a bounded string. Consequences:

- In C++11 codegen: `std::array<char, 32>` — no null-termination guarantee,
  comparison requires `strncmp`.
- In Python DynamicData: requires `set_char_values()` with null-padded sequences
  (already observed as painful in `plc_types.py`).
- Wire format: always 32 bytes, regardless of actual string length.
- No semantic "this is text" signal — it looks like raw bytes to introspection tools.

If the intent is "a string value up to 32 characters," the IDL should use
`string<32>`, which:
- Generates `std::string` (bounded) in C++11
- Works naturally with Python's string APIs
- Is null-terminated by contract
- Uses only the bytes needed on the wire (with a length prefix)

**Options.**

| | Option | Consequence |
|---|---|---|
| A | **Keep `char[32]`** | Wire-compatible with existing PLC protocols that send fixed-length fields. Document null-padding contract. Accept the ergonomic cost in Python and the comparison cost in C++. |
| B | **Change to `string<32>`** | Natural string semantics everywhere. Breaks wire compat with anything already using the char-array encoding. Smaller on the wire for short strings. |
| C | **Both** — `char[32]` for raw PLC wire, with a helper that converts to/from `string<32>` at the boundary | Over-engineered; the sim is the only producer. |

**Recommendation: B**, unless there is a real PLC protocol constraint requiring
fixed-width char fields. The sim is the only publisher today and it already fights
the char-array encoding. Change it now while the wire format is uncommitted.

---

### OQ-30
**Does the selector need an acknowledgment or feedback channel back to scada-web?**

- **Status:** DEFERRED · **Priority:** MEDIUM · **Owner:** DG
- **Blocks:** Command reliability guarantee, error observability
- **Raised:** 2026-07-27 (architecture review of scada-select)
- **Deferred:** 2026-07-27. PoC uses a preset uid range (DD-039); ADD/DELETE are
  optional refinements. A lost command is visible (tag stays on/off incorrectly)
  but not catastrophic. Revisit for multi-client production use.

**Context.** scada-web sends `ValueRequest` commands (ADD/DELETE/METADATA) and never
learns whether the selector processed them. Under `RELIABLE` delivery, the
transport guarantees the bytes arrived — but not that the application logic
succeeded. Failure modes:

- Selector crashes after transport ACK but before processing → command lost.
- Selector rejects a command (e.g., unknown uid for METADATA) → silent failure.
- Selector restarts → entire table lost, scada-web does not learn this happened
  unless it detects absence of expected data.

**Options.**

| | Option | Consequence |
|---|---|---|
| A | **No ACK — status quo** | Simple; rely on SR-003 reconciliation and staleness detection. Accept that command failures are invisible. |
| B | **Selector publishes its selection table as a `TRANSIENT_LOCAL` keyed topic** | scada-web can read the selector's truth, detect divergence, and re-drive. No per-command ACK needed — eventual consistency via state publication. |
| C | **Per-command ACK topic** | Complex; request-reply pattern over DDS; significant protocol overhead for little benefit over B. |

**Recommendation: A for phase 0.** If OQ-27 is answered as B (keyed + durable
requests), the middleware itself becomes the ground truth and this question is
largely retired — the selector's subscription set is the content of the durable
topic, readable by anyone. Revisit only if OQ-27 stays as A.

---

### OQ-31
**Is WaitSet dispatch order guaranteed when multiple conditions trigger simultaneously?**

- **Status:** DECIDED · **Priority:** MEDIUM · **Owner:** DG
- **Blocks:** The control-before-data invariant (scada-select §3.5)
- **Raised:** 2026-07-27 (architecture review of scada-select)
- **Decision:** 2026-07-27 — [DD-041](design-decisions.md#dd-041). **Option B: explicit
  two-phase drain.** `request_reader.take()` before `waitset.dispatch()`
  guarantees control-before-data regardless of middleware dispatch order.

**Context.** The architecture relies on control commands being processed before data
samples in the same dispatch pass (§3.5: "a tag enabled in a batch is forwarded in
the same dispatch pass rather than one pass later"). The claimed mechanism is that
the control ReadCondition is *attached first* to the WaitSet.

`WaitSet::dispatch()` calls handlers for all triggered conditions, but the Connext
documentation does not specify that handlers fire in attachment order. The DDS
specification (§7.1.2.1.6) says `wait()` returns the *set* of triggered conditions
— unordered.

**Options.**

| | Option | Consequence |
|---|---|---|
| A | **Rely on attachment order** | Works today (empirically); may break silently on a Connext upgrade. One-pass lag for a newly-enabled tag is benign anyway. |
| B | **Explicit two-phase: drain control, then dispatch data** | Guaranteed correct regardless of middleware behavior. Slightly more code but trivial. |
| C | **Accept one-pass lag** | Document that a tag enabled mid-batch may not be forwarded until the next pass. Consequence: ~100ms latency on first sample after ADD, which is invisible to a human. |

**Recommendation: C, with B as the implementation if it costs nothing.** The
practical consequence of wrong ordering is one pass of latency on a freshly-enabled
tag — invisible at display rates. But if B is two extra lines (`request_reader.take()`
before `waitset.dispatch()`), just do it.

---

### OQ-32
**Should the inbound `PLC::IdValue` reader be `BEST_EFFORT` rather than `RELIABLE`?**

- **Status:** DECIDED · **Priority:** MEDIUM · **Owner:** DG
- **Blocks:** Field-side backpressure behavior when the selector stalls
- **Raised:** 2026-07-27 (architecture review of scada-select)
- **Decision:** 2026-07-27 — [DD-042](design-decisions.md#dd-042). **Option D: RELIABLE
  with bounded resource limits + `SampleLostStatus` monitoring.** Gives burst
  headroom without unbounded blocking; overflow is observable.

**Context.** The architecture prevents web→field backpressure (DD-029, §3.8). But
if the **selector itself** stalls (debugger, overload, long computation), the
field-side `RELIABLE` writer to `PLC::IdValue` will eventually block the sim's
publish thread when the selector's reader cache fills — because the selector is the
only subscriber, and reliable delivery requires the subscriber to acknowledge.

The selector already discards most inbound samples via rate limiting (§3.3). Losing
them one hop earlier (at the transport layer rather than the application layer) has
the same user-visible outcome: the display shows the latest value it received.

**Options.**

| | Option | Consequence |
|---|---|---|
| A | **Keep `RELIABLE` inbound** | Guarantees the selector sees every sample the sim publishes, which matters for lifecycle events (dispose/unregister must not be lost). A stalled selector blocks the sim — accepted if the selector is treated as infrastructure that must not stall. |
| B | **`BEST_EFFORT` inbound for values, `RELIABLE` for lifecycle** | Not possible on a single reader — DDS reliability is per-DataReader, not per-sample. Would require splitting value and lifecycle into separate topics. |
| C | **`BEST_EFFORT` inbound** | Sim never blocks. Lifecycle events (dispose) can be lost in transit, but §3.4 already acknowledges they can be lost on the *outbound* hop. The selector is already not the reliability guarantee for lifecycle — scada-web's staleness timeout is. |
| D | **`RELIABLE` with bounded resource limits and `on_sample_lost` monitoring** | Sim blocks only if the selector falls behind by more than N samples. Gives the selector breathing room without going fully best-effort. |

**Recommendation: D for phase 0, C as future consideration.** A bounded reliable
reader with `max_samples_per_instance` set to a reasonable depth (e.g., 4–8 at
expected publish rate) gives the selector a burst buffer without unbounded blocking.
Monitor `SampleLostStatus` to know when the selector is falling behind. Going fully
best-effort (C) is the cleaner long-term answer but loses lifecycle guarantees that
may matter.

---

### OQ-33
**How should reader-cache overflow (silent sample loss) be made observable?**

- **Status:** ANSWERED · **Priority:** LOW · **Owner:** DG
- **Blocks:** Observability, silent data loss detection
- **Raised:** 2026-07-27 (architecture review of scada-select)
- **Decision:** 2026-07-27 — subsumed by [DD-042](design-decisions.md#dd-042).
  `SampleLostStatus` is polled each read cycle and logged when non-zero.

**Context.** A `KEEP_LAST` reader with a shallow depth silently overwrites unread
samples under load. The selector has no metric for "samples that overflowed my
cache before I could read them." This is invisible data loss — the selector cannot
know what it never saw.

`SampleLostStatus` (accessible via `DataReader::sample_lost_status()`) reports the
total and incremental count of samples lost by the reader, including cache
overflows. It is available in the Modern C++ API.

**Options.**

| | Option | Consequence |
|---|---|---|
| A | **Poll `SampleLostStatus` periodically and log/export** | Simple; adds one call per read cycle or on a timer. No new topics. |
| B | **Use a Listener with `on_sample_lost` callback** | Immediate notification; but listeners run on the middleware's internal thread, which complicates the single-threaded design. |
| C | **Defer to future observability work** | Accept the blind spot for the PoC. Document as a known limitation. |

**Recommendation: A.** One line per read cycle: check `sample_lost_status()`, log
if non-zero. No new infrastructure needed. Wire it to a counter for the eventual
metrics surface (§9 future work).

---

### OQ-34
**How should the IDL be shared between sim/ and scada_select/ with build-system enforcement?**

- **Status:** DECIDED · **Priority:** MEDIUM · **Owner:** DG
- **Blocks:** Type duplication risk between components
- **Raised:** 2026-07-27 (architecture review of scada-select)
- **Decision:** 2026-07-27 — [DD-043](design-decisions.md#dd-043). **Option B+D: move IDL
  to `dds/idl/`; CMake generates both C++ types and XML from it.**

**Context.** `PlcValue.idl` lives in `sim/` and must also be consumed by
`scada_select/`'s CMake build (for `rtiddsgen`) and by the Python runtime (via
`rtiddsgen -convertToXml`). The current plan (§3.7) says "point CMakeLists.txt at
`../sim/PlcValue.idl`" — a fragile relative path that breaks if either directory
moves, with no build-system check that the two consumers see the same file.

**Options.**

| | Option | Consequence |
|---|---|---|
| A | **Relative path `../sim/PlcValue.idl`** in CMakeLists.txt | Works now; breaks on restructure; no enforcement. |
| B | **Top-level `idl/` directory** with both CMake and Python targeting it | Single source of truth, both builds reference the same path. Slight project restructure. |
| C | **CMake `FetchContent` or symlink** from scada_select to sim | Adds indirection; symlinks are fragile across platforms. |
| D | **`rtiddsgen -convertToXml` as a CMake custom target** that also produces the XML for Python | Both C++ types and Python XML are generated from one IDL in one build step. Strongest enforcement. |

**Recommendation: B+D.** Move `PlcValue.idl` to a top-level `idl/` directory. The
scada_select CMake build runs `rtiddsgen` (C++11) against it; a second target runs
`rtiddsgen -convertToXml` to produce the XML that `plc_types.py` and `gateway.py`
load. One file, two generated outputs, enforced by the build system.

---

### OQ-35
**Config YAML references non-existent `instantaneousValue` — fix or rename IDL field?**

- **Status:** OPEN · **Priority:** BLOCKING · **Owner:** DG
- **Blocks:** Gateway startup (crash on first sample)
- **Raised:** 2026-07-27 (architecture review, ISS-001)

**Context.** `scada_web/config.yaml` view `tag_value` maps
`wire: instantaneousValue` but the `IdValue` struct in `PlcValue.idl` has
`rawValue`, not `instantaneousValue`. The gateway will throw at runtime when the
mapping engine (or even `_sample_to_dict`) tries to access a non-existent
DynamicData member path.

**Options.**

| | Option | Consequence |
|---|---|---|
| A | **Fix the config** — change `instantaneousValue` to `rawValue` | Trivial; matches the IDL as-is. |
| B | **Rename the IDL field** to `instantaneousValue` | Breaks the sim's `plc_publisher.py` and any existing subscriber. |

**Recommendation: A.** The config has a typo. The IDL is the source of truth.

---

### OQ-36
**`_ws_clients` dict concurrent mutation in the async event loop — what pattern to use?**

- **Status:** OPEN · **Priority:** HIGH · **Owner:** DG
- **Blocks:** Runtime correctness under client churn
- **Raised:** 2026-07-27 (architecture review, ISS-002)

**Context.** `server.py` iterates `_ws_clients` in `_on_dds_sample()` (called
from the gateway's async read loop) while the WebSocket endpoint adds/removes
entries on connect/disconnect. Both run in the same event loop, so no OS-level
race, but `await` points interleave tasks — a disconnect handled between the
`list(...)` copy and the `_ws_send` task's execution can leave a stale reference.

The `list(_ws_clients.items())` snapshot is *almost* sufficient in CPython (dict
iteration under GIL is atomic for a single `list()` call), but correctness
depends on a CPython implementation detail that is not guaranteed by the language.

**Options.**

| | Option | Consequence |
|---|---|---|
| A | **Per-client asyncio.Queue** — gateway pushes to each queue; client task drains it | Backpressure per client; clean disconnect; no shared dict iteration. Slightly more memory. |
| B | **`asyncio.Lock` around `_ws_clients`** | Correct; adds lock acquisition to the hot path (one per sample × clients). |
| C | **Accept the CPython snapshot** — document it, add a try/except in `_ws_send` | Pragmatic for PoC; not portable to other runtimes (PyPy, free-threading). |

**Recommendation: A for production, C for the PoC** with a `# TODO` noting the
debt. The per-client queue pattern also naturally solves slow-consumer
backpressure (drop oldest if queue full).

---

### OQ-37
**PoC reader QoS: match the sim's RELIABLE/TRANSIENT_LOCAL, or accept missing metadata?**

- **Status:** OPEN · **Priority:** HIGH · **Owner:** DG
- **Blocks:** MetaData never arrives at gateway if it starts after the sim
- **Raised:** 2026-07-27 (architecture review, ISS-005)

**Context.** `gateway.py` creates DataReaders with **default QoS** (BEST_EFFORT +
VOLATILE on most Connext installs). The sim's MetaData writer is RELIABLE +
TRANSIENT_LOCAL. A VOLATILE reader cannot receive TRANSIENT_LOCAL history — so if
the gateway starts after the sim, it never gets MetaData.

Per system-architecture.md §4.3 / DD-029, the **final design** deliberately
uses BEST_EFFORT + VOLATILE on the web side (after the selector exists and the
catalogue is requested). But **right now** the gateway talks directly to the sim
(the selector doesn't exist), so it needs matching QoS to receive the startup
burst.

**Options.**

| | Option | Consequence |
|---|---|---|
| A | **Match the sim: RELIABLE + TRANSIENT_LOCAL** on MetaData reader, RELIABLE + VOLATILE on IdValue reader | Works now; must change when selector lands. |
| B | **Keep defaults** but require the sim to re-publish MetaData periodically | Sim change; defeats the "once at startup" pattern. |
| C | **Add QoS profiles to config.yaml** and reference them per topic | General solution; reader QoS is declarative. Requires gateway code to apply profiles. |

**Recommendation: C, implemented with A's values for now.** The config already
has a `qos_profile` field per topic — implement it in `_create_readers()`.

---

### OQ-38
**No `PlcValue.xml` committed — require `rtiddsgen` or commit generated file?**

- **Status:** OPEN · **Priority:** HIGH · **Owner:** DG
- **Blocks:** Repo is unrunnable without a manual `rtiddsgen` step
- **Raised:** 2026-07-27 (architecture review, ISS-007)

**Context.** `scada_web/config.yaml` references `sim/PlcValue.xml` but no such
file exists in the repo. The sim uses programmatic type building (`plc_types.py`),
which works for the publisher, but the gateway needs the XML file. Anyone
cloning the repo cannot run `python -m scada_web` without first running
`rtiddsgen -convertToXml sim/PlcValue.idl -d sim/`.

Related to [OQ-34](#oq-34) (single IDL source with build enforcement), but that
question is about the long-term build system. This is about **right now**: can
someone clone and run?

**Options.**

| | Option | Consequence |
|---|---|---|
| A | **Commit the generated XML** | Works immediately; generated file in VCS (drift risk, but .gitattributes can mark it). |
| B | **Add a `make xml` / setup script** that generates it | Repo stays clean; requires tooling. |
| C | **Remove XML dependency** — gateway uses programmatic types like the sim | Eliminates the file entirely; gateway shares `plc_types.py`'s output. QosProvider path goes away. |

**Recommendation: C for the PoC.** The gateway and sim are in the same repo and
already share `PlcValue.idl` semantics. Making the gateway load types from the
same `plc_types.py` module (or import `build_plc_types()`) eliminates the XML
dependency, the `rtiddsgen` prerequisite, and OQ-41's interop concern — all in
one move. Reserve XML-based type loading for when scada-web becomes a standalone
C++ service. Validate with B as fallback if QosProvider features are needed.

---

### OQ-39
**Poll loop vs WaitSet for the Python gateway read path**

- **Status:** OPEN · **Priority:** MEDIUM · **Owner:** DG
- **Blocks:** CPU waste at scale; not blocking for PoC
- **Raised:** 2026-07-27 (architecture review, ISS-009)

**Context.** `gateway.py` `_read_loop()` polls all readers every 50ms regardless
of data availability. With 5 tags at 1 Hz, the loop runs ~20× per publish cycle
doing nothing. Connext Python supports `WaitSet` with `ReadCondition` which
would wake only on data arrival.

**Options.**

| | Option | Consequence |
|---|---|---|
| A | **Keep 50ms poll** | Simple; wastes CPU; acceptable for PoC with 5 tags. |
| B | **WaitSet with ReadCondition per reader** | Correct; requires running the WaitSet in a thread (WaitSet.wait is blocking) and posting results to the asyncio loop. |
| C | **Status condition + asyncio integration** | Ideal but may not be supported by `rti.connextdds` Python bindings. |

**Recommendation: A for now** with a `# TODO` noting the path to B. The PoC has
5 tags at 1 Hz — 50ms poll is harmless. Revisit when tag count or rate increases.

---

### OQ-40
**Gateway testability: module globals + deprecated FastAPI events**

- **Status:** OPEN · **Priority:** MEDIUM · **Owner:** DG
- **Blocks:** Test isolation; future FastAPI upgrade
- **Raised:** 2026-07-27 (architecture review, ISS-015)

**Context.** `server.py` stores `_gateway`, `_interest`, `_config`, `_ws_clients`
as module-level globals set by `create_app()`. This makes it impossible to
instantiate two apps in one process (needed for parallel test isolation) and
couples test setup to import order. Additionally, `@app.on_event("startup")` is
deprecated in FastAPI ≥0.109 in favor of `lifespan` context managers.

**Options.**

| | Option | Consequence |
|---|---|---|
| A | **Move state to `app.state`** + use `lifespan` | Standard FastAPI pattern; testable; no deprecation warnings. |
| B | **Keep globals** for PoC simplicity | Works; tests must mock at module level; deprecation warning in logs. |

**Recommendation: A.** Small refactor, large testability gain. Do it when adding
the first test (OQ-42), not as a separate task.

---

### OQ-41
**Programmatic types (sim) vs XML types (gateway) — is interop validated?**

- **Status:** OPEN · **Priority:** MEDIUM · **Owner:** DG
- **Blocks:** End-to-end correctness (sim → gateway)
- **Raised:** 2026-07-27 (architecture review, ISS-016)

**Context.** The sim builds types programmatically via `plc_types.py`
(StructType, UnionType, etc.); the gateway plans to load them from XML via
`QosProvider`. These must produce **wire-compatible** types for DDS discovery to
match endpoints. Potential mismatches:

- Module scoping: programmatic types have no module prefix by default
  (`"MetaData"`) vs XML which may emit `"PLC::MetaData"`.
- Type extensibility annotations (FINAL, APPENDABLE, MUTABLE) defaulting
  differently between programmatic construction and rtiddsgen output.
- The `@nested` annotation on `Value_t` may or may not propagate to XML.

**Resolution path:** If OQ-38 resolves as option C (gateway uses programmatic
types), this question becomes moot — both sides use the same type objects. If
XML is retained, a simple integration test (sim publishes, gateway subscribes,
verify samples arrive) validates interop.

**Recommendation:** Resolve OQ-38 first. If C, mark this MOOT. If A/B, write the
integration test.

---

### OQ-42
**Test strategy: what tests does the PoC need?**

- **Status:** OPEN · **Priority:** MEDIUM · **Owner:** DG
- **Blocks:** Regression visibility; confidence in refactoring
- **Raised:** 2026-07-27 (architecture review, ISS-018)

**Context.** No tests exist anywhere in the repo. `interest.py` is pure Python
and trivially unit-testable. `config.py`'s loader and validator are testable
without DDS. The gateway and server need either mocking or a live DDS domain.

**Options (non-exclusive).**

| Layer | What | Effort |
|---|---|---|
| Unit | `interest.py` — subscribe/unsubscribe/disconnect/reconcile | Trivial; no deps |
| Unit | `config.py` — valid/invalid YAML loading, cross-ref validation | Trivial; no deps |
| Integration | sim publishes → gateway receives → WebSocket client gets JSON | Needs DDS; ~1 hour |
| Smoke | `python -m scada_web --config ...` starts without error, `/health` returns 200 | Needs DDS for participant creation |

**Recommendation:** Start with the two unit-test modules (interest, config).
Add the smoke test when the gateway is runnable end-to-end. Integration test
when the mapping engine lands (it's the thesis — if it's not tested, it's not
proven).

---

## 3. Resolved / deferred / moot

Entries stay in §2 with their status; this table is the index.

| ID | Question | Outcome | Resolved |
|---|---|---|---|
| [OQ-4](#oq-4) | Cross-topic join in the PoC? | ANSWERED — relocated to scada-selector → [DD-021](design-decisions.md#dd-021) | 2026-07-27 |
| [OQ-9](#oq-9) | Embeddable library v1 or v2? | ANSWERED — neither; withdrawn → [DD-018](design-decisions.md#dd-018) | 2026-07-27 |
| [OQ-10](#oq-10) | Reference hardware for §7.1? | MOOT for PoC → [DD-018](design-decisions.md#dd-018) | 2026-07-27 |
| [OQ-2](#oq-2) | Ingest RS assignment configs? | DEFERRED — reopen if migration becomes real | 2026-07-27 |
| [OQ-7](#oq-7) | Long-lived WebSocket re-auth? | DEFERRED — one architectural constraint honored anyway | 2026-07-27 |
| [OQ-8](#oq-8) | Horizontal scaling? | DEFERRED — needs a reference platform first | 2026-07-27 |

---

## 4. Notes and observations

Things worth remembering that are not yet questions. Promote to §3 with an ID
if one turns out to need an answer.

- **WIS 7.7.0 is installed locally** at `/home/rti/rti_connext_dds-7.7.0` with
  `bin/rtiwebintegrationservice` and `librtirsassigntransf.so`. It is our only
  authoritative oracle for undocumented behavior (RISK-5) regardless of how
  OQ-3 resolves.
- **`rti_web_integration_service.xsd` is 86 lines.** WIS defines almost no
  configuration vocabulary of its own; it reuses DDS XML-Based Application
  Creation. There is no existing extension point for mapping constructs, so
  DD-014 has to extend the schema rather than fit into it.
- **Connext 7.7 changed type discovery timing** (TypeLookup Service and
  TypeObject v2 on by default). Discovery callbacks may fire before a type
  resolves, and may fire more than once per endpoint. See RISK-4; FR-DDS-008 is
  deliberately `MAY`.
- **Local toolchain is GCC 9.4 / CMake 3.16.** Hence DD-006 (C++17). If the
  toolchain is upgraded, revisit.
- **`CONNEXTDDS_ARCH` is `x64Linux4gcc7.3.0`**, not `x64Linux4gcc8.5.0`. The core
  libraries under `lib/` are gcc 7.3.0; the gcc 8.5.0 tree under
  `resource/app/lib` holds the bundled *services*. Picking the wrong one fails at
  link, not configure. `BUILD_SHARED_LIBS=ON` is also required or
  `FindRTIConnextDDS` resolves a static variant that is not present. Both
  verified by building — see
  [scada-selector-implementation.md](../scada_select/docs/scada-selector-implementation.md) §1.
- **rtiddsgen 4.7.0 generates public data members, not accessors** for C++11:
  `sample.uid`, not `sample.uid()`. Most RTI example code shows the older
  getter/setter style.
- **No published WIS performance figures exist.** Every comparative claim must
  be measured against the local binary, never cited.
