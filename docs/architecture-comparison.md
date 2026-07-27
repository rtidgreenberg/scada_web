# Architecture Comparison: Standalone Service vs Routing Service Plugins

**Status:** Decision input — see [OQ-23](questions.md#oq-23)
**Date:** 2026-07-27

> **Superseded in part (2026-07-27).** §5 and §7 recommended hosting
> scada-selector as a Routing Service **Processor**. A subsequent requirement —
> the selector must use **compiled IDL types**, not `DynamicData`, because it
> subscribes to high-rate topics — makes that impossible: Routing Service's
> built-in DDS adapter is DynamicData-based and offers no documented way to bind
> generated types to a Processor's `TypedInput<T>`. **Both components are now
> standalone.** See [DD-026](design-decisions.md#dd-026). The analysis of why
> scada-web should not be an Adapter (§3.1) is unaffected and still governs.
**Question:** Should scada-web be a custom WIS-style standalone application, or a
Routing Service Adapter + Processor?

Companion to [RTI_REST_Adapter_Proposal.md](RTI_REST_Adapter_Proposal.md), which
argues the Adapter case in detail. This document evaluates it against the
standalone option **for our specific system** and reaches a different
recommendation — a hybrid the proposal does not consider.

All Routing Service behavior below was verified against Connext 7.7.0
documentation via Connext AI; citations are in §8.

---

## 1. The options

| | Option | Shape |
|---|---|---|
| **A** | **Standalone service** | Custom C++ app: embedded HTTP/WS server + Connext participant + mapping engine. What [technical-requirements.md](technical-requirements.md) currently assumes. |
| **B** | **RS Adapter + Processor** | Adapter hosts the HTTP/WS server as a Routing Service "port"; Processor does mapping/join. One RS process. The proposal's design, extended with a Processor. |
| **C** | **Hybrid** | **scada-selector as an RS Processor**; **scada-web standalone**. Splits the decision by component instead of taking it system-wide. |

Option C is not in the proposal. It emerged from noticing that the two components
have opposite fits (§5).

---

## 2. What Routing Service gives you free

Genuinely substantial, and the strongest argument for B or C.

**Remote administration** over DDS — topics `rti/service/administration/command_request`
and `.../command_reply`, with a REST-like `action + resource_identifier + body`
model supporting `CREATE`/`GET`/`UPDATE`/`DELETE` on Service, DomainRoute,
Session, Route, AutoRoute, Connection, Input, and Output. Includes config
load/unload/save, per-entity state control, and shutdown. `rtirssh` ships as a
client. This covers most of TRD §8.3 (admin API) and FR-CFG-005 (hot reload).

**Monitoring** — three topics (`rti/service/monitoring/config`, `/event`,
`/periodic`) carrying per-route, per-session, per-input, and per-output metrics:
`in_samples_per_sec`, `out_samples_per_sec`, `in_bytes_per_sec`,
`out_bytes_per_sec`, `latency_millisec`, plus a per-session `thread_pool` with
per-thread CPU usage. Covers a large share of NFR-OBS-002.

**Also free:** XML configuration and validation, QoS profile handling, XTypes and
type registration, route lifecycle, log verbosity control, and standard shutdown
semantics for both executable and embedded-library deployments.

Building the equivalent in Option A is real work — call it several weeks for a
credible admin plane and metrics surface, and it is work that produces no
progress on the mapping thesis.

---

## 3. Where Routing Service fights our requirements

### 3.1 The one that decides it: REST reads

**Routing Service has no request/reply primitive.** Its model is asynchronous
stream forwarding: RS pulls samples out of an input and hands them to an output.
Once forwarded, they are gone.

So in Option B, an HTTP `GET` has nothing to read from, and the adapter must
maintain its own cache — the proposal's §5.1, sized at 2–3 weeks.

#### What "DataReader read semantics" means

Shorthand I used loosely elsewhere. Concretely, a DataReader is not a delivery
callback — it is a **queryable, instance-indexed, QoS-managed store**, and a REST
GET is a query against it. What it provides:

| Capability | What the middleware maintains |
|---|---|
| **Instance indexing** | Samples grouped per key. `KEEP_LAST depth=N` retains N per instance, evicting per instance — not one global buffer. |
| **`read()` vs `take()`** | `read()` returns without consuming, so repeated queries see the same data; `take()` removes. `removeFromReaderCache` maps directly. |
| **Sample state** | READ / NOT_READ per sample, flipped when a read returns it. |
| **View state** | NEW / NOT_NEW per instance — is this the first sample seen for this instance, or the first since it returned from disposal. |
| **Instance state** | ALIVE / NOT_ALIVE_DISPOSED / NOT_ALIVE_NO_WRITERS, derived from dispose messages and matched-writer tracking. NOT_ALIVE_NO_WRITERS in particular requires per-instance writer bookkeeping. |
| **`filterExpression`** | DDS SQL via QueryCondition — a specified grammar with a working evaluator. |
| **`maxWait`** | A WaitSet on a ReadCondition triggers when a *matching* sample arrives — not merely when any sample arrives. |
| **Invalid samples** | Dispose/unregister surface as samples with `valid_data == false` carrying only the key, so lifecycle transitions are observable through the same query path. |
| **Ordering** | Per DESTINATION_ORDER QoS, with loan/`return_loan` lifetime management. |

- **Option A:** the reader cache *is* the store the REST layer queries. `read()`
  with a QueryCondition gives filtering, per-instance latest values, and lifecycle
  state, without consuming — implemented by RTI, correctly.
- **Option B:** Routing Service **takes** from its DataReader and forwards. By the
  time samples reach the adapter they have left the store; state was consumed by
  RS's forwarding, not by the client's query. The adapter must rebuild an
  instance-indexed store with eviction, lifecycle derivation, and a filter
  evaluator. Every item above is a well-specified behavior that is easy to get
  approximately right and hard to get exactly right.

This is the crux: Option B discards the component that already solves the read
path and rebuilds it worse.

#### An honest limit on this argument

The table above describes semantics that are **per DataReader**. WIS makes them
per-client because in the WEDDS model each web client *creates its own*
DataReader. **Our architecture does not** —
[DD-020](design-decisions.md#dd-020) gives scada-web one shared reader on
`SelectedValue`, precisely to avoid a reader per client.

On a shared reader, three of those capabilities do not mean per-client what
FR-REST-003 implies, **and this is true in Option A as well as Option B**:

- **`take()` is unsafe.** One client consuming a sample removes it for everyone.
- **Sample state** is "read by the gateway", not "read by this client".
- **View state** is "first seen by the gateway" — a client that connects later
  sees NOT_NEW for instances that are new *to it*.

Instance state and `filterExpression` are unaffected: instance state is a property
of the instance, and per-client QueryConditions on one shared reader are supported
and cheap.

So Option A's advantage is real but narrower than "FR-REST-003 comes free". The
accurate claim: **the reader cache is a queryable instance-indexed store that
Option A keeps and Option B throws away.** The per-client layer sits on top in
either case, and is tracked as [OQ-25](questions.md#oq-25) — where the likely
answer is that our system wants latest-value reads and push, not
poll-and-take, so most of the WIS polling surface should be dropped rather than
reimplemented.

### 3.2 Runtime mutation is partly unsupported

The C adapter API explicitly marks `session_update`, `stream_reader_update`, and
`stream_writer_update` as **not supported**. So per-stream behavior cannot be
mutated at runtime through update callbacks; changes must come via discovery-driven
stream lifecycle or be fixed at creation.

Notably, `Processor` is *not* subject to this — it inherits
`rti::routing::UpdatableEntity` and its `update()` **is** supported. That
asymmetry matters for §5.

### 3.3 Session serialization and thread hand-off

RS serializes all operations on a concrete StreamReader/StreamWriter within a
Session; different Sessions may run concurrently. **The default session thread
pool is 1 thread.** Blocking inside `write()` stalls every other route in that
Session.

An adapter Connection owning its own thread pool and listening socket is
documented-compatible and matches shipped examples (the MongoDB adapter uses a
client pool in the Connection). So this is workable — but it means two thread
domains and a hand-off queue in both directions, which is where the proposal
correctly locates the bugs. In Option A there is one thread domain we control.

### 3.4 Notification is push, data is pull

An adapter signals `StreamReaderListener::on_data_available()`; RS then calls
`read()`/`take()` when it decides to. Fine, but it inserts a scheduling hop
between "sample arrived" and "sample delivered to the web client" that Option A
does not have. Relevant to NFR-PERF-001, though at SCADA rates not decisive.

### 3.5 Errors are log-and-continue

RS logs runtime operation errors and continues rather than failing the route. Not
wrong, but NFR-REL-001 wants per-request fault containment with defined behavior,
and in Option B the error policy is partly the host's.

---

## 4. Where Routing Service fits better than expected

Two of my earlier assumptions turned out to favor B, and it is worth being
explicit rather than quietly dropping them.

**DD-020 removed the dynamic-entity problem.** Moving key-based selection into
scada-selector means scada-web holds exactly one reader and one writer, forever. RS's
static, config-driven stream model is a *good* fit for a fixed small topology —
and the entity-CRUD requirement, which is where adapters are weakest and which the
proposal defers to a late optional phase, may not be needed at all if
[OQ-3](questions.md#oq-3) resolves to `/api/v1` only. The architecture decision
made two turns ago accidentally removed Option B's second-worst problem.

**Processors are genuinely multi-input.** A Processor sees all inputs and all
outputs of its route, with callbacks `on_data_available(Route&)`,
`on_input_enabled`, `on_periodic_action`, `on_start`/`on_stop`, and a supported
`update()`. Multi-input correlation is a documented use case — merging two inputs
into one output appears in RTI's own examples. It is application code, not a
declarative join operator, but it is application code inside a framework built to
host it.

---

## 5. Option C: the components pull in opposite directions

The proposal treats this as one system-wide choice. It isn't. **scada-selector and
scada-web have opposite fits to the Routing Service model**, and the reason is
§3.1: whether the component needs request/reply.

| | scada-selector | scada-web |
|---|---|---|
| Interaction model | Stream in → stream out | Request/reply + streaming |
| Inputs | `IdValue`, `ValueRequest` | `SelectedValue`, `MetaData` |
| Needs DataReader read/take semantics? | **No** | **Yes** — FR-REST-003 |
| Needs its own socket/thread pool? | **No** | **Yes** |
| Needs runtime mutable state? | Yes — the enable set | Yes — client interest |
| Type strategy | **Compiled** — one type, high rate | **DynamicData** — arbitrary types |
| Fit to Routing Service | Excellent on shape, **ruled out on types** ([DD-026](design-decisions.md#dd-026)) | **Poor** |

> **Two corrections since this table was written.** The `MetaData` input moved to
> scada-web ([DD-024](design-decisions.md#dd-024)) — correlation is presentation
> work, so the selector has two inputs, not three. And the selector's RS fit,
> excellent on shape, is void on types (DD-026). The shape argument survives only
> as the reason to revisit if the type constraint relaxes.

**scada-selector is a textbook Processor.** Its entire job is: three inputs, one
output, holding a per-uid enable set and a per-uid MetaData cache, emitting
enriched samples. That is multi-input correlation with state — exactly what
Processors are for. `update()` is supported, so the enable set is even mutable
through remote administration if we want that in addition to the `ValueRequest`
topic. It needs no sockets, no request/reply, and no cache beyond the metadata map
it needs anyway.

Writing it as a Processor means roughly the correlation logic and nothing else —
no participant setup, no XML config parsing, no lifecycle, no monitoring, no admin
plane. All of that comes from RS.

**scada-web is the opposite.** It needs synchronous reads with DDS state
semantics (§3.1), owns a socket server, and has per-connection state. Every RS
affordance is either unused or an obstacle.

So Option C: **scada-selector as an RS Processor, scada-web standalone.** No adapter
anywhere, which means the request/reply impedance mismatch — the proposal's
"primary source of effort and risk" — never arises.

---

## 6. Comparison

Effort is relative, for our system, and excludes the mapping engine itself — which
is identical in all three options because [DD-010](design-decisions.md#dd-010)
already requires it to be independent of both HTTP and DDS. That independence is
what makes this decision reversible.

| Dimension | A: Standalone | B: Adapter + Processor | C: Hybrid |
|---|---|---|---|
| REST read semantics (FR-REST-003) | **Free** — DataReader | Rebuild states + SQL filter | **Free** — DataReader |
| Streaming/WebSocket push | Direct | Via RS hop + hand-off | Direct |
| Remote admin (§8.3) | Build it | **Free** | **Free for the filter**, build for web |
| Monitoring (NFR-OBS-002) | Build it | **Free** | **Free for the filter**, build for web |
| XML config, QoS, lifecycle | Build it | **Free** | Free for filter, build for web |
| The join (DD-021) | Bespoke filter app | Processor | **Processor** |
| Thread model complexity | One domain | Two domains + queues | One each, no bridging |
| Processes to operate | 2 | **1** | 2 |
| Framework risk | Low | **High** — proposal budgets 1–2 wks just to prove thread hand-off | Low |
| Extra licensing surface | None beyond Connext | Routing Service | Routing Service |
| Reversibility | — | Adapter is a rewrite to undo | Filter is ~200 lines either way |

---

## 7. Recommendation

> **Point 1 below is withdrawn** by the compiled-types requirement
> ([DD-026](design-decisions.md#dd-026)). scada-selector is standalone, not a
> Processor. Points 2 and 3 stand, and the reasoning for them is unchanged.
> Original text kept because the *reason* the Processor fit so well — multi-input
> correlation with state — is still true, and is why this would be the first thing
> to reconsider if the type constraint ever relaxes.

**Option C.** Specifically:

1. ~~**scada-selector becomes a Routing Service Processor** rather than a
   standalone app. It is the natural shape for multi-input correlation with state,
   and RS supplies its config, lifecycle, admin, and monitoring.~~
   **Withdrawn — see DD-026.** The built-in DDS adapter is DynamicData-based, and
   the selector must use compiled types. Standalone.
2. **scada-web stays standalone.** The REST read surface is DataReader semantics;
   giving that up to gain an admin plane we can add later is a bad trade.
3. **Do not build the REST adapter.** Its central problem — reconstructing
   read/take over a cache — is work whose output is strictly worse than the
   DataReader it replaces.

**Net effect: Routing Service is not used.** That is a genuine loss — the free
remote administration and monitoring in §2 were the strongest argument for
involving it, and both components must now provide their own. It is the
consequence of two requirements that each independently rule RS out for their
component: compiled types for Role 1, DataReader read semantics for Role 2.

**If Option C is rejected, prefer A over B.** B's free infrastructure is real but
buys the wrong things: we would gain an admin plane and metrics while
reimplementing sample-state tracking and DDS SQL filtering, and we would spend the
prototype's schedule proving a thread hand-off model rather than testing the
mapping thesis.

**The proposal's own decision criteria agree.** Its §11 says: prefer a standalone
app when you want a tailored API and are not already running Routing Service for
other bridging. We are not running RS for bridging, and OQ-3 is leaning toward a
tailored `/api/v1` rather than WEDDS parity. By the proposal's test, the adapter is
the wrong choice for scada-web — and its recommendation is conditional in exactly
the way that matters.

### Caveats on C

- **Licensing/deployment.** RS ships with Connext Professional and is installed
  locally, but deployment licensing for a Processor plugin in an RS host must be
  confirmed. Folds into [OQ-1](questions.md#oq-1) and is the one thing that could
  invalidate C.
- **Two processes, not one.** C forfeits the consolidated-deployment argument.
  Acceptable: the components are at different Purdue positions anyway
  ([OQ-22](questions.md#oq-22)).
- **A Processor is only loadable inside RS**, so its logic must stay separable to
  be unit-testable — the same discipline DD-010 already imposes on the engine.
- **If the filter's logic outgrows correlation** — arbitrary per-client policy,
  say — reassess. Today it is an enable set and a metadata cache.

### What this does not change

The mapping engine, its plan compiler, key semantics, and the round-trip property
tests are unaffected in all three options. TRD §12 P1 stands as written. This
decision is about plumbing, and DD-010 is what keeps it that way.

---

## 8. Sources

Routing Service 7.7.0, verified via Connext AI:

- [Adapter API (C++)](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/api/routing_service/api_cpp/group__RTI__RoutingServiceAdapterModule.html)
- [Multi-threading safety](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/api/routing_service/api_cpp/mtsafety.html) — session serialization
- [Processor API](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/api/routing_service/api_cpp/group__RTI__RoutingServiceProcessorModule.html)
- [`Processor` class reference](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/api/routing_service/api_cpp/classrti_1_1routing_1_1processor_1_1Processor.html)
- [Controlling Data: Processing Data Streams](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/services/routing_service/controlling_data.html)
- [Data Integration: Combining Different Data Domains](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/services/routing_service/adapters.html)
- [Remote Administration](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/services/routing_service/remote_admin.html)
- [Monitoring](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/services/routing_service/monitoring.html)
- [Configuration — session `<thread_pool>`](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/services/routing_service/configuration.html)
- [shapes_processor example](https://github.com/rticommunity/rticonnextdds-examples/tree/master/examples/routing_service/shapes_processor)
- [mongo_db adapter example](https://github.com/rticommunity/rticonnextdds-examples/tree/master/examples/routing_service/mongo_db)
