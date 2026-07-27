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
| [OQ-6](#oq-6) | Bespoke expression grammar or restricted CEL? | OPEN | BLOCKING | — | mapping-dsl §4/§5, **P1** |
| [OQ-11](#oq-11) | What must the PoC demonstrate to count as a success? | OPEN | BLOCKING | DG | Judging the outcome |
| [OQ-4](#oq-4) | Is cross-topic join in the PoC? | READY | HIGH | — | Engine state design, P1 |
| [OQ-3](#oq-3) | Is `/dds/rest1` wire compatibility required? | READY | MEDIUM | DG | Web surface design, P3 |
| [OQ-5](#oq-5) | Which HTTP stack? | OPEN | MEDIUM | — | P3 |
| [OQ-1](#oq-1) | RTI licensing/support position on reimplementing WIS | OPEN | MEDIUM | DG | Productization, not the PoC |
| [OQ-2](#oq-2) | Must we mechanically ingest Routing Service assignment configs? | DEFERRED | LOW | — | FR-XF-053 scope |
| [OQ-7](#oq-7) | How to re-authenticate a long-lived WebSocket? | DEFERRED | LOW | — | Post-PoC |
| [OQ-8](#oq-8) | Multi-instance / horizontal scaling story? | DEFERRED | LOW | — | Post-PoC |
| [OQ-9](#oq-9) | Is the embeddable library a v1 requirement or v2? | ANSWERED | — | — | → DD-018 |
| [OQ-10](#oq-10) | What is the reference hardware for §7.1 targets? | MOOT | — | — | → DD-018 |

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

- **Status:** READY · **Priority:** MEDIUM · **Owner:** DG
- **Blocks:** Web surface design (P3); TRD §5.1 and §5.5
- **Raised:** 2026-07-27 · **Downgraded:** 2026-07-27 (PoC scoping)

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

- **Status:** READY · **Priority:** HIGH · **Owner:** —
- **Blocks:** Transformation engine state design; mapping-dsl join syntax; **P1**
- **Raised:** 2026-07-27

**Now blocks P1, not P3**, because the engine moved to the front of the schedule
(TRD §12). It needs answering early — but the recommendation below is unchanged
and cheap to adopt, so this should not hold anything up.

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

- **Status:** OPEN · **Priority:** MEDIUM · **Owner:** —
- **Blocks:** P3 (was P1)
- **Raised:** 2026-07-27 · **Reframed:** 2026-07-27 (PoC scoping)

**Substantially reframed — this got easier in two ways and harder in none.**

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

- **Status:** OPEN · **Priority:** HIGH · **Owner:** —
- **Blocks:** [mapping-dsl.md](mapping-dsl.md) §4 and §5 finalization; P3
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

- **Status:** OPEN · **Priority:** BLOCKING · **Owner:** DG
- **Blocks:** Judging the outcome; secondarily the P3 scope
- **Raised:** 2026-07-27 (PoC scoping)

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

## 3. Resolved / deferred / moot

Entries stay in §2 with their status; this table is the index.

| ID | Question | Outcome | Resolved |
|---|---|---|---|
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
- **Local toolchain is GCC 9.4 / CMake 3.16**; shipped Connext libraries are
  built for `x64Linux4gcc8.5.0`. Hence DD-006 (C++17). If the toolchain is
  upgraded, revisit.
- **No published WIS performance figures exist.** Every comparative claim must
  be measured against the local binary, never cited.
