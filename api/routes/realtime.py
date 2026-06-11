"""
WebSocket realtime — Fase 11.2.

Ruta: WS /whatsbot/ws?token=<JWT>
Auth: mismo JWT que REST (claim business_id).
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from api.middleware.auth import decode_access_token
from config.settings import REALTIME_ENABLED
from services.realtime_service import realtime_hub, run_heartbeat

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsbot", tags=["realtime"])


@router.websocket("/ws")
async def whatsbot_websocket(
    websocket: WebSocket,
    token: str = Query(default=""),
) -> None:
    if not REALTIME_ENABLED:
        await websocket.close(code=4403, reason="Realtime disabled")
        return

    token = (token or "").strip()
    if not token:
        await websocket.close(code=4401, reason="Token required")
        return

    try:
        payload = decode_access_token(token)
    except Exception:
        await websocket.close(code=4401, reason="Invalid token")
        return

    business_id = str(payload.get("business_id", "")).strip()
    if not business_id:
        await websocket.close(code=4401, reason="Token without business_id")
        return

    await realtime_hub.connect(business_id, websocket)
    heartbeat = asyncio.create_task(run_heartbeat(websocket, business_id))

    # Subscribe to Redis pub/sub for this business (delivers events from other workers)
    redis_task = asyncio.create_task(
        _redis_subscriber(business_id, websocket)
    )

    try:
        while True:
            raw = await websocket.receive_text()
            await realtime_hub.handle_client_message(business_id, websocket, raw)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("WS error business=%s", business_id, exc_info=True)
    finally:
        heartbeat.cancel()
        redis_task.cancel()
        for task in (heartbeat, redis_task):
            try:
                await task
            except asyncio.CancelledError:
                pass
        await realtime_hub.disconnect(business_id, websocket)


async def _redis_subscriber(business_id: str, websocket: WebSocket) -> None:
    """Receive events published by other workers and deliver to local socket."""
    try:
        from infrastructure.cache import subscribe_ws_events

        gen = subscribe_ws_events(business_id)
        if gen is None:
            return  # Redis disabled
        import json

        async for event in gen:
            try:
                await websocket.send_text(json.dumps(event, default=str))
            except Exception:
                break
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.debug("Redis subscriber error business=%s", business_id, exc_info=True)
