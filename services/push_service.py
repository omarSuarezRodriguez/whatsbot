"""
Firebase Cloud Messaging — Fase 11.4.

Envía push cuando hay mensaje entrante y el dueño no tiene WebSocket activo.
Credenciales solo en servidor (.env); nunca en la app Flutter.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from config.settings import (
    FCM_ENABLED,
    FCM_SERVICE_ACCOUNT_JSON,
    FCM_SERVICE_ACCOUNT_JSON_PATH,
)
from models.conversation import Conversation
from models.message import Message
from services import device_token_service as token_svc

logger = logging.getLogger(__name__)

_firebase_ready = False
_init_attempted = False


def is_push_enabled() -> bool:
    return FCM_ENABLED


def _init_firebase() -> bool:
    global _firebase_ready, _init_attempted
    if _firebase_ready:
        return True
    if _init_attempted or not FCM_ENABLED:
        return False
    _init_attempted = True

    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError:
        logger.warning("firebase-admin not installed; push disabled")
        return False

    if firebase_admin._apps:
        _firebase_ready = True
        return True

    cred = None
    inline = (FCM_SERVICE_ACCOUNT_JSON or "").strip()
    if inline:
        try:
            cred = credentials.Certificate(json.loads(inline))
        except json.JSONDecodeError:
            logger.exception("FCM_SERVICE_ACCOUNT_JSON is not valid JSON")
            return False
    else:
        path = (FCM_SERVICE_ACCOUNT_JSON_PATH or "").strip()
        if not path:
            logger.warning("FCM enabled but no service account configured")
            return False
        try:
            cred = credentials.Certificate(path)
        except Exception:
            logger.exception("Failed to load FCM service account from %s", path)
            return False

    try:
        firebase_admin.initialize_app(cred)
        _firebase_ready = True
        logger.info("Firebase Admin SDK initialized for push")
    except Exception:
        logger.exception("Firebase Admin SDK init failed")
    return _firebase_ready


def _display_name(conv: Conversation) -> str:
    if conv.customer_name and conv.customer_name.strip():
        return conv.customer_name.strip()
    return conv.customer_wa_id


def _preview(body: str, max_len: int = 120) -> str:
    text = (body or "").strip()
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


async def maybe_push_incoming_message(
    db: Session,
    business_id: str,
    msg: Message,
    conv: Conversation,
    *,
    ws_delivered: int,
) -> int:
    """
  Push to registered devices when no active WebSocket received the event.
  Only for incoming client messages (not admin / outgoing).
  """
    if not FCM_ENABLED or ws_delivered > 0:
        return 0
    if msg.direction != "incoming" or msg.is_admin:
        return 0
    if not _init_firebase():
        return 0

    tokens = token_svc.list_device_tokens(db, business_id)
    if not tokens:
        return 0

    try:
        from firebase_admin import messaging
    except ImportError:
        return 0

    title = _display_name(conv)
    body = _preview(msg.body)
    data = {
        "type": "message.new",
        "conversation_id": str(conv.id),
        "message_id": str(msg.id),
        "preview": body,
        "business_id": business_id,
    }

    sent = 0
    dead_tokens: list[str] = []
    for row in tokens:
        message = messaging.Message(
            token=row.token,
            notification=messaging.Notification(title=title, body=body),
            data=data,
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    channel_id="whatsbot_messages",
                    sound="default",
                ),
            ),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        sound="default",
                        badge=1,
                    ),
                ),
            ),
        )
        try:
            messaging.send(message)
            sent += 1
        except Exception as exc:
            err = str(exc).lower()
            if "not-found" in err or "registration-token-not-registered" in err:
                dead_tokens.append(row.token)
            logger.debug("FCM send failed token=%s...", row.token[:12], exc_info=True)

    for token in dead_tokens:
        token_svc.delete_device_token(db, business_id=business_id, token=token)
    if dead_tokens:
        db.commit()

    if sent:
        logger.info(
            "FCM push sent business=%s conv=%s devices=%d",
            business_id,
            conv.id,
            sent,
        )
    return sent


def build_push_payload_for_test(
    msg: Message,
    conv: Conversation,
    *,
    business_id: str,
) -> dict[str, Any]:
    """Helper for tests — same data dict as production push."""
    return {
        "type": "message.new",
        "conversation_id": str(conv.id),
        "message_id": str(msg.id),
        "preview": _preview(msg.body),
        "business_id": business_id,
        "title": _display_name(conv),
    }
