"""
Redis cache / pub-sub wrapper (OLA 4).

All operations are no-ops when REDIS_ENABLED=false or when the connection fails,
so the system degrades gracefully to in-process operation (single-worker).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from config.settings import REDIS_ENABLED, REDIS_URL

logger = logging.getLogger(__name__)

_redis_client = None
_redis_pubsub_client = None


def _is_enabled() -> bool:
    return bool(REDIS_ENABLED and REDIS_URL)


async def get_redis():
    """Return async Redis client (singleton). None if Redis disabled or unavailable."""
    global _redis_client
    if not _is_enabled():
        return None
    if _redis_client is None:
        try:
            import redis.asyncio as aioredis

            _redis_client = aioredis.from_url(
                REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            await _redis_client.ping()
            logger.info("Redis connected: %s", REDIS_URL.split("@")[-1][:40])
        except Exception:
            logger.warning("Redis unavailable — running in single-worker mode", exc_info=True)
            _redis_client = None
    return _redis_client


async def publish_event(channel: str, event: dict[str, Any]) -> bool:
    """Publish JSON event to Redis channel.  Returns False if Redis unavailable."""
    r = await get_redis()
    if r is None:
        return False
    try:
        await r.publish(channel, json.dumps(event, default=str))
        return True
    except Exception:
        logger.debug("Redis publish failed channel=%s", channel, exc_info=True)
        return False


async def ws_channel(business_id: str) -> str:
    return f"ws:{business_id}"


async def subscribe_ws_events(
    business_id: str,
) -> "AsyncIterator[dict[str, Any]] | None":
    """Subscribe to WS events for a business. Yields event dicts. Returns None if no Redis."""
    r = await get_redis()
    if r is None:
        return None
    channel = await ws_channel(business_id)
    pubsub = r.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message and message.get("type") == "message":
                try:
                    yield json.loads(message["data"])
                except (json.JSONDecodeError, TypeError):
                    continue
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
        except Exception:
            pass
