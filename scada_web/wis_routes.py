"""RTI Web Integration Service compatible HTTP + WebSocket routes.

Mounts the WIS surface onto the scada_web FastAPI app so a browser client
written against WIS 7.7 works unchanged:

    POST /dds/v1/websocket_connections
    GET  /dds/rest1/applications/{a}/domain_participants/{dp}
              /subscribers/{s}/data_readers/{dr}
    POST /dds/rest1/applications/{a}/domain_participants/{dp}
              /publishers/{p}/data_writers/{dw}
    WS   /dds/websocket/{connection}

The wire contract lives in wis.py; this module is the HTTP/DDS plumbing around
it. The native /api/v1 + /ws surface in server.py is unaffected — both run side
by side on the same port.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import APIRouter, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from . import wis
from .config import ScadaWebConfig
from .gateway import DdsGateway
from .mapping import sample_to_dict
from .wis import WisError, WisRegistry, WisResource

logger = logging.getLogger(__name__)


@dataclass
class WisConnection:
    """One live WIS WebSocket client.

    `selected` is the uid set this client asked for with ValueRequest ADD. It
    gates delivery: binding a reader alone streams nothing. With no selector
    deployed, scada_web applies the selection itself — relaying every tag on the
    field domain would swamp a client that only asked for a handful.
    """
    connection_id: str
    name: str
    ws: WebSocket
    handshaked: bool = False
    binds: dict[str, WisResource] = field(default_factory=dict)
    selected: set[int] = field(default_factory=set)

    def reader_binds_for(self, topic: str) -> list[str]:
        return [bind_id for bind_id, res in self.binds.items()
                if res.kind == "reader" and res.topic == topic]

    def reader_topics(self) -> list[str]:
        return sorted({res.topic for res in self.binds.values()
                       if res.kind == "reader"})


class WisHub:
    """Tracks WIS WebSocket connections and fans samples out to their binds."""

    def __init__(self) -> None:
        self._connections: dict[str, WisConnection] = {}
        self._reserved: set[str] = set()
        self._next_id = 0

    # --- connection resources (POST /dds/v1/websocket_connections) ---

    def reserve(self, name: str) -> None:
        self._reserved.add(name)

    def is_reserved(self, name: str) -> bool:
        return name in self._reserved

    # --- live connections ---

    def add(self, name: str, ws: WebSocket) -> WisConnection:
        self._next_id += 1
        connection_id = f"{name}#{self._next_id}"
        conn = WisConnection(connection_id=connection_id, name=name, ws=ws)
        self._connections[connection_id] = conn
        return conn

    def remove(self, conn: WisConnection) -> None:
        self._connections.pop(conn.connection_id, None)

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    def wants(self, topic: str, uid: Any) -> bool:
        """Whether any client has this topic bound AND this uid selected.

        Checked before building an envelope: the field domain carries every tag
        at full publish rate, so serializing samples nobody asked for is pure
        waste.
        """
        return any(conn.handshaked and uid in conn.selected
                   and conn.reader_binds_for(topic)
                   for conn in self._connections.values())

    def push(self, topic: str, uid: Any, envelope: dict[str, Any]) -> None:
        """Deliver one sample to every bind that selected this uid."""
        for conn in list(self._connections.values()):
            if not conn.handshaked or uid not in conn.selected:
                continue
            for bind_id in conn.reader_binds_for(topic):
                frame = json.dumps(wis.b_push_frame(bind_id, [envelope]))
                asyncio.create_task(self._send(conn, frame))

    async def _send(self, conn: WisConnection, frame: str) -> None:
        try:
            await conn.ws.send_text(frame)
        except Exception:
            # Client vanished mid-push; the receive loop performs the cleanup.
            pass


def create_wis_router(config: ScadaWebConfig, gateway: DdsGateway,
                      registry: WisRegistry) -> tuple[APIRouter, WisHub]:
    """Build the WIS-compatible router and the hub that feeds its clients."""
    router = APIRouter()
    hub = WisHub()

    def _error(err: WisError) -> JSONResponse:
        return JSONResponse(err.body(), status_code=err.http_status)

    def _envelopes(samples: list[tuple[Any, Any]]) -> list[dict[str, Any]]:
        return [wis.sample_envelope(sample_to_dict(data), info)
                for data, info in samples]

    # ─── Connection resource ─────────────────────────────────────────────

    @router.post("/dds/v1/websocket_connections")
    async def create_websocket_connection(request: Request):
        """Reserve a WebSocket connection name.

        Accepts both the object form {"name": x} and the legacy array form
        [{"name": x}] that older RTI examples send. Re-reserving an existing
        name succeeds: browser clients re-POST on every reconnect.
        """
        try:
            payload = await request.json()
        except Exception:
            return _error(WisError(wis.INVALID_INPUT, "body must be JSON"))

        if isinstance(payload, list):
            payload = payload[0] if payload else {}
        if not isinstance(payload, dict) or not payload.get("name"):
            return _error(WisError(wis.INVALID_INPUT,
                                   "body must contain a 'name'"))

        name = str(payload["name"])
        hub.reserve(name)
        logger.info("wis_connection_reserved name=%s", name)
        return Response(status_code=204)

    # ─── Data operations ─────────────────────────────────────────────────

    @router.get("/dds/rest1/applications/{application}/domain_participants"
                "/{participant}/subscribers/{subscriber}/data_readers"
                "/{data_reader}")
    async def read_data_reader(
        application: str,
        participant: str,
        subscriber: str,
        data_reader: str,
        sampleFormat: str = "json",
        removeFromReaderCache: bool = True,
        # Optional[...] not `int | None`: FastAPI evaluates route annotations and
        # rti.connextdds pins this project to Python 3.8, which has no PEP 604.
        maxSamples: Optional[int] = None,
        prettyPrint: bool = False,
    ):
        """Read or take samples — WIS GET on a data_reader resource."""
        uri = wis.reader_uri(application, participant, subscriber, data_reader)
        try:
            if sampleFormat.lower() != "json":
                raise WisError(wis.INVALID_INPUT,
                               "only sampleFormat=json is supported")
            if maxSamples is not None and maxSamples < 0:
                raise WisError(wis.INVALID_INPUT, "maxSamples must be >= 0")
            resource = registry.resolve(uri, kind="reader")
            if removeFromReaderCache:
                samples = gateway.take_samples(resource.topic, maxSamples)
            else:
                samples = gateway.snapshot(resource.topic)
                if maxSamples is not None:
                    samples = samples[:maxSamples]
        except WisError as err:
            return _error(err)
        except Exception:
            logger.exception("wis_read_failed uri=%s", uri)
            return _error(WisError(wis.GENERIC_SERVICE_ERROR,
                                   "read failed", http_status=500))

        body = _envelopes(samples)
        if prettyPrint:
            return Response(json.dumps(body, indent=2),
                            media_type=wis.CONTENT_TYPE)
        return JSONResponse(body)

    @router.post("/dds/rest1/applications/{application}/domain_participants"
                 "/{participant}/publishers/{publisher}/data_writers"
                 "/{data_writer}")
    async def write_data_writer(
        application: str,
        participant: str,
        publisher: str,
        data_writer: str,
        request: Request,
    ):
        """Write a sample — WIS POST to a data_writer resource."""
        uri = wis.writer_uri(application, participant, publisher, data_writer)
        try:
            payload = await request.json()
        except Exception:
            return _error(WisError(wis.INVALID_INPUT, "body must be JSON"))
        try:
            _write(uri, payload)
        except WisError as err:
            return _error(err)
        return Response(status_code=204)

    def _write(uri: str, payload: Any) -> wis.ValueRequestIntent:
        """Resolve a writer URI, write the translated sample(s), return intent.

        The sample still goes out on DDS even though nothing consumes it yet —
        that back-channel is what scada_select will read. The returned intent is
        what scada_web acts on in the meantime.
        """
        resource = registry.resolve(uri, kind="writer")
        intent, samples = wis.translate_value_request(payload)
        for sample in samples:
            try:
                gateway.write_json(resource.topic, sample)
            except WisError:
                raise
            except Exception as exc:
                logger.exception("wis_write_failed topic=%s", resource.topic)
                raise WisError(wis.GENERIC_SERVICE_ERROR,
                               f"write failed: {exc}",
                               http_status=500) from exc
        logger.info("wis_write topic=%s samples=%d command=%s uid=%s",
                    resource.topic, len(samples), intent.command, intent.uid)
        return intent

    async def _apply_selection(conn: WisConnection,
                               intent: wis.ValueRequestIntent) -> None:
        """Update this client's uid selection and seed it from the reader cache.

        Standing in for scada_select: ADD starts delivery for a uid, DELETE stops
        it. On ADD the uid's currently cached sample is pushed on each bound
        reader, so the row appears immediately with its name and limits instead
        of waiting up to a full publish period — tags in this sim publish as
        slowly as every 10 s.
        """
        uid = intent.uid
        if intent.command == "DELETE" and uid is not None:
            conn.selected.discard(uid)
            logger.info("wis_deselected connection=%s uid=%d",
                        conn.connection_id, uid)
            return
        if intent.command not in ("ADD", "METADATA") or uid is None:
            return

        if intent.command == "ADD":
            conn.selected.add(uid)
            logger.info("wis_selected connection=%s uid=%d selected=%d",
                        conn.connection_id, uid, len(conn.selected))

        for topic in conn.reader_topics():
            try:
                cached = gateway.read_sample(topic, uid)
            except Exception:
                logger.exception("wis_seed_failed topic=%s uid=%s", topic, uid)
                continue
            if cached is None:
                continue
            data, info = cached
            envelope = wis.sample_envelope(sample_to_dict(data), info)
            for bind_id in conn.reader_binds_for(topic):
                await conn.ws.send_text(
                    json.dumps(wis.b_push_frame(bind_id, [envelope])))
                logger.info("wis_seeded connection=%s bind_id=%s uid=%d",
                            conn.connection_id, bind_id, uid)

    # ─── WebSocket ───────────────────────────────────────────────────────

    @router.websocket("/dds/websocket/{connection}")
    async def wis_websocket(ws: WebSocket, connection: str):
        await ws.accept()

        if (config.wis.strict_websocket_connections
                and not hub.is_reserved(connection)):
            await ws.send_text(wis.hello_failure(
                f"unknown websocket connection '{connection}' — "
                "POST /dds/v1/websocket_connections first"))
            await ws.close()
            logger.warning("wis_ws_rejected connection=%s reason=unreserved",
                           connection)
            return

        conn = hub.add(connection, ws)
        logger.info("wis_ws_connected connection=%s", conn.connection_id)

        try:
            # First frame must be the HELLO header block.
            try:
                hello = wis.parse_hello(await ws.receive_text())
            except WisError as err:
                await ws.send_text(wis.hello_failure(err.message))
                await ws.close()
                logger.warning("wis_hello_failed connection=%s reason=%s",
                               conn.connection_id, err.message)
                return

            conn.handshaked = True
            await ws.send_text(wis.HELLO_OK)
            logger.info("wis_hello_ok connection=%s version=%s",
                        conn.connection_id, hello.get("Version"))

            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except Exception:
                    await _send_error(ws, "response", WisError(
                        wis.INVALID_INPUT, "frame is not valid JSON"))
                    continue
                await _dispatch(conn, msg)

        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("wis_ws_error connection=%s", conn.connection_id)
        finally:
            hub.remove(conn)
            logger.info("wis_ws_disconnected connection=%s", conn.connection_id)

    async def _send_error(ws: WebSocket, kind: str, err: WisError, *,
                          request_id: str | None = None,
                          bind_id: str | None = None) -> None:
        frame = wis.error_frame(kind, err, request_id=request_id,
                                bind_id=bind_id)
        try:
            await ws.send_text(json.dumps(frame))
        except Exception:
            pass

    async def _dispatch(conn: WisConnection, msg: dict[str, Any]) -> None:
        kind = msg.get("kind") or msg.get("Kind")
        if kind == "bind":
            await _handle_bind(conn, msg)
        elif kind == "request":
            await _handle_request(conn, msg)
        elif kind == "b_req":
            await _send_error(conn.ws, "response", WisError(
                wis.INVALID_INPUT,
                "b_req streaming writes are not supported — send a "
                "'request' frame with method POST to the writer URI"),
                request_id=msg.get("id"))
        else:
            await _send_error(conn.ws, "response", WisError(
                wis.INVALID_INPUT, f"unsupported frame kind: {kind!r}"),
                request_id=msg.get("id"))

    async def _handle_bind(conn: WisConnection, msg: dict[str, Any]) -> None:
        """Associate client-chosen bind_ids with reader resources.

        Bind replies only on error, matching WIS. Binding alone delivers
        nothing: samples flow only for uids the client selects with a
        ValueRequest ADD (see _apply_selection).
        """
        entries = msg.get("body") or []
        if isinstance(entries, dict):
            entries = [entries]

        for entry in entries:
            if not isinstance(entry, dict):
                await _send_error(conn.ws, "bind_response", WisError(
                    wis.INVALID_INPUT, "each bind entry must be an object"))
                continue

            bind_id = entry.get("bind_id")
            bind_kind = entry.get("bind_kind")
            uri = entry.get("uri", "")

            if not bind_id:
                await _send_error(conn.ws, "bind_response", WisError(
                    wis.INVALID_INPUT, "bind_id is required"))
                continue
            if bind_kind == "bind_datawriter":
                await _send_error(conn.ws, "bind_response", WisError(
                    wis.INVALID_INPUT,
                    "bind_datawriter is not supported — send a 'request' "
                    "frame with method POST to the writer URI"),
                    bind_id=bind_id)
                continue
            if bind_kind != "bind_datareader":
                await _send_error(conn.ws, "bind_response", WisError(
                    wis.INVALID_INPUT,
                    f"unsupported bind_kind: {bind_kind!r}"), bind_id=bind_id)
                continue

            try:
                resource = registry.resolve(uri, kind="reader")
            except WisError as err:
                await _send_error(conn.ws, "bind_response", err,
                                  bind_id=bind_id)
                continue

            conn.binds[bind_id] = resource
            logger.info("wis_bound connection=%s bind_id=%s topic=%s",
                        conn.connection_id, bind_id, resource.topic)

    async def _handle_request(conn: WisConnection, msg: dict[str, Any]) -> None:
        """REST semantics tunneled over the socket, correlated by client id.

        A successful POST stays silent, matching observed WIS behavior (writes
        reply only on error). A GET must return data, so it always replies.
        """
        request_id = msg.get("id")
        method = str(msg.get("method", "")).upper()
        uri = msg.get("uri", "")

        try:
            if method == "POST":
                await _apply_selection(conn, _write(uri, msg.get("body")))
                return
            if method == "GET":
                resource = registry.resolve(uri, kind="reader")
                envelopes = _envelopes(gateway.snapshot(resource.topic))
                await conn.ws.send_text(json.dumps({
                    "kind": "response",
                    "id": request_id,
                    "return_code": "OK",
                    "body": {"read_sample_seq": envelopes},
                }))
                return
            raise WisError(wis.INVALID_INPUT,
                           f"unsupported method: {method or '(none)'}")
        except WisError as err:
            await _send_error(conn.ws, "response", err, request_id=request_id)

    return router, hub
