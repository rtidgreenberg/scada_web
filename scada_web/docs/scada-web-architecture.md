# scada_web — Python Gateway Architecture

**Status:** Draft v0.2
**Date:** 2026-07-27

The `scada_web/` package is the Level 2 (supervisory) web gateway. It bridges
the DDS global data space to browser clients over REST and WebSocket, applying a
declarative mapping layer that decouples the client view schema from the wire
type.

---

## 1. Placement in the System

```
Level 0/1 (sim/)              Level 2 (scada_web/)           Browser
┌──────────────────┐          ┌──────────────────────┐       ┌──────────┐
│ field_simulation │          │  config.yaml         │       │  HMI     │
│ plc_publisher    │──DDS───▶│  PlcValue.xml→gateway│──HTTP─▶│  trends  │
│ plc_types        │          │  interest → server   │◀─WS───│  alarms  │
└──────────────────┘          └──────────────────────┘       └──────────┘
```

scada_web never touches the simulated process (Level 0) and never speaks raw DDS
to the browser. It owns the boundary between the two worlds.

---

## 2. Module Architecture

```
scada_web/
├── __init__.py       Package root
├── __main__.py       Entry point: python -m scada_web --config ...
├── config.py         YAML config loader + validation
├── config.yaml       Default configuration (wired to sim/)
├── gateway.py        DDS entity lifecycle (participants, readers)
├── interest.py       Per-client uid refcounting
└── server.py         FastAPI REST + WebSocket surface
```

### 2.1 Dependency Flow (acyclic)

```
config.py
   │
   └──▶ gateway.py ────▶ (rti.connextdds + QosProvider for XML types)
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

### 3.1 XML Type Library — Types Loaded at Startup

The gateway loads DynamicTypes from an XML type library at startup via
`dds.QosProvider`. The XML is generated from the canonical IDL source:

```bash
rtiddsgen -convertToXml sim/PlcValue.idl -d sim/
```

In SCADA, the data model is **commissioned infrastructure** — it is defined
once during system engineering and does not change at runtime. This makes
wire-learned types (the pattern from `references/act-sim-scope-infra/`) 
unnecessarily complex for this use case. That pattern suits generic DDS tools
(routers, scopes) that must handle arbitrary types; a SCADA master knows
exactly what types it will see.

**Consequence:** the gateway creates all DDS readers immediately at startup —
no dependency on publishers being up first. Simpler code, faster startup,
easier to test.

### 3.2 YAML Configuration

All DDS topology (participants, topics, filters) and view mappings are declared
in a single YAML file. The schema is modeled after the act-sim-scope-infra
router config:

```yaml
types:
  xml: sim/PlcValue.xml        # XML type library path

participants:
  <name>:
    domain: <int>

topics:
  - name: <TopicName>
    participant: <name>
    type: "PLC::MetaData"      # fully-qualified type from XML
    filter:                    # optional content filter
      expression: "uid = %0"
      parameters: ["5"]

views:
  - name: <view_name>
    topic: <TopicName>
    fields:
      - wire: <DynamicData path>
        view: <JSON key>
        transform: union_scalar | char_array_string
```

### 3.3 Async Event Loop (not thread-per-connection)

The gateway uses Python `asyncio` throughout:
- Sample reading: `DdsGateway._read_loop()` polls readers on a 50ms cadence
- WebSocket push: fire-and-forget `asyncio.create_task` per client per sample

This maps to DD-009 (async I/O, not thread-per-connection) and DD-022 (bounded
concurrency) from the system design decisions.

### 3.4 Interest Refcounting (SR-001 – SR-004)

The `InterestManager` implements all four system requirements from
[system-architecture.md](system-architecture.md) §5:

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
2. Load XML types via QosProvider(types.xml)
3. Create DomainParticipants (per config)
4. Create Topic + DataReader for each configured topic immediately
5. Start read loop (50ms poll)
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
| `type` | string | yes | Fully-qualified type name from XML |
| `qos_profile` | string | no | QoS profile name |
| `filter.expression` | string | no | Content filter SQL expression |
| `filter.parameters` | list | no | Filter parameter values |

### 6.3 `views`

List of view projections (wire → JSON).

| Key | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | View identifier |
| `topic` | string | yes | References a topic name |
| `fields[].wire` | string | yes | DynamicData field path |
| `fields[].view` | string | yes | JSON output key |
| `fields[].transform` | string | no | `union_scalar`, `char_array_string` |

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
| GET | `/api/v1/topics/{name}/type` | Type schema from XML library |

### WebSocket (`/ws`)

Client → Server messages:

```json
{"action": "subscribe", "uids": [5, 12, 30]}
{"action": "unsubscribe", "uids": [5]}
```

Server → Client pushes:

```json
{"topic": "PLC::IdValue", "uid": 5, "data": {"uid": 5, "valueTime": 1722100000000, ...}}
```

---

## 8. Relationship to act-sim-scope-infra

The submodule at `references/act-sim-scope-infra/` provides proven patterns:

| This module | Derived from |
|---|---|
| `gateway.py` (DdsGateway) | `router/src/core/DynamicRouteFactory.cxx` + `RouteEntityFactory.hpp` |
| `config.py` (YAML schema) | `router/config/control-platform.yaml` + `RouteConfigParser.cxx` |

The C++ router uses wire-learned types because it is a generic DDS tool that
routes arbitrary data. scada_web uses XML-loaded types because it is a
purpose-built SCADA master that knows its data model at commission time.
Both share YAML-driven topology declaration.

---

## 9. Future Work

- **Mapping engine** (`mapping.py`): union projection, char-array decode,
  field rename/flatten — the thesis under test per the TRD §1.1.
- **ValueRequest writer**: back-channel to scada-selector for interest management.
- **Historian hook**: periodic snapshot recording independent of live scan rate.
- **Alarm state machine** (ISA-18.2): Normal → Unack → Ack → RTN, with
  priority, shelving, and rate-limiting per the scada-sme guidance.
- **Auth**: per-topic, per-operation authorization (DD-013).
