# Proposal: Custom RTI Connext Routing Service Adapter Exposing a WIS-like REST/WebSocket Interface

**Status:** Draft for internal engineering review
**Audience:** RTI engineering (assumes fluency with Connext DDS, XTypes/DynamicData, and Routing Service)
**Date:** 2026-07-27

---

## 1. Executive summary

We propose building a **custom Routing Service Adapter** (C++, via the Adapter SDK) that hosts an embedded HTTP/WebSocket server and bridges REST calls to the DDS databus — providing a REST interface *similar in spirit* to **Web Integration Service (WIS)**, but running **inside a Routing Service instance** and driven by Routing Service's config-driven stream model.

This is technically feasible. The Adapter SDK is explicitly built to "consume and produce data for different data domains (Connext, MQTT, raw Socket, etc.)" and adapters own their own I/O (sockets, servers). An embedded HTTP listener fits that model directly.

The **one significant design challenge** is an architectural impedance mismatch: Routing Service's model is *asynchronous stream forwarding* (StreamReader → StreamWriter), while REST is *synchronous request/reply* — often over transient data. Bridging the two requires an in-adapter **caching/buffering layer** and disciplined **thread hand-off** between the HTTP thread pool and Routing Service's session threads. This is the primary source of effort and risk.

**Recommendation up front:** build this **only** when the value is specifically "REST as a plug-in port of a Routing Service we're already running," or when we need an **opinionated REST schema** that WIS's generic WEDDS resource model doesn't provide. If the need is a generic REST/WebSocket façade over DDS, **WIS already exists and is supported** — prefer it. If the need is a tailored REST API with no Routing Service involvement, a **standalone Connext + web-framework app** is usually the faster path. Section 11 gives explicit decision criteria.

---

## 2. Background & motivation

### 2.1 The benchmark: WIS

WIS implements the OMG **Web-Enabled DDS (WEDDS)** standard and provides:

- A **RESTful HTTP** interface with CRUD-like operations over DDS entities (create/delete/list/update participants, publishers, subscribers, readers, writers).
- **Read/write of data samples** in both **JSON and XML**.
- A **WebSocket** interface for real-time push.
- **API-key access control** over HTTPS / secure WebSocket.
- Support for **disconnected / stateless clients** that would otherwise have to join a domain and manage discovery and data delivery themselves.

WIS is the reference for what "similar REST interface" means. Our target is a **pragmatic subset** of this surface (see §3), not a full WEDDS reimplementation.

### 2.2 Why build an adapter instead of using WIS

Legitimate drivers for an in-Routing-Service REST adapter:

- **Consolidated deployment.** A Routing Service instance is already deployed for domain/protocol bridging; adding HTTP as one more adapter "port" avoids standing up and operating a separate WIS process.
- **Opinionated REST schema.** We want clean, domain-specific endpoints (e.g. `POST /streams/{name}`) rather than the generic WEDDS resource tree.
- **Config-driven multi-stream plumbing.** Routing Service already gives us topic/type discovery, XTypes handling, route lifecycle, and monitoring "for free" — we reuse it rather than rebuild it.
- **Custom payload shaping, auth, or transport** details WIS doesn't expose.

If none of these apply, this proposal is not the right investment — see §11.

---

## 3. Goals & non-goals

### Goals
- A loadable Routing Service Adapter (shared library) that starts an embedded HTTP + WebSocket server.
- **Write path:** `POST` a JSON sample → publish to a DDS topic via a StreamWriter.
- **Read path:** `GET` returns the latest value / a bounded queue of samples for a topic, served from an in-adapter cache fed by a StreamReader.
- **Streaming path:** WebSocket (and/or SSE) subscription delivering samples in real time.
- **JSON ⇄ DynamicData** conversion using XTypes.
- **HTTPS + API-key auth**, aligned with WIS's access-control model.
- **XML-configurable** via standard Routing Service config (port, TLS, exposed streams).

### Non-goals (initial scope)
- Full WEDDS standard compliance / URL scheme parity with WIS.
- Full dynamic entity CRUD lifecycle (create arbitrary participants/readers at runtime) in the MVP — deferred to a later phase.
- XML sample representation (JSON-only initially).
- Replacing WIS as a product.

---

## 4. Architecture

### 4.1 Plugin type and language

- **Plugin type:** Adapter (of the three SDK plugin types — Adapter, Processor, Transformation — only the Adapter owns external I/O and produces/consumes non-DDS data).
- **Language:** **C++**. The C++ Adapter API is the most ergonomic for managing an embedded server's lifecycle and RAII of native resources. (C and Java are also supported; Java is adapter-capable but a less natural fit for a native HTTP/TLS stack.)

