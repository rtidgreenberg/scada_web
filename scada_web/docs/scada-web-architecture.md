# scada_web — Python Gateway Architecture

**Status:** Draft v0.3
**Date:** 2026-07-28

The `scada_web/` package is the Level 2 (supervisory) web gateway. It bridges
selected DDS data to browser clients over REST and WebSocket. It applies typed
Python view mappings that decouple the client view schema from the wire type.

---

## 1. Placement in the System

```
Level 0/1 (sim/)       Level 2 (scada-selector)      Level 2 (scada_web/)      Browser
┌──────────────────┐   ┌────────────────────────┐    ┌──────────────────┐    ┌──────────┐
│ field_simulation │   │ field dp  →  web dp    │    │ generated types  │    │ HMI      │
│ plc_publisher    │──▶│ SelectedValue/MetaData │───▶│ views.py/server  │───▶│ trends   │
│ plc_types        │   │ ValueRequest ◀─────────│◀───│ interest.py      │◀──│ alarms   │
└──────────────────┘   └────────────────────────┘    └──────────────────┘    └──────────┘
```

scada-selector owns the hard-real-time/soft-real-time DDS boundary. scada_web owns
the presentation boundary: selected DDS samples in, view JSON over REST/WebSocket
out. In the target topology scada_web has no field-domain participant and no
direct readers on `PLC::IdValue` or `PLC::MetaData`.

---

## 2. Module Architecture

```
scada_web/
├── __init__.py       Package root
├── __main__.py       Entry point: python -m scada_web --config ...
├── config.py         YAML config loader + validation
├── config.yaml       Pre-selector PoC configuration; target topology uses selected topics
├── gateway.py        DDS entity lifecycle (participants, readers)
├── interest.py       Per-client uid refcounting
├── mapping.py        [DEPRECATED] DynamicData char-array / union patching
├── views.py          View dataclasses + field mapping from generated types
├── server.py         FastAPI REST + WebSocket surface
└── gen/              Python generated types (rtiddsgen output, committed)
```

### 2.1 Dependency Flow (acyclic)

```
config.py
   │
   └──▶ gateway.py ────▶ (rti.connextdds + generated types from gen/)
            │
            ▼
        views.py ───────▶ (gen/PLC → view dataclasses)
            │
            ▼
        server.py ──────▶ (fastapi, uvicorn)
            │
            ▼
        interest.py      (pure Python, no DDS dependency)
```

No module imports upward. `interest.py` is deliberately DDS-free so it can be
unit-tested without the Connext runtime.

---

## 3. Key Design Decisions

### 3.1 Python Generated Types (DD-052)

The gateway uses **Python generated types** produced by `rtiddsgen`, not
DynamicData. The types are generated once from the canonical IDL source:

```bash
rtiddsgen -language python -d scada_web/gen/ dds/idl/PlcValue.idl
```

The generated output is committed to the repository — types are static SCADA
infrastructure that does not change at runtime.

In SCADA, the data model is **commissioned infrastructure** — it is defined
once during system engineering and does not change at runtime. This makes
DynamicData (the pattern from `references/act-sim-scope-infra/`) unnecessarily
complex for this use case. That pattern suits generic DDS tools (routers,
scopes) that must handle arbitrary types; a SCADA master knows exactly what
types it will see.

**Consequence:** the gateway creates typed DataReaders directly at startup —
no DynamicData, no XML type loading, no string-based member access. IDE
autocompletion, import-time error detection, and direct attribute access for
field mapping.

### 3.2 YAML Configuration

DDS topology (participants, topics, filters) is declared in a YAML file.
The schema is modeled after the act-sim-scope-infra router config:

```yaml
participants:
  <name>:
    domain: <int>

selection:
  default_min_separation_ms: 250

topics:
  - name: <TopicName>
    participant: <name>
    type: "PLC::MetaData"      # fully-qualified generated type name
    filter:                    # optional content filter
      expression: "uid = %0"
      parameters: ["5"]
```

`selection.default_min_separation_ms` initializes the web UI/runtime subscribe
path. Browser messages may override the global runtime value with `period_ms` or
`min_separation_ms`; the selector applies nonzero `period_ms` values as global
minimum-separation updates.

