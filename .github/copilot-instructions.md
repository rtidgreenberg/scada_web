# Copilot Instructions — scada_web workspace

## Debugging: check logs first

When diagnosing runtime issues, **always inspect `logs/` before reading source code or guessing**.

| Log file | Component | What it captures |
|----------|-----------|------------------|
| `logs/scada_web.log` | scada_web (Python gateway + HTTP/WS server) | DDS gateway lifecycle, sample routing, WebSocket errors, interest management |
| `logs/sim.log` | sim/plc_publisher (field simulator) | Tag metadata publication, scan-loop events, DDS writer errors |
| `logs/scada_select.log` | scada_select (C++ selector) | Startup config, ValueRequest handling, data-plane forwarding, selection-table changes |

### Workflow

1. `tail -50 logs/<component>.log` to see recent activity
2. `grep -i error logs/*.log` for cross-component error sweep
3. Only then open source files to trace the root cause

Log files rotate at 5 MB (3 backups kept for Python apps). The selector log is append-only via tee and should be truncated manually if it grows large.

## Project layout (quick reference)

- `sim/` — Field simulator (Purdue Level 0/1), publishes on DDS domain 15
- `scada_select/` — C++ selector binary, bridges domain 15 → 16
- `scada_web/` — Python web gateway on domain 16, serves REST + WebSocket
- `UI/` — Browser HMI (single index.html)
- `dds/idl/` — IDL type definitions
- `dds/qos/` — QoS profiles XML
- `scripts/` — Start scripts for each component
- `tests/` — pytest test suite
- `docs/` — Architecture, design decisions, implementation plan

## Running the system

```bash
scripts/start-sim.sh        # terminal 1
scripts/start-select.sh     # terminal 2
scripts/start-web.sh        # terminal 3
# then open http://localhost:8080/
```

## Key conventions

- scada_web uses Python `logging` module (not print)
- The sim uses Python `logging` (logger name: `scada_sim`)
- The selector writes to stdout/stderr; start script tees to log file
- All log output goes to both console AND `logs/` directory
- Never write test output outside the workspace — use `test_output/` or `logs/`