### 4.2 Component mapping

The adapter object model maps cleanly onto HTTP concerns:

| SDK entity | Lifecycle | Responsibility in this adapter |
|---|---|---|
| **AdapterPlugin** | Created at service start | Registration, global config parse, shared thread pool / TLS context |
| **Connection** | Created when the DomainRoute is enabled | **Owns the embedded HTTP + WebSocket server** (bind, listen, accept); owns the route-wide topic registry |
| **Session** | Created when the service Session is enabled | Concurrency unit; RS **serializes** access to the StreamReaders/StreamWriters it contains |
| **StreamWriter** | Per output stream | **Write path**: receives samples pushed from the HTTP handler, calls DDS write |
| **StreamReader** | Per input stream | **Read/stream path**: receives DDS samples asynchronously, updates the cache, fans out to WebSocket subscribers |
| **Discovery StreamReader** | Optional | Advertises available streams so routes/topics can be discovered dynamically rather than fully static |

### 4.3 Data representation

- Use **DynamicData (XTypes)** as the universal representation, consistent with the SDK's data model. This gives schema-flexible, any-topic handling without recompiling per type.
- **JSON ⇄ DynamicData**: leverage Connext's built-in JSON serialization for DynamicData for both directions. Type information comes from the route's registered types (XML type definitions or discovered types).

### 4.4 Data-flow diagram (logical)

```
                 ┌─────────────────────── Adapter (Connection) ───────────────────────┐
   HTTP client   │                                                                     │
   ── POST ─────►│  HTTP thread pool ──► write queue ──► [Session thread] StreamWriter ├──► DDS topic (out)
                 │                                                                      │
   ── GET ──────►│  HTTP thread pool ◄── read cache  ◄── [Session thread] StreamReader ◄├── DDS topic (in)
                 │                                    ▲                                 │
   ══ WS/SSE ═══►│  subscriber registry ◄────────────┘ (fan-out on sample arrival)     │
                 └──────────────────────────────────────────────────────────────────── ┘
```

The two horizontal boundaries — HTTP thread pool ↔ Session thread — are the crux of the design (§5).

---

## 5. Core design challenge: request/reply over a streaming framework

Routing Service has **no request/reply primitive**; its entire model is asynchronous stream forwarding. REST GET/CRUD is synchronous request/reply, frequently over transient data. Three sub-problems follow:

### 5.1 Read cache ("current state" for GET)
DDS samples arrive asynchronously in the StreamReader; an HTTP `GET` needs *something* to return synchronously. We maintain an **in-adapter cache** per exposed stream:
- **Keyed topics:** a last-value-per-instance map (mirrors `READ`/`DURABILITY`-style semantics), plus optional bounded history.
- **Unkeyed / streaming topics:** a bounded ring buffer (configurable depth) so `GET` can return the last N samples.
- Cache is updated on the Session thread when the StreamReader is called; read by HTTP threads under a read-write lock (or lock-free snapshot).

### 5.2 Thread hand-off
- Routing Service **serializes** access within a Session — StreamReader/StreamWriter calls happen on RS-owned threads.
- The embedded HTTP server has its **own** thread pool.
- **Write:** HTTP handler enqueues the parsed sample onto a **write queue**; a session-affine worker drains it and calls `StreamWriter::write()`. HTTP threads must **never** call the StreamWriter directly.
- **Read:** HTTP handler reads from the cache snapshot; never blocks on a session thread.
- **WebSocket fan-out:** on sample arrival (session thread), push to a **subscriber registry**; actual socket writes happen on the HTTP/WS thread pool to avoid blocking RS threads.

### 5.3 Backpressure & lifecycle
- Bounded queues with a defined **overflow policy** (drop-oldest vs. reject-with-503).
- Clean shutdown ordering: stop accepting HTTP → drain/settle queues → tear down StreamReaders/Writers → stop server. Must interoperate with Routing Service enable/disable and remote administration.
- WebSocket subscriber cleanup on disconnect; guard against slow consumers (per-subscriber bounded queue, disconnect on sustained overflow).

This layer is where the effort and the bugs concentrate; it should be prototyped first (§10).

---

## 6. Proposed REST API surface

A pragmatic, opinionated subset. `{stream}` is a configured route stream (topic + type).

