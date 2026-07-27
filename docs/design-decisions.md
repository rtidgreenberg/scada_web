# scada_web — Design Decision Log

**Status:** Living document — this is the canonical record of *why*.
**Last updated:** 2026-07-27

Lightweight ADRs. One decision per entry, numbered `DD-nnn`, never renumbered
and never deleted. A decision that turns out wrong gets a new entry that
supersedes the old one; the old entry stays, with its status changed, so the
reasoning that led us astray is still legible.

Rationale lives **here only**. [technical-requirements.md](technical-requirements.md)
states requirements; [questions.md](questions.md) tracks what is undecided.
Neither should duplicate a rationale — they link to it.

---

## Workflow

An entry is created when a decision is actually made — either by resolving an
[OQ-](questions.md) or because implementation forced a choice worth recording.

**Record a decision when** it constrains future work, it was not obvious, or a
reasonable engineer would ask "why is it like this?" six months from now.
**Do not record** routine style or naming choices, or anything the code states
plainly on its own.

**Statuses:** `PROPOSED` (written up, not ratified) · `ACCEPTED` ·
`SUPERSEDED by DD-nnn` · `REVERSED` (tried, did not work — keep the entry, it is
the most valuable kind).

**Template:**

```markdown
### DD-nnn — <short imperative title>
- **Status:** · **Date:** · **Resolves:** OQ-n / — · **Affects:** <req ids>
**Decision.** One or two sentences. What we will do.
**Context.** What forced the choice.
**Alternatives.** What we rejected, and the specific reason.
**Consequences.** What this costs us, including what it makes harder.
**Revisit if.** The concrete condition that should reopen this.
```

The **Revisit if** field is the point of the whole exercise. A decision without
a stated invalidation condition is a belief, and beliefs are what rot.

---

## Index

