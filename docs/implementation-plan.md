# SCADA Demo — Implementation Plan

**Status:** Active
**Date:** 2026-07-27

---

## Phase 1: End-to-End Demo with WIS

**Goal:** Live data from simulated field devices displayed in a browser, proving
the DDS pipeline works before building custom software.

```
sim/                    scada-selector         WIS (off-the-shelf)       Browser
┌────────────┐          ┌──────────────┐       ┌──────────────────┐      ┌─────┐
│ field_sim  │──DDS───▶│ compiled C++ │──DDS─▶│ RTI Web Int Svc  │─HTTP─▶│ GUI │
│ plc_pub    │          │ uid gating   │       │ (stock, no mods) │◀─────│     │
└────────────┘          └──────────────┘       └──────────────────┘      └─────┘
```

### Deliverables

| # | Component | Work | Status |
|---|---|---|---|
| 1.1 | **scada-sim** | Already exists (`sim/`). Publishes `PLC::MetaData` + `PLC::IdValue` on domain 0. | Done |
| 1.2 | **scada-selector** | Compiled-type C++ app. Subscribes to `IdValue`, holds enabled-uid set, republishes enabled tags on `PLC::SelectedValue`. Receives `ValueRequest` (ADD/DELETE) commands. | Not started |
| 1.3 | **WIS config** | XML config for RTI Web Integration Service: participants, types (from IDL→XML), readers on `SelectedValue` + `MetaData`, writer on `ValueRequest`. | Not started |
| 1.4 | **Browser GUI** | Minimal web page that hits WIS REST to subscribe (POST ValueRequest), polls/streams tag values, and renders a basic mimic with trends. | Not started |

### Phase 1 Success Criteria

- Operator opens the GUI, selects tags → values stream live from the sim
- Adding/removing tags is immediate (refcount through WIS→ValueRequest→selector)
- MetaData (names, limits) populates the display on connect (TRANSIENT_LOCAL)
- No custom middleware — stock WIS only

### Phase 1 Constraints

- WIS exposes the **raw wire type** (Value_t union, char[32] strings, nested limits) — the GUI must handle it directly
- No per-field mapping, no union projection, no unit conversion on the server side
- This is intentionally ugly on the client — it motivates Phase 2

---

## Phase 2: scada_web Replaces WIS

**Goal:** The Python `scada_web` gateway replaces WIS, adding the mapping/
transformation layer that gives clients a clean view schema decoupled from
the wire type.

```
sim/                    scada-selector         scada_web (Python)        Browser
┌────────────┐          ┌──────────────┐       ┌──────────────────┐      ┌─────┐
│ field_sim  │──DDS───▶│ compiled C++ │──DDS─▶│ discovery.py     │─HTTP─▶│ GUI │
│ plc_pub    │          │ uid gating   │       │ gateway.py       │◀─WS──│     │
└────────────┘          └──────────────┘       │ mapping engine   │      └─────┘
                                               │ interest.py      │
                                               │ server.py        │
                                               └──────────────────┘
```

### Deliverables

| # | Component | Work | Status |
|---|---|---|---|
| 2.1 | **scada_web gateway** | Wire type learning + dynamic subscription (from YAML config). Already scaffolded in `scada_web/`. | Scaffolded |
| 2.2 | **Mapping engine** | `mapping.py` — union projection (Value_t → scalar), char[32] → string, field rename/flatten, unit conversion. The thesis under test. | Not started |
| 2.3 | **ValueRequest writer** | Back-channel DDS writer in `gateway.py` to send ADD/DELETE to scada-selector. | Not started |
| 2.4 | **WebSocket streaming** | Server pushes mapped samples to subscribed clients in real time. | Scaffolded |
| 2.5 | **Browser GUI update** | GUI consumes the clean view schema (`{uid, timestamp, value, name, limits}`) instead of raw DDS types. Simpler client code. | Not started |

### Phase 2 Success Criteria

- Same operator workflow as Phase 1, but the JSON the GUI receives is:
  ```json
  {"uid": 5, "timestamp": 1722100000000, "value": 72.4, "name": "WTP1_PMP01_FLOW_PV"}
  ```
  instead of the raw `Value_t` union with discriminator + nested char arrays
- Mapping is declarative (YAML `views:` section) — no code change to reshape the output
- WIS is fully removed from the pipeline
- Adding a new topic type requires only a config change (no recompile, no IDL on the gateway)

### Phase 2 Validates

- DD-002: DynamicData throughout (no generated types on the web side)
- The mapping DSL thesis: declarative transformation on the web boundary
- Wire type learning: gateway subscribes with no prior type knowledge

---

## Sequencing

```
Phase 1                              Phase 2
────────────────────────────────     ──────────────────────────────────
1.1 sim (done)                       2.1 gateway (scaffolded)
1.2 scada-selector ─────────────┐    2.2 mapping engine
1.3 WIS config          ────────┤    2.3 ValueRequest writer
1.4 browser GUI ────────────────┘    2.4 WebSocket streaming
         │                           2.5 GUI update (consume clean JSON)
         ▼                                    │
    [Phase 1 demo]                            ▼
         │                              [Phase 2 demo]
         └── Phase 1 GUI complexity ──▶ motivates Phase 2
```

Phase 2 reuses 1.1 (sim) and 1.2 (selector) unchanged. Only the web tier swaps.
