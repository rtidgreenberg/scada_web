"""Web server — REST + WebSocket surface for scada_web.

FastAPI/uvicorn-based. Exposes:

  - REST: GET /api/v1/topics, GET /api/v1/topics/{name}/samples
  - WebSocket: /ws — streaming push of samples to subscribed clients
  - Health: GET /health

The server knows nothing about DDS directly — it receives samples from the
gateway via callback and routes them to interested clients via InterestManager
(SR-004 per-client demux by uid). Client interest changes (subscribe/
unsubscribe/period) are translated into ValueRequest DDS writes consumed by
scada_select's ControlPlane.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import ScadaWebConfig
from .gateway import DdsGateway
from .interest import InterestManager
from .gen.PlcValue import PLC
from .views import TagValue, TagMeta

logger = logging.getLogger(__name__)

app = FastAPI(title="scada_web", version="0.1.0")

# The DDS topic name ValueRequest commands are written to (see config.yaml).
VALUE_REQUEST_TOPIC = "PLC::ValueRequestTopic"

# These are set by create_app() at startup
_gateway: DdsGateway | None = None
_interest: InterestManager | None = None
_config: ScadaWebConfig | None = None
_ws_clients: dict[str, WebSocket] = {}


def create_app(config: ScadaWebConfig) -> FastAPI:
    """Wire up the FastAPI app with DDS gateway and interest manager."""
    global _gateway, _interest, _config
    _config = config
    _gateway = DdsGateway(config)
    _interest = InterestManager(
        on_add=_send_add,
        on_delete=_on_interest_delete,
        on_period=_send_period,
        min_separation_ms=config.selection.default_min_separation_ms,
    )
    _gateway.on_sample = _on_dds_sample
    _gateway.on_publication_matched = _on_publication_matched

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Serve the browser UI. Mounted last so it cannot shadow declared routes
    # (the /api/v1/{rest:path} catch-all above ensures unmatched API paths
    # never reach this mount either — see CR-036).
    document_root = config.document_root
    if document_root:
        root = Path(document_root)
        if root.is_dir():
            app.mount("/", StaticFiles(directory=str(root), html=True),
                      name="ui")
            logger.info("document_root_mounted path=%s", root)
        else:
            logger.warning("document_root_missing path=%s", root)

    @app.on_event("startup")
    async def startup():
        await _gateway.start()

    @app.on_event("shutdown")
    async def shutdown():
        await _gateway.stop()

    return app


# ─── REST endpoints ──────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok", "topics": _gateway.topics if _gateway else []}


@app.get("/api/v1/topics")
async def list_topics():
    if not _gateway:
        return JSONResponse({"error": "not started"}, status_code=503)
    return {"topics": _gateway.topics}


@app.get("/api/v1/topics/{topic_name}/samples")
async def get_topic_samples(topic_name: str, uid: Optional[int] = None):
    """Return the current sample from the DDS reader cache without taking it."""
    if not _gateway:
        return JSONResponse({"error": "not started"}, status_code=503)
    try:
        sample = _gateway.read_sample(topic_name, uid)
    except KeyError:
        return JSONResponse({"error": f"unknown topic '{topic_name}'"},
                            status_code=404)

    if sample is None:
        return {"topic": topic_name, "sample": None}

    data, _info = sample
    return {
        "topic": topic_name,
        "sample": {
            "uid": int(data.uid),
            "data": _sample_to_view_dict(data),
        },
    }


@app.get("/api/v1/topics/{topic_name}/samples/all")
async def get_all_topic_samples(topic_name: str):
    """Return one retained sample per key from the DDS reader cache."""
    if not _gateway:
        return JSONResponse({"error": "not started"}, status_code=503)
    try:
        samples = _gateway.read_samples(topic_name)
    except KeyError:
        return JSONResponse({"error": f"unknown topic '{topic_name}'"},
                            status_code=404)

    payload = []
    for data, _info in samples:
        payload.append({
            "uid": int(data.uid),
            "data": _sample_to_view_dict(data),
        })
    return {"topic": topic_name, "samples": payload}


@app.get("/api/v1/{rest:path}")
async def unknown_api_route(rest: str):
    """Catch-all for unmatched /api/v1/* paths.

    Declared after every real route above, so a real route always matches
    first. Without this, an unmatched API path falls through to the static
    mount (below) and returns StaticFiles' own 404 — indistinguishable from a
    deliberate "unknown topic" 404 (CR-036). This is what let two tests read
    "endpoint does not exist" as "not wired yet" for two commits after the
    endpoint they targeted was actually removed (CR-029, CR-R02).
    """
    return JSONResponse({"error": f"no such endpoint '/api/v1/{rest}'"},
                        status_code=404)


# ─── WebSocket ───────────────────────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    client_id = str(uuid.uuid4())
    _ws_clients[client_id] = ws
    logger.info("ws_connected client=%s", client_id)

    try:
        while True:
            msg = await ws.receive_json()
            try:
                _handle_ws_message(client_id, msg)
            except (ValueError, KeyError, TypeError) as exc:
                logger.warning("ws_bad_message client=%s err=%s", client_id, exc)
                await ws.send_json({"error": str(exc)})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("ws_error client=%s", client_id)
    finally:
        _ws_clients.pop(client_id, None)
        if _interest:
            _interest.client_disconnect(client_id)
        logger.info("ws_disconnected client=%s", client_id)


def _handle_ws_message(client_id: str, msg: dict[str, Any]) -> None:
    """Process a client command: subscribe/unsubscribe uids."""
    action = msg.get("action")
    if action == "subscribe":
        period_ms = _parse_global_min_separation(msg)
        if period_ms is not None:
            _interest.set_min_separation(period_ms)
        for item in msg.get("uids", []):
            _interest.client_subscribe(client_id, _parse_uid(item))
    elif action == "unsubscribe":
        for item in msg.get("uids", []):
            _interest.client_unsubscribe(client_id, _parse_uid(item))
    elif action in {"set_min_separation", "set_period"}:
        period_ms = _parse_global_min_separation(msg)
        if period_ms is None:
            raise ValueError("period_ms/min_separation_ms is required")
        _interest.set_min_separation(period_ms)


def _parse_global_min_separation(msg: dict[str, Any]) -> int | None:
    """Parse a message-level runtime minimum separation update."""
    if "period_ms" in msg:
        period_ms = int(msg["period_ms"])
    elif "min_separation_ms" in msg:
        period_ms = int(msg["min_separation_ms"])
    else:
        item_periods = {
            int(item[key])
            for item in msg.get("uids", [])
            if isinstance(item, dict)
            for key in ("period_ms", "min_separation_ms")
            if key in item
        }
        if not item_periods:
            return None
        if len(item_periods) > 1:
            raise ValueError("minimum separation is global; values must agree")
        period_ms = item_periods.pop()
    # Must be > 0, not >= 0 — see interest.py's _require_positive_separation
    # for why PERIOD 0 must never reach the selector from here.
    if period_ms <= 0:
        raise ValueError("period_ms/min_separation_ms must be > 0")
    return period_ms


def _parse_uid(item: Any) -> int:
    if isinstance(item, dict):
        return int(item["uid"])
    return int(item)


# ─── Callbacks ───────────────────────────────────────────────────────────────


def _on_dds_sample(topic_name: str, data: Any, info: Any) -> None:
    """Called by DdsGateway when a sample arrives. Route to interested clients."""
    try:
        uid = data.uid
    except Exception:
        return
    if _interest is None:
        return

    # SR-004: per-client demux
    interested = [(client_id, ws) for client_id, ws in list(_ws_clients.items())
                  if _interest.is_interested(client_id, uid)]
    if not interested:
        return

    # Built once and reused for every interested client, rather than once per
    # client — the payload is identical for all of them.
    payload = json.dumps({
        "topic": topic_name,
        "uid": int(uid),
        "data": _sample_to_view_dict(data),
    })
    for client_id, ws in interested:
        asyncio.create_task(_ws_send(client_id, ws, payload))


async def _ws_send(client_id: str, ws: WebSocket, payload: str) -> None:
    try:
        await ws.send_text(payload)
    except Exception:
        # Client gone — will be cleaned up on next receive failure
        pass


def _send_add(uid: int) -> None:
    """Interest 0→1: send selector ADD command via ValueRequest union."""
    logger.info("selector_add uid=%d", uid)
    if _gateway is None:
        return
    try:
        req = PLC.ValueRequest()
        req.addRequest = PLC.AddRequest_t(uid=uid, name="")
        _gateway.write(VALUE_REQUEST_TOPIC, req)
    except Exception:
        logger.exception("value_request_add_failed uid=%d", uid)


def _send_period(min_separation_ms: int) -> None:
    """Global minimum separation changed: send selector PERIOD command.

    Fires once per actual change, regardless of how many uids are active —
    unlike the per-uid ADD fan-out this replaced, a change with nothing
    subscribed still reaches the wire (closes CR-004).
    """
    logger.info("selector_period min_separation_ms=%d", min_separation_ms)
    if _gateway is None:
        return
    try:
        req = PLC.ValueRequest()
        req.periodRequest = PLC.PeriodRequest_t(period_ms=min_separation_ms)
        _gateway.write(VALUE_REQUEST_TOPIC, req)
    except Exception:
        logger.exception("value_request_period_failed period_ms=%d", min_separation_ms)


def _on_interest_delete(uid: int) -> None:
    """Interest 1→0: send ValueRequest{DELETE, uid} to selector."""
    logger.info("selector_delete uid=%d", uid)
    if _gateway is None:
        return
    try:
        req = PLC.ValueRequest()
        req.uid = uid
        _gateway.write(VALUE_REQUEST_TOPIC, req)
    except Exception:
        logger.exception("value_request_delete_failed uid=%d", uid)


def _on_publication_matched(topic_name: str, status: Any) -> None:
    """SR-003: ValueRequest writer (re)matched -- replay the full interest set.

    `presentation::value_request` is RELIABLE + VOLATILE (dds/qos/profiles.xml),
    so a ValueRequest written before the selector's ControlPlane reader is
    matched is discarded, not queued. current_count rising from 0 -- checked
    via current_count_change == current_count, i.e. the previous count was
    zero -- is the first moment a write to this topic can land, whether that's
    initial startup or a selector restart. PERIOD is sent before the ADD burst
    so no tag is briefly at the wrong rate (CR-003, closes CR-011's deferral).
    """
    if topic_name != VALUE_REQUEST_TOPIC or _interest is None:
        return
    if status.current_count_change <= 0:
        return
    if status.current_count != status.current_count_change:
        return  # not a 0→N transition -- writer was already matched
    logger.info("selector_reconcile_triggered topic=%s current_count=%d",
                topic_name, status.current_count)
    _send_period(_interest.min_separation_ms)
    for uid in _interest.reconcile():
        _send_add(uid)


# Exact-type dispatch, not isinstance: generated IDL types are not subclassed,
# so this loses no coverage and lets an unhandled sample type raise instead of
# silently shipping a stringified repr to the browser (CR-013).
_VIEW_DISPATCH: dict[type, Any] = {
    PLC.IdValue: lambda data: TagValue.from_idvalue(data).to_dict(),
    PLC.MetaData: lambda data: TagMeta.from_metadata(data).to_dict(),
}


def _sample_to_view_dict(data: Any) -> dict[str, Any]:
    """Convert a typed DDS sample to a browser-friendly dict via views."""
    try:
        convert = _VIEW_DISPATCH[type(data)]
    except KeyError:
        raise KeyError(f"no view mapping for sample type {type(data).__name__!r}")
    return convert(data)