**Note:** View mappings are **not** in config — they are Python code in
`views.py` (DD-053). This gives typed attribute access, IDE completion, and
import-time validation rather than string-path resolution at runtime.

### 3.5 View Types and Field Mapping (DD-053)

The mapping from DDS generated types to smaller web-facing view types lives
in `views.py` as classmethods on each view dataclass:

```python
@dataclass(slots=True)
class TagValue:
    uid: int
    value: float
    timestamp: int

    @classmethod
    def from_idvalue(cls, s: PLC.IdValue) -> "TagValue":
        return cls(
            uid=s.uid,
            value=s.smoothedValue.float64Value,
            timestamp=s.valueTime,
        )
```

This pattern:
- Defines a **smaller type** than the full DDS wire type
- Maps only the fields the web client needs
- Handles union discrimination with normal Python (no config DSL)
- Is individually unit-testable without DDS infrastructure

### 3.3 Async Event Loop (not thread-per-connection)

The gateway uses Python `asyncio` throughout:
- Sample reading: `DdsGateway._read_loop()` polls readers on a 50ms cadence
- WebSocket push: fire-and-forget `asyncio.create_task` per client per sample

This maps to DD-009 (async I/O, not thread-per-connection) and DD-022 (bounded
concurrency) from the system design decisions.

### 3.4 Interest Refcounting (SR-001 – SR-004)

The `InterestManager` implements all four system requirements from
[system-architecture.md](../../docs/system-architecture.md) §5:

| Requirement | Implementation |
|---|---|
| SR-001: ADD on 0→1, DELETE on 1→0 | `_refcounts[uid]` dict with transition callbacks |
| SR-002: disconnect decrements | `client_disconnect()` iterates the client's uid set |
| SR-003: reconcile after selector restart | `reconcile()` returns the full active set |
| SR-004: per-client demux | `is_interested(client_id, uid)` checked before each push |

---

## 4. Data Flow

### 4.1 Startup Sequence

```
1. Load config.yaml
2. Load QoS profiles via QosProvider
3. Create DomainParticipant(s) from config — target deployment is web domain only
4. Create typed Topic + DataReader for each selected topic
5. Start one `rti.asyncio` read task per reader
6. Start FastAPI/uvicorn
```

### 4.2 Steady-State Sample Flow

```
DDS network
    │
    ▼  (builtin discovery already done; reader exists)
DataReader.take()
    │
    ▼
gateway._read_loop()
    │  calls on_sample(topic_name, data, info)
    ▼
server._on_dds_sample()
    │  extract uid from sample
    │  for each connected ws client:
    │      if interest.is_interested(client_id, uid):
    │          asyncio.create_task(ws.send_text(json))
    ▼
Browser
```

### 4.3 Client Subscribe Flow

```
Browser → WebSocket {"action": "subscribe", "uids": [5, 12, 30]}
    │
    ▼
server._handle_ws_message()
    │
    ▼
interest.client_subscribe(client_id, uid)
    │  if 0→1 transition:
    │      on_add(uid) → write ValueRequest(uid, ADD) to selector
    ▼
DDS network (ValueRequest topic)
```

---

## 5. External Dependencies

| Package | Purpose | Required |
|---|---|---|
| `rti.connextdds` | DDS connectivity (Connext Python API) | Yes |
| `pyyaml` | YAML config parsing | Yes |
| `fastapi` | REST + WebSocket framework | Yes |
| `uvicorn` | ASGI server | Yes |

Install: `pip install pyyaml fastapi uvicorn`

(`rti.connextdds` is installed via the Connext SDK, not pip.)

---

## 6. Configuration Reference

### 6.1 `participants`

Map of participant name → settings.

| Key | Type | Required | Description |
|---|---|---|---|
| `domain` | int | yes | DDS domain ID |
| `qos_xml` | string | no | Path to QoS provider XML |

### 6.2 `topics`

List of topic subscriptions.

| Key | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | DDS topic name |
| `participant` | string | yes | References a participant name |
| `type` | string | yes | Fully-qualified generated type name |
| `qos_profile` | string | no | QoS profile name |
| `filter.expression` | string | no | Content filter SQL expression |
| `filter.parameters` | list | no | Filter parameter values |

