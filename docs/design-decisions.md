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
| [DD-002](#dd-002) | Operate on `DynamicData` throughout; no generated types | SUPERSEDED by DD-052 | — |
| [DD-003](#dd-003) | Fix `to`/`from` to mean view/wire, not output/input | ACCEPTED | — |
| [DD-004](#dd-004) | Classify mapping invertibility at compile time | ACCEPTED | — |
| [DD-005](#dd-005) | Require `<key_mapping>`; restrict it to pure assignment | ACCEPTED | — |
| [DD-006](#dd-006) | Target C++17 (scada-selector) | ACCEPTED | — |
| [DD-007](#dd-007) | No runtime IDL parsing in v1 | ACCEPTED | — |
| [DD-008](#dd-008) | Do not inherit WIS's insecure or ambiguous defaults | ACCEPTED | — |
| [DD-009](#dd-009) | Async I/O, not thread-per-connection | CLOSED by DD-022 | — |
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
| [DD-021](#dd-021) | scada-selector enriches values with MetaData; join stays out of the engine | SUPERSEDED by DD-024 | OQ-4 |
| [DD-022](#dd-022) | Thread-per-connection is correct for this system, not just for the PoC | ACCEPTED | — |
| [DD-023](#dd-023) | `ValueRequest` must be RELIABLE + KEEP_ALL | ACCEPTED | — |
| [DD-024](#dd-024) | Selection and presentation are separate roles; metadata lookup belongs to presentation | ACCEPTED | supersedes DD-021 |
| [DD-025](#dd-025) | Enable/disable ids over the in-band DDS topic, not Routing Service remote administration | ACCEPTED | — |
| [DD-026](#dd-026) | scada-selector uses compiled types — which rules out a Routing Service Processor | ACCEPTED | OQ-23 (Role 1) |
| [DD-027](#dd-027) | scada-selector downrates per id; scada-web relays ids, selector handles **rate** via PERIOD command | ACCEPTED | — |
| [DD-045](#dd-045) | `mapping.py` applies WIS-compatible DynamicData→JSON transforms automatically | SUPERSEDED by DD-052/DD-053 | OQ-50, OQ-54, OQ-58 |
| [DD-052](#dd-052) | scada-web uses Python generated types, not DynamicData | ACCEPTED | — |
| [DD-053](#dd-053) | Field mapping is Python code, not config | ACCEPTED | — |

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

- **Status:** SUPERSEDED by [DD-052](#dd-052)
- **Date:** 2026-07-27 · **Amended:** 2026-07-27 · **Affects:** FR-DDS-006, FR-TYPE-001

> **Superseded.** This was the original generic-gateway premise. DD-026 already
> chose compiled C++ types for scada-selector; DD-052 later rejected DynamicData
> for scada-web as well, because this SCADA system has a fixed commissioned data
> model. The reasoning below is historical context, not current implementation
> guidance.

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
**Target C++17 for scada-selector.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Affects:** NFR-PORT-003

> **Scope note.** This applies to **scada-selector** (the C++ component).
> scada-web is Python and is not subject to a C++ standard requirement.

**Decision.** C++17 is the required standard for the C++ component. C++20
features must not be mandatory; C++20 may be enabled where a newer toolchain
exists.

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

- **Status:** **CLOSED by [DD-022](#dd-022)** — thread-per-connection is the intended design
- **Date:** 2026-07-27 · **Amended:** 2026-07-27 (PoC scoping) · **Closed:** 2026-07-27 · **Affects:** NFR-PERF-005 [Post-PoC], OQ-5

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
carrying `ADD`/`DELETE`/`METADATA`/`PERIOD` as a discriminated union, maintains the
set of enabled uids and a global minimum separation, and republishes only those
onto an output topic. scada-web holds exactly one reader and one writer against it,
regardless of client count.

**Context.** Direction from the project owner. The alternative — which the TRD
implicitly assumed — was per-client content-filtered readers inside scada-web.
The control topic for this already exists in
[dds/idl/PlcValue.idl](../dds/idl/PlcValue.idl) (`ValueRequest`, `Command_t`), so the
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

**Context.** `ValueRequest` is a discriminated union switched on `Command_t`
([dds/idl/PlcValue.idl](../dds/idl/PlcValue.idl)), with no `@key`, so every command
lands on a single instance. Under `KEEP_LAST depth=1` — the QoS the sim uses for
its other topics — a writer may replace an unacknowledged sample with a newer one.
`RELIABLE` guarantees the *latest* sample is delivered, not that every sample is.
So a burst of `ADD(1) ADD(2) ADD(3)` can silently lose the first two.

This is a command stream, where every message carries distinct intent and none is
superseded by the next. It needs `KEEP_ALL`.

**Alternatives.** (a) Key the union by discriminator or uid — a `@key`-ed
approach so `KEEP_LAST depth=1` retains one command per uid. Genuinely tempting
but the semantics are subtly wrong for a union: `ADD(5)` followed quickly by
`DELETE(5)` would have the DELETE replace the ADD on the same instance, which
happens to be the right outcome but only by luck. (b) Batching commands into one
sample — a sequence of requests rather than one per sample. Reduces exposure but
does not remove it.

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

- **Status:** ACCEPTED, amended by [DD-028](#dd-028) · **Date:** 2026-07-27 · **Supersedes:** [DD-021](#dd-021) · **Affects:** FR-XF-022, OQ-13, OQ-20, system-architecture §1a, §4.2, §6.2

> **Amended by [DD-028](#dd-028) — transport path only.** The "subscribes to
> `MetaData` directly" clause below is withdrawn: metadata now reaches scada-web
> through scada-selector, so the selector can be the sole hard-RT ↔ soft-RT
> conduit. **Everything else here stands**, and the ownership argument is
> untouched: scada-web still holds the uid→metadata map and performs all
> correlation, and the selector still holds no metadata map. Forwarding a topic
> unmodified is transport; the `EnabledValue` merge this entry withdrew stays
> withdrawn.

**Decision.** Two roles, cleanly divided:

- **Role 1, selection (scada-selector):** gate which uids flow. **The output type is
  the input type** — filtered `IdValue` republished on a different topic name. No
  data-model changes of any kind.
- **Role 2, presentation (scada-web):** all model transformation and protocol
  conversion. ~~Subscribes to `MetaData` directly and~~ holds the uid→metadata map
  (receives `MetaData` via the selector per DD-028).

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

---

### DD-027
**scada-selector selects ids and applies one global minimum separation.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Affects:** DD-002, DD-020, DD-024, DD-025, OQ-17, OQ-24, system-architecture §1a, §4.1

**Decision.** Role 1 is **selection plus global downrating**. scada-web sends the
set of enabled uids and the current global minimum separation. scada-selector
enforces both, absorbing the full-rate stream with compiled types and emitting a
decimated one. It still makes **no data-model change** — the output type is the
input type.

**Context — the field finding this answers.** Batched reception of small samples
can still concentrate work into bursts: Connext does **not** keep a batch as a
unit in the reader queue — each sample in a batch is deserialized and processed
individually. Batching reduces network overhead without reducing per-sample
application work. A display tier then adds view mapping, JSON serialization, and
browser fan-out on top of the DDS receive cost.

The selector is the mitigation. It sits where the high-rate batched stream
arrives, handles it with compiled types (DD-026), and emits a stream reduced on
**both** axes before scada-web sees it:

| | Reduction | Effect on the downstream presentation path |
|---|---|---|
| Tags | Only enabled uids | Fewer instances |
| Rate | Global minimum separation | Fewer samples per instance per second |

The two multiply. An operator display showing 200 of 5,000 tags at 1 Hz, from a
source publishing all 5,000 at 50 Hz, is a reduction of three orders of magnitude
before the web gateway, JSON path, and browser see the data. DD-052 later removed
`DynamicData` from scada-web, but the rate decision still stands: high-rate field
traffic belongs upstream of the presentation tier.

**Consequences.**

*The IDL was redesigned as a discriminated union* — **applied 2026-07-28.** `ValueRequest`
is now a `Command_t`-discriminated union carrying case-specific payloads:

```idl
union ValueRequest switch (Command_t) {
case ADD:
    AddRequest_t     addRequest;   // {uid, name}
case DELETE:
case METADATA:
    UniqueId_t       uid;
case PERIOD:
    PeriodRequest_t  periodRequest; // {period_ms}
};
```

The `PERIOD` case sets the selector's global minimum separation: `0` means use
the selector YAML default, nonzero overrides the runtime setting. `ADD` enables
forwarding for a uid; `DELETE` and `METADATA` operate on an existing uid. Integer
milliseconds rather than float Hz, so there is no rounding ambiguity. The selector
loads `selection.default_min_separation_ms` from YAML at startup.

*This was the minimal change, not the fuller redesign.*
[OQ-17](questions.md#oq-17) and [OQ-24](questions.md#oq-24) recommend going
further — `@key uid` with `{enabled, period_ms}` and `TRANSIENT_LOCAL`, i.e.
keyed desired state rather than a command stream. That step was **not** taken, so
its two benefits are not yet realised: [DD-023](#dd-023)'s `RELIABLE + KEEP_ALL`
is still required, and SR-003 reconciliation is still required. Both remain open
questions rather than settled design.

*Do not batch the selector's output.* Batching would reconcentrate exactly the
burst the downrating exists to remove, and buys little once volume is low. Batch
the *input* side if the publisher benefits; leave the output unbatched.

*Refcounting remains uid-only.* The minimum separation is global runtime state,
not part of the per-client interest key. Changing it updates the selector for all
active uids.

*Rate semantics — recommended, not yet ratified:*
- **Decimate on arrival**, not on a timer: keep a per-uid `last_emitted`, forward
  the first sample arriving at or after `last_emitted + period`. O(1) per sample,
  no timers, and naturally correct when the source is slower than requested.
  Even-spacing via a timer would be smoother but requires holding samples and
  waking up; not worth it for display data.
- **Lifecycle events bypass the rate limit.** Dispose and unregister
  (`valid_data == false`) must be forwarded immediately. A display learning that a
  tag went stale at the next tick rather than now is a real defect, and this is
  the sort of detail that gets missed.
- **Wall clock, not `valueTime`**, for the decimation decision — source timestamps
  may be irregular or skewed.

**Revisit if.** Measurement shows the typed scada-web path — DDS receive, view
mapping, JSON serialization, and WebSocket fan-out — is still the bottleneck after
downrating. Mitigations then are batching/flow-control on the web side,
additional decimation, or per-view sampling policy; do not move data-model work
back into the selector to paper over presentation cost.

---

### DD-028
**scada-selector is the sole conduit between the hard-real-time field side and the
soft-real-time presentation side; `MetaData` is forwarded through it.**

- **Status:** ACCEPTED, QoS amended by [DD-029](#dd-029) · **Date:** 2026-07-27 · **Amends:** [DD-024](#dd-024) (transport path only) · **Affects:** DD-020, DD-023, DD-027, OQ-13, OQ-22, OQ-26, SR-003, system-architecture §2, §4.3, §4.4, §7, scada-web `config.yaml`

> **QoS amended by [DD-029](#dd-029).** The web side is `BEST_EFFORT`, so two
> claims below are superseded: the forwarded catalogue is **not**
> `TRANSIENT_LOCAL` and the selector is **not** a durability re-origin —
> `TRANSIENT_LOCAL` requires `RELIABLE` on both ends, so the catalogue is served
> on request instead. The `KEEP_LAST`-never-`KEEP_ALL` rule still holds but is no
> longer what carries the invariant: a `BEST_EFFORT` writer cannot block on a slow
> consumer at all. **The boundary itself, and every structural claim about it, is
> unchanged** — DD-029 only makes it cheaper to enforce.

**Decision.** The system has two timing zones, and scada-selector is the boundary
between them:

- **Hard real time (field side):** sim L1 publishers and the selector's readers.
  Bounded, deterministic latency; a missed deadline is a failure.
- **Soft real time (web side):** the selector's writers, scada-web, browsers.
  Latency is a target; a late or dropped display update is a degradation.

Two consequences, and the second is what forced this entry:

1. **`PLC::MetaData` is forwarded through the selector** — read on the field side,
   republished unmodified as `PLC::SelectedMetaData` on the web side — rather than
   read directly by scada-web.
2. **No component other than the selector has DDS endpoints on both sides.**
   scada-web has no field-side reader, no field-side participant, and no field-side
   discovery traffic.

**Context.** DD-024 correctly moved metadata *ownership* to scada-web: the
uid→metadata map, correlation, and the `<lookup>` construct are presentation work.
But it also had scada-web subscribe to `MetaData` **directly**, and that clause —
incidental to DD-024's argument — put a Level 2 web gateway on the field-side
domain. The boundary was drawn in the diagram and then crossed by one topic.

The cost of that crossing is not the metadata bytes; `MetaData` is written once per
tag at startup. It is that scada-web's **discovery traffic, restarts, and
per-client churn appear on the control network**, and that no domain or zone
separation is expressible while a soft-real-time consumer holds a field-side
endpoint.

**What this does and does not change about DD-024.** Only the transport path
changes. Ownership does not: scada-web still holds the uid→metadata map, still
performs all correlation, and the selector still holds no metadata map (its
catalogue lives entirely in middleware caches it configures but does not
interpret). Forwarding two topics unmodified is transport; merging metadata into
value samples — the `EnabledValue` design DD-024 withdrew — is presentation, and
stays withdrawn. The test: the selector reads `uid` and no other field of either
type.

**Alternatives.** (a) **Keep the direct subscription** — rejected: it is the one
thing that makes the zone boundary unenforceable, for no benefit beyond one fewer
hop on a startup-only topic. (b) **Forward metadata only for selected uids** —
rejected: scada-web's map *is* the tag catalogue, needed to answer "what tags
exist" and to resolve a name to a uid before anything is selected. Filtering it
creates a bootstrapping deadlock — a client cannot ask for a tag it cannot
discover. (c) **Merge metadata into `SelectedValue`** — rejected; this is DD-021,
withdrawn by DD-024, and nothing here reopens it. (d) **Separate bridge process for
metadata** — rejected: two conduits are not a boundary, and the selector already
has both sides.

**Consequences.**

*The invariant that must hold, or the boundary is decorative:* **no soft-side
congestion may back-pressure the hard side.** Concretely, both outbound writers use
`KEEP_LAST`, never `KEEP_ALL`. A `RELIABLE` + `KEEP_ALL` writer that fills its
resource limits blocks in `write()` on the dispatch thread, which stops draining
the inbound reader, whose cache then overflows — so a stalled browser would degrade
field-side reception. `KEEP_LAST` overwrites the oldest sample instead of blocking,
confining the cost to the slow consumer's own data. `max_blocking_time` is short
and a timeout is a logged drop, never a retry inside the callback. This makes
`KEEP_ALL` correct on the inbound `ValueRequest` reader ([DD-023](#dd-023)) and
wrong on both outbound writers; the asymmetry is deliberate.

*Dropping under congestion is policy, not failure.* [DD-027](#dd-027) already
drops deliberately, so the same disposition under a different trigger needs no new
semantics: the contract downstream is "latest, at most this often", never "all".

*The selector becomes the durability re-origin.* `MetaData` is `TRANSIENT_LOCAL`,
so the forwarded topic must be too, or a late-joining scada-web gets no catalogue.
`TRANSIENT_LOCAL` dies with the writer, so on a selector restart the catalogue is
re-read from the sim and republished — the recovery path is the startup path. Cost:
during a selector restart a late-joining scada-web sees an empty catalogue for two
DDS hops instead of one, and must not read "catalogue empty" as "no tags exist".
Its map update is keyed by uid and therefore idempotent, so re-delivery is
harmless.

*`Command_t::METADATA` finally has an owner.* The IDL has carried it since before
the selector existed, and under DD-024 nothing could service it. The selector now
can, by re-reading its own reader cache and rewriting one instance. This also makes
`read()` — not `take()` — a **requirement** on the metadata reader, since taking
would empty the cache that both the command and restart recovery depend on.

*[OQ-22](questions.md#oq-22) becomes structurally answerable.* Its option (b),
"separate DDS domains per level with a deliberate bridge as the conduit", was
already the recommended cheap step and was impossible while scada-web held a
field-side endpoint. The conduit is now a real component rather than an assumption.
Whether to actually run two domains is [OQ-26](questions.md#oq-26); the selector
takes `--field-domain` and `--web-domain` either way, and setting them equal is the
single-domain deployment. Topic names stay distinct across the boundary even though
two domains would permit reuse, so that single-domain deployment works and a
misconfigured domain flag fails loudly.

*Entity count rises from three to five*, and to two participants in the two-domain
deployment. A `WaitSet` may hold conditions from entities on different
participants, so the single-threaded dispatch loop survives unchanged; each
participant brings its own discovery and receive threads, which is the cost.

*scada-web's configuration must change when the selector lands.*
[scada_web/config.yaml](../scada_web/config.yaml) currently subscribes to
`PLC::MetaData` on domain 0 directly. It stays that way while the selector does not
exist — the PoC works today — and switches to `PLC::SelectedMetaData` on the web
domain when it does. Flagged in the file rather than changed early, because
changing it first would break the working demo.

*Two metrics become necessary, not optional:* outbound writes that hit
`max_blocking_time`, and outbound samples lost to `KEEP_LAST` overwrite. Without
them, a soft-side consumer problem is invisible until it shows up as unexplained
field-side jitter.

**Revisit if.** (a) A second component legitimately needs field-side data — then
the question is whether it belongs on the field side entirely, not whether to add
a second conduit. (b) Measurement shows the outbound send path intruding on the
inbound read path, which points to `ASYNCHRONOUS_PUBLISH_MODE` with a
`FlowController` rather than to reopening this. (c) The catalogue stops being
startup-only and becomes a high-rate topic, which would make forwarding it a data-
plane concern with its own rate policy.

---

### DD-029
**The presentation side is `RELIABLE` + `TRANSIENT_LOCAL`, so late-joining
scada-web readers get the latest value and the whole catalogue per uid. The
boundary invariant is therefore maintained by QoS discipline rather than
guaranteed by the reliability kind.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 (revised 2026-07-28) · **Amends:** [DD-028](#dd-028) (QoS of the outbound topics) · **Affects:** DD-023, DD-027, DD-042, OQ-25, OQ-26, SR-003, system-architecture §2, §4.3, §4.4, scada-select-architecture §3.3, §3.4, §3.6, §3.8, §4.4, §6, §8

> **Revision note.** This entry was originally titled "The web side is
> `BEST_EFFORT`" and argued that a best-effort presentation side removed the
> back-pressure failure mode by construction. That was reversed for the reason in
> **Context** below: some selected values change too slowly for a late-joining
> reader to wait for the next publish. The decision table has carried
> `RELIABLE` since then, and
> [dds/qos/profiles.xml](../dds/qos/profiles.xml) implements it; the prose below is
> now consistent with both. The best-effort argument is retained under
> **Alternatives** because it remains the strongest reason one might reverse this
> again.

**Decision.** Dynamic value traffic on the field domain remains optimized for the
sim/selector field hop. On the presentation domain, selected values and selected
metadata both use `RELIABLE` + `TRANSIENT_LOCAL` so late-joining scada-web readers
receive the latest sample per uid, including slow-changing values:

| Side | Topic | Reliability | Durability |
|---|---|---|---|
| Field | `PLC::IdValue` | `RELIABLE` | `VOLATILE` |
| Field | `PLC::MetaData` | `RELIABLE` | `TRANSIENT_LOCAL` |
| Web | `PLC::SelectedValue` | **`RELIABLE`** | `TRANSIENT_LOCAL` |
| Web | `PLC::SelectedMetaData` | **`RELIABLE`** | `TRANSIENT_LOCAL` |
| Web | `PLC::ValueRequest` | **`RELIABLE` + `KEEP_ALL`** — the exception | `VOLATILE` |

**`ValueRequest`'s `KEEP_ALL` is what now distinguishes it.** Every stream in the
table is `RELIABLE`, so the reliability *kind* is no longer what sets the control
channel apart — its history is. `ValueRequest` carries operator intent on an unkeyed
command stream, where a lost `ADD` means a tag silently never turns on — the failure
[DD-023](#dd-023) exists to prevent, and it does not self-heal because nothing
repeats the command. `KEEP_ALL` is therefore correct here and nowhere else: this is
a queue of commands, not a current-value stream, and every element matters. It is
also the low-volume, human-paced direction, so the cost is nil. Note that the
inbound reader being `RELIABLE` + `KEEP_ALL` cannot block the selector's dispatch
thread; only writers block, and the writer for this topic is in scada-web.

**Context.** The field side runs the process and the web side draws pictures of
it. Some selected values update slowly enough that waiting for the next publish is
not acceptable for late-joining scada-web readers. Presentation selected values
therefore use `RELIABLE` + `TRANSIENT_LOCAL` with `KEEP_LAST(1)`: the latest value
per uid is available without preserving an unbounded history.

**This keeps the DD-028 boundary invariant disciplinary rather than structural, and
that is the real cost of this decision.** DD-028 required `KEEP_LAST` on outbound
writers so that soft-side congestion could not block the dispatch thread and stall
field-side reception. With a `RELIABLE` writer that requirement is load-bearing
again, and it needs two companions:

1. **`KEEP_LAST 1`, never `KEEP_ALL`,** on both presentation writers — a
   `KEEP_LAST` writer replaces per instance instead of retaining, so there is no
   queue to fill and block on.
2. **An explicitly unlimited reliable send window.**
   `rtps_reliable_writer.max_send_window_size` throttles `write()` when a reader
   stops ACKing, *independently* of history depth; the default is
   `LENGTH_UNLIMITED`, but a strict-reliable builtin snippet pins it to 40. Both
   writers state it explicitly so that inheriting a profile cannot silently
   reintroduce back-pressure.
3. **A short `max_blocking_time` (100 ms), and a timeout is a counted drop.** This
   is the backstop for 1 and 2: the selector catches `dds::core::TimeoutError`,
   counts it, and continues — never retrying on the dispatch thread. A nonzero
   count means one of the two rules above has been broken.

**The catalogue uses durability, and the constraint on it was verified rather than
assumed.** `TRANSIENT_LOCAL` delivers historical samples to a late joiner **only if
both the DataWriter and the DataReader are `RELIABLE`** (Connext 7.7.0; sources
below). That is satisfied here, which is exactly why this decision can keep
DD-028's "the selector is the durability re-origin" — and why the intermediate
best-effort draft could not.

**`Command_t::METADATA` is therefore a targeted re-read, not a bootstrap.**
scada-web receives the catalogue from the writer cache on join; `METADATA` re-reads
one uid out of the selector's field-side reader cache on demand. Consequences:

- The **sentinel `uid` meaning "all"** that the best-effort draft required is **not
  implemented and not needed**. If a future case wants it, it remains a semantic
  addition to the existing field rather than an IDL change.
- **scada-web can still re-ask** for a uid it believes it is missing. That is a
  diagnostic path now, not the mechanism the catalogue depends on.

**Alternatives.** (a) **`BEST_EFFORT` on the presentation side** — the original
form of this entry, and still the strongest argument against the current decision:
a best-effort writer has no send window to exhaust, no unacknowledged samples to
retain, and no ACK to wait for, so it **removes** the back-pressure failure mode
instead of mitigating it, and no QoS discipline is required to keep the boundary
safe. Rejected because it also denies a late-joining scada-web the latest value per
uid, which for slow-changing tags means a blank or stale display for an unbounded
time, and because it makes every lifecycle retraction lossy and never repeated.
Reverse this decision if measurement ever shows presentation-side reliability
intruding on the field side; the cost of reversing is the catalogue bootstrap and
absence-as-staleness work described in the revision history. (b) **Split the two:
`SelectedMetaData` reliable, `SelectedValue` best-effort** — RTI's own suggested
"catalogue reliable, live stream best-effort" split, and the tidiest theory, since
only the low-volume topic would ever be capable of blocking. Rejected because it
reintroduces lossy retractions exactly on the topic where §3.4 cares most about
them, but it is a small change if the hot path proves to be the problem.
(c) **Republish the catalogue from `on_publication_matched()`** — rejected: it is an
application workaround rather than a documented mechanism, and it races. The
callback means the *writer* matched, not that the remote reader is ready to receive.
(d) **Periodic re-announce of the whole catalogue** — unnecessary now that
durability bootstraps it; reasonable only as a configurable backstop, default off.
(e) **`TopicQuery`** — the documented on-demand mechanism, worth revisiting if the
per-uid `METADATA` path grows awkward.

**Consequences.**

*DD-028's durability re-origination stands.* Both presentation writers are
`TRANSIENT_LOCAL` + `KEEP_LAST 1`, so the selector re-originates durability across
the boundary, and a selector restart therefore does have a window in which the
catalogue is briefly empty from scada-web's point of view — bounded by how quickly
the field-side `MetaData` reader refills. That reader cache remains load-bearing
(`RELIABLE` + `TRANSIENT_LOCAL` + `read()` rather than `take()`), because
`Command_t::METADATA` re-reads it.

*Lifecycle notifications are reliable, which is a real benefit of this form.* A
dispose on `SelectedValue` or `SelectedMetaData` is delivered as long as the reader
stays matched, so "this tag went away" is an event rather than an inference. Two
caveats keep §3.4 honest: a retraction issued while scada-web is **disconnected**
reaches it on reconnect only for instances still held in the writer's cache, and the
selector must not filter lifecycle samples out on the way — a
`DataState::new_data()` mask silently drops them, since it constrains instance state
to `ALIVE`. **scada-web should still treat absence as staleness** — no sample for a
tag within N expected periods marks it stale on the display — but as ISA-101 display
practice rather than as compensation for a lossy transport. This does not weaken
[scada-select-architecture](../scada_select/docs/scada-select-architecture.md)
§3.4's rule that lifecycle events bypass the rate limit.

*Loss becomes invisible at the receiver unless we look.* The selector must count
what it wrote; scada-web cannot infer what never arrived. Whether a `BEST_EFFORT`
reader's `SampleLostStatus` reports useful gap information here is **unverified** —
do not design on it without checking.

*[OQ-25](questions.md#oq-25)'s recommendation is reinforced.* Its option A —
latest-value reads, `KEEP_LAST depth=1`, `read()` never `take()`, change
notification by push — is exactly what a durable current-value stream supports.
Take-once queue semantics were already a poor fit; they are now untenable, which
removes the last reason to keep the WIS polling surface.

*A late-joining scada-web receives the latest selected value per uid* because the
presentation value stream is `RELIABLE` + `TRANSIENT_LOCAL` + `KEEP_LAST(1)`.
This matters for values that do not update frequently.

*Rate limiting is unaffected.* [DD-027](#dd-027) still does the volume reduction;
`BEST_EFFORT` is about what happens to a sample in flight, not how many are sent.

**Revisit if.** (a) The catalogue bootstrap proves unreliable in practice — take
alternative (a) above, one QoS line. (b) A web-side consumer appears that genuinely
needs every sample (a historian, [OQ-21](questions.md#oq-21)) — it should read the
*field* side under its own reliability contract, or be a separate reliable route,
rather than making the display path reliable for everyone. (b′) **Tags appear whose
values are not idempotent** — totalizers, event counters, discrete state
transitions, setpoint-write confirmations — where "the next periodic sample
supersedes the lost one" is simply false. That is the case for **per-key reliability
classes**, scoped as post-PoC work in
[scada-web-architecture.md](../scada_web/docs/scada-web-architecture.md) §9.1.
Two things to carry into that work: DDS reliability is per *endpoint*, so per-key
means partitioning tags across topics rather than tuning a policy; and a reliable
outbound writer reintroduces exactly the blocking path this decision removed, so the
deliverable is isolating it, not configuring it. (c) Measurement shows
best-effort loss on the web side is high enough to be visible to operators, which
would indicate a network problem this decision is not the right fix for.

**Sources.** Connext 7.7.0, via Connext AI:
[Ensuring Information is Available to Late-Joining Applications](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/users_manual/users_manual/Ensuring_Information_is_Available_to_Lat.htm) ·
[Resending DDS Samples to Late-Joiners with the Durability QosPolicy](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/users_manual/users_manual/Resending_DDS_Samples_to_Late_Joiners_wi.htm) ·
[KB: Why does my DDS DataReader miss the first few samples?](https://community.rti.com/kb/why-does-my-dds-datareader-miss-first-few-samples) — "To enable this level of durability, you must also set the Reliability QoS policy kind to DDS_RELIABLE_RELIABILITY_QOS" ·
[Basic QoS (Getting Started 7.7.0)](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/getting_started_guide/cpp11/intro_qos.html) — "Late-joining DataReaders that also use reliability and Transient Local durability are automatically sent historical data"

---

### DD-030
**POC success criterion: end-to-end read path from sim through browser.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Resolves:** [OQ-11](questions.md#oq-11)

**Decision.** The POC demonstrates:

1. GUI sends select commands (add/remove tag UIDs)
2. scada-selector publishes selected values + metadata
3. GUI displays those selected values in real time
4. Configuration is YAML, as simple as possible

No mapping engine, no expression language, no write-through, no round-trip
correctness proofs. Success = real DDS data flowing sim → scada-selector →
scada-web → browser.

---

### DD-031
**POC uses one shared output topic (single client).**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Resolves:** [OQ-12](questions.md#oq-12) · **Extends:** [DD-020](#dd-020)

**Decision.** scada-selector publishes one shared output topic carrying the union
of all requested UIDs. The initial POC targets a single client, making per-client
demux moot. scada-web will implement per-client demux if multiple clients are
added later.

---

### DD-032
**`uid`-only addressing for POC; name-based lookup deferred.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Resolves:** [OQ-13](questions.md#oq-13)

**Decision.** `ValueRequest` uses `uid` only for `ADD`/`DELETE`. The `name` field
is retained for logging but is not used as a lookup key. Name-based tag selection
(name→uid resolution) is deferred to the future implementation roadmap.

---

### DD-033
**Alarm/limit evaluation is out of scope for POC.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Resolves:** [OQ-14](questions.md#oq-14)

**Decision.** No alarm limit evaluation, no severity field on `SelectedValue`, no
ISA-18.2 state machine. The POC passes through raw values. Alarm evaluation is
future roadmap for scada-selector.

---

### DD-034
**`ValueRequest` remains unkeyed; commands queue via `KEEP_ALL`.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Resolves:** [OQ-17](questions.md#oq-17) · **Reinforces:** [DD-023](#dd-023)

**Decision.** `ValueRequest` has no `@key`. It remains a single-instance command
stream with `KEEP_ALL` reliability per DD-023. The keyed desired-state model
(option b from OQ-17) is a future consideration if restart recovery becomes
needed.

---

### DD-035
**Client-side trend buffer; no server-side historian.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Resolves:** [OQ-21](questions.md#oq-21)

**Decision.** Trends are implemented as a client-side memory buffer in the
browser — the browser accumulates the last N minutes from the WebSocket stream.
No server-side historian, no query API. A real historian (Purdue Level 3) is
out of scope.

---

### DD-036
**`ValueRequest` uses incremental deltas (`ADD`/`DELETE`).**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Resolves:** [OQ-24](questions.md#oq-24)

**Decision.** `ValueRequest` carries one command per sample (`ADD(uid)` or
`DELETE(uid)`) per the current IDL. The desired-state and keyed-boolean
alternatives are deferred — the single-client POC has no restart or reconciliation
concerns that would benefit from idempotent state publishing.

---

### DD-037
**Latest-value + WebSocket push; no WIS polling surface.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Resolves:** [OQ-25](questions.md#oq-25)

**Decision.** scada-web provides current-value reads and pushes changes via
WebSocket. `KEEP_LAST 1` + `read()` on the shared reader. The WIS polling surface
(`removeFromReaderCache`, `sampleStateMask`, `viewStateMask`) is dropped — those
semantics are meaningless on a shared reader. The POC is single-client, so
per-client state tracking is not needed.

---

### DD-038
**Match WIS `/dds/rest1` wire format; initial dev uses WIS, scada-web replaces it.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Resolves:** [OQ-3](questions.md#oq-3)

**Decision.** The browser client is built against the WIS `/dds/rest1` wire
format. Initial development uses WIS as the gateway. scada-web replaces WIS in
the next phase, implementing the same API surface so the browser is unaffected
by the swap.

---

### DD-039
**PoC selector pre-enables a fixed uid range (100–500); no catalogue bootstrap.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Defers:** [OQ-28](questions.md#oq-28)

**Decision.** For the initial PoC the selector starts with uids 100–500
pre-enabled in the selection table (configurable via CLI flag, e.g.
`--uid-range 100 500`). No `METADATA_ALL` command is needed — the sim publishes
within this range and the selector forwards all of them from startup.

**Consequences.**

- The catalogue bootstrap problem (scada-web asking "give me all metadata" over
  a best-effort link) does not arise — metadata for uids in the range is forwarded
  unconditionally as it arrives from the sim.
- `ValueRequest` ADD/DELETE remains available to narrow or widen selection within
  the range at runtime, but is not required for initial operation.
- The `METADATA_ALL` enum value (OQ-28 option B) is deferred to the roadmap.
- scada-web knows the uid range by configuration, not by discovery.

**Trigger to revisit:** when the uid space becomes dynamic or open-ended.

---

### DD-040
**`Value_t` string arm keeps `char[32]` — fixed memory allocation.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Resolves:** [OQ-29](questions.md#oq-29)

**Decision.** `char stringValue[MAX_STRING_VALUE_LENGTH]` stays as a fixed-size
array. Fixed memory allocation on the data path is a deliberate real-time
constraint for this exercise — no heap allocation per sample.

**Consequences.**

- C++: generated as `std::array<char, 32>`; comparison via `strncmp` or
  `std::string_view`.
- Python: access via `set_char_values()`/`get_char_values()` with null-padding;
  the `set_value_t` helper in `plc_types.py` encapsulates this.
- Wire: always 32 bytes regardless of content length.
- Convention: values shorter than 32 chars are **null-padded** (trailing `'\0'`).
  Consumers must use length-aware comparison, not bare `==`.

---

### DD-041
**Explicit two-phase dispatch: drain control reader before WaitSet dispatch.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Resolves:** [OQ-31](questions.md#oq-31)

**Decision.** The selector's main loop explicitly takes from the control reader
(`request_reader.take()`) **before** calling `waitset.dispatch()`, rather than
relying on condition attachment order. This guarantees control-before-data
regardless of the middleware's internal dispatch ordering, which is unspecified
by both the DDS standard and RTI's documentation.

**Pattern:**

```cpp
while (running) {
    // Phase 1: drain control — guaranteed first
    for (const auto &s : request_reader.take()) {
        if (!s.info().valid()) continue;
        // process ADD/DELETE/METADATA
    }
    // Phase 2: dispatch data (+ any control that arrived mid-phase-1)
    waitset.dispatch(dds::core::Duration::from_millisecs(100));
}
```

**Why.** `WaitSet::dispatch()` does not guarantee handler invocation order when
multiple conditions trigger simultaneously. RTI confirmed this is unspecified.
The practical consequence of wrong ordering is ~100ms first-sample delay on a
freshly-enabled tag (invisible at display rates), but the two-line fix removes
the ambiguity entirely at zero cost.

---

### DD-042
**Inbound `IdValue` reader: RELIABLE with bounded resource limits.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Resolves:** [OQ-32](questions.md#oq-32)

**Decision.** The selector's inbound `PLC::IdValue` reader stays `RELIABLE` but
with bounded `ResourceLimits` (`max_samples_per_instance` = 4–8 at expected
publish rate). This gives the selector burst headroom without allowing a stalled
selector to block the sim's writer indefinitely.

**Monitoring:** poll `DataReader::sample_lost_status()` each read cycle and log
non-zero counts. This makes cache overflow visible rather than silent (also
addresses [OQ-33](#oq-33)).

**Why not BEST_EFFORT.** Lifecycle events (dispose/unregister) must not be
silently lost on the field side — a disposed tag must reach the selector so it
can propagate the retraction. BEST_EFFORT would make lifecycle loss a normal
condition on both hops rather than just the outbound hop (DD-029).

**Why bounded.** Without resource limits, a RELIABLE + KEEP_LAST reader with
depth N still holds at most N samples per instance, but the writer's send window
can still fill if the reader is not acknowledging — blocking the sim. Bounded
resource limits cap the total memory the reader will allocate, and once full the
middleware drops the oldest unread sample (KEEP_LAST semantics) rather than
applying backpressure to the writer indefinitely.

---

### DD-043
**IDL lives in `dds/idl/`; both C++ and XML types are generated from it.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Resolves:** [OQ-34](questions.md#oq-34)

**Decision.** `PlcValue.idl` moves to `dds/idl/PlcValue.idl` — a system-level
location outside any single component. Both consumers generate from this one file:

- `scada_select/CMakeLists.txt` runs `rtiddsgen -language C++11` against it for
  compiled types.
- A second CMake target (or standalone script) runs `rtiddsgen -convertToXml` to
  produce `PlcValue.xml` for the Python components (`plc_types.py`, `gateway.py`).

**Layout:**

```
dds/
  idl/
    PlcValue.idl          ← single source of truth
scada_select/
  CMakeLists.txt          ← points at ${PROJECT_SOURCE_DIR}/../dds/idl/PlcValue.idl
sim/
  plc_types.py            ← loads generated XML (or keeps programmatic build)
scada_web/
  gateway.py              ← loads generated XML via QosProvider
```

**Enforcement:** if the IDL changes and the build is re-run, both outputs
regenerate. No component can silently use a stale type definition.

---

### DD-044
**Use separate DDS domain IDs for each link: sim→selector and selector→web.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Resolves:** [OQ-26](questions.md#oq-26) · **Affects:** DD-028, OQ-22, system-architecture §2

**Decision.** The system runs three distinct domain IDs:

| Domain ID | Link | Participants |
|---|---|---|
| 0 (field) | sim ↔ selector field-side | scada-sim, scada-selector (field participant) |
| 1 (web) | selector web-side ↔ scada-web | scada-selector (web participant), scada-web |

scada-selector bridges domains 0 and 1 via two participants, one per side. No
component other than the selector holds a participant on more than one domain.

**Context.** DD-028 made the selector the sole conduit and established that the
zone boundary is enforced by topology. OQ-26 asked whether to also enforce it by
domain configuration. With separate domains, a misconfigured scada-web *cannot*
reach field topics — the middleware refuses the match — rather than merely not being
pointed at them. This moves the enforcement from "nobody creates a field-side
reader" (discipline) to "the middleware will not deliver field traffic to domain 1"
(mechanism).

Discovery traffic is the concrete payoff: domain 0 carries only the sim's writers
and the selector's readers — no browser-driven churn, no web-side restarts, no
DynamicData readers with their type-object announcements. The field side stays
quiet.

**Alternatives.** (a) **One domain for everything** — rejected: the zone claim in
DD-028 rests on discipline only, and a single domain means field-side discovery
grows with every web-side entity change. (b) **Partitions instead of domains** —
rejected per OQ-26 analysis: partitions are a matching filter, not an isolation
boundary; a participant that names the partition still joins. (c) **Two domains but
with sim on domain 1 alongside the web** — rejected: that moves the system boundary
away from the selector, contradicting DD-028's invariant.

**Consequences.**

- scada-selector runs two `DomainParticipant`s (one per domain). Both share a
  single `WaitSet` dispatch loop — conditions from different participants may
  coexist on one `WaitSet`. Cost: two sets of discovery and receive threads.
- scada-sim stays on domain 0. No code change; it already defaults to 0.
- scada-web stays on domain 1. Its `config.yaml` `domain_id` changes from 0 to 1
  (or is parameterized via `--domain`).
- The selector's CLI takes `--field-domain 0 --web-domain 1`. Setting them equal
  collapses to single-domain deployment for local debugging.
- Topic names remain distinct across the boundary (`IdValue` vs `SelectedValue`,
  `MetaData` vs `SelectedMetaData`) so that a single-domain fallback works without
  name collisions.
- `rtiddsspy` on domain 0 shows only field traffic; on domain 1 only web traffic.
  Debugging is cleaner.

**Revisit if.** DDS Security Governance is deployed per-domain with different
policies for field and web — then the domain split is load-bearing for security,
not just isolation, and should be documented under OQ-22 as well.

---

### DD-045
**`mapping.py` applies WIS-compatible DynamicData→JSON transforms automatically.**

- **Status:** SUPERSEDED by [DD-052](#dd-052) / [DD-053](#dd-053) · **Date:** 2026-07-27 · **Superseded:** 2026-07-28 · **Resolves:** [OQ-50](questions.md#oq-50), [OQ-54](questions.md#oq-54), [OQ-58](questions.md#oq-58) · **Affects:** scada-web read path, browser binding

> **Superseded.** This was the DynamicData/WIS-compatible PoC path. The accepted
> scada-web architecture now uses Python generated types and `views.py`
> classmethods, so `mapping.py`, `DynamicData.to_json()`, and YAML `views:` are
> historical context rather than current implementation guidance.

**Decision.** `scada_web/mapping.py` uses `DynamicData.to_json()` (which already
projects unions to the active branch only) then recursively converts `char[N]`
arrays from single-char lists to NUL-trimmed strings. This matches RTI Web
Integration Service output without explicit per-field configuration.

**Context.** `to_json()` was untested (OQ-54) and the architecture declared a
mapping module that didn't exist (OQ-50). The `ViewConfig` schema is parsed but
not consumed (OQ-58) — the WIS-style auto-transform covers the PoC need without
requiring per-field config. `ViewConfig` remains available for future field
renaming/flattening beyond what WIS does.

**Alternatives.** (a) Raw `to_json()` with no transform — rejected: `char[32]`
arrives as `["R","U","N","","",...]` which is unusable by a browser binding.
(b) Full config-driven mapping with explicit transform declarations per field —
overkill for the PoC; the only two transforms needed (`union_scalar` and
`char_array_string`) are already handled automatically by `to_json()` + the
recursive char-array fixer.

**Consequences.** The mapping module is ~55 LOC with no configuration required.
Browser clients receive clean JSON matching WIS format. The `ViewConfig`
infrastructure remains unused for now but is not dead — it's the extension point
for field renaming and explicit projection when needed.

**Revisit if.** Clients need field renaming, flattening, or selective projection
beyond what the automatic transform provides — at which point `ViewConfig.fields`
becomes the driver and OQ-6 (expression language) may reopen.

---

### DD-046
**Shared QoS profiles XML at `dds/qos/profiles.xml`; both sim and gateway use it.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Resolves:** [OQ-52](questions.md#oq-52) (implements [OQ-37](questions.md#oq-37)) · **Affects:** gateway.py, plc_publisher.py, config.yaml

**Decision.** A single QoS profiles XML (`dds/qos/profiles.xml`) defines two
libraries by DDS domain boundary: `field::` for field-domain endpoints and
`presentation::` for presentation-domain endpoints. Each profile names a stream
contract and contains both reader and writer QoS for that stream when both
endpoints exist. The selector reads with `field::*` profiles on its field
participant and writes with `presentation::*` profiles on its presentation
participant.
Each topic in `config.yaml` specifies a `qos_profile:` reference (for the current
pre-selector PoC, `field::metadata` and `field::idvalue`). The
gateway loads profiles via `QosProvider` and applies them at reader creation. The
sim uses the same file for field-domain writer QoS.

**Profiles:**

| Library::Profile | Entity | Reliability | Durability | History |
|---|---|---|---|---|
| `field::metadata` | DataWriter/DataReader | RELIABLE | TRANSIENT_LOCAL | KEEP_LAST(1) |
| `field::idvalue` | DataWriter | RELIABLE | TRANSIENT_LOCAL | KEEP_LAST(10) |
| `field::idvalue` | DataReader | RELIABLE | VOLATILE | KEEP_LAST(1) |
| `presentation::selected_value` | DataWriter/DataReader | RELIABLE | TRANSIENT_LOCAL | KEEP_LAST(1) |
| `presentation::selected_metadata` | DataWriter/DataReader | RELIABLE | TRANSIENT_LOCAL | KEEP_LAST(1) |
| `presentation::value_request` | DataWriter/DataReader | RELIABLE | VOLATILE | KEEP_ALL |

**Context.** OQ-37 decided the MetaData reader needs RELIABLE + TRANSIENT_LOCAL;
OQ-52 noted the code never applied it. Rather than hardcoding QoS in Python (the
pattern already proven fragile — sim and gateway drifted), a shared XML file
makes the contract between writers and readers explicit and inspectable. Both
components load from the same file so they cannot diverge.

**Alternatives.**
- (a) Per-topic hardcoded QoS in Python — rejected: already the failure mode that
  caused this bug. The sim set RELIABLE + TRANSIENT_LOCAL; the gateway used
  defaults. A shared file is the standard RTI pattern for preventing this.

**Consequences.** One new file (`dds/qos/profiles.xml`). Both `plc_publisher.py`
and `gateway.py` load it via `QosProvider`. Config.yaml gains a `qos_profiles:`
top-level key and per-topic `qos_profile:` references. No QoS is hardcoded in
Python.

**Revisit if.** A DDS Security Governance file or DomainParticipant QoS profiles
are needed — at which point this file may be merged into a larger XML
configuration or loaded via `NDDS_QOS_PROFILES` env var.

---

### DD-047
**Replace poll loop with `rti.asyncio` WaitSet-backed normal reads.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Resolves:** [OQ-51](questions.md#oq-51) · **Affects:** [OQ-39](questions.md#oq-39), gateway.py

**Decision.** The gateway uses `rti.asyncio`'s WaitSet dispatcher — one asyncio
task per reader, each waking only when data arrives — then performs a normal
`reader.read()`. The 50 ms poll-sleep loop is removed, and samples remain in the
DDS reader cache so REST calls can read the latest retained value after the
callback path has already observed it.

**Context.** The poll loop had three defects: `reader.take()` is a blocking call
in the event loop thread; `on_sample()` dispatch is synchronous with no yield
between samples; and the 50 ms sleep adds unnecessary latency. `rti.asyncio`
provides a `_WaitSetAsyncDispatcher` that runs `wait_async()` in an executor
thread and dispatches in the asyncio thread — exactly the fd-bridge approach
listed as OQ-51 option (c), already implemented by RTI.

**Alternatives.** (a) `run_in_executor` for `reader.take()` — rejected because
DynamicData loan references may not be safe to access across threads without
copying, and the copy is the mapping layer (deferred). (b) Accept for PoC —
rejected because the fix is trivial now that `rti.asyncio` exists.

**Consequences.** The gateway now depends on `rti.asyncio`, which is part of the
Connext Python API but not heavily documented. The `on_sample` callback is still
synchronous within the asyncio thread; under extreme load a single reader's burst
could still delay other tasks. Mitigation: yield every N samples if profiling
shows starvation.

**Revisit if.** Profiling shows `on_sample` dispatch within a single read batch
exceeds 5 ms, or `rti.asyncio` is removed from the Connext Python distribution.

---

### DD-048
**Track `instance_handle → uid` in selection table; don't call `key_value()`.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Resolves:** [OQ-44](questions.md#oq-44) · **Affects:** scada-selector dispatch loop

**Decision.** The selector maintains a `dict[InstanceHandle, int]` mapping,
updated on every valid sample (`handle_map[info.instance_handle] = sample.uid`).
Lifecycle events look up the uid from this map instead of calling
`reader.key_value()`. The entry is removed when a NOT_ALIVE disposition is
forwarded.

**Context.** `key_value()` can throw if the instance has been purged from the
reader cache between `take()` and the call. The race window is small but real
under resource-limit pressure, and the failure mode (uncaught exception in the
dispatch loop) is a crash.

**Alternatives.** (a) try/catch around `key_value()` — rejected because it makes
lifecycle forwarding silently lossy in an edge case. (b) High `max_instances` +
assert — rejected because it converts a rare race into a crash under growth.

**Consequences.** One additional dict insert per valid sample (negligible).
The map grows to at most `max_instances` entries. No DDS API call needed for
lifecycle key recovery.

**Revisit if.** The DDS API gains a guaranteed-safe `key_value()` that never
throws on purged handles, making the map redundant.

---

### DD-049
**Selector shutdown relies on participant liveliness lease expiry.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Resolves:** [OQ-45](questions.md#oq-45) · **Affects:** [OQ-47](questions.md#oq-47), QoS profiles

**Decision.** The selector does not explicitly dispose instances on shutdown.
Downstream (scada-web) detects selector departure via participant liveliness:
`on_liveliness_changed` fires when the lease expires. The QoS profile sets
`liveliness.lease_duration` to 5 seconds (down from default 100s) so detection
is prompt without application-level shutdown code.

**Context.** The downstream link is BEST_EFFORT, so explicit dispose writes can
be lost. Adding reliability for lifecycle only (while data remains best-effort)
is complex and contradicts DD-029. Participant liveliness is the DDS-native
mechanism for exactly this — it doesn't depend on sample delivery.

**Alternatives.** (b) Explicit dispose loop (2–3 writes) — rejected because
still lossy on best-effort, and adds shutdown-ordering complexity for
uncertain benefit. (c) Dedicated RELIABLE status topic — rejected as overkill
for a PoC with one client.

**Consequences.** Selector shutdown detection takes up to 5s (one lease
duration). The SPDP assertion period becomes ~1.67s (lease/3), adding trivial
network overhead. No application shutdown code beyond stopping the dispatch
loop and closing the participant.

**Revisit if.** Detection latency of 5s is unacceptable for the use case, or
multiple selectors are deployed and individual failure must be identified
faster than lease expiry.

---

### DD-050
**Rely on XTypes TypeObject structural matching; no type-name coordination.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Resolves:** [OQ-46](questions.md#oq-46) · **Affects:** system-architecture §4

**Decision.** Topic compatibility between selector and scada-web relies on
XTypes TypeObject structural matching. Both components load types from the
shared `dds/idl/PlcValue.xml` (DD-043), guaranteeing structural identity.
No `register_type()` aliasing or explicit type-name coordination is needed.
The registered type name is not a matching criterion when TypeObject is
available (Connext 7.x default).

**Context.** `PLC::SelectedValue` uses the `IdValue` struct. Both sides
get it from the same XML. Connext 7.7 propagates TypeObject v2 by default;
matching uses structural assignability, not the registered name string.

**Alternatives.** (a) Mandate identical registered type name — rejected
because it adds a constraint the middleware doesn’t require and creates
confusion about what actually drives matching. (b) Alias via
`register_type()` — rejected as non-standard and misleading.

**Consequences.** If TypeObject propagation is ever disabled (non-default),
matching falls back to registered-type-name comparison and could silently
fail. The shared-XML constraint (DD-043) is the real invariant.

**Revisit if.** The system must interoperate with Connext < 6.x or with
TypeObject propagation disabled, in which case registered type names must
match explicitly.

---

### DD-051
**Two select calls for metadata: `NOT_READ` for arrival, `ANY` for commands.**

- **Status:** ACCEPTED · **Date:** 2026-07-27 · **Resolves:** [OQ-48](questions.md#oq-48) · **Affects:** scada-selector metadata plane

**Decision.** The metadata reader uses two distinct select calls:
1. Arrival path: `select().state(NOT_READ).read()` — forwards each sample
   exactly once on arrival.
2. Command path: `select().state(ANY).instance(handle).read()` — re-reads
   the cached KEEP_LAST(1) value for a specific instance (or all instances
   for the sentinel) regardless of sample state, and republishes it.

The selector keeps the sample in cache (KEEP_LAST(1) + `read()` not `take()`)
so it is always available for republish on demand.

**Context.** Metadata is TRANSIENT_LOCAL/KEEP_LAST(1). Each instance has
exactly one sample in the cache. The arrival path must not re-forward old
data; the command path must return data that has already been read. DDS
sample-state selectors are the native mechanism for this distinction.

**Alternatives.** (b) Single `any_sample_state()` path with application-level
“already forwarded” tracking — rejected because it reimplements what DDS
sample-state already provides.

**Consequences.** Two read call sites in the metadata handler, each a
one-liner with a different DataState selector. No additional application
state. `read()` (not `take()`) ensures the cache always holds the last value.

**Revisit if.** Metadata QoS changes to KEEP_ALL (multiple samples per
instance), requiring per-sample forwarding tracking.

---

### DD-052
**scada-web uses Python generated types, not DynamicData.**

- **Status:** ACCEPTED · **Date:** 2026-07-28 · **Supersedes:** [DD-002](#dd-002) · **Affects:** FR-DDS-006, FR-TYPE-001, scada-web gateway, mapping layer

**Decision.** scada-web subscribes using Python generated types produced by
`rtiddsgen -language python`. The DynamicData approach is abandoned for this
component. View types are plain Python dataclasses; field mapping is typed
attribute access, not string-path member lookup.

**Context.** DD-002's premise was "a gateway cannot know its types at build time."
That premise no longer holds: the PLC data model is commissioned SCADA
infrastructure — it does not change at runtime. The types (`IdValue`, `MetaData`,
`ValueRequest`) are static and known. Using DynamicData for static types imposes
string-based access, manual union discrimination, and char-array patching
(current `mapping.py`) with no offsetting benefit.

Generated types give: IDE autocompletion, import-time error detection for typos,
native union discriminator access, and direct attribute mapping to smaller view
types — which is the core job of scada-web's presentation layer.

**Alternatives.**
(a) Keep DynamicData + XML types. Rejected: string-based access makes the
field-mapping goal harder, not easier. Typos discovered at first sample arrival
rather than at import time.
(b) XML types for transport, convert to generated types at the reader boundary.
Rejected: unnecessary conversion step; if generated types are available, read
with them directly.

**Consequences.**
- One-time codegen step: `rtiddsgen -language python -d scada_web/gen/ dds/idl/PlcValue.idl`.
  Output is committed (types are static; no CI codegen pipeline needed).
- `mapping.py` (char-array and union patching) becomes unnecessary and can be removed.
- The gateway creates typed DataReaders directly instead of DynamicData readers.
- DD-026's observation stands: Role 1 (selector) and Role 2 (web) now **both**
  use compiled/generated types, but for the same reason — the type set is fixed.

**Revisit if.** scada-web is ever required to handle types unknown at build time
(e.g., a generic DDS web gateway for arbitrary domains). In that case, DynamicData
returns — but that would be a different product, not this SCADA system.

---

### DD-053
**Field mapping is Python code (view classmethods), not configuration.**

- **Status:** ACCEPTED · **Date:** 2026-07-28 · **Resolves:** — · **Affects:** scada-web mapping/view layer

**Decision.** The mapping from DDS generated types to smaller web-facing view
types is defined as Python classmethods on the view dataclass, not in YAML or
XML configuration.

```python
@dataclass
class TagView:
    uid: int
    value: float
    timestamp: int

    @classmethod
    def from_idvalue(cls, s: PLC.IdValue) -> "TagView":
        return cls(
            uid=s.uid,
            value=s.smoothedValue.float64Value,
            timestamp=s.valueTime,
        )
```

**Context.** The goal is to define smaller view types and map DDS fields into
them. A config-driven mapping (YAML paths like `"smoothedValue.float64Value"`)
reintroduces the string-path problem that DD-052 eliminates. Python code gives
typed attribute access, IDE completion, and import-time validation — the same
benefits that motivated the move to generated types.

**Alternatives.**
(a) YAML mapping config with string field paths. Rejected: negates the type
safety gained by DD-052; requires a path parser, resolver, and runtime
validation infrastructure that Python's attribute access provides for free.
(b) Declarative lambda dict (`{"value": lambda s: s.smoothedValue.float64Value}`).
Viable but less readable and less testable than a classmethod. Rejected in
favour of explicit classmethods that are individually unit-testable.

**Consequences.**
- Mapping changes require editing Python, not config. Acceptable: the people
  editing this system write Python, and the types are static.
- Each view type is self-contained: definition + mapping in one place.
- Union discrimination and edge cases (e.g., choosing the active branch of
  `Value_t`) are handled with normal Python, not a DSL.
- No mapping engine, no parser, no validator — just functions.

**Revisit if.** Non-Python operators need to edit mappings without touching code.
In that case, add a thin YAML layer that generates the classmethods — do not
replace this pattern with a runtime interpreter.
