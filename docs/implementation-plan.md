# SCADA Demo — Implementation Plan

**Status:** Active
**Date:** 2026-07-27

---

## Phase 1: Typed SCADA PoC

**Goal:** Live data from simulated field devices displayed in a browser through
the target component boundaries: scada-sim on the field domain, scada-selector as
the only hard-RT/soft-RT DDS conduit, scada-web on the web domain, and the browser
over REST/WebSocket.

```
sim/                    scada-selector         scada_web (Python)        Browser
┌────────────┐ domain 0 ┌──────────────┐ domain 1 ┌────────────────┐     ┌─────┐
│ field_sim  │──DDS───▶│ compiled C++ │──DDS───▶│ generated types │─HTTP▶│ GUI │
│ plc_pub    │          │ fixed uid    │          │ views.py       │◀─WS─│     │
└────────────┘          │ range + QoS  │          │ server.py      │     └─────┘
                        └──────────────┘          └────────────────┘
```

### Deliverables

| # | Component | Work | Status |
|---|---|---|---|
| 1.1 | **scada-sim** | Already exists (`sim/`). Publishes `PLC::MetaData` + `PLC::IdValue` on domain 0. | Done |
| 1.2 | **scada-selector** | Compiled-type C++ app. Bridges domain 0 → domain 1, pre-enables the fixed PoC uid range (DD-039), republishes values on `PLC::SelectedValue`, and forwards metadata on `PLC::SelectedMetaData`. | Not started |
| 1.3 | **scada_web gateway** | Python generated-type readers on domain 1 selected topics; `views.py` maps generated DDS samples to slim web-facing dataclasses (DD-052/DD-053). | Scaffolded; target-topic switch not done |
| 1.4 | **Browser GUI** | Minimal HMI that consumes latest-value WebSocket pushes and keeps a client-side trend buffer. | Not started |

### Phase 1 Success Criteria

- Operator opens the GUI and sees live values from the sim via `SelectedValue`
- scada-web has no field-side participant: no reader on domain 0 and no direct subscription to `PLC::IdValue` or `PLC::MetaData`
- Metadata for the configured PoC uid range reaches scada-web on `SelectedMetaData`
- Web-side selected topics use `BEST_EFFORT` + `VOLATILE`; `ValueRequest` remains the one reliable keep-all exception when dynamic selection is added
- Browser receives typed view JSON, not raw DDS wire shape

### Phase 1 Constraints

- The PoC uses a configured uid range instead of dynamic catalogue discovery (DD-039)
- Name-based lookup, alarms, historian, and per-key reliability classes are out of scope
- Dynamic `ValueRequest` ADD/DELETE, refcounting, and selector restart reconciliation are follow-up work unless the demo needs runtime selection

---

## Phase 2: Dynamic Selection and Catalogue Bootstrap

**Goal:** Add the runtime selection and catalogue behavior that the fixed-range
PoC deliberately avoids, without weakening the selector boundary.

```
Browser subscribe/unsubscribe
  │
  ▼
scada_web InterestManager ──ValueRequest(RELIABLE + KEEP_ALL)──▶ scada-selector
  ▲                                                            │
  └──────────── SelectedValue / SelectedMetaData ◀─────────────┘
```

### Deliverables

| # | Component | Work | Status |
|---|---|---|---|
| 2.1 | **ValueRequest writer** | Back-channel DDS writer in `gateway.py` to send ADD/DELETE/METADATA/PERIOD union commands to scada-selector with `RELIABLE` + `KEEP_ALL`. | Not started |
| 2.2 | **Interest refcounting** | Aggregate per-client uid interest; send ADD on 0→1, DELETE on 1→0, and send PERIOD command when the global minimum separation changes. | Not started |
| 2.3 | **Per-client demux** | Do not forward a selected sample to a client that did not request its uid. | Not started |
| 2.4 | **Catalogue bootstrap** | Pick the `METADATA` all-sentinel value, request the catalogue, retry missing replies, and define UI readiness. | Not started |
| 2.5 | **Selector restart reconciliation** | Detect selector restart/liveliness loss and resend the active interest set. | Not started |

### Phase 2 Success Criteria

- Operator can add/remove tags at runtime and the selector output changes immediately
- Two clients interested in the same uid do not disable each other accidentally
- A late-joining or restarted scada-web obtains the metadata catalogue by request/retry, not by assuming web-side durability
- The JSON the GUI receives remains the typed view shape:
  ```json
  {"uid": 5, "timestamp": 1722100000000, "value": 72.4, "name": "WTP1_PMP01_FLOW_PV"}
  ```

### Phase 2 Validates

- DD-023/DD-034/DD-036: the command stream remains unkeyed and reliable keep-all
- DD-029: selected values and selected metadata are reliable/transient-local on the web side
- DD-052/DD-053: scada-web remains generated-type Python with view classmethods
- DD-044: scada-web stays on domain 1 and never regains a field-side endpoint

---

## Sequencing

```
Phase 1                              Phase 2
────────────────────────────────     ──────────────────────────────────
1.1 sim (done)                       2.1 ValueRequest writer
1.2 selector fixed range ───────┐    2.2 interest refcount + rates
1.3 scada_web selected topics ──┤    2.3 per-client demux
1.4 browser latest-value UI ────┘    2.4 catalogue request/retry
      │                           2.5 selector restart reconciliation
      ▼                                    │
    [Typed PoC demo]                          ▼
                 [Dynamic selection demo]
```

The historical WIS-compatible route remains useful as a comparison/reference, but
it is no longer the implementation path for the accepted PoC.