| Method & path | DDS operation | Notes |
|---|---|---|
| `GET /streams` | list configured streams | discovery/introspection |
| `POST /streams/{stream}` | write one sample | JSON body → DynamicData → `StreamWriter::write()` |
| `GET /streams/{stream}` | read latest / last-N | served from read cache; query params `?max_samples=&instance=` |
| `GET /streams/{stream}/{instanceKey}` | read a specific instance | keyed topics |
| `GET /streams/{stream}/schema` | return the type schema | derived from registered XTypes |
| `WS /streams/{stream}/subscribe` | live subscription | server pushes samples as they arrive |
| `GET /streams/{stream}/events` | SSE alternative to WS | for HTTP-only clients |

**Optional Phase 3 (WEDDS-closer) entity CRUD**, if we want to approach WIS parity:

| Method & path | Purpose |
|---|---|
| `POST /entities/writers`, `.../readers` | create writer/reader at runtime |
| `DELETE /entities/{id}` | tear down |
| `GET /entities` | list active entities |

**Payloads:** JSON only initially; sample envelope carries `data`, and optionally `info` (source timestamp, instance state) for reads. Error model: standard HTTP status codes + JSON error body.

**Relationship to WIS:** the write/read/subscribe core mirrors WIS's data operations; the entity-CRUD layer is where WIS is far richer (full WEDDS). We deliberately treat CRUD as optional/late.

---

## 7. Security

- **Transport:** HTTPS + secure WebSocket (WSS). The adapter owns the TLS stack, so we control cipher/cert policy.
- **AuthN/AuthZ:** **API-key** scheme matching WIS's model — keys authorize clients and can be scoped per stream and per operation (read/write/subscribe).
- **DDS Security alignment:** the adapter is a normal Connext participant; when the domain uses Connext DDS Security, the adapter authenticates/enforces at the DDS layer as usual. Document the trust boundary clearly: REST clients are *outside* the DDS security perimeter and are gated by the adapter's API-key/TLS layer, which then acts as an authenticated DDS participant on their behalf.
- **Hardening:** request size limits, rate limiting, per-subscriber quotas, no sensitive data in URLs/query strings.

---

## 8. Configuration (Routing Service XML sketch)

The adapter is wired like any other Routing Service adapter plugin. Illustrative:

```xml
<dds>
  <plugin_library name="RestAdapterLib">
    <adapter_plugin name="RestAdapter">
      <dll>rti_rest_adapter</dll>
      <create_function>RestAdapter_create</create_function>
    </adapter_plugin>
  </plugin_library>

  <routing_service name="RestGateway">
    <domain_route name="RestBridge">
      <!-- DDS side -->
      <participant name="dds">
        <domain_id>0</domain_id>
      </participant>
      <!-- REST side: our custom adapter connection owns the HTTP server -->
      <connection name="rest" plugin_name="RestAdapterLib::RestAdapter">
        <property>
          <value>
            <element><name>http.port</name><value>8080</value></element>
            <element><name>http.tls.enabled</name><value>true</value></element>
            <element><name>http.tls.cert</name><value>certs/server.pem</value></element>
            <element><name>auth.api_keys_file</name><value>keys.json</value></element>
          </value>
        </property>
      </connection>

      <session name="s">
        <!-- REST write -> DDS publish -->
        <route name="ingest">
          <dds_output participant="dds">
            <topic_name>SensorData</topic_name>
            <registered_type_name>SensorData</registered_type_name>
          </dds_output>
          <input connection="rest">
            <stream_name>SensorData</stream_name>
          </input>
        </route>
        <!-- DDS subscribe -> REST read/stream -->
        <route name="egress">
          <dds_input participant="dds">
            <topic_name>SensorData</topic_name>
            <registered_type_name>SensorData</registered_type_name>
          </dds_input>
          <output connection="rest">
            <stream_name>SensorData</stream_name>
          </output>
        </route>
      </session>
    </domain_route>
  </routing_service>
</dds>
```

(Exact tag shapes follow the current Routing Service adapter configuration schema; the above shows intent — one adapter connection, streams mapped to DDS topics in both directions.)

---

## 9. Build & dependencies

- **RTI Routing Service Adapter SDK** (C++ API) — headers/libs from the Connext Professional install.
- **Embedded HTTP/WebSocket library.** Options to evaluate:
  - A small header-only C++ HTTP/WS lib (fast to integrate, fewer transitive deps).
  - A more full-featured async framework (better TLS/WS ergonomics, heavier).
  - Selection criteria: TLS support, WebSocket support, license compatibility, static-link friendliness, thread model that plays well with RS.