| ID | Decision | Status | Resolves |
|---|---|---|---|
| [DD-001](#dd-001) | Adopt the OMG Web-Enabled DDS resource model | ACCEPTED | — |
| [DD-002](#dd-002) | Operate on `DynamicData` throughout; no generated types | ACCEPTED | — |
| [DD-003](#dd-003) | Fix `to`/`from` to mean view/wire, not output/input | ACCEPTED | — |
| [DD-004](#dd-004) | Classify mapping invertibility at compile time | ACCEPTED | — |
| [DD-005](#dd-005) | Require `<key_mapping>`; restrict it to pure assignment | ACCEPTED | — |
| [DD-006](#dd-006) | Target C++17 | ACCEPTED | — |
| [DD-007](#dd-007) | No runtime IDL parsing in v1 | ACCEPTED | — |
| [DD-008](#dd-008) | Do not inherit WIS's insecure or ambiguous defaults | ACCEPTED | — |
| [DD-009](#dd-009) | Async I/O, not thread-per-connection | ACCEPTED | — |
| [DD-010](#dd-010) | Keep the transformation engine independent of HTTP and DDS | ACCEPTED | — |
| [DD-011](#dd-011) | The expression language must not be Turing-complete | ACCEPTED | — |
| [DD-012](#dd-012) | Compile mappings to a flat instruction sequence | ACCEPTED | — |
| [DD-013](#dd-013) | Authorization is resource- and operation-scoped, deny-by-default | ACCEPTED | — |
| [DD-014](#dd-014) | Extend the WIS XSD rather than invent a separate mapping file | ACCEPTED | — |
| [DD-015](#dd-015) | Serve two API surfaces: `/dds/rest1` and `/api/v1` | PROPOSED | OQ-3 |
| [DD-016](#dd-016) | Model the native plugin ABI on Routing Service's | PROPOSED | OQ-1 |
| [DD-017](#dd-017) | Encode 64-bit integers as JSON strings by default | ACCEPTED | — |
| [DD-018](#dd-018) | Scope to a prototype PoC: no hardware targets, no embeddable library | ACCEPTED | OQ-9, OQ-10 |
| [DD-019](#dd-019) | PoC uses the simplest workable concurrency model | ACCEPTED | — |
| [DD-020](#dd-020) | Four-component system; scada-selector owns key-based selection | ACCEPTED | — |
| [DD-021](#dd-021) | scada-selector enriches values with MetaData; join stays out of the engine | ACCEPTED | OQ-4 |
| [DD-022](#dd-022) | Thread-per-connection is correct for this system, not just for the PoC | ACCEPTED | — |
| [DD-023](#dd-023) | `ValueRequest` must be RELIABLE + KEEP_ALL | ACCEPTED | — |
| [DD-024](#dd-024) | Selection and presentation are separate roles; metadata lookup belongs to presentation | ACCEPTED | supersedes DD-021 |
| [DD-025](#dd-025) | Enable/disable ids over the in-band DDS topic, not Routing Service remote administration | ACCEPTED | — |
| [DD-026](#dd-026) | scada-selector uses compiled types — which rules out a Routing Service Processor | ACCEPTED | OQ-23 (Role 1) |

---

## Decisions

### DD-001
**Adopt the OMG Web-Enabled DDS resource model rather than designing a new one.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Resolves:** — · **Affects:** FR-REST-001, TRD §2.1

**Decision.** The resource hierarchy, URI shape, and entity lifecycle follow OMG
Web-Enabled DDS as WIS implements it: `/dds/rest1/applications/{a}/domain_participants/{dp}/...`.

**Context.** The DDS entity model is what it is — participants own publishers own
writers. Any web projection of it converges on roughly this tree, and a
standards-aligned one costs nothing extra.

**Alternatives.** A flattened topic-centric API (`/topics/{t}/samples`) is much
friendlier for the common case, but it cannot express QoS scoping, partitions, or
per-reader content filters — all of which are the reason to use DDS. Rejected as
the *primary* model; it may be worth adding later as a convenience layer over
the real one.

**Consequences.** Web clients must create four entities before reading a sample,
which is genuinely awkward. Mitigated by the view/mapping layer, which is where
the friendly surface belongs.

**Revisit if.** Client feedback shows the entity ceremony is the dominant
complaint, in which case add a convenience layer — do not replace this model.

---

### DD-002
**Operate on `DynamicData` throughout; require no generated type support code.**

- **Status:** ACCEPTED — **scoped to scada-web (Role 2)** by [DD-026](#dd-026)
- **Date:** 2026-07-27 · **Amended:** 2026-07-27 · **Affects:** FR-DDS-006, FR-TYPE-001

> **Scope amendment.** This applies to **scada-web only**. scada-selector uses
> compiled types for the opposite and equally good reason (DD-026). The two roles
> have deliberately opposite type strategies: Role 2 must handle types it has
> never seen, Role 1 handles one known type as fast as possible.

**Decision.** All DDS interaction **in scada-web** uses
`dds::core::xtypes::DynamicData` and `DynamicType`. The service is never rebuilt
to add a user type.

**Context.** A gateway cannot know its types at build time. This is also what
makes the mapping engine possible at all — mapping operates on type descriptors,
not on C++ structs.

**Alternatives.** Generated types plus a plugin per type would be faster per
sample but would make the service undeployable without a build step per data
model. Non-starter.

**Consequences.** Member access is by offset lookup rather than a struct field,
which is why DD-012 exists. Accept a per-sample cost that generated code would
not pay.

**Revisit if.** Profiling shows `DynamicData` access dominates NFR-PERF-002 even
after DD-012. The escape hatch would be JIT-compiling a plan for hot types, not
abandoning DynamicData.

---

### DD-003
**Fix `to` to mean the view path and `from` to mean the wire path, in both
directions.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Affects:** FR-XF-001, FR-XF-053, mapping-dsl §3.1, OQ-2

**Decision.** In every mapping rule, `to` is always the view-side member path
and `from` is always the wire-side path, regardless of whether the mapping is
inbound, outbound, or bidirectional.

**Context.** Routing Service's Assignment Transformation uses `<name>` = output
and `<value>` = input. Because "output" depends on route direction, the same
member path changes meaning depending on where the transformation is attached.
For a bidirectional mapping the convention has no coherent reading at all.

**Alternatives.** Matching RS's `name`/`value` convention would make existing
configurations copy-pasteable. Rejected: it imports a genuine ambiguity into the
feature that is supposed to be our differentiator, and the ambiguity is
silent — a reversed mapping produces plausible wrong data, not an error.

**Consequences.** RS assignment configurations cannot be pasted in; they need a
real rewrite. This is the entire justification for `import-rs` tooling
(FR-XF-053) and it makes OQ-2 more likely to need a translator rather than a
migration table.

**Revisit if.** Never, on the merits. If migration volume is the problem, solve
it with tooling.

---

### DD-004
**Classify mapping invertibility at compile time; a mismatch with the declared
direction is a startup error.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Affects:** FR-XF-025, RISK-2, mapping-dsl §7

**Decision.** The compiler derives each mapping's invertibility class
(`bidirectional` / `outbound_only` / `inbound_only`) from its rules and compares
it to the declared `direction`. A mapping declared `bidirectional` that contains
a non-invertible rule fails to load, naming the offending members.

**Context.** General expression inversion is undecidable, so we will never
invert `<compute>` automatically. The question was what to do when a user
declares a direction we cannot deliver.

**Alternatives.** (a) Silently degrade to read-only and let writes fail at
runtime. (b) Warn and continue. Both rejected for the same reason: the failure
is invisible until someone's setpoint write does not reach the plant. In a SCADA
context that is discovered during an incident, at the worst possible moment.
Failing at startup moves the discovery to deploy time, where it belongs.

**Consequences.** Startup is stricter and some configurations that "mostly work"
will be rejected. That is the intent. Requires the compiler to track
invertibility per member, not per mapping, to produce a useful error.

**Revisit if.** A legitimate pattern emerges that is provably safe but that our
analysis rejects. Fix the analysis; do not soften the failure mode.

---

### DD-005
**Require `<key_mapping>` on every mapping, and restrict it to pure assignment.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Affects:** FR-XF-030…033, RISK-3, mapping-dsl §3.6

**Decision.** Every mapping declares its view-key-to-wire-key correspondence
explicitly. Key rules may not use expressions, aggregation, non-injective value
maps, or lossy conversions. Every wire key member must be covered for inbound and
bidirectional mappings.

**Context.** DDS instance lifecycle is keyed. If key mapping is not bijective,
then two distinct instances can collapse into one, or one instance can fragment
into many, and `dispose`/`unregister` land on the wrong instance. Nothing errors;
the data is just wrong, and wrong in a way that looks like a plant problem
rather than a gateway problem.

**Alternatives.** Inferring keys by name matching would be more convenient and is
what most mapping tools do. Rejected — the failure is silent and severe, and the
cost of being explicit is a few lines of configuration.

**Consequences.** More verbose configuration, including for the trivial case
where key names already match. Accepted deliberately. Keys cannot be
transformed, only renamed and restructured — e.g. a unit conversion on a key
member is illegal even though it is arithmetically invertible, because floating
point round-tripping is not exact.

**Revisit if.** Never for the bijectivity requirement. The *verbosity* could be
eased by inferring `<key_mapping>` when every wire key member has an
unambiguous identity `<assign>`, and requiring it otherwise.

---

### DD-006
**Target C++17.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Affects:** NFR-PORT-003

**Decision.** C++17 is the required standard. C++20 features must not be
mandatory; C++20 may be enabled where a newer toolchain exists.

**Context.** The local toolchain is GCC 9.4 with CMake 3.16. GCC 9 supports C++17
fully and C++20 only partially. The shipped Connext libraries are built for
`x64Linux4gcc8.5.0`.

**Alternatives.** Requiring C++20 would give us concepts, coroutines (attractive
for the async I/O in DD-009), `std::span`, and formatted output. Rejected for now
because it forces a toolchain upgrade on every deployment target before the first
line of code, and coroutines in GCC 10/11 were not yet dependable.

**Consequences.** No coroutines, so the async I/O in DD-009 is callback- or
future-based, which is more verbose. No `std::format`. Third-party dependencies
must be C++17-compatible, which constrains OQ-5.

**Revisit if.** The deployment toolchain moves to GCC 11+ across all tier-1
targets. Coroutines alone would justify reopening this.

---

### DD-007
**No runtime IDL parsing in v1.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Affects:** FR-TYPE-003, FR-TYPE-004

**Decision.** Types are loaded from XML type libraries at runtime, built
programmatically, or resolved from discovery. IDL is converted to XML out of
band, at build or deploy time, via `rtiddsgen -convertToXml`.

**Context.** Connext Modern C++ has no documented runtime IDL parser — there is
no API that turns IDL text into a `DynamicType`. This is a platform fact, not a
preference.

**Alternatives.** Embedding an IDL parser (our own, or by shelling out to
`rtiddsgen` at runtime). Both rejected for v1: writing an IDL4 parser is a
project in itself, and shelling out to a code generator from a network-facing
service to process user input is an obvious attack surface.

**Consequences.** Users who think in IDL have an extra deploy step. "Upload an
IDL file and get an endpoint" — an appealing feature — is off the table for v1.

**Revisit if.** RTI exposes a runtime IDL-to-`DynamicType` API, or IDL upload
becomes a top user request. If the latter, the safe shape is offline conversion
in a build pipeline, not in-process parsing.

---

### DD-008
**Do not inherit WIS defaults that are insecure or semantically ambiguous.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Affects:** DIV-001…006, NFR-SEC-006, NFR-SEC-010

**Decision.** Six documented divergences (TRD §5.5). The security-relevant ones:
CORS is deny-by-default (WIS defaults `Access-Control-Allow-{Origin,Methods,Headers}`
to `*`); no document root is served by default (WIS serves its documentation
directory); read failures return `409`/`503` rather than `404`; entity creation
returns `201` with a `Location` header rather than a bare `204`; JSON is the
default sample format; errors carry `details` and `request_id`.

**Context.** These are not WIS bugs so much as defaults chosen for a demo-friendly
product. `Access-Control-Allow-Origin: *` on a service that fronts plant control
data is not a default we can ship. `404` for a DDS take failure is
indistinguishable from a typo'd URI, which makes client-side error handling
guesswork.

**Alternatives.** Bit-exact defaults for drop-in compatibility. Rejected — we
would be shipping a known-permissive CORS policy on a SCADA boundary.

**Consequences.** Not drop-in for clients that depended on the old behavior. Each
divergence is individually flag-gated on `/dds/rest1` (see DD-015), so
compatibility is recoverable per deployment, explicitly and visibly.

**Revisit if.** A specific divergence proves to break more than it protects. Take
them one at a time; this is not a package deal.

---

### DD-009
**Use async I/O with a bounded thread pool, not thread-per-connection.**

- **Status:** ACCEPTED as product direction — **deferred beyond the PoC**, see [DD-019](#dd-019)
- **Date:** 2026-07-27 · **Amended:** 2026-07-27 (PoC scoping) · **Affects:** NFR-PERF-005 [Post-PoC], OQ-5

> **Amendment (PoC scoping).** The justification below rests on NFR-PERF-003's
> 10,000-connection target, which became [Post-PoC] when the reference platform
> went away — there is now no hardware on which to state or verify it. The
> reasoning stands as product direction and the analysis is unchanged, but the
> PoC does not build it. DD-019 records what the PoC does instead.

**Decision.** Connection concurrency is decoupled from thread count. A blocked or
idle client must not hold a thread.

**Context.** WIS handles each connection on its own worker thread (`-numThreads`,
default 50), so concurrent client count is bounded by thread count. A long-poll
request or an open WebSocket occupies a thread for its lifetime. NFR-PERF-003
asks for 10,000 concurrent connections; at one thread each that is not
achievable, and this is a primary reason the reimplementation exists at all
(TRD §1.3).

**Alternatives.** Raising `numThreads` — the WIS answer. Does not scale: stack
memory and scheduler overhead grow linearly, and `-enableResourceCaching`
compounds it by retaining WaitSet, sample buffer, and DynamicData objects per
worker thread.

**Consequences.** Substantially more implementation complexity, especially where
async I/O meets Connext's threading. DDS reader notifications arrive on Connext
threads and must be handed to the I/O layer without a thread per endpoint —
AsyncWaitSet is the intended mechanism and must be validated in the OQ-5 spike.
No blocking calls anywhere on the request path, which is an invariant that needs
enforcing, not just intending.

**Revisit if.** The OQ-5 spike shows the AsyncWaitSet-to-async-I/O bridge cannot
meet NFR-PERF-001 latency. Even then the answer is a hybrid, not
thread-per-connection.

---

### DD-010
**Keep the transformation engine independent of both HTTP and DDS.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Affects:** NFR-MAINT-001, NFR-TEST-001, NFR-TEST-003, FR-XF-060…062

**Decision.** The engine is a pure function of (compiled plan, input sample) →
output sample. It has no knowledge of HTTP, no knowledge of the resource
manager, and no I/O.

**Context.** It is the highest-risk and highest-value component, needs ≥ 95% test
coverage (NFR-TEST-001) and property-based round-trip testing (NFR-TEST-003).
Neither is affordable if exercising it requires a live domain and a socket.

**Alternatives.** Letting the engine read directly from reader caches would save
a copy. Rejected — it would make the engine untestable in isolation and put
NFR-TEST-003 out of reach.

**Consequences.** A defined sample-buffer boundary between DDS and the engine,
which may cost a copy — acceptable, and no longer constrained by an absolute
budget now that §7.1 states only relative requirements. Directly enables the
`scada-web-mapc` CLI, since offline mapping evaluation is just the engine with a
file for input.

**Revisit if.** The boundary copy proves to violate NFR-PERF-002. Fix with
loaning across the boundary, keeping the interface pure.

---

### DD-011
**The expression language must be total and must not be Turing-complete.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Affects:** FR-XF-011, FR-XF-012, OQ-6

**Decision.** No loops, no recursion, no I/O, no unbounded allocation, and a
statically computable cost bound. Expressions are type-checked against XTypes at
compile time. This constrains OQ-6 rather than answering it.

**Context.** Expressions evaluate inline on the data path, on every sample, in a
process fronting plant control data. A non-terminating or unboundedly expensive
expression is a denial-of-service vector reachable through configuration — and
configuration may be editable by someone who is not a programmer.

**Alternatives.** Embedding Lua or a JS engine. Both rejected: they are
Turing-complete, they allocate unpredictably, and sandboxing them to the standard
above amounts to writing a restricted language anyway, with a much larger attack
surface.

**Consequences.** Genuinely complex logic cannot be expressed declaratively and
must go through a native plugin (DD-016), where the author is a programmer who
has accepted responsibility. Ruling out jq-style languages narrows OQ-6.

**Revisit if.** Never for the totality requirement. Individual restrictions
(e.g. bounded iteration over a bounded sequence, which is still total) may be
relaxed if the cost bound stays statically computable.

---

### DD-012
**Compile mappings to a flat instruction sequence over precomputed member
offsets.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Affects:** NFR-PERF-002, NFR-PERF-003, RISK-1, mapping-dsl §9

**Decision.** Compilation resolves every member path to an offset and type
descriptor once, emitting a flat instruction sequence. No name lookup, no tree
walk, and no allocation on the per-sample path.

**Context.** RISK-1 — the engine sits on the data path with a 20 µs p99 budget
(NFR-PERF-002). Interpreting an XML tree or looking up members by name per
sample would not come close.

**Alternatives.** (a) Walk the mapping AST per sample — simple, far too slow.
(b) JIT-compile per type — fastest, but adds a code generator and its security
surface. Flat interpretation over resolved offsets is the middle ground and
leaves (b) available later without changing the plan representation.

**Consequences.** A compilation step that must be correct, and a plan
representation distinct from the configuration AST. Plans are immutable, which
makes hot reload (FR-CFG-005) tractable: build the new plan, swap the pointer.
Also enables per-member provenance reporting (FR-XF-041), since resolution is
already explicit.

**Revisit if.** Benchmarks miss NFR-PERF-002 for realistic mappings. Escalate to
JIT for hot types rather than redesigning.

---

### DD-013
**Authorization is resource- and operation-scoped, and deny-by-default.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Affects:** NFR-SEC-003, NFR-SEC-004, NFR-SEC-009, TRD §1.3

**Decision.** A policy grants a principal a set of operations (`read`, `write`,
`create`, `delete`, `admin`) over resources matched by pattern (application,
participant, topic, view). No match means denied.

**Context.** WIS access control is API-key admission: a valid key in the SQLite
ACL file grants access to the service. There is no documented per-topic,
per-method, or read-versus-write granularity. For a SCADA boundary that is not
sufficient — "can read tank levels" and "can write pump setpoints" must be
different grants, and this gap is one of the four stated reasons for the
reimplementation.

**Alternatives.** Keeping WIS's model and relying on Connext Security Plugins
for enforcement. Rejected — DDS permissions apply to the *participant*, which is
the gateway, not to the web principal. Every web client shares the gateway's DDS
identity, so DDS-level permissions cannot distinguish them. This is exactly the
confused-deputy problem NFR-SEC-009 addresses, and it is why web authorization
must be evaluated independently and intersected with DDS permissions.

**Consequences.** A policy model, an evaluation engine, and a hot-reload path to
build and test. Interacts with OQ-7: a long-lived WebSocket bind must hold a
reference to its principal rather than a snapshot of its permissions, or policy
changes will not take effect on established connections.

**Revisit if.** The pattern-matching model proves insufficiently expressive
(e.g. attribute-based rules are needed). Extend the model; do not weaken
deny-by-default.

---

### DD-014
**Extend the WIS XSD in place rather than introducing a separate mapping file
format.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Affects:** FR-CFG-001, FR-CFG-002, FR-XF-050

**Decision.** `<transformation_library>` and its children are added to the
existing DDS XML configuration schema. One configuration file describes types,
QoS, entities, and mappings together.

**Context.** `rti_web_integration_service.xsd` is 86 lines and defines almost no
vocabulary of its own — it reuses DDS XML-Based Application Creation. There is no
existing extension point, so mapping constructs require extending the schema
either way. The choice is whether they live in the same file as the entities they
attach to.

**Alternatives.** A separate mapping file, plausibly in YAML, which would be more
pleasant to write than XML. Rejected: mappings reference topics, registered
types, and readers by name, so splitting them across files means cross-file name
resolution and two schema validators, and it becomes possible to deploy entities
without their mappings. Keeping them together makes FR-CFG-005 atomic reload
straightforward.

**Consequences.** Mapping expressions must be XML-escaped or wrapped in `CDATA`,
which is genuinely unpleasant — see mapping-dsl §5. Accepted for cohesion. Our
schema is a superset of WIS's, so a WIS config loads unchanged (FR-CFG-001) while
ours does not load in WIS — an acceptable asymmetry.

**Revisit if.** Authoring friction becomes a real complaint. The fix is a YAML
front end that compiles to the same plan, not a second source of truth.

---

### DD-015
**Serve two API surfaces: `/dds/rest1` for compatibility and `/api/v1` for
corrected semantics.**

- **Status:** PROPOSED — **likely to be withdrawn**, see amendment
- **Date:** 2026-07-27 · **Amended:** 2026-07-27 (PoC scoping) · **Resolves:** OQ-3 (provisionally) · **Affects:** FR-REST-008, §5.5

> **Amendment (PoC scoping).** OQ-3's recommendation is now option B —
> `/api/v1` only — because a compatibility surface plus a differential
> conformance suite is a large share of the total effort and proves nothing about
> the mapping thesis. On that resolution **this entry becomes MOOT**. Left
> PROPOSED pending OQ-3's formal close.

**Decision (provisional).** `/dds/rest1` reproduces WIS behavior including its
quirks; `/api/v1` enables all DD-008 divergences by default. Both are served by
one implementation, differing only in a response-shaping and defaults layer.

**Context.** Written up so the architecture accommodates it, but it *presumes*
the answer to OQ-3. If wire compatibility is not required, this decision is
unnecessary complexity and should be withdrawn rather than implemented.

**Alternatives.** `/api/v1` only (OQ-3 option B); or a partial `/dds/rest1` shim
covering only routes real clients use (option C — rejected as drafted, because
partial compatibility that looks total is a support trap).

**Consequences.** Two documented surfaces, two OpenAPI documents, and every
divergence needing a per-surface default. Roughly doubles the API-layer test
matrix.

**Revisit if.** OQ-3 resolves to B — then withdraw this entry as MOOT and keep
differential testing against WIS as a development technique only, per the note in
OQ-3.

---

### DD-016
**Model the native transformation plugin ABI on Routing Service's.**

- **Status:** PROPOSED — **out of scope for the PoC**
- **Date:** 2026-07-27 · **Amended:** 2026-07-27 (PoC scoping) · **Resolves:** OQ-1 (dependent) · **Affects:** FR-XF-052

> **Amendment (PoC scoping).** Native plugins are not in the PoC — the whole
> point is to test whether the *declarative* layer suffices, and offering a
> code escape hatch would mask the answer. Deferring this also defuses OQ-1's
> hardest sub-question, which is why OQ-1 dropped to MEDIUM.

**Decision (provisional).** The native plugin interface mirrors
`rti::routing::transf::TransformationPlugin` / `Transformation` — a factory
taking input and output `TypeInfo` plus properties, a `transform()` over sample
batches, and `return_loan()` — loaded from a shared library via an exported C
factory named in configuration.

**Context.** It is a proven design for exactly this problem, and engineers who
have written RS transformations would carry their knowledge and possibly their
code across.

**Alternatives.** A cleaner interface of our own, taking one sample at a time and
using RAII instead of explicit loan return. Genuinely nicer, but it discards
compatibility with existing plugins for a modest ergonomic gain.

**Consequences.** We inherit a batch-oriented, explicit-loan design that is
clunkier than a modern C++ interface would be. **Gated on OQ-1** — if reusing
the interface shape is not acceptable, fall back to the alternative, which is a
contained change since no plugins exist yet.

**Revisit if.** OQ-1 forbids it, or no user ever ports an RS plugin — in which
case the compatibility argument was worth nothing and a cleaner interface is
free.

---

### DD-017
**Encode 64-bit integers as JSON strings by default.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Affects:** FR-TYPE-005, FR-TYPE-006

**Decision.** `int64` and `uint64` are emitted as JSON strings by default,
configurable to numbers. On input, both are accepted.

**Context.** JSON numbers are IEEE-754 doubles in every browser. Values above
2^53 lose precision silently. DDS types carry `int64` routinely — timestamps in
nanoseconds, sequence numbers, instance counters — so this is the common case,
not an edge case.

**Alternatives.** Numbers by default, matching most JSON APIs and probably WIS.
Rejected: the failure is silent corruption of a plausible-looking value, which is
the worst failure class in a SCADA context. Losing precision on a nanosecond
timestamp produces a wrong-but-believable time.

**Consequences.** Clients must parse strings for 64-bit fields, and this
diverges from WIS. Published JSON Schemas must reflect the encoding, and the
policy must be discoverable through them (FR-XF-040).

**Revisit if.** Client feedback shows the string encoding causes more bugs than
it prevents — though per-field opt-out is the better response than flipping the
default.

---

### DD-018
**Scope the project to a prototype PoC: no hardware performance targets, no
embeddable library.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Resolves:** OQ-9, OQ-10 · **Affects:** §1.1–1.3, §7.1, §8.1, §10, §12, NFR-MAINT-002, NFR-PORT-001

**Decision.** The deliverable is a prototype whose purpose is to test one thesis:
that a declarative mapping layer on the web boundary can present a data model
that does not exist in the IDL, correctly and bidirectionally. There is no target
hardware, so no absolute performance requirements. There is no embeddable-library
requirement; standalone service only.

**Context.** Direction from the project owner. The v0.1 TRD was written as a
product specification — tiered platforms, CI performance gates, 72-hour soak,
coverage thresholds, client SDKs — which is the wrong shape for a prototype and
would have consumed the schedule on scaffolding rather than on the thesis.

**Alternatives.** Keeping the production requirements as aspirational and simply
not doing them. Rejected: unenforced requirements are worse than absent ones,
because they make the document untrustworthy and give false comfort that a gap is
covered. Everything deferred is now marked **[Post-PoC]** so the gap is
enumerable rather than implied.

**Consequences.**

*What was removed:* FR-LIB-001…005 (§8.1) and NFR-MAINT-002 — removed, not
deferred; embedding would be a new requirement, not a resumed one. Absolute
performance targets and the CI performance gate. Multi-platform tiering.
Coverage gates, fuzzing, soak, sanitizer matrix. Client SDKs. Full authz model
and observability stack, deferred.

*What was strengthened:* §7.1 was rewritten as *relative and shape* requirements
rather than deleted, because those are machine-independent and therefore the only
performance claims a PoC can honestly make. Round-trip property testing
(NFR-TEST-002) and key semantics (§6.5) keep production-strength rigor — they are
the evidence for the thesis, not scaffolding. §12 was reordered to put the engine
first (see below).

*What loosened elsewhere:* dropping NFR-MAINT-002 reopened the HTTP stack
decision (OQ-5) to dependency options previously excluded. Worth flagging
because a dropped requirement quietly widening an earlier choice is easy to miss.

*Phase reordering:* transformation moved from P3 to P1, ahead of DDS and HTTP.
The v0.1 order would have built a production-grade streaming layer before
touching the thesis — for a prototype that is backwards, and risks the schedule
expiring before the question gets asked. DD-010 (engine independent of HTTP and
DDS) is what makes the inversion possible and is now load-bearing.

**Revisit if.** The PoC succeeds and productization begins. At that point this
entry is superseded rather than amended, and every [Post-PoC] marker becomes a
work item. See RISK-9 — the failure mode is the prototype being promoted
*without* that transition happening.

---

### DD-019
**The PoC uses the simplest workable concurrency model, not the target
architecture.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Affects:** DD-009, OQ-5, §12 P3

**Decision.** Thread-per-connection, or whatever the chosen HTTP library gives
for free, is acceptable for the PoC. Async I/O (DD-009) is deferred.

**Context.** DD-009 rejected thread-per-connection on the strength of a
10,000-connection requirement. With no reference platform that requirement is
[Post-PoC], so its justification does not currently apply. Meanwhile the mapping
thesis is entirely indifferent to how connections are serviced — a mapped view is
just as correct or incorrect over one connection as over ten thousand.

**Alternatives.** Building async I/O anyway, on the argument that retrofitting it
later is expensive. That argument is real but does not survive the priorities: it
spends the prototype's schedule on the one part of the system whose feasibility
is *not* in doubt. Thread-per-connection at PoC scale is a known quantity; the
mapping engine is not.

**Consequences.** The PoC will not demonstrate connection scaling, and must not
be represented as having done so. If it is later productized, the web layer is
substantially rewritten — acceptable, because it is the best-understood part of
the system and the least likely to invalidate anything learned from the engine.

One invariant to hold anyway, because it costs nothing now and is expensive to
retrofit: **keep blocking DDS calls out of the mapping and serialization path.**
Even under a blocking connection model, an engine that assumes it may block is
much harder to move to async later.

**Revisit if.** The PoC needs to demo more than a handful of concurrent clients,
or productization begins — at which point DD-009 takes effect as written.
**Amended by [DD-022](#dd-022):** this is no longer merely a prototype shortcut.

---

### DD-020
**Adopt a four-component architecture, with a separate scada-selector app owning
key-based selection.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Affects:** FR-XF-021, DD-022, [system-architecture.md](system-architecture.md)

**Decision.** The deliverable is four components: **scada-sim** (exists, Python,
Level 0/1), **scada-selector** (new, Level 2), **scada-web** (the gateway), and a
**browser interface**. scada-selector subscribes to a `ValueRequest` command topic
carrying `ADD`/`DELETE`/`METADATA` for a `uid`, maintains the set of enabled
uids, and republishes only those onto an output topic. scada-web holds exactly one
reader and one writer against it, regardless of client count.

**Context.** Direction from the project owner. The alternative — which the TRD
implicitly assumed — was per-client content-filtered readers inside scada-web.
The control topic for this already exists in
[sim/PlcValue.idl](../sim/PlcValue.idl) (`ValueRequest`, `Command_t`), so the
data model anticipated this design before the requirement was stated.

**Alternatives.** Per-client content-filtered DataReaders in the web tier.
Rejected on DDS resource grounds rather than threading: a reader per client means
discovery traffic per client, a queue per client, and filter predicates evaluated
once per sample per reader inside the middleware — plus discovery churn every
time an operator navigates between mimic screens. Expressing selection as *data*
rather than as *entities* avoids all of it.

**Consequences.**

*Good:* scada-web's DDS footprint is fixed and small. Selection logic is testable
without a web tier at all — drive `ValueRequest` by hand and watch the output
topic with `rtiddsspy`, which makes scada-selector the cheapest real progress
available (system-architecture §9).

*Cost:* a new component to build and operate, and a new failure mode — if
scada-selector is down, everything downstream is blind. It also introduces
interest-refcounting state in scada-web (SR-001…004): two clients watching the
same tag must not have one's disconnect turn the tag off for the other. That
refcount is a classic bug source, and reconciliation after a filter restart
(SR-003) is the part most likely to be forgotten, because its symptom is a blank
display with no error.

*Deliberately not moved into the filter:* view-schema mapping stays in scada-web.
The filter operates on the DDS data model; the moment it starts shaping data for
web clients, the separation collapses and both components need to know about
views.

**Revisit if.** The refcounting and reconciliation state in scada-web turns out
to cost more than the per-client readers it replaced — unlikely, but it is the
honest comparison.

---

### DD-021
**scada-selector enriches values with cached MetaData; cross-topic join stays out
of the mapping engine.**

- **Status:** **SUPERSEDED by [DD-024](#dd-024)** — the conclusion (no general join in the engine) survives; the placement was wrong
- **Date:** 2026-07-27 · **Superseded:** 2026-07-27 · **Resolves:** OQ-4 (by relocation) · **Affects:** FR-XF-022, system-architecture §6.2

> **Superseded.** This entry put the `IdValue` × `MetaData` correlation in
> scada-selector. A role clarification showed that is the wrong component:
> enrichment is data-model work, and it makes the model *fatter* while the
> presentation role exists to make it *slimmer*. The correlation moved to
> scada-web, which needs the same map for its tag catalogue regardless.
> **OQ-4's answer is unchanged** — general join stays out of the v1 engine.
> Reasoning preserved below.

**Decision.** scada-selector caches `MetaData` per uid and publishes an
`EnabledValue` type carrying the value together with `longName`, `hostname`, and
`limits`. FR-XF-022 (join) stays out of the v1 mapping engine.

**Context.** A useful HMI view is `{tag, value, units, limits, alarm_state}`,
which spans `IdValue` and `MetaData` correlated on `uid`. That is precisely the
`latest_value` join that OQ-4 recommended cutting from the PoC — so **the natural
view for this system requires the one transformation feature we planned to drop.**
Discovered only when the real IDL appeared; not visible when the TRD was drafted.

**Alternatives.** (a) Reinstate join in the mapping engine. Rejected: it is the
single largest driver of state in the engine — a per-key cache with eviction,
memory bounds, and staleness semantics — and it would land in P1, the phase whose
whole purpose is to derisk the engine quickly. (b) Have the browser correlate the
two topics itself. Rejected: it pushes DDS data-model knowledge into the HMI,
across a level boundary the architecture is supposed to maintain.

scada-selector is the right home because it *already* holds per-uid state for the
enabled set, so a per-uid MetaData cache is nearly free, and `MetaData` is
`TRANSIENT_LOCAL`, so the filter reliably has every tag's description regardless
of startup ordering.

**Consequences.** The join is hard-coded in C++ rather than declarative — a real
loss of generality, accepted because there is exactly one join in this system and
its shape is fixed. `EnabledValue` becomes a slightly denormalized type,
repeating static metadata on every sample; at SCADA rates that is not a concern,
but it is a genuine cost rather than a free lunch.

**Revisit if.** A second join appears, or a view needs correlation the filter does
not already perform. That is the signal to reopen OQ-4 and build it declaratively
rather than adding a second hard-coded special case.

---

### DD-022
**Thread-per-connection is correct for this system, not merely tolerable for the
PoC.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Affects:** DD-009 (closed), DD-019, OQ-5, NFR-PERF-005

**Decision.** Close DD-009 (async I/O) rather than leaving it deferred. The
concurrency model chosen in DD-019 is the intended design, not a shortcut to be
unwound later.

**Context.** Two separate things resolve the threading question, and conflating
them would leave a wrong conclusion on the record.

1. **scada-selector (DD-020) removes the per-client DDS cost** — no reader per
   client, no repeated filter evaluation, no discovery churn. This was the
   serious resource problem and it is genuinely solved.

2. **But it does not reduce connection count.** N browser clients are still N
   sockets; thread-per-connection still means N threads. The filter app does not
   touch that axis, and it would be wrong to claim otherwise.

What actually retires the concern is that **NFR-PERF-003's 10,000-connection
target was the wrong requirement for this system.** I wrote it by importing a
web-scale assumption into a plant-control context. The client population is
Level 2 operator consoles and HMI displays — tens, plausibly low hundreds. Thread
-per-connection is comfortable there with room to spare.

**Alternatives.** Keeping DD-009 as deferred product direction. Rejected because
it would leave a standing implication that the web tier needs rewriting before
production, which is not true at this client scale and would misdirect effort.

**Consequences.** OQ-5's decision criterion is now simply time-to-working, which
points at Boost.Beast; HTTP/2 and connection-scaling comparisons are irrelevant.
The system must not be represented as having demonstrated large-scale connection
fan-out, because it has not and is not designed to.

The DD-019 invariant still stands and is worth keeping even here: **no blocking
DDS calls on the mapping or serialization path.** Cheap to honor now; expensive to
retrofit if the client population is ever wrong by an order of magnitude.

**Revisit if.** The client population turns out to be thousands — e.g. a
read-only public dashboard is added, which is a different system with a different
shape. Then DD-009 is reinstated as written.

---

### DD-023
**`ValueRequest` must be published RELIABLE + KEEP_ALL.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Affects:** system-architecture §4.1, SR-001

**Decision.** The `ValueRequest` topic uses `RELIABLE` reliability with
`KEEP_ALL` history on both writer and reader. Not `KEEP_LAST`.

**Context.** `ValueRequest` has no `@key` in
[sim/PlcValue.idl](../sim/PlcValue.idl), so every command lands on a single
instance. Under `KEEP_LAST depth=1` — the QoS the sim uses for its other
topics — a writer may replace an unacknowledged sample with a newer one.
`RELIABLE` guarantees the *latest* sample is delivered, not that every sample is.
So a burst of `ADD(1) ADD(2) ADD(3)` can silently lose the first two.

This is a command stream, where every message carries distinct intent and none is
superseded by the next. It needs `KEEP_ALL`.

**Alternatives.** (a) Add `@key uid` to `ValueRequest`, making each uid its own
instance so `KEEP_LAST depth=1` retains one command per uid. Genuinely tempting
and arguably the better data model — but the keyed semantics are subtly wrong,
because `ADD(5)` followed quickly by `DELETE(5)` would have the DELETE replace
the ADD on the same instance, which happens to be the right outcome here but only
by luck. Changing the IDL also touches the sim. Worth considering if the IDL is
open to revision. (b) Batching commands into one sample — a sequence of requests
rather than one per sample. Reduces exposure but does not remove it.

**Verified against Connext 7.7.0 documentation.** Under `KEEP_LAST`, when an
instance already holds `depth` samples the DataWriter replaces the oldest
**independently of its acknowledged status** and still returns `RETCODE_OK`. The
guarantee is "reliably deliver the latest N samples per instance", not "deliver
every write". Two specifics that follow:

- **`KEEP_ALL` must be set on both the writer and the reader.** Setting it on
  only one side does not give strict reliability.
- **`write()` blocks and then returns `RETCODE_TIMEOUT`** once
  `reliability.max_blocking_time` expires. Callers must check the return — a
  timed-out command is a silently dropped command otherwise, which is the exact
  failure this decision exists to prevent.

**Consequences.** `KEEP_ALL` means the writer blocks when resource limits are
reached rather than dropping — correct behavior for commands, but send paths must
handle a blocking or failing write rather than assuming fire-and-forget. Requires
explicit `RESOURCE_LIMITS` so a stuck or dead filter cannot block scada-web
indefinitely. Backpressure here is a feature: it surfaces overload instead of
silently discarding intent.

**Consider also:** a `LIFESPAN` QoS on `ValueRequest` so that stale commands
queued during an outage do not execute long after they stopped being meaningful.
Tracked as [OQ-18](questions.md#oq-18).

**Failure mode if ignored:** tags silently never turn on, load-dependently, most
likely when an operator opens a screen requesting many tags at once — i.e. it
will pass every light test and fail in the demo.

**Revisit if.** The IDL is opened for revision, in which case evaluate keying
`ValueRequest` on `uid` as the cleaner fix — tracked as
[OQ-17](questions.md#oq-17), which also notes that a keyed `TRANSIENT_LOCAL`
"desired state" topic would let a restarted scada-selector recover its enable set
from the middleware instead of needing reconciliation (SR-003).

---

### DD-024
**Selection and presentation are separate roles; all data-model work — including
metadata lookup — belongs to presentation.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Supersedes:** [DD-021](#dd-021) · **Affects:** FR-XF-022, OQ-13, OQ-20, system-architecture §1a, §4.2, §6.2

**Decision.** Two roles, cleanly divided:

- **Role 1, selection (scada-selector):** gate which uids flow. **The output type is
  the input type** — filtered `IdValue` republished on a different topic name. No
  data-model changes of any kind.
- **Role 2, presentation (scada-web):** all model transformation and protocol
  conversion. Subscribes to `MetaData` directly and holds the uid→metadata map.

The enriched `EnabledValue` type from DD-021 is withdrawn.

**Context.** DD-021 put the `IdValue` × `MetaData` correlation in scada-selector to
keep join out of the mapping engine. A role clarification exposed the flaw:
enrichment is data-model work, and it makes the model **fatter**, while the
presentation role exists to make it **slimmer**. Fattening in one component so the
next can slim it is incoherent, and it placed model concerns in a component whose
job is selection.

**The decisive argument is duplication, not purity.** scada-web needs the
uid→metadata map anyway — it is the tag catalogue for name-based lookup
([OQ-13](questions.md#oq-13)). Under DD-021, scada-web would have held the
catalogue *and* received the same metadata repeated on every value sample. Same
data, twice, one copy denormalized.

**Alternatives.** (a) Keep DD-021's enrichment — rejected above. (b) Reinstate
general join (FR-XF-022) in the engine — rejected: it is the largest driver of
engine state and this correlation does not need it (below). (c) Have the browser
correlate — rejected, pushes DDS data-model knowledge across a level boundary.

**Consequences.**

*Simplifications, all of them:*
- **No new type.** `SelectedValue` reuses `IdValue`, so
  [OQ-20](questions.md#oq-20) shrinks to almost nothing — no definition to
  duplicate or drift across components.
- **No denormalization.** Static metadata is no longer repeated per sample.
- **The filter becomes expressible as a plain route** — input topic `IdValue`,
  output topic `SelectedValue`, same registered type — which is what makes the
  Processor recommendation ([OQ-23](questions.md#oq-23)) clean.
- **One map serves two needs** in scada-web: catalogue and view lookup.

*Cost:* scada-web gains a second reader and holds metadata for all tags, not just
enabled ones. Bounded by tag count at a few hundred bytes each — megabytes at
plant scale, and it is what a catalogue requires regardless.

*New DSL surface:* a `<lookup>` construct (mapping-dsl §3.8), which is **not**
FR-XF-022. Reference-data lookup is single-key exact match against a
slowly-changing keyed topic, read-only, with no time semantics and no eviction
policy. General join has all four. Keeping them distinct is what preserves OQ-4's
answer.

**Revisit if.** A correlation appears that needs time semantics, a non-static
source, or bidirectional participation. That is a real join, and it reopens OQ-4
rather than stretching `<lookup>` to cover it.

---

### DD-025
**Enable/disable ids over the in-band `ValueRequest` DDS topic, not Routing
Service remote administration.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Affects:** OQ-23, DD-020, DD-023, system-architecture §4.1

**Decision.** Per-id enablement travels as ordinary DDS data on the
`ValueRequest` topic, consumed as a named **input** of the Processor's route.
Routing Service remote administration is **not** used for per-id commands — it
remains the right tool for operational changes (disable a route, change a
non-per-id property, save config, manual intervention via `rtirssh`).

**Context.** If scada-selector becomes a Routing Service Processor
([OQ-23](questions.md#oq-23)), RS's own admin plane looks like a natural command
channel: it is DDS request/reply on
`rti/service/administration/command_request` with `CREATE`/`GET`/`UPDATE`/`DELETE`,
and a Processor's properties *can* be updated at runtime. So the question is real
rather than rhetorical.

**Why remote administration is the wrong tool here.** Verified against 7.7.0 docs:

1. **It is a control plane, not a data path.** Every change is a request/reply
   round trip. An operator opening a mimic with 50 tags is 50 round trips, or one
   bulky XML document.
2. **There is no processor resource path.** You `UPDATE` the *route* with a
   `<processor><property>` block, so the granularity is "replace the processor's
   property set", not "add uid 5". Concurrent changes from two clients race on the
   whole set.
3. **Properties are string key/value pairs in XML.** A set of hundreds of uids
   becomes either one giant comma-separated value rewritten wholesale, or one
   property per uid. Both are poor.
4. **Only mutable properties can change while enabled.** Anything else requires
   disable → update → re-enable, which drops the route and its data flow.
5. **It couples scada-web to Routing Service.** OQ-23 is still open. The
   `ValueRequest` design works identically whether scada-selector is a Processor or
   a standalone app; an admin-based design breaks entirely if OQ-23 resolves to
   standalone. Given an open question, prefer the mechanism that survives both
   answers.

**Alternatives.** (a) Remote admin — rejected above. (b) A dynamically rewritten
content-filter expression on the Input via admin `UPDATE` — already rejected in
system-architecture §1a: `uid = 1 OR uid = 2 OR ...` collapses past a few dozen
tags. (c) In-band DDS topic — chosen.

**Consequences.** The Processor declares two inputs — `ValueRequest` (control) and
`IdValue` (data) — and one output. `on_data_available(Route&)` fires when either
has data, so the processor must drain control first, then data, in that order
within each callback. The enable set is processor state, which is why
[DD-023](#dd-023)'s `KEEP_ALL` matters: a lost `ADD` is a tag that silently never
turns on.

**Unresolved second axis, tracked as [OQ-24](questions.md#oq-24):** this decision
covers *transport*, not *semantics*. Whether the topic carries incremental deltas
(`ADD`/`DELETE`, as the IDL does today) or a full desired-state set is a separate
question with real consequences for DD-023 and SR-003. Both work over this
transport.

**Revisit if.** Command rate ever becomes high enough to matter as a data path —
it will not; this is operator-driven, so tens per second at worst.

---

### DD-026
**scada-selector uses compiled IDL types, not `DynamicData` — which rules out
hosting it as a Routing Service Processor.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Resolves:** [OQ-23](questions.md#oq-23) for Role 1 · **Affects:** DD-002 (scoped), DD-020, OQ-20, architecture-comparison §5, §7

**Decision.** scada-selector is built against **rtiddsgen-generated C++ types**
from `PlcValue.idl`, and runs as a **standalone C++ application**. It is not a
Routing Service Processor.

**Context.** Requirement from the project owner: the selector subscribes to
high-rate SCADA topics and republishes only selected samples, so per-sample cost
is its defining constraint. With `DynamicData`, reading the key is
`data.value<int32_t>("uid")` — a member lookup by name on every sample. With a
generated type it is `sample.uid()`, a struct field access resolved at compile
time. On the hot path of a high-rate stream that difference is the whole point of
the component.

**The finding that forces standalone.** Verified against 7.7.0 documentation:
**Routing Service's built-in DDS adapter is DynamicData-based, and there is no
documented XML configuration that binds `<dds_input>`/`<dds_output>` to generated
C++ types for a Processor's `TypedInput<T>`.** `TypedInput<T>` is a real framework
capability, but with the built-in DDS adapter the route's data representation is
DynamicData. Getting generated types into a Processor would require a *custom
adapter* — i.e. writing DDS-to-DDS plumbing to replace the adapter that exists
precisely to provide it. Absurd, and rejected.

So the compiled-types requirement and the Processor recommendation are
incompatible. **The requirement wins**; the Processor recommendation for Role 1 is
withdrawn.

**Alternatives considered.**

- *DynamicData with `skip_deserialization`.* Connext can keep a `DynamicData`
  sample CDR-backed rather than eagerly deserializing, which helps when a route
  forwards without inspecting fields. It does not fit: the selector must inspect
  `uid` on every sample to decide, which is exactly the case the optimization
  does not cover.
- *Custom RS adapter exposing generated types.* Rejected above.
- *Content-filtered topic driven by admin updates.* Already rejected
  (system-architecture §1a) — the expression collapses past a few dozen tags.

**Consequences.**

*Lost:* everything Routing Service was going to supply free for this component —
XML configuration, lifecycle, remote administration, and monitoring topics. The
selector now owns its own config, logging, and shutdown. This is the real price of
the requirement and it should be stated plainly rather than discovered.

*Gained:* full control of the hot path, and the ability to use techniques that are
awkward or impossible inside RS (below).

*Type flexibility:* the selector is compiled against `PlcValue.idl`. A new SCADA
type means a rebuild. Correct for Role 1 — it handles one known high-rate stream —
and precisely the opposite of Role 2's requirement, which is why DD-002 is now
scoped rather than superseded.

*[OQ-20](questions.md#oq-20) gets cleaner:* one IDL, two automated derivations —
`rtiddsgen` for the selector's C++ types, `rtiddsgen -convertToXml` for the XML
types library scada-web loads at runtime (DD-007). Neither is hand-transcribed, so
there is nothing to drift.

*[DD-025](#dd-025) is vindicated:* its fifth argument was that the in-band
`ValueRequest` topic works whether or not the selector is an RS Processor. It is
now not one, and the command path needs no change.

**Implementation note — filtering without touching the payload.** `IdValue` is
keyed on `uid`, so `SampleInfo::instance_handle` identifies the tag without
deserializing anything. `DataReader::lookup_instance()` maps a known key value to
its handle, so the selector can hold a set of *enabled instance handles* and
filter on `SampleInfo` alone. `take_instance()` is a further option — read only
the instances that are enabled. Worth benchmarking against the straightforward
`sample.uid()` check, which is already cheap with compiled types; do not assume
the clever version wins.

**Revisit if.** RTI documents a way to bind generated types to built-in DDS
adapter routes, or measurement shows `DynamicData` key access is not in fact the
bottleneck at the rates involved — in which case the Processor option, and the
free infrastructure with it, becomes available again.
