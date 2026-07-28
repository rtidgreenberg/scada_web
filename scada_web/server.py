"""Web server — REST + WebSocket surface for scada_web.

FastAPI/uvicorn-based. Exposes:
  - REST: GET /api/v1/topics, GET /api/v1/topics/{name}/samples
  - WebSocket: /ws — streaming push of samples to subscribed clients
  - Health: GET /health

The server knows nothing about DDS directly — it receives samples from the
gateway via callback and routes them to interested clients via InterestManager.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from .config import ScadaWebConfig
from .gateway import DdsGateway
from .interest import InterestManager
from .mapping import sample_to_dict

logger = logging.getLogger(__name__)

app = FastAPI(title="scada_web", version="0.1.0")

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
        on_add=_on_interest_add,
        on_delete=_on_interest_delete,
    )
    _gateway.on_sample = _on_dds_sample

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


@app.get("/api/v1/topics/{topic_name}/type")
async def get_topic_type(topic_name: str):
    """Return the type structure for a topic (loaded from XML library)."""
    if not _gateway:
        return JSONResponse({"error": "not started"}, status_code=503)
    try:
        dtype = _gateway.get_type(topic_name)
    except Exception:
        return JSONResponse({"error": f"unknown type '{topic_name}'"},
                            status_code=404)
    members = []
    for i in range(dtype.member_count):
        m = dtype.member(i)
        members.append({"name": m.name, "type": str(m.type.kind)})
    return {"topic": topic_name, "type_name": dtype.name, "members": members}


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
            _handle_ws_message(client_id, msg)
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
        for uid in msg.get("uids", []):
            _interest.client_subscribe(client_id, int(uid))
    elif action == "unsubscribe":
        for uid in msg.get("uids", []):
            _interest.client_unsubscribe(client_id, int(uid))


# ─── Callbacks ───────────────────────────────────────────────────────────────


def _on_dds_sample(topic_name: str, data: Any, info: Any) -> None:
    """Called by DdsGateway when a sample arrives. Route to interested clients."""
    # Extract uid from the sample (key field)
    try:
        uid = data["uid"]
    except Exception:
        return

    # SR-004: per-client demux
    for client_id, ws in list(_ws_clients.items()):
        if _interest and _interest.is_interested(client_id, uid):
            # Fire-and-forget push (async via event loop)
            payload = json.dumps({
                "topic": topic_name,
                "uid": uid,
                "data": _sample_to_dict(data),
            })
            asyncio.create_task(_ws_send(client_id, ws, payload))


async def _ws_send(client_id: str, ws: WebSocket, payload: str) -> None:
    try:
        await ws.send_text(payload)
    except Exception:
        # Client gone — will be cleaned up on next receive failure
        pass


def _on_interest_add(uid: int) -> None:
    """Interest 0→1: would send ValueRequest ADD to selector."""
    logger.info("selector_add uid=%d", uid)
    # TODO: write ValueRequest(uid, ADD) via a DDS DataWriter


def _on_interest_delete(uid: int) -> None:
    """Interest 1→0: would send ValueRequest DELETE to selector."""
    logger.info("selector_delete uid=%d", uid)
    # TODO: write ValueRequest(uid, DELETE) via a DDS DataWriter


def _sample_to_dict(data: Any) -> dict[str, Any]:
    """Convert a DynamicData sample to WIS-compatible JSON dict."""
    try:
        return sample_to_dict(data)
    except Exception:
        return {"raw": str(data)}