### 6.3 Views (code, not config)

View mappings are **not** configured in YAML. They are Python classmethods
in `views.py` — see §3.5 and [DD-053](../../docs/design-decisions.md#dd-053).

### 6.4 `server`

| Key | Type | Default | Description |
|---|---|---|---|
| `host` | string | `0.0.0.0` | Bind address |
| `port` | int | `8080` | Listen port |
| `websocket_path` | string | `/ws` | WebSocket endpoint |
| `rest_prefix` | string | `/api/v1` | REST base path |

---

## 7. API Surface

### REST

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness + ready topics |
| GET | `/api/v1/topics` | List ready and pending topics |
| GET | `/api/v1/topics/{name}/type` | Type/view schema for the configured topic |

### WebSocket (`/ws`)

Client → Server messages:

```json
{"action": "subscribe", "uids": [5, 12, 30]}
{"action": "unsubscribe", "uids": [5]}
```

Server → Client pushes:

```json
{"topic": "PLC::SelectedValue", "uid": 5, "data": {"uid": 5, "timestamp": 1722100000000, ...}}
```

---

## 8. Relationship to act-sim-scope-infra

The submodule at `references/act-sim-scope-infra/` provides proven patterns:

| This module | Derived from |
|---|---|
| `gateway.py` (DdsGateway) | `router/src/core/DynamicRouteFactory.cxx` + `RouteEntityFactory.hpp` |
| `config.py` (YAML schema) | `router/config/control-platform.yaml` + `RouteConfigParser.cxx` |

The C++ router uses wire-learned types because it is a generic DDS tool that
routes arbitrary data. scada_web uses Python generated types because it is a
purpose-built SCADA master that knows its data model at commission time.
Both share YAML-driven topology declaration.

---

## 9. Future Work

- **Remove `mapping.py`**: the DynamicData char-array / union patching is
  superseded by generated types + view classmethods (DD-052, DD-053).
- **ValueRequest writer**: back-channel to scada-selector for interest management.
- **Historian hook**: periodic snapshot recording independent of live scan rate.
- **Alarm state machine** (ISA-18.2): Normal → Unack → Ack → RTN, with
  priority, shelving, and rate-limiting per the scada-sme guidance.
- **Auth**: per-topic, per-operation authorization (DD-013).
- **Per-key reliability classes** — see §9.1. Post-PoC; the PoC is uniformly
  best-effort on the web side.

### 9.1 Per-Key Reliability Classes (post-PoC)

**Today, and for the PoC:** selected value and selected metadata streams on the
web side are `RELIABLE` + `TRANSIENT_LOCAL` + `KEEP_LAST(1)`
([DD-029](../../docs/design-decisions.md#dd-029)). The reader cache holds the
latest sample per uid, which matters for slow-changing selected values and repeat
REST reads.

**Why it will not hold forever:** not every tag is display data. Some values are
**not idempotent** — a totalizer, an event or trip counter, a discrete state
transition, a setpoint-write confirmation. For those, "the next periodic sample
repairs it" is false, because the next sample carries a *different* value rather
than a repetition of the lost one. Those tags want reliable delivery; the other few
thousand do not.

**The constraint that shapes the whole design: DDS reliability is per *endpoint*,
not per instance.** There is no per-key `RELIABILITY` to set. So "reliability per
key" necessarily means **partitioning tags across endpoints**, not tuning a policy:

- **Separate topics, not separate writers on one topic.** Two writers with different
  reliability on one topic looks tempting and misbehaves: a `RELIABLE` reader will
  not match a `BEST_EFFORT` writer at all (requested exceeds offered), while a
  `BEST_EFFORT` reader matches *both* — so critical samples arrive twice on the
  best-effort path. A second topic (`PLC::SelectedValueCritical`, `RELIABLE`, with a
  `RELIABLE` reader here) keeps matching unambiguous.
- **`ValueRequest` gains a class per uid**, alongside the global `period_ms`.
  The selector then routes each selected uid to the writer for its class — a
  small extension of the per-uid selection state it already keeps
  ([DD-027](../../docs/design-decisions.md#dd-027)).
- **Interest refcounting gains a second dimension** for class/criticality. The
  minimum separation remains global; one client asking for reliable delivery
  would upgrade the tag class for everyone.

**Which reliability, and on which hop.** There are four separate delivery paths in
this system, and only one of them is what this section is about:

| Hop | Mechanism | Today | This section |
|---|---|---|---|
| sim → selector | DDS `RELIABILITY` | `RELIABLE` | no |
| **selector → scada-web** | **DDS `RELIABILITY`** | **`BEST_EFFORT`** ([DD-029](../../docs/design-decisions.md#dd-029)) | **yes — this one** |
| scada-web → selector (`ValueRequest`) | DDS `RELIABILITY` | `RELIABLE` (the stated exception) | no |
| scada-web → browser | WebSocket over TCP | reliable by transport, no DDS QoS involved | no |

So: **DDS reliability on the selector's outbound DataWriter and scada-web's matching
DataReader.** Nothing here is about HTTP, WebSocket, or TCP — and nothing here is
about the browser, which does not speak DDS at all.

**The trap: switching that reliability back on can slow down the plant side.** This
is why the item is roadmap work and not a config change.

Here is the chain, one step at a time:

1. Reliable delivery means the sending DataWriter keeps each sample until the
   receiving DataReader acknowledges it.
2. If that DataReader stops acknowledging, the writer's queue of unacknowledged
   samples fills up. **The reader here is scada-web** — this gateway process — so the
   causes are things that stall *it*: the process is paused, swapped, or CPU-starved;
   its read loop is blocked on something slow; or the network between the two hosts
   drops packets faster than they can be repaired.
3. When that queue is full, the next `write()` in the selector **waits** instead of
   returning.
4. That wait happens on the selector's single thread — the same thread that reads
   from the field side.
5. While it waits, nothing is being read from the field. Incoming samples pile up
   and eventually get dropped.

So a stalled **gateway** ends up degrading the plant-facing half of the selector.
That is exactly the coupling [DD-029](../../docs/design-decisions.md#dd-029) got rid
of by making the web side best-effort: a best-effort writer never waits for an
acknowledgement, so step 3 cannot happen.

**A frozen browser is a different problem on a different hop.** It stalls the
WebSocket, so TCP backpressure lands in scada-web's own send path — never in the
selector's, because DDS acknowledgements come from this process, not from the
browser. That hop needs its own answer (bounded per-client queues, drop or
disconnect a client that cannot keep up) and it is scada-web's to give: see
[DD-022](../../docs/design-decisions.md#dd-022) and §3.3's fire-and-forget push. The
two must not be conflated — the isolation described below buys nothing against a slow
browser.

Turning reliability back on for some tags therefore means making sure that waiting
can never touch the read loop. Three ways, roughly in order of preference:

- **Send asynchronously** — a background thread does the sending, so the read loop
  hands off and moves on (`ASYNCHRONOUS_PUBLISH_MODE` with a `FlowController`).
- **Give the reliable writer its own thread**, separate from the read loop.
- **Cap the queue and drop when it is full** — simplest, but then delivery is not
  actually reliable, and the docs must say so plainly instead of implying a
  guarantee nobody checked.

**Building that isolation is the real work here. Changing the QoS setting is one
line.**

**Evaluate this cheaper option first:** application-level per-key gap detection with
re-request over the control channel. `ValueRequest` stays `RELIABLE`
([DD-029](../../docs/design-decisions.md#dd-029)), so scada-web can detect a gap for
a critical tag and ask for a resend — the same request/reply machinery the tag
catalogue already requires, applied to values. It gives eventual per-key
completeness with **no reliable data writer at all**, so the boundary invariant
stays structural. It needs a per-instance sequence number or writer-side sample
count to detect gaps against; whether a `BEST_EFFORT` reader's `SampleLostStatus`
is usable for this is **unverified** and should be checked before designing on it.
RTI's `TopicQuery` is the documented on-demand catch-up mechanism and is worth
evaluating in the same pass.

**Prerequisite for either:** a decision about *which* tags are critical, which is
plant-engineering input rather than an architecture choice, and which overlaps
[OQ-14](../../docs/questions.md#oq-14) (where alarm evaluation lives) — an
alarm-triggering value is the obvious first member of the reliable class.
