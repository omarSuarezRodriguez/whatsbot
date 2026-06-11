"""
Realtime hub — Fase 11.2.

Distribuye eventos WebSocket por business_id (dueño conectado en Flutter).
Entrada: hooks en api/routes tras persistir en BD.
Salida: JSON a todos los sockets del negocio (multidispositivo).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket
from sqlalchemy.orm import Session

from config.settings import REALTIME_ENABLED, WS_HEARTBEAT_SECONDS
from models.conversation import Conversation
from models.message import Message

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def serialize_message(msg: Message) -> dict[str, Any]:
    return {
        "id": msg.id,
        "conversation_id": msg.conversation_id,
        "direction": msg.direction,
        "body": msg.body,
        "wa_id": msg.wa_id,
        "is_admin": msg.is_admin,
        "channel": msg.channel,
        "status": msg.status,
        "delivered_at": _iso(msg.delivered_at),
        "read_at": _iso(msg.read_at),
        "created_at": _iso(msg.created_at),
        "client_id": msg.client_id,
        "twilio_sid": msg.twilio_sid,
    }


def serialize_conversation(conv: Conversation) -> dict[str, Any]:
    return {
        "id": conv.id,
        "business_id": conv.business_id,
        "customer_wa_id": conv.customer_wa_id,
        "customer_name": conv.customer_name,
        "last_message_preview": conv.last_message_preview,
        "last_message_at": _iso(conv.last_message_at),
        "updated_at": _iso(conv.updated_at),
    }


def build_message_new_event(msg: Message, conv: Conversation) -> dict[str, Any]:
    return {
        "type": "message.new",
        "message": serialize_message(msg),
        "conversation": serialize_conversation(conv),
    }


def build_conversation_updated_event(conv: Conversation) -> dict[str, Any]:
    return {
        "type": "conversation.updated",
        "conversation": serialize_conversation(conv),
    }


def build_message_status_event(msg: Message) -> dict[str, Any]:
    return {
        "type": "message.status",
        "message_id": msg.id,
        "conversation_id": msg.conversation_id,
        "status": msg.status,
        "delivered_at": _iso(msg.delivered_at),
        "read_at": _iso(msg.read_at),
    }


def serialize_order(order: Any) -> dict[str, Any]:
    return {
        "id": order.id,
        "business_id": order.business_id,
        "order_id": order.order_id,
        "wa_id": order.wa_id,
        "items": order.items,
        "total": float(order.total or 0),
        "status": order.status,
        "customer_name": order.customer_name,
        "address": order.address,
        "delivery_type": order.delivery_type,
        "created_at": _iso(order.created_at),
    }


def build_order_pending_event(order: Any) -> dict[str, Any]:
    return {"type": "order.pending", "order": serialize_order(order)}


def build_order_updated_event(order: Any) -> dict[str, Any]:
    return {
        "type": "order.updated",
        "order": serialize_order(order),
        "status": order.status,
    }


class RealtimeHub:
    """In-memory WebSocket hub keyed by business_id.

    When Redis is enabled, events are also published to Redis pub/sub so that
    multiple API workers behind a load balancer can fan out to their local sockets.
    """

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    def is_enabled(self) -> bool:
        return REALTIME_ENABLED

    async def connect(self, business_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(business_id, set()).add(websocket)
        logger.info(
            "WS connected business=%s (active=%d)",
            business_id,
            self.connection_count(business_id),
        )
        await self._send_json(
            websocket,
            {
                "type": "connected",
                "business_id": business_id,
                "at": _iso(_utcnow()),
            },
        )

    async def disconnect(self, business_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(business_id)
            if sockets and websocket in sockets:
                sockets.discard(websocket)
                if not sockets:
                    self._connections.pop(business_id, None)
        logger.info(
            "WS disconnected business=%s (active=%d)",
            business_id,
            self.connection_count(business_id),
        )

    def has_active_connection(self, business_id: str) -> bool:
        return bool(self._connections.get(business_id))

    def connection_count(self, business_id: str) -> int:
        return len(self._connections.get(business_id, set()))

    async def broadcast_to_business(
        self,
        business_id: str,
        event: dict[str, Any],
        *,
        exclude: WebSocket | None = None,
    ) -> int:
        """Broadcast to all sockets except optional exclude (typing relay)."""
        if not REALTIME_ENABLED:
            return 0
        async with self._lock:
            sockets = [
                ws
                for ws in self._connections.get(business_id, set())
                if ws is not exclude
            ]
        if not sockets:
            return 0
        payload = json.dumps(event, default=str)
        delivered = 0
        dead: list[tuple[str, WebSocket]] = []
        for ws in sockets:
            try:
                await ws.send_text(payload)
                delivered += 1
            except Exception:
                dead.append((business_id, ws))
        for bid, ws in dead:
            await self.disconnect(bid, ws)
        return delivered

    async def emit(self, business_id: str, event: dict[str, Any]) -> int:
        """Broadcast event to local sockets and publish to Redis (if enabled)."""
        if not REALTIME_ENABLED:
            return 0

        # Publish to Redis so all workers receive the event
        try:
            from infrastructure.cache import publish_event, ws_channel
            channel = await ws_channel(business_id)
            await publish_event(channel, event)
        except Exception:
            pass  # Redis optional; continue with local delivery

        return await self._emit_local(business_id, event)

    async def _emit_local(self, business_id: str, event: dict[str, Any]) -> int:
        """Deliver event to this worker's local WebSocket connections."""
        async with self._lock:
            sockets = list(self._connections.get(business_id, set()))
        if not sockets:
            return 0

        payload = json.dumps(event, default=str)
        delivered = 0
        dead: list[tuple[str, WebSocket]] = []
        for ws in sockets:
            try:
                await ws.send_text(payload)
                delivered += 1
            except Exception:
                logger.debug("WS send failed business=%s", business_id, exc_info=True)
                dead.append((business_id, ws))
        for bid, ws in dead:
            await self.disconnect(bid, ws)
        return delivered

    def schedule_emit(self, business_id: str, event: dict[str, Any]) -> None:
        """Schedule emit from sync route handlers."""
        if not REALTIME_ENABLED:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("No event loop for realtime emit business=%s", business_id)
            return
        loop.create_task(self.emit(business_id, event))

    async def _send_json(self, websocket: WebSocket, data: dict[str, Any]) -> None:
        await websocket.send_text(json.dumps(data, default=str))

    async def handle_client_message(
        self,
        business_id: str,
        websocket: WebSocket,
        raw: str,
    ) -> None:
        """Handle ping/pong from Flutter."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return
        if not isinstance(data, dict):
            return
        msg_type = data.get("type")
        if msg_type == "ping":
            await self._send_json(
                websocket,
                {"type": "pong", "at": _iso(_utcnow())},
            )
        elif msg_type == "pong":
            pass
        elif msg_type in {"typing.start", "typing.stop"}:
            conversation_id = data.get("conversation_id")
            if conversation_id is None:
                return
            await self.broadcast_to_business(
                business_id,
                {
                    "type": msg_type,
                    "conversation_id": conversation_id,
                    "business_id": business_id,
                    "at": _iso(_utcnow()),
                },
                exclude=websocket,
            )


realtime_hub = RealtimeHub()


def _load_conversation(db: Session, msg: Message) -> Conversation | None:
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == msg.conversation_id)
        .one_or_none()
    )
    return conv


async def emit_message_saved(
    db: Session,
    business_id: str,
    msg: Message,
) -> int:
    """Emit message.new + conversation.updated after DB commit."""
    from services import conversation_service as conv_svc
    from services.push_service import maybe_push_incoming_message

    conv = _load_conversation(db, msg)
    if conv is None:
        return 0
    if msg.direction == "outgoing" and msg.status == "sent":
        conv_svc.mark_outgoing_delivered(db, msg)
    event = build_message_new_event(msg, conv)
    count = await realtime_hub.emit(business_id, event)
    await realtime_hub.emit(business_id, build_conversation_updated_event(conv))
    if msg.direction == "outgoing" and msg.status == "delivered":
        await realtime_hub.emit(business_id, build_message_status_event(msg))
    await maybe_push_incoming_message(
        db,
        business_id,
        msg,
        conv,
        ws_delivered=count,
    )
    return count


async def emit_message_status(
    db: Session,
    business_id: str,
    msg: Message,
) -> None:
    await realtime_hub.emit(business_id, build_message_status_event(msg))


async def emit_order_pending(business_id: str, order: Any) -> None:
    await realtime_hub.emit(business_id, build_order_pending_event(order))


async def emit_order_updated(business_id: str, order: Any) -> None:
    await realtime_hub.emit(business_id, build_order_updated_event(order))


def schedule_order_pending(business_id: str, order: Any) -> None:
    realtime_hub.schedule_emit(business_id, build_order_pending_event(order))


def schedule_order_updated(business_id: str, order: Any) -> None:
    realtime_hub.schedule_emit(business_id, build_order_updated_event(order))


def schedule_message_status(business_id: str, msg: Message) -> None:
    realtime_hub.schedule_emit(business_id, build_message_status_event(msg))


def schedule_message_saved(
    db: Session,
    business_id: str,
    msg: Message,
) -> None:
    """Sync wrapper for REST handlers."""
    conv = _load_conversation(db, msg)
    if conv is None:
        return
    realtime_hub.schedule_emit(business_id, build_message_new_event(msg, conv))
    realtime_hub.schedule_emit(business_id, build_conversation_updated_event(conv))


async def run_heartbeat(websocket: WebSocket, business_id: str) -> None:
    """Server-side ping while connection is open."""
    try:
        while True:
            await asyncio.sleep(WS_HEARTBEAT_SECONDS)
            await realtime_hub._send_json(
                websocket,
                {"type": "ping", "at": _iso(_utcnow())},
            )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.debug("WS heartbeat ended business=%s", business_id, exc_info=True)
