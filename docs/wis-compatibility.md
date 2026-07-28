# WIS Compatibility Surface

**Status:** Implemented
**Date:** 2026-07-28

scada_web serves the RTI Web Integration Service REST/WebSocket URIs so that
browser clients written against WIS run against scada_web unmodified. `UI/index.html`
is the reference client and required no changes.

This exists so WIS can be removed from the data path without touching the GUI.
The native `/api/v1` + `/ws` surface (slimmer, typed, uid-demuxed) runs on the
same port and is unaffected — see [system-architecture.md](system-architecture.md).

Behavioral reference for everything below is
[technical-requirements.md §2](technical-requirements.md).

---

## 1. What is served

| Surface | Path |
|---|---|
| Reserve connection | `POST /dds/v1/websocket_connections` |
| Read / take samples | `GET /dds/rest1/applications/{a}/domain_participants/{dp}/subscribers/{s}/data_readers/{dr}` |
| Write a sample | `POST /dds/rest1/applications/{a}/domain_participants/{dp}/publishers/{p}/data_writers/{dw}` |
| WebSocket | `WS /dds/websocket/{connection}` |
| Static UI | `/` (mirrors WIS `-documentRoot`) |

WebSocket frames: `HELLO` handshake, then `bind` (readers), `b_push` (server →
client samples), `request` (REST tunneled over the socket, correlated by `id`).

Supported read query parameters: `sampleFormat=json`, `removeFromReaderCache`,
`maxSamples`, `prettyPrint`.

Error bodies follow the WIS contract — `{"code": ..., "message": ...}` with
`INVALID_INPUT`, `INVALID_OBJECT`, `GENERIC_SERVICE_ERROR`; 404 for an unknown
resource, 422 for bad input, 204 on write/create.

## 2. Where the URIs come from

Resource names are **configuration**, not code. Each participant carries a
`wis_name`, and each topic/writer carries a `wis:` block; the URI is assembled
from them in `wis.build_registry()`. This mirrors `scada_web/wis-config.xml`,
so the names the browser is configured with stay in one place:

```yaml
wis:
  application: ScadaWebApp
participants:
  plc_domain:
    domain: 15
    wis_name: Plant
topics:
  - name: "PLC::IdValueTopic"
    wis: { subscriber: IdValueSubscriber, data_reader: IdValueReader }
writers:
  - name: "PLC::ValueRequestTopic"
    wis: { publisher: ControlPublisher, data_writer: ValueRequestWriter }
```

→ `/dds/rest1/applications/ScadaWebApp/domain_participants/Plant/subscribers/IdValueSubscriber/data_readers/IdValueReader`

On startup every registered URI is logged, so a client URI mismatch is
diagnosable from the log alone.

## 3. Two deliberate deviations

**Delivery is selection-gated; binding alone streams nothing.** WIS relays every
sample on a bound DataReader. scada_web pushes only the uids a client has asked
for with a `ValueRequest` `ADD`, and stops on `DELETE`.

This is the significant deviation, and it is deliberate. Relaying all 500 field
tags is both unrepresentative of the target architecture — where scada-select
decides what crosses to the presentation domain — and fatal to the client:
`UI/index.html` rebuilds its entire table via `innerHTML` on *every* sample
([index.html:276](../UI/index.html#L276)), so at the sim's ~340 samples/sec
against a 500-row table it does ~170,000 row-writes/sec and the browser's main
thread never recovers. Measured: the page froze permanently and stopped
responding to DOM queries. With gating, the same page stays responsive with
one-to-a-few tags selected.

Until scada-select exists, scada_web stands in for it: the `ValueRequest` is
still published on DDS for the future selector to consume, *and* applied locally
to decide what that client receives.

**ADD seeds from the reader cache.** On `ADD`, the uid's currently cached sample
is pushed on each bound reader before any new sample arrives. Two reasons: the
row would otherwise stay blank for up to a full publish period (tags 301-500
publish every 10 s), and `PLC::MetaData` is `TRANSIENT_LOCAL` published once per
tag at sim startup, so without this the name and alarm-limit columns would never
populate at all. Measured: a 10 s-tier tag appears in 0.08 s with its name and
limits.

**ValueRequest bodies are translated.** `UI/index.html` predates the
`Command_t`-discriminated union (commit `d32611c`) and still posts the flat
struct `{uid, name, command, period_ms}`. `wis.value_request_samples()` maps it
to the union. An `ADD` with a nonzero `period_ms` becomes **two** samples —
`PERIOD` then `ADD` — because minimum separation is global in the union API while
the flat struct carried it per request; `PERIOD` goes first so the rate is in
effect before the uid starts forwarding.

Translation is done via `DynamicData.from_json()` with an explicit
`$discriminator`, which is the only way to select `METADATA`: it shares the `uid`
member with `DELETE`, and assigning that member always selects `DELETE` (the
first case). Bodies already in union shape pass through untouched.

## 4. Not implemented

Nothing in `UI/index.html` uses these; they raise a clear WIS-shaped error rather
than failing obscurely.

- `sampleFormat=xml` → 422 (JSON only)
- `maxWait` long-poll reads
- `filterExpression`, `sampleStateMask`, `viewStateMask`, `instanceStateMask`,
  `enumsAsIntegers`
- `b_req` streaming writes and `bind_datawriter` → error frame directing the
  client to a `request` frame with `method: POST`
- Builtin discovery topics (`-enableBuiltinTopics`)
- ACL / API keys — the `OMG-DDS-API-Key` HELLO header is required to be *present*
  but its value is not checked, matching WIS run without `-aclFile`
- Resource-management verbs: `POST`/`DELETE`/`PUT` on collections and instances
  (participants, topics, readers and writers are created from YAML at startup)
- HTTPS/TLS (`-sslCertificate`)

`strict_websocket_connections: false` (the default) accepts a socket whose
connection name was never reserved. WIS requires the reservation; set it `true`
to match exactly. The default is forgiving because a browser whose POST is
blocked otherwise fails at the socket with no useful diagnostic.

## 5. Characteristics to be aware of

- One `b_push` frame per sample per bound client, dispatched as a task each. Not
  batched — but note that batching would not help the client, because the UI
  calls `render()` per sample regardless of how many arrive in a frame. The only
  effective lever on that cost is how many samples are delivered, which is what
  selection gating controls.
- Envelopes are built only when some client has that topic bound *and* that uid
  selected (`WisHub.wants`), so unselected tags cost no serialization at all.
- Selection is per-connection, so two browsers cannot disable each other's tags.
  It is not refcounted across clients the way `InterestManager` is for the native
  surface — it does not need to be, since scada_web is filtering its own output
  rather than issuing selector commands on behalf of all clients.
- On reconnect the UI re-sends `ADD` for its active request
  ([index.html:510](../UI/index.html#L510)), so selection restores itself without
  extra server-side reconciliation.
- The push loop selects `new_data` (NOT_READ) rather than reading the whole
  cache. A plain `read()` returns every retained sample on every wake, which
  re-delivered all instances whenever any one updated.

## 6. Verifying

With the sim running on the field domain:

```bash
export RTI_LICENSE_FILE=$NDDSHOME/rti_license.dat
python3 sim/plc_publisher.py --domain-id 15 &
python3 -m scada_web                      # serves API + UI on :8080
```

Open <http://localhost:8080/> — the UI auto-connects; no settings change needed.
The table starts **empty**: enter a uid in the Value Request box and hit Send to
begin streaming that tag. This is expected, not a fault.
