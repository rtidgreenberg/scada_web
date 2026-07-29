# scada_web

A proof-of-concept SCADA system built on RTI Connext DDS, demonstrating a web gateway with declarative data-model transformation between the DDS data space and browser-based HMI clients.

## Overview

The system simulates a field process (PLCs/RTUs), selects and filters tag data through a DDS selector, and presents live values to a browser HMI via REST and WebSocket APIs.

### Components

| Component | Role | Language | Location |
|-----------|------|----------|----------|
| **scada-sim** | Simulated field process + PLC/RTU (Purdue Level 0–1) | Python | `sim/` |
| **scada-selector** | Key-based data selection & rate filtering (Level 2) | C++ | `scada_select/` |
| **scada-web** | Web gateway — REST + WebSocket API (Level 2) | Python (FastAPI + `rti.connextdds`) | `scada_web/` |
| **Browser HMI** | Tag monitor / operator interface | HTML + JS | `UI/` |

### Data Flow

```
Field Simulator (Domain 15)
    │
    ├── PLC::MetaDataTopic  (tag catalog)
    └── PLC::IdValueTopic   (live values)
            │
      scada_select  (filters by UID + rate)
            │
            ├── PLC::SelectedMetaDataTopic  (Domain 16)
            └── PLC::SelectedValueTopic     (Domain 16)
                    │
              scada_web  (DDS → REST/WS)
                    │
              Browser HMI
```

## DDS Topic Topology

![DDS Topic Topology](docs/dds-topology.drawio.svg)

## Running

```bash
scripts/start-sim.sh        # terminal 1 — field simulator
scripts/start-select.sh     # terminal 2 — selector
scripts/start-web.sh        # terminal 3 — web gateway
# then open http://localhost:8080/
```

## Project Structure

```
dds/idl/        IDL type definitions
dds/qos/        QoS profiles XML
sim/            Field simulator (publisher)
scada_select/   C++ selector binary
scada_web/      Python web gateway
UI/             Browser HMI (single-page)
scripts/        Start scripts
tests/          pytest test suite
docs/           Architecture & design docs
```

## Documentation

- [System Architecture](docs/system-architecture.md)
- [Technical Requirements](docs/technical-requirements.md)
- [Design Decisions](docs/design-decisions.md)
- [Implementation Plan](docs/implementation-plan.md)