- **JSON handling:** Connext's DynamicData JSON serialization for data; a general JSON lib for envelopes/config if needed.
- **Packaging:** a shared library (`.so`/`.dll`) exposing the adapter `create` entry point, loaded by Routing Service via `<dll>`/`<create_function>`.
- **Platforms:** match the Connext-supported platform matrix for the target deployment.

---

## 10. Effort estimate & phasing

Rough sizing for one experienced C++/Connext engineer. Treat as order-of-magnitude, not a commitment.

| Phase | Scope | Rough effort |
|---|---|---|
| **0. Spike** | Adapter loads in RS; embedded HTTP server starts/stops cleanly under RS lifecycle; prove the thread hand-off model end-to-end with one hardcoded topic | ~1–2 weeks |
| **1. Write path** | `POST → StreamWriter::write()`, JSON→DynamicData, config-driven streams | ~1–2 weeks |
| **2. Streaming** | WebSocket/SSE subscribe, fan-out from StreamReader, subscriber lifecycle/backpressure | ~2 weeks |
| **3. Read cache** | `GET` latest/last-N, keyed-instance cache, history bound, snapshot reads | ~2–3 weeks |
| **4. Security** | HTTPS/WSS, API-key auth, scoping, hardening | ~1–2 weeks |
| **5. Entity CRUD (optional)** | Runtime reader/writer creation toward WEDDS-closer parity | ~3–4 weeks+ |
| **Cross-cutting** | Tests, docs, packaging, monitoring integration | ongoing |

**MVP** = Phases 0–2 (write + live streaming) — this alone covers a large share of real "web client talks to DDS" use cases and is the fastest path to a demonstrable result. Read/cache and CRUD are where scope (and cost) grow toward WIS parity.

### Key risks
- **Thread-model correctness** (deadlocks/blocking RS session threads) — mitigate by front-loading the Phase 0 spike.
- **Backpressure under load** — bounded queues + explicit overflow policy, load-test early.
- **Type/schema management** for arbitrary topics — rely on XTypes/DynamicData; validate with evolving types.
- **Scope creep toward full WEDDS** — hold the line on the non-goals; CRUD is explicitly late/optional.
- **We are partly rebuilding WIS** — continuously re-justify against §11.

---

## 11. Recommendation & decision criteria

**Build the custom adapter when:**
- We are **already running Routing Service** for bridging and want REST to be a plug-in port of that same process; **and/or**
- We need an **opinionated, domain-specific REST schema** rather than the generic WEDDS resource model; **and/or**
- Consolidated deployment/operations (one service, not two) is a hard requirement.

**Prefer WIS (don't build) when:**
- The need is a **generic, standards-based** REST/WebSocket façade over DDS. WIS already does this, is supported, and implements the hard parts (WEDDS semantics, entity CRUD, JSON/XML, auth). Building a parallel general-purpose façade is hard to justify.

**Prefer a standalone Connext + web-framework app when:**
- We want a **tailored REST API** and **don't** need Routing Service's config-driven plumbing. This is often the **fastest** path to a bespoke API and avoids working against the adapter framework's streaming grain.

**Deciding question:** *Are we already deploying Routing Service for other bridging, and do we want HTTP to be a port of that process?*
→ **Yes** → custom adapter (this proposal).
→ **No, and we want generic REST-over-DDS** → WIS.
→ **No, and we want a bespoke API** → standalone app.

---

## 12. References

- [Routing Service — SDK](https://community.rti.com/static/documentation/connext-dds/current/doc/manuals/connext_dds_professional/services/routing_service/sdk.html)
- [Routing Service — Core Concepts](https://community.rti.com/static/documentation/connext-dds/current/doc/manuals/connext_dds_professional/services/routing_service/core_concepts.html)
- [Routing Service — Adapter API (C)](https://community.rti.com/static/documentation/connext-dds/current/doc/api/routing_service/api_c/group__RTI__RoutingServiceAdapterModule.html)
- [HOWTO: Create a Routing Service Adapter](https://community.rti.com/howto/create-a-routing-service-adapter)
- [Web Integration Service — Introduction](https://community.rti.com/static/documentation/connext-dds/current/doc/manuals/connext_dds_professional/services/web_integration_service/introduction.html)
- [Web Integration Service — REST API](https://community.rti.com/static/documentation/connext-dds/current/doc/manuals/connext_dds_professional/services/web_integration_service/using_rest_api.html)
- [Web Integration Service — Configuration](https://community.rti.com/static/documentation/connext-dds/current/doc/manuals/connext_dds_professional/services/web_integration_service/configuration.html)
