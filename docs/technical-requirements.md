# scada_web — Technical Requirements Document

**Status:** Draft v0.2 — **prototype / proof of concept**
**Author:** David Greenberg
**Date:** 2026-07-27
**Reviewers:** _TBD_

> **This is a PoC.** There is no target hardware and no embeddable-library
> requirement. Requirements below are marked **[PoC]** where they are in scope
> now, and **[Post-PoC]** where they are retained as the eventual product
> direction but are explicitly *not* built or gated yet. Unmarked requirements
> are [PoC]. See [DD-018](design-decisions.md#dd-018) for what this scoping
> does and does not change.

**Scope of this document: the scada-web component only.** The deliverable is four
components — scada-sim, scada-selector, scada-web, and a browser interface. See
[system-architecture.md](system-architecture.md) for the system, the topic
contracts between components, and what scada-web is *not* responsible for.

**Companion documents**
- [system-architecture.md](system-architecture.md) — the four-component system and its interfaces
- [questions.md](questions.md) — open questions register (canonical; supersedes §11.2)
- [design-decisions.md](design-decisions.md) — decision log; the canonical record of *why*
- [mapping-dsl.md](mapping-dsl.md) — mapping language specification (§6 detail)

This document states **requirements**. Rationale belongs in `design-decisions.md`
and undecided matters in `questions.md`; none of the three should duplicate
another.

---

## 1. Purpose and Scope

`scada_web` is a modern C++ reimplementation of the capability provided by
[RTI Web Integration Service](https://community.rti.com/static/documentation/connext-dds/current/doc/manuals/connext_dds_professional/services/web_integration_service/index.html)
(WIS): a gateway that exposes the RTI Connext DDS global data space to
web clients over HTTP/REST and WebSocket.

Beyond parity with WIS, `scada_web` adds a first-class **data model
transformation and field member mapping** layer, so that the type a web client
sees is decoupled from the type on the wire. Today this decoupling is only
available in a separate product (Routing Service transformations) and is not
reachable from the web-facing API at all.

### 1.1 In scope for the PoC

The PoC exists to answer one question: **can a declarative mapping layer on the
web boundary give clients a data model that does not exist in the IDL, correctly
and in both directions?** Everything below serves that.

- Declarative transformation/mapping engine applied on the web boundary (§6).
  **This is the thesis under test.**
- Enough REST and WebSocket surface to exercise it end to end: entity setup,
  read, write, streaming push.
- XML configuration, including DDS XML-Based Application Creation.
- Mapping validation CLI (§6.8), since offline evaluation is how we demonstrate
  correctness cheaply.

### 1.2 Out of scope for the PoC

- **Embeddable library.** Dropped as a requirement entirely (§8.1). Standalone
  service only.
- **Hardware performance targets.** No reference platform exists, so there are
  no absolute latency or throughput budgets and no CI performance gate (§7.1).
- Production hardening: soak testing, fuzzing, sanitizer matrix, coverage gates
  (§10).
- Full WIS wire compatibility, pending [OQ-3](questions.md#oq-3).
- Horizontal scaling and multi-instance deployment.
- Client SDKs (§8.2). Hand-written test clients suffice.

### 1.3 Out of scope permanently

- Acting as a general DDS-to-DDS router (that is Routing Service's job). We
  transform only on the web boundary, not between DDS domains.
- Non-DDS adapters (Kafka, MQTT, files).
- A bundled web UI.
- gRPC.

### 1.4 Why reimplement

Four motivations for the eventual product. **Only the first is what the PoC
tests**; the others are known engineering problems with known solutions, and
proving them is not what a prototype is for.

1. **The mapping feature has no home in WIS.** WIS exposes DDS types verbatim.
   Web clients are forced to consume the IDL data model, including its naming,
   nesting, and unit conventions. There is no supported hook to change that.
2. **The threading model does not fit a streaming SCADA workload.** WIS handles
   each connection on its own worker thread (`-numThreads`, default 50), so a
   long-poll or WebSocket client occupies a thread for its lifetime. Concurrent
   client count is bounded by thread count, not by memory or I/O.
3. **Authorization is coarse.** WIS access control is API-key admission control
   against a SQLite ACL file: a valid key grants access to the service. There is
   no documented per-topic, per-method, or read-vs-write granularity. SCADA
   deployments need topic-scoped, operation-scoped authorization.
4. **Modern C++ and a modern HTTP stack** give us HTTP/2, structured
   observability, and a testable core.

---

## 2. Baseline: What RTI Web Integration Service Does

This section is the behavioral reference. It is drawn from the WIS 7.7.0 manual,
the HTTP routing table, the shipped `rti_web_integration_service.xsd`, and the
Connext AI knowledge base. Compatibility requirements in §5 refer back here.

### 2.1 Resource model

Rooted at `/dds/rest1`, mirroring the OMG Web-Enabled DDS resource hierarchy:

```
/dds/rest1
├── applications/{a}
│   └── domain_participants/{dp}
│       ├── registered_types/{r}
│       ├── topics/{t}
│       ├── publishers/{p}/data_writers/{dw}
│       ├── subscribers/{s}/data_readers/{dr}
│       └── builtin_subscribers/{bs}/builtin_data_readers/{bdr}
├── domain_libraries/{dl}
├── qos_libraries/{ql}/qos_profiles/{qp}
└── types/{tn}
```

Collections accept `POST` (create) and `GET` (list); instances accept `DELETE`
(destroy) and `PUT` (enable/update). Data flows through the DataWriter and
DataReader instance resources themselves.

### 2.2 Data operations

| Operation | Method + path |
|---|---|
| Write samples | `POST .../publishers/{p}/data_writers/{dw}` |
| Dispose / unregister instance | `POST .../data_writers/{dw}/instances:{op}` where `op` ∈ `dispose`, `unregister` |
| Read / take samples | `GET .../subscribers/{s}/data_readers/{dr}` |
| Read builtin discovery data | `GET .../builtin_subscribers/{bs}/builtin_data_readers/{bdr}` |

Read query parameters:

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `sampleFormat` | `xml` \| `json` | `xml` | Response body format |
| `removeFromReaderCache` | bool | `true` | `true` → DDS `take`, `false` → DDS `read` |
| `maxSamples` | int | unlimited | Cap on returned samples |
| `maxWait` | int (s) | `0` | Long-poll timeout; blocks on a WaitSet |
| `filterExpression` | string | — | DDS SQL query condition |
| `sampleStateMask` | `READ` \| `NOT_READ` | — | Sample state filter |
| `viewStateMask` | `NEW` \| `NOT_NEW` | — | View state filter |
| `instanceStateMask` | `ALIVE` \| `NOT_ALIVE_DISPOSED` \| `NOT_ALIVE_NO_WRITERS` | — | Instance state filter |
| `prettyPrint` | bool | `false` | Indent output |
| `enumsAsIntegers` | bool | `false` | Emit enums as ordinals rather than names |

Content types are `application/dds-web+json` and `application/dds-web+xml`.
Sample envelopes carry `read_sample_info` / `write_sample_info` alongside `data`:

```json
[ { "read_sample_info": { "source_timestamp": {"sec": 1456962954, "nanosec": 150101000},
                          "valid_data": true, "instance_state": "ALIVE",
                          "sample_state": "NOT_READ", "view_state": "NEW" },
    "data": { "color": "ORANGE", "x": 80, "y": 80, "shapesize": 30 } } ]
```

Status codes: `204` on create/delete/write/enable, `200` on list/read, `404` on
read/take failure, `422` on invalid input, `500` on DDS or internal error. Errors
carry `{ "code": ..., "message": ... }` with codes `INVALID_INPUT`,
`INVALID_OBJECT`, `GENERIC_SERVICE_ERROR`.

### 2.3 WebSocket protocol

Disabled by default in WIS (`-enableWebSockets`). Two-stage bring-up:

1. `POST /dds/v1/websocket_connections` with `{"name": "<conn>"}` to reserve a
   connection name.
2. Open `ws(s)://host[:port]/dds/websocket/<conn>`.
3. First frame **must** be `HELLO` — *not* JSON, but CRLF-terminated
   colon-separated pairs with required fields `Accept`, `Content-Type`,
   `OMG-DDS-API-Key`, `Version`. Server replies `HELLO_OK: ...` or
   `HELLO_FAIL: ...` and closes on failure.

Frame kinds thereafter: `request` / `response` (REST semantics tunneled over the
socket, correlated by client-supplied `id`), `bind` (associate a client-chosen
`bind_id` with a reader or writer URI), `b_req` (streaming write to a bound
writer), `b_push` (server-initiated sample delivery from a bound reader, tagged
with `bind_id`). Bind-family operations respond **only on error**. There is no
application-level WebSocket keepalive; `-enableKeepAlive` /
`-keepAliveTimeout` govern HTTP connection reuse only.

### 2.4 Configuration

The shipped `rti_web_integration_service.xsd` is deliberately thin — it defines
`dds`, `configuration_variables`, `types`, `qos_library`, `domain_library`,
`domain_participant_library`, `web_integration_service`, and `application`, and
otherwise reuses the standard DDS XML-Based Application Creation schema. A
config declares one or more `<web_integration_service name="...">` blocks, each
containing `<application>` → `<domain_participant>` → `<register_type>`,
`<topic>`, `<publisher>/<data_writer>`, `<subscriber>/<data_reader>`. The runtime
instance is selected with `-cfgName`.

Notable WIS behaviors we must not inherit as bugs:

- A configuration and one of its applications may not share a name.
- Some XML tags must appear in a strict order.

### 2.5 Operational surface

Command-line: `-cfgFile`, `-cfgName` (required), `-listeningPorts` (suffix `s`
for TLS, default `8080`), `-sslCertificate` (PEM with key + cert),
`-numThreads` (default 50), `-enableWebSockets`, `-enableBuiltinTopics`,
`-enableResourceCaching`, `-enableKeepAlive`, `-keepAliveTimeout`,
`-documentRoot`, `-accessLogFile`, `-aclFile`, `-createAPIKey`, `-deleteAPIKey`,
`-listAPIKeys`, `-accessControlAllow{Origin,Methods,Headers}` (all default `*`),
`-heapSnapshotDir`, `-heapSnapshotPeriod`, `-verbosity` (1–7), `-version`,
`-help`.

Threading: thread-per-connection up to `-numThreads`. `-enableResourceCaching`
retains WaitSet, sample buffer, and DynamicData objects in worker-thread-local
storage, trading memory for allocation churn. RTI publishes no throughput or
latency figures for WIS.

Deployment: standalone `rtiwebintegrationservice`, or embedded via the Web
Integration Service Library API (`rti/webdds/Service.hpp`,
`ServiceProperty.hpp`) — C++ only. Client-side examples exist in JavaScript and
Python; there are no first-party client libraries beyond examples.

### 2.6 Transformation prior art (Routing Service)

The mapping capability we need exists in Routing Service, not WIS:

- `rti::routing::transf::TransformationPlugin` is a factory:
  `create_transformation(input_type_info, output_type_info, properties)`.
- `rti::routing::transf::Transformation` does the work, via
  `transform(out_samples, out_infos, in_samples, in_infos)` and `return_loan()`.
  `TypedTransformation<Data, Info>` and the `DynamicDataTransformation` alias
  provide typed vectors.
- Plugins are loaded from a shared library named in
  `<plugin_library>/<transformation_plugin>/<dll>` and instantiated through an
  exported C factory named in `<create_function>`, conventionally generated by
  `RTI_TRANSFORMATION_PLUGIN_CREATE_FUNCTION_DECL/DEF`.
- A **built-in Assignment Transformation** ships as `librtirsassigntransf.so`
  (present in the local 7.7.0 install) with create function
  `RTI_RoutingServiceAssignTransformationPlugin_create`. It is configured as
  property pairs where `<name>` is the **output** member path and `<value>` is
  the **input** member path, supporting dotted nested paths.

Its limits are exactly what §6 must exceed: assignment only — no computed
fields, no unit conversion, no conditionals, no reshaping between sequences and
arrays, no type synthesis, and no way to invoke it from a web API.

---

## 3. Stakeholders and Personas

| Persona | Needs |
|---|---|
| **Web/UI developer** | Stable JSON contract in their own vocabulary; push updates; no IDL knowledge. |
| **Integration engineer** | Declaratively map an existing DDS data model to a partner's expected schema without writing C++. |
| **DDS/systems engineer** | Correct QoS, correct instance and lifecycle semantics, no surprises on the wire. |
| **Operator / SRE** | Config-driven deploys, health and metrics endpoints, structured logs, predictable resource use. |
| **Security engineer** | TLS, real authentication, topic- and operation-scoped authorization, audit trail. |

---

## 4. System Architecture

```
                 HTTP/1.1 · HTTP/2 · WebSocket (TLS)
                                │
                    ┌───────────▼────────────┐
                    │   Transport Layer      │  async I/O, TLS, HTTP framing,
                    │                        │  WS framing, CORS, access log
                    └───────────┬────────────┘
                                │
                    ┌───────────▼────────────┐
                    │   API Layer            │  routing, URI → resource,
                    │  REST · WS · Admin     │  content negotiation, validation
                    └───────────┬────────────┘
                                │
                    ┌───────────▼────────────┐
                    │   Security Layer       │  authn (API key/JWT/mTLS),
                    │                        │  authz policy eval, audit
                    └───────────┬────────────┘
                                │
                    ┌───────────▼────────────┐
                    │  Resource Manager      │  Application/Participant/Pub/Sub/
                    │                        │  Writer/Reader registry, lifecycle
                    └───────────┬────────────┘
                                │
        ┌───────────────────────▼────────────────────────┐
        │            Transformation Engine               │  ◄── the new capability
        │  view schema · mapping plan · expression eval  │
        └───────────────────────┬────────────────────────┘
                                │
                    ┌───────────▼────────────┐
                    │  Serialization Layer   │  DynamicData ⇄ JSON/CBOR/XML
                    └───────────┬────────────┘
                                │
                    ┌───────────▼────────────┐
                    │  DDS Layer             │  Connext Modern C++, XTypes,
                    │                        │  AsyncWaitSet, type discovery
                    └────────────────────────┘
```

Layer rules: each layer depends only on the one below it; the DDS layer is
reachable only through the Resource Manager; the Transformation Engine has no
knowledge of HTTP. The engine is a pure function of (mapping plan, input sample)
→ output sample, which makes it unit-testable without a network or a domain.

---

## 5. Functional Requirements — Parity Surface

Requirement IDs are stable. `MUST` / `SHOULD` / `MAY` per RFC 2119.

### 5.1 REST API

- **FR-REST-001** The service MUST expose the complete `/dds/rest1` resource
  hierarchy and method set enumerated in §2.1–§2.2.
- **FR-REST-002** The service MUST accept and produce both
  `application/dds-web+json` and `application/dds-web+xml`, honoring the
  `Accept` and `Content-Type` headers.
- **FR-REST-003** ⚠️ **Under revision — see [OQ-25](questions.md#oq-25).** As
  written this requires all read query parameters in §2.2, inherited from the WIS
  baseline. But `removeFromReaderCache` (take), `sampleStateMask`, and
  `viewStateMask` are **per-DataReader** semantics, and
  [DD-020](design-decisions.md#dd-020) gives scada-web *one shared reader* rather
  than one per client — so on this architecture a `take` by one client would
  consume samples belonging to others, and the two state masks would report
  gateway-level state rather than client-level. `filterExpression`,
  `maxSamples`, `maxWait`, and `instanceStateMask` are unaffected and remain
  required. The recommendation is latest-value reads plus WebSocket push, which
  drops the three problematic parameters rather than reimplementing them.
- **FR-REST-004** The service MUST reproduce WIS status codes and the
  `{code, message}` error body with the documented error codes.
- **FR-REST-005** The service MUST support instance `dispose` and `unregister`
  via `POST .../instances:{op}` with a key-fields-only body.
- **FR-REST-006** The service MUST support reading builtin discovery topics when
  enabled, gated by configuration (WIS `-enableBuiltinTopics`).
- **FR-REST-007** The service MUST support runtime creation and deletion of
  types, QoS libraries and profiles, and domain libraries.
- **FR-REST-008** The service SHOULD additionally expose `/api/v1` as a
  versioned alias with corrected semantics (see §5.5); `/dds/rest1` remains the
  compatibility surface.

### 5.2 WebSocket API

- **FR-WS-001** The service MUST implement the two-stage connection bring-up of
  §2.3, including the non-JSON `HELLO` frame and `HELLO_OK` / `HELLO_FAIL`.
- **FR-WS-002** The service MUST implement frame kinds `request`, `response`,
  `bind`, `b_req`, `b_push` with `id` correlation for request/response and
  `bind_id` correlation for bound streams.
- **FR-WS-003** A single connection MUST support multiple simultaneous reader
  and writer binds.
- **FR-WS-004** Bind-family operations MUST respond only on error, matching WIS.
- **FR-WS-005** The service MUST implement RFC 6455 ping/pong liveness with a
  configurable interval, closing dead connections. This closes a WIS gap.
- **FR-WS-006** The service MUST apply per-connection backpressure: when a
  client cannot keep up with `b_push`, behavior MUST be configurable as
  `drop_oldest`, `drop_newest`, `coalesce_by_instance`, or `disconnect`, and the
  chosen action MUST be counted in metrics.
- **FR-WS-007** WebSocket support MUST be enabled by default (WIS defaults it
  off; for this service it is a primary transport).

### 5.3 DDS entity and data semantics

- **FR-DDS-001** All six DDS entity kinds MUST be creatable both from XML
  configuration at startup and dynamically over the API.
- **FR-DDS-002** Full QoS MUST be configurable via XML QoS profiles referenced
  by `base_name`, with the same inheritance semantics as Connext.
- **FR-DDS-003** Content-filtered topics MUST be supported, both from
  configuration (`<filter>`) and from `filterExpression` on read.
- **FR-DDS-004** Sample metadata (source timestamp, instance handle, valid_data,
  and the three state fields) MUST be preserved end to end, including through
  transformation.
- **FR-DDS-005** The service MUST support Connext Security Plugins by
  configuring participant QoS properties.
- **FR-DDS-006** The service MUST operate on `DynamicData` throughout, requiring
  no generated type support code for user types.
- **FR-DDS-007** Types MUST be loadable from an XML types library at runtime
  (`dds::core::QosProvider::extensions().type(name)`) and constructible
  programmatically via `dds::core::xtypes::StructType`.
- **FR-DDS-008** The service MAY create readers for types it has never been
  configured with, by resolving `PublicationBuiltinTopicData::type()` from
  builtin discovery. Implementations MUST tolerate Connext 7.7 type-lookup
  behavior: discovery callbacks may fire before the type is resolved and may
  fire more than once per endpoint. See RISK-4.

### 5.4 Configuration

- **FR-CFG-001** Configuration MUST be XML and MUST accept a valid WIS
  configuration file unchanged, ignoring only unrecognized extension elements.
- **FR-CFG-002** The XSD MUST be extended for transformation constructs (§6.7)
  and the service MUST validate against it at startup, reporting all errors with
  file, line, and XPath rather than failing at the first one.
- **FR-CFG-003** Element ordering MUST NOT be significant, and a configuration
  and its application MUST be permitted to share a name. Both are WIS known
  issues we explicitly do not carry forward.
- **FR-CFG-004** `configuration_variables` and environment-variable
  substitution MUST be supported.
- **FR-CFG-005** The service MUST support hot reload of transformation and
  authorization policy on `SIGHUP` or via an admin endpoint, without dropping
  DDS entities or client connections. Reload MUST be atomic: a config that fails
  validation leaves the running config untouched.

### 5.5 Deliberate divergences from WIS

Each divergence is opt-in on `/dds/rest1` and default-on under `/api/v1`.

| ID | Divergence | Rationale |
|---|---|---|
| **DIV-001** | Entity creation returns `201 Created` with a `Location` header and a body describing the entity, instead of bare `204`. | Clients currently cannot learn a server-assigned identity. |
| **DIV-002** | Read failure returns `409`/`503` as appropriate; `404` is reserved for a genuinely absent resource. | WIS returns `404` for DDS take errors, which is indistinguishable from a bad URI. |
| **DIV-003** | JSON is the default `sampleFormat`. | XML default is a legacy artifact. |
| **DIV-004** | CORS defaults to deny-all and must be configured explicitly. | WIS defaults `Access-Control-Allow-{Origin,Methods,Headers}` to `*`. |
| **DIV-005** | Errors carry an additional `details` array and a `request_id`. | Field-level validation feedback and log correlation. |
| **DIV-006** | Timestamps MAY be rendered as RFC 3339 strings when `timeFormat=rfc3339`. | `{sec, nanosec}` is awkward for web clients. Default stays `{sec, nanosec}`. |

---

## 6. Functional Requirements — Transformation and Field Mapping

This is the differentiating capability. The design goal is that **a web client
can be given a data model that does not exist anywhere in the IDL**, produced
declaratively from one or more DDS types, and that writes through that model
land correctly on the DDS types underneath.

### 6.1 Concepts

- **Wire type** — the DDS `DynamicType` registered on a topic.
- **View schema** — the type presented to web clients. Either derived from a
  mapping or declared explicitly.
- **Mapping** — a named, directional set of rules producing a view sample from
  wire samples (*outbound*, read path) or wire samples from a view sample
  (*inbound*, write path).
- **Mapping plan** — the compiled, validated, immutable form of a mapping,
  resolved against concrete types. Built once at bind time, executed per sample.
- **View endpoint** — a reader or writer resource with a mapping attached. Web
  clients interact with the view; DDS sees only the wire type.

### 6.2 Field mapping

- **FR-XF-001** Mappings MUST support member-path assignment between wire and
  view, using dotted paths with array/sequence indexing:
  `header.stamp.sec`, `points[0].x`, `sensors[*].value`.
- **FR-XF-002** Renaming, reordering, omission, and flattening of nested members
  into a flat view MUST be supported, along with the inverse (nesting flat wire
  members into a structured view).
- **FR-XF-003** Widening primitive conversions MUST be implicit. Narrowing
  conversions MUST be explicit and MUST have configurable overflow behavior
  (`error`, `saturate`, `wrap`), defaulting to `error`.
- **FR-XF-004** Enumerations MUST be mappable by name, by ordinal, or through an
  explicit value table, including to and from strings.
- **FR-XF-005 [PoC · P1 · primary case]** Optional members and unions MUST be
  handled: absent optionals MUST be distinguishable from zero-valued ones, and
  union discriminators MUST be mappable. **This is the engine's first job, not a
  completeness item** — in the actual data model every value is a `Value_t` union
  discriminated over string/int32/int64/float32/float64, so union-to-scalar
  projection must work before anything is demonstrable. One concrete case from
  [dds/idl/PlcValue.idl](../dds/idl/PlcValue.idl): the string branch is `char[32]`, not
  `string<32>`, and so needs an explicit char-array-to-string decode with
  NUL-trimming rather than JSON's array-of-chars. See
  [system-architecture.md](system-architecture.md) §6.1.
- **FR-XF-006** Sequence ⇄ array reshaping MUST be supported, with a declared
  policy when a source exceeds a bounded destination (`error`, `truncate`).
- **FR-XF-007** Constant injection and default values for unmapped view members
  MUST be supported.
- **FR-XF-008** Unmapped members MUST be handled per a declared
  `unmapped_policy`: `omit`, `default`, or `error`. Default is `error` for
  inbound (writes must be complete or explicitly defaulted) and `omit` for
  outbound.

### 6.3 Expressions and computed fields

- **FR-XF-010** A restricted expression language MUST be available for computed
  members: arithmetic, comparison, boolean, and string operations over member
  paths and literals; conditional (`cond ? a : b`); and a fixed function library
  (numeric, string, time, unit conversion).
- **FR-XF-011** The expression evaluator MUST be **total and bounded**: no
  loops, no recursion, no I/O, no allocation beyond a fixed per-evaluation
  arena, and a compile-time-checkable cost. It MUST NOT be Turing-complete.
  This is a hard requirement — the evaluator runs inline on the data path.
- **FR-XF-012** Expressions MUST be type-checked at plan compile time. A
  mapping that cannot be proven type-correct MUST be rejected at startup, not at
  first sample.
- **FR-XF-013** Unit conversion MUST be declarable (e.g. `degC -> degF`,
  `rad -> deg`, scale/offset pairs) rather than hand-written arithmetic.
- **FR-XF-014** Evaluation errors at runtime (division by zero, narrowing
  overflow under `error`, absent optional dereference) MUST be handled per a
  declared `on_error` policy: `drop_sample`, `substitute_default`, or
  `fail_request`. The event MUST be counted and rate-limited-logged.

### 6.4 Structural transformation

- **FR-XF-020** **Projection** — a view MAY expose a subset of wire members.
- **FR-XF-021** **Filtering** — a mapping MAY carry a predicate; outbound
  samples failing it are not delivered. Where the predicate is expressible as
  DDS SQL it SHOULD be pushed down into a content-filtered topic so filtering
  happens before the sample reaches this process. **Note:** key-based selection
  is *not* this mechanism — it is scada-selector's job
  ([DD-020](design-decisions.md#dd-020)), and scada-web must not create a reader
  per client to achieve it. This requirement covers only value-based predicates
  within an already-selected stream.
- **FR-XF-022 [Out of scope — relocated]** **Join** — a view composed from more
  than one wire topic, correlated by a declared key expression.
  **Not built in the mapping engine.** The system's one join
  (`IdValue` × `MetaData` on `uid`) is performed by scada-selector instead, which
  already holds per-uid state; see [DD-021](design-decisions.md#dd-021). The
  mapping engine MUST reject a mapping with more than one `<input>` at compile
  time, while the schema retains the cardinality so join can be added later
  without reshaping the plan representation.
- **FR-XF-023** **Split / fan-out** — one inbound view sample MAY produce writes
  to more than one wire topic. Multi-topic writes are **not** atomic; the API
  MUST report per-topic outcomes and MUST NOT imply transactional semantics.
- **FR-XF-024** **Aggregation** — a view member MAY aggregate over a sequence
  member (`sum`, `min`, `max`, `avg`, `count`, `first`, `last`). Aggregation is
  outbound-only; it is not invertible.
- **FR-XF-025** Invertibility MUST be analyzed at compile time. Each mapping is
  classified `bidirectional`, `outbound_only`, or `inbound_only`, and the class
  MUST be reported. Attaching an `outbound_only` mapping to a writer MUST be a
  configuration error, caught at startup.

### 6.5 Key and instance semantics

Getting this wrong silently corrupts instance lifecycles, so it is called out
separately.

- **FR-XF-030** Every mapping MUST resolve view keys to wire keys. If any wire
  key member is not derivable from the view for an inbound mapping, the mapping
  MUST be rejected at compile time.
- **FR-XF-031** Instance identity MUST be preserved across transformation: two
  wire samples of the same instance MUST produce view samples of the same view
  instance, and vice versa.
- **FR-XF-032** `dispose` and `unregister` through a view MUST map to the
  correct wire instances, using only view members that map to wire key members.
- **FR-XF-033** Invalid samples (`valid_data == false`, i.e. dispose/unregister
  notifications) MUST be forwarded with key fields mapped and non-key members
  omitted. The engine MUST NOT attempt to evaluate expressions over absent data.

### 6.6 View schema publication

- **FR-XF-040** The service MUST publish the view schema for every view endpoint
  as JSON Schema, via `GET .../data_readers/{dr}/schema` (and the writer
  equivalent). Connext 7.7 can render a `DynamicType` as JSON Schema
  (`DynamicTypePrintKind::json_schema`); for views the schema MUST be derived
  from the compiled plan's output type.
- **FR-XF-041** The service MUST expose the compiled mapping plan in a
  human-readable form for debugging, including the invertibility class,
  per-member provenance (which wire path or expression each view member came
  from), and any pushdown decisions.
- **FR-XF-042** An OpenAPI 3.1 document MUST be generated for the configured
  endpoint set, with view schemas inlined.

### 6.7 Configuration syntax

Mappings are declared in a `<transformation_library>` and referenced from reader
and writer declarations. Draft syntax — the full grammar is specified in
[mapping-dsl.md](mapping-dsl.md).

```xml
<dds>
  <types>
    <!-- wire types, or loaded from a separate types file -->
  </types>

  <transformation_library name="ScadaViews">
    <mapping name="TankToUi" direction="bidirectional">
      <input  topic_ref="TankTelemetry" registered_type_name="TankReading"/>
      <output view_schema="TankUiView"/>

      <unmapped_policy outbound="omit" inbound="error"/>
      <on_error>drop_sample</on_error>

      <!-- simple renames and nested flattening -->
      <assign to="tag"          from="device.tag_name"/>
      <assign to="level_pct"    from="level.percent"/>
      <assign to="updated_sec"  from="header.stamp.sec"/>

      <!-- unit conversion -->
      <assign to="temp_f"       from="temp_c" convert="degC->degF"/>

      <!-- computed, with an explicit view type -->
      <compute to="status" type="string">
        level.percent &gt; 95 ? "HIGH" : (level.percent &lt; 5 ? "LOW" : "OK")
      </compute>

      <!-- enum by name, plus an explicit remap table -->
      <assign to="mode" from="control_mode" enum_as="name">
        <value_map from="MODE_AUTO"   to="auto"/>
        <value_map from="MODE_MANUAL" to="manual"/>
      </assign>

      <!-- aggregation: outbound only; makes this member non-invertible -->
      <aggregate to="sensor_max" from="sensors[*].value" op="max"
                 direction="outbound"/>

      <!-- key resolution is mandatory -->
      <key_mapping>
        <key view="tag" wire="device.tag_name"/>
      </key_mapping>
    </mapping>
  </transformation_library>

  <web_integration_service name="ScadaWeb">
    <application name="Scada">
      <domain_participant name="Plant" domain_id="0">
        <register_type name="TankReading" type_ref="TankReading"/>
        <topic name="TankTelemetry" register_type_ref="TankReading"/>
        <subscriber name="Sub">
          <data_reader name="TankView" topic_ref="TankTelemetry">
            <transformation mapping_ref="ScadaViews::TankToUi"/>
          </data_reader>
        </subscriber>
      </domain_participant>
    </application>
  </web_integration_service>
</dds>
```

- **FR-XF-050** Mappings MUST be declarable in XML with no code and no rebuild.
- **FR-XF-051** Mappings MUST also be creatable, listed, and deleted at runtime
  over the admin API, subject to authorization.
- **FR-XF-052** A native plugin interface MUST exist for transformations that
  exceed the declarative language, modeled on
  `rti::routing::transf::TransformationPlugin` so that existing Routing Service
  transformation plugins can be reused with minimal change. Plugins are loaded
  from a shared library named in configuration via an exported C factory.
- **FR-XF-053** The built-in Assignment Transformation semantics
  (`<name>` = output path, `<value>` = input path) MUST be expressible, so that
  existing Routing Service assignment configurations can be mechanically
  translated. A translation tool SHOULD be provided.

### 6.8 Transformation validation tooling

- **FR-XF-060** A CLI MUST validate a configuration offline: schema-check it,
  compile every mapping plan, report invertibility classes, and list every
  member that is unmapped in either direction.
- **FR-XF-061** The CLI MUST support applying a mapping to a sample supplied as
  JSON and printing the result, for use in tests and CI.
- **FR-XF-062** The CLI MUST support round-trip checking: for a
  `bidirectional` mapping, verify that wire → view → wire is the identity over a
  supplied sample set, and report any member that does not round-trip.

---

## 7. Non-Functional Requirements

### 7.1 Performance — [PoC: relative only]

**There is no target hardware, so there are no absolute budgets and no CI
performance gate.** Absolute numbers measured on a developer workstation would
be meaningless as requirements and actively misleading if quoted later. What a
PoC *can* establish is **relative** cost — comparisons that hold across
machines because both sides are measured on the same one.

- **NFR-PERF-001 [PoC]** Transformation cost MUST be measured against an
  identity mapping on the same host and reported as a ratio. The PoC's finding
  is a ratio and an order of magnitude, never a millisecond figure.
- **NFR-PERF-002 [PoC]** The per-sample path MUST be shown to have cost
  independent of mapping *declaration* size — i.e. resolving a member path must
  not happen per sample (DD-012). Verified by comparing per-sample cost across
  mappings of 5, 30, and 100 members: growth should be linear in members
  *touched*, not in mapping complexity.
- **NFR-PERF-003 [PoC]** Steady-state allocation on the sample path MUST be
  measured and SHOULD be zero. This is checkable with an allocation counter,
  not a stopwatch, so it is machine-independent and worth doing now.
- **NFR-PERF-004 [PoC]** Memory MUST NOT grow without bound with connection
  count or uptime. Verified by trend over a short run, not by an absolute
  per-connection figure.
- **NFR-PERF-005 [Post-PoC]** Absolute latency, throughput, and concurrency
  targets — including the ≥ 10,000 concurrent connection goal that motivates
  DD-009 — MUST be set against a named reference platform once one exists, and
  gated in CI thereafter ([OQ-10](questions.md#oq-10)).

Note for later: RTI publishes no WIS performance figures. Any comparative claim
against WIS must be measured against the local binary, on the same host, never
cited from documentation.

### 7.2 Reliability and availability — [PoC: 001 and 004 only]

NFR-REL-001 and 004 stay in scope because a prototype that crashes or OOMs
during a demo proves nothing. NFR-REL-002 and 003 are [Post-PoC].

- **NFR-REL-001** No client request or connection may crash the service. A fault
  in transformation or serialization for one endpoint MUST be contained to that
  request.
- **NFR-REL-002** Loss of DDS liveliness with matched endpoints MUST be surfaced
  to clients rather than silently manifesting as absent data.
- **NFR-REL-003** Graceful shutdown: stop accepting, drain in-flight requests up
  to a deadline, close WebSockets with a status code, then delete DDS entities.
- **NFR-REL-004** Resource limits MUST be enforced and configurable: max
  connections, max binds per connection, max entities per application, max
  samples per response, max request body size, max mapping plan complexity.
  Exceeding a limit MUST produce a specific error, never an OOM.

### 7.3 Security — [PoC: a subset, see §12 P4]

In scope for the PoC: TLS (NFR-SEC-001), one authentication mechanism
(NFR-SEC-002), deny-by-default CORS (NFR-SEC-006), no default document root
(NFR-SEC-010), and input validation (NFR-SEC-008) — the last because
`filterExpression` reaches DDS SQL and mapping expressions are parsed, so
validation is correctness, not just hardening. The full authorization model
(NFR-SEC-003/004/009) and audit (NFR-SEC-005) are [Post-PoC]; they are retained
below because DD-013 is a design commitment that shapes how principals are
threaded through the code even before the policy engine exists.

- **NFR-SEC-001** TLS 1.2 minimum, TLS 1.3 preferred, for both HTTPS and WSS,
  with configurable cipher suites. Separate key and certificate files MUST be
  supported (WIS requires them concatenated into one PEM).
- **NFR-SEC-002** Authentication MUST support API keys (WIS-compatible
  `OMG-DDS-API-Key`), bearer JWT with configurable issuer and JWKS, and mutual
  TLS. At least one mechanism MUST be enabled unless the service is explicitly
  started in an insecure development mode, which MUST log a warning on every
  start.
- **NFR-SEC-003** Authorization MUST be **resource- and operation-scoped**: a
  policy grants a principal a set of operations (`read`, `write`, `create`,
  `delete`, `admin`) over a set of resources matched by pattern (application,
  participant, topic, view). This is the primary security gap versus WIS's
  service-level admission control.
- **NFR-SEC-004** Authorization decisions MUST be deny-by-default.
- **NFR-SEC-005** Every mutating operation and every authorization denial MUST
  be auditable to a structured log with principal, resource, operation, outcome,
  and request ID. Audit records MUST NOT contain sample payloads by default.
- **NFR-SEC-006** CORS MUST be deny-by-default and explicitly configured
  (DIV-004).
- **NFR-SEC-007** Secrets (API keys, private key passphrases, JWT signing
  material) MUST NOT appear in logs, error responses, metrics, or heap
  snapshots.
- **NFR-SEC-008** All input — URIs, query parameters, JSON and XML bodies,
  filter expressions, mapping expressions — MUST be validated before use.
  `filterExpression` reaches DDS SQL and MUST be treated as untrusted:
  length-bounded, syntax-validated, and rejected if it references members
  outside the endpoint's type.
- **NFR-SEC-009** When Connext Security Plugins are configured, the service MUST
  NOT become a confused deputy: a web principal's authorization MUST be
  evaluated independently of the participant's DDS permissions, and the more
  restrictive of the two MUST apply.
- **NFR-SEC-010** The service MUST NOT serve a document root by default (WIS
  defaults `-documentRoot` to its documentation directory).

### 7.4 Observability — [Post-PoC, except NFR-OBS-001]

For the PoC, structured logs plus the mapping-plan dump (FR-XF-041) are the
debugging tools that matter; the rest is production operations.

- **NFR-OBS-001 [PoC]** Structured JSON logs with levels, a request/connection ID on
  every record, and configurable per-subsystem verbosity.
- **NFR-OBS-002** Prometheus metrics on a separate admin listener: request rate
  and latency histograms by route and status; WebSocket connection and bind
  gauges; samples read/written/dropped by endpoint; transformation evaluation
  latency, error, and drop counters by mapping; DDS match and liveliness counts;
  pool utilization.
- **NFR-OBS-003** OpenTelemetry tracing, with spans covering request → authz →
  transform → serialize → DDS operation.
- **NFR-OBS-004** `/healthz` (liveness) and `/readyz` (readiness, including DDS
  participant health) on the admin listener.
- **NFR-OBS-005** An admin endpoint MUST dump current resource state: entities,
  active binds, loaded mappings and their compile results.

### 7.5 Portability and compatibility

- **NFR-PORT-001 [PoC]** Linux x86-64 only — the development host. Multi-platform
  tiering is [Post-PoC]; nothing in the design may *assume* Linux-only, but
  nothing is built or tested elsewhere.
- **NFR-PORT-002** Connext 7.3 or later MUST be supported, with 7.7 as the
  primary target. Version-conditional behavior MUST be isolated behind an
  adapter — notably the 7.7 default of TypeLookup Service and TypeObject v2,
  which changes remote type discovery timing (FR-DDS-008, RISK-4).
- **NFR-PORT-003** The build MUST target **C++17**. The local toolchain is
  GCC 9.4 / CMake 3.16, and the shipped Connext libraries are built for
  `x64Linux4gcc8.5.0`; C++20 features MUST NOT be required. C++20 MAY be enabled
  optionally where a newer toolchain is available.
- **NFR-PORT-004** No dependency on Routing Service or on WIS binaries at
  runtime. Interop with their configuration formats is a compatibility feature,
  not a dependency.

### 7.6 Maintainability

- **NFR-MAINT-001** The Transformation Engine and the DDS layer MUST be
  independently unit-testable, with no network or HTTP dependency in engine
  tests.
- **NFR-MAINT-002** ~~No external dependency in public headers.~~ **Withdrawn**
  with §8.1 — the constraint existed for the embeddable library. Dependencies are
  now chosen on merit.
- **NFR-MAINT-003 [PoC]** Dependencies MUST be pinned to explicit versions so
  the prototype is reproducible. SBOM generation is [Post-PoC].

---

## 8. Interface Requirements

### 8.1 Embeddable library API — **out of scope**

**Withdrawn.** The PoC is a standalone service only. FR-LIB-001…005 are removed
rather than deferred; if embedding is wanted later it is a new requirement, not
a resumed one. See [DD-018](design-decisions.md#dd-018).

Two consequences worth recording, because they *loosen* constraints elsewhere:

- **NFR-MAINT-002 is relaxed.** The rule forbidding external dependencies in
  public headers existed to keep the embeddable library clean. With no library,
  dependency choice is free — which reopens the HTTP stack decision
  ([OQ-5](questions.md#oq-5)) to options previously ruled out.
- **Sharing a host-supplied `DomainParticipant`** (the old FR-LIB-003) is no
  longer needed, so the service always owns its participant. This simplifies
  entity lifecycle and shutdown.

### 8.2 Client SDKs — [Post-PoC]

- **FR-SDK-001 [Post-PoC]** A TypeScript client covering REST and WebSocket,
  with types generated from published view schemas.
- **FR-SDK-002 [Post-PoC]** A Python client with equivalent coverage.
- **FR-SDK-003 [Post-PoC]** SDKs generated from the OpenAPI document
  (FR-XF-042) so they cannot drift from the server.

For the PoC, hand-written test clients in Python and JavaScript are sufficient
and are test artifacts, not deliverables.

### 8.3 Admin API

- **FR-ADM-001** A separate admin listener, bindable to a different interface
  and port, MUST host health, metrics, config reload, state dump, and mapping
  management. It MUST require its own authorization scope and MUST NOT be
  exposed on the public listener.

---

## 9. Data Model and Type Handling

- **FR-TYPE-001** The full XTypes type system MUST be supported: primitives,
  strings and wstrings, enums, bitmask, structs with inheritance, unions,
  sequences, arrays, maps, optional members, and `@external`.
- **FR-TYPE-002** Type mutability and assignability rules MUST be respected;
  the service MUST NOT create an endpoint whose type is incompatible with the
  matched remote type.
- **FR-TYPE-003** Types MUST be loadable from an XML types library at runtime.
  Note that **Connext Modern C++ has no runtime IDL parser** — there is no
  documented API to turn IDL text into a `DynamicType` at runtime.
- **FR-TYPE-004** Because of FR-TYPE-003, IDL support MUST be handled out of
  band: either by invoking `rtiddsgen -convertToXml` at build or deploy time, or
  by a first-party IDL-to-XML converter. Runtime IDL upload MUST NOT be a v1
  feature.
- **FR-TYPE-005** JSON ⇄ `DynamicData` conversion MUST be lossless for all
  supported types. Connext provides `to_string`/`from_string` JSON conversion;
  where its behavior is lossy or ambiguous (64-bit integers exceeding IEEE-754
  exact range, NaN and infinity, byte sequences) the service MUST define and
  document an explicit encoding, and MUST NOT rely on implicit behavior.
- **FR-TYPE-006** 64-bit integers MUST be encodable as JSON strings under a
  configurable policy, defaulting to string, to avoid silent precision loss in
  JavaScript clients.
- **FR-TYPE-007** CBOR SHOULD be supported as a binary alternative to JSON for
  bandwidth-sensitive links.

---

## 10. Verification and Validation

Scaled to a prototype. The principle: **test the thesis hard, test the
scaffolding lightly.** The transformation engine is what the PoC is claiming, so
its correctness evidence stays at production strength. Everything else drops to
smoke-level.

- **NFR-TEST-001 [PoC]** The transformation engine MUST have thorough unit
  coverage. No numeric gate for the rest of the codebase — a coverage percentage
  on prototype scaffolding measures nothing.
- **NFR-TEST-002 [PoC]** Property-based tests MUST generate random XTypes types
  and samples and assert (a) JSON round-trip identity and (b) for
  `bidirectional` mappings, wire → view → wire identity. **This is the single
  most important test in the PoC** — it is the evidence for the thesis, and the
  only practical defense against the silent-corruption failure modes in RISK-3.
- **NFR-TEST-003 [PoC]** Key and instance semantics (§6.5) MUST be tested
  explicitly, including `dispose`/`unregister` through a view and invalid-sample
  forwarding. Not covered by round-trip tests, and silently wrong if untested.
- **NFR-TEST-004 [PoC]** ASan and UBSan builds SHOULD run locally. TSan when
  concurrency is introduced.
- **NFR-TEST-005 [PoC]** Interoperability smoke test against Shapes Demo, plus
  at least one non-trivial mapped view demonstrated end to end to a browser
  client. This is the demo.
- **NFR-TEST-006 [PoC]** WIS remains available locally as a behavioral oracle
  for ambiguous cases (RISK-5), used ad hoc. A full differential conformance
  suite is [Post-PoC] and contingent on [OQ-3](questions.md#oq-3).
- **NFR-TEST-007 [Post-PoC]** Coverage gates, fuzzing (JSON/XML parsers, URI
  router, WebSocket framer, `HELLO` parser, expression parser), 72-hour soak,
  CI performance regression gating, and Security Plugins interop.

Even in a prototype, fuzzing the expression parser is worth doing early if the
parser is hand-written — it is cheap and finds real bugs. If
[OQ-6](questions.md#oq-6) resolves to CEL, that need largely disappears.

---

## 11. Risks and Open Questions

### 11.1 Risks

| ID | Risk | Impact | Mitigation |
|---|---|---|---|
| **RISK-1** | Transformation evaluation is too expensive on the data path. | Medium (PoC) | Compile plans to a flat instruction sequence over precomputed member offsets; no per-sample name lookup (DD-012). With no hardware target, the PoC establishes the *cost shape* (NFR-PERF-002) rather than an absolute figure — which is the more useful finding anyway, since a bad shape does not improve with faster hardware. |
| **RISK-2** | Bidirectional mapping is genuinely undecidable for expressive mappings, and users expect writes to work through any view. | High | Do not attempt automatic inversion of general expressions. Classify at compile time (FR-XF-025), surface the class in the API, and require an explicit inbound mapping where inversion is not provable. |
| **RISK-3** | Instance and key semantics break under transformation, silently corrupting lifecycle state. | High | §6.5 requirements are non-negotiable and gated by property-based tests. Reject at compile time rather than degrade at runtime. |
| **RISK-4** | Connext 7.7 defaults to TypeLookup Service and TypeObject v2; remote type resolution is asynchronous and discovery callbacks may fire repeatedly and before the type is available. Dynamic reader creation (FR-DDS-008) is fragile. | Medium | Treat type resolution as an explicit state machine with a resolution timeout; never assume a type is present on first callback. Document required `request_types_filter` and type-propagation settings. Keep FR-DDS-008 `MAY`, not `MUST`, for v1. |
| **RISK-5** | Behavioral parity with WIS is under-specified by the manual; some behavior is only discoverable empirically. | Medium | The conformance suite (NFR-TEST-002) differentially tests against the real WIS 7.7.0 binary, which is installed locally. Ambiguities become test cases, not assumptions. |
| **RISK-6** | Connext's JSON conversion has undocumented edge-case behavior, so FR-TYPE-005 losslessness is not guaranteed by the platform. | Medium | Own the JSON codec against `DynamicData` accessors rather than delegating to `to_string`/`from_string`, if property tests find losses. Decide by spike. |
| **RISK-7** | Reimplementing an RTI product creates a support and licensing boundary question. | Medium | Resolve with RTI before committing engineering (OQ-1). We consume documented public APIs only. |
| **RISK-8** | Scope. The mapping DSL can absorb unlimited effort. | High | Build §6.2 (field mapping) and §6.3 (expressions) only. Join (FR-XF-022) and split (FR-XF-023) are out of the PoC. |
| **RISK-9** | **PoC-specific:** the prototype gets promoted to production because it demos well, carrying prototype shortcuts into a plant-facing deployment. | High | Every deferral is marked [Post-PoC] here rather than left implicit, so the gap is enumerable. Do not let the PoC front a real domain with real setpoints, regardless of how well it works. |

### 11.2 Open questions

> **The canonical register is [questions.md](questions.md).** It holds the full
> option analysis, owners, and decision criteria, and is extended as new
> questions surface. The summary below is a snapshot at the time of drafting;
> where the two disagree, `questions.md` wins. Resolutions are recorded in
> [design-decisions.md](design-decisions.md), not here.

- **OQ-1** What is the licensing and support position on reimplementing WIS
  behavior and reusing Routing Service transformation plugin interfaces?
  **Owner: DG. Blocks: project start, not drafting.**
- **OQ-2** Do we need to ingest existing Routing Service Assignment
  Transformation configurations mechanically (FR-XF-053), or is a documented
  migration path enough? Depends on how many exist in the field.
- **OQ-3** Is strict `/dds/rest1` wire compatibility actually required, or do we
  have the freedom to ship only `/api/v1`? This materially changes §5.1 and
  NFR-TEST-002 cost. **Needs a decision before the API layer is designed.**
- **OQ-4** Is joining across topics (FR-XF-022) a v1 requirement? It is the
  single largest driver of state and cache design.
- **OQ-5** Which HTTP stack? Candidates: Boost.Beast (mature, header-heavy,
  no HTTP/2), nghttp2 with a hand-written layer (HTTP/2, more work), or a
  vendored async framework. Prototype needed against NFR-PERF-003.
- **OQ-6** Should the expression language be a bespoke grammar or a restricted
  profile of an existing one (CEL, JSONPath, jq)? CEL is attractive — total,
  type-checked, and specified — but adds a dependency. Prototype needed.
- **OQ-7** How do we authenticate and authorize a WebSocket after `HELLO`?
  Long-lived connections outlive short-lived tokens. Need a re-authentication or
  token-refresh frame, which is a protocol extension beyond WIS.
- **OQ-8** What is the multi-instance and horizontal-scaling story? Stateless
  REST scales trivially; bound WebSocket readers and joined views carry state.
  Sticky routing versus shared state is undecided.

---

## 12. Phasing

**Reordered for the PoC.** The v0.1 ordering put transformation in P3, behind a
production-grade streaming layer — which for a prototype is backwards: it spends
most of the effort on the part that is *not* under test and risks running out of
time before reaching the thesis. Transformation now comes as early as the DDS
plumbing allows.

| Phase | Content | Exit criteria |
|---|---|---|
| **P0 — Spikes** | Expression language (OQ-6), **including union-typed comparison** (OQ-14); JSON losslessness for `Value_t` and `char[32]` (RISK-6); transformation cost shape (RISK-1). HTTP stack is now near-settled (OQ-5 → Boost.Beast). | Each question closed with measured data. Throwaway code. |
| **P1 — Engine first** | Transformation engine standalone: **union-to-scalar projection (FR-XF-005) first**, then plan compiler, mapping evaluation, key semantics, invertibility classification, `scada-web-mapc` CLI. **No HTTP, no DDS domain.** | Round-trip property tests green (NFR-TEST-002); §6.5 covered; `Value_t` projected to JSON correctly including the `char[32]` string branch. |
| **P2 — DDS plumbing** | DDS layer, Resource Manager, DynamicData ⇄ JSON, XML config incl. `<transformation_library>`. One reader on `SelectedValue`, one writer on `ValueRequest`; interest refcounting (system-architecture §5, SR-001…004). | A mapped view readable from a live domain, driven by real `ValueRequest` traffic against scada-selector. |
| **P3 — Web surface** | REST for entity setup and data; WebSocket bind/push; per-client demux (SR-004). Simplest workable concurrency model (DD-019, DD-022). | End-to-end demo: browser client consuming a mapped view that exists in no IDL, and writing back through it. **This is scada-web's part of the deliverable.** |
| **P4 — Enough security to demo safely** | TLS, one authn mechanism, deny-by-default CORS, no default document root. | Demoable on a shared network without embarrassment. Not a security review. |
| **Post-PoC** | Async I/O at scale (DD-009), full authz model (DD-013), observability (§7.4), WIS compat surface (DD-015), plugin ABI (DD-016), SDKs, join/split, hardware-gated performance. | — |

The P1/P2 inversion is the substantive change: putting the engine first means the
thesis is testable — via the CLI and property tests — before any network or DDS
code exists. It is also the highest-risk component, so it fails early if it is
going to. DD-010 (engine independent of HTTP and DDS) is what makes this ordering
possible, and it is now load-bearing rather than merely tidy.

---

## 13. References

**RTI Web Integration Service 7.7.0**
- [Manual index](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/services/web_integration_service/index.html)
- [REST API](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/services/web_integration_service/using_rest_api.html)
- [WebSocket API](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/services/web_integration_service/using_websocket_api.html)
- [Configuration](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/services/web_integration_service/configuration.html)
- [Usage / command line](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/services/web_integration_service/usage.html)
- [HTTP routing table](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/services/web_integration_service/http-routingtable.html)
- [SDK / Library API](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/api/web_integration_service/api_cpp/group__RTI__WebIntegrationServiceLibModule.html)

**RTI Routing Service transformations**
- [Transformation API](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/api/routing_service/api_cpp/group__RTI__RoutingServiceTransformationModule.html)
- [`Transformation.hpp`](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/api/routing_service/api_cpp/Transformation_8hpp_source.html)
- [`TransformationPlugin.hpp`](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/api/routing_service/api_cpp/TransformationPlugin_8hpp_source.html)
- [Examples: `struct_array_transf`](https://github.com/rticommunity/rticonnextdds-examples/tree/master/examples/routing_service/struct_array_transf/c%2B%2B11)

**Connext XTypes / Modern C++**
- [DynamicType and DynamicData](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/api/connext_dds/api_cpp2/group__DDSXTypesModule.html)
- [XTypes use cases](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/api/connext_dds/api_cpp2/group__DDSXTypesExampleModule.html)
- [Migration guide 7.7.0 — type lookup changes](https://community.rti.com/static/documentation/connext-dds/current/doc/manuals/migration_guide/770/general770.html)

**Local artifacts inspected**
- `/home/rti/rti_connext_dds-7.7.0/resource/schema/rti_web_integration_service.xsd`
- `/home/rti/rti_connext_dds-7.7.0/include/rti/webdds/{Service,ServiceProperty}.hpp`
- `/home/rti/rti_connext_dds-7.7.0/resource/app/lib/x64Linux4gcc8.5.0/librtirsassigntransf.so`
- `/home/rti/rti_connext_dds-7.7.0/bin/rtiwebintegrationservice`

**Standards**
- OMG Web-Enabled DDS (DDS-WEB)
- OMG DDS-XTypes 1.3
- RFC 6455 (WebSocket), RFC 7519 (JWT), RFC 3339 (timestamps)
- OpenAPI 3.1, JSON Schema 2020-12
