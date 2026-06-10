"""
Única puerta de entrada al chatbot (Fase 2).

Entrada payload:
  - phone / wa_id: identificador del remitente (requerido)
  - message / body: texto del mensaje
  - from_number / from: número Twilio From (opcional)
  - profile_name: nombre WhatsApp (opcional)
  - timestamp: ISO8601 (opcional, passthrough)
  - business_id: str (opcional, reservado multi-negocio Fase 5+)
  - channel: str (opcional, ej. whatsapp)
  - metadata: dict (opcional, claves Twilio extra)

Salida:
  - response_text: str | list[str] — respuesta al usuario (vacío si bloqueado)
  - is_admin: bool
  - blocked: bool
  - wa_id: str
  - business_id: str | None
  - deliver_via_rest: bool — hint para capa API (TwiML vs REST)
  - media: None (reservado)
  - actions: list (reservado)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Union

from config.settings import use_rest_webhook_replies

from chatbot.business_context import business_scope, get_prompt
from chatbot.runtime import get_bot_context
from app.utils.client_message_log import schedule_client_message_log
from services import notification_service as notify_svc

logger = logging.getLogger(__name__)

Reply = Union[str, List[str]]


def _normalize_reply(reply: Reply) -> Reply:
    if not reply or (isinstance(reply, str) and not reply.strip()):
        return get_prompt("empty_body_hint")
    return reply


def _reply_to_response_text(reply: Reply) -> Union[str, List[str]]:
    if isinstance(reply, list):
        return [str(part).strip() for part in reply if part and str(part).strip()]
    return str(reply).strip()


def handle_incoming_message(payload: dict) -> dict:
    """
    Procesa un mensaje entrante con la misma lógica que POST /bot en app/app.py.
    No envía Twilio; solo devuelve la respuesta para la capa API/webhook.
    """
    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    wa_id = (
        payload.get("phone")
        or payload.get("wa_id")
        or metadata.get("WaId")
        or ""
    )
    from_number = (
        payload.get("from_number")
        or payload.get("from")
        or metadata.get("From")
        or ""
    )
    body = payload.get("message") or payload.get("body") or metadata.get("Body") or ""
    profile_name = (
        payload.get("profile_name")
        or metadata.get("ProfileName")
        or ""
    )
    business_id = payload.get("business_id") or None
    channel = payload.get("channel") or "whatsapp"
    timestamp = payload.get("timestamp") or datetime.now(timezone.utc).isoformat()

    ctx = get_bot_context()
    admin_service = ctx.admin_service
    flow_engine = ctx.flow_engine
    user_service = ctx.user_service
    blocked_cache = ctx.blocked_cache

    if not wa_id and from_number:
        wa_id = from_number.replace("whatsapp:", "").strip()

    if wa_id:
        canonical = admin_service.canonical_wa_id(wa_id, from_number)
        wa_id = canonical or wa_id

    if not wa_id:
        return {
            "response_text": get_prompt("missing_wa_id"),
            "is_admin": False,
            "blocked": False,
            "wa_id": "",
            "business_id": business_id,
            "channel": channel,
            "timestamp": timestamp,
            "deliver_via_rest": use_rest_webhook_replies(),
            "media": None,
            "actions": [],
        }

    is_admin = False
    blocked = False
    reply: Reply = ""

    try:
        with business_scope(business_id):
            sender_ids = [wa_id]
            if from_number and from_number != wa_id:
                sender_ids.append(from_number)
            if any(notify_svc.is_admin_sender(sender) for sender in sender_ids):
                is_admin = True
                reply = notify_svc.handle_admin_confirmation(
                    body,
                    business_id=business_id,
                )
            elif blocked_cache.is_blocked(wa_id):
                blocked = True
                schedule_client_message_log(
                    wa_id=wa_id,
                    client_message=(body or "").strip(),
                    bot_message="(usuario bloqueado — sin respuesta)",
                )
                reply = ""
            else:
                user_service.touch(wa_id=wa_id, name=profile_name)
                reply = flow_engine.process_message(wa_id=wa_id, body=body)
            reply = _normalize_reply(reply)
    except Exception:
        logger.exception("Gateway error processing message for wa_id=%s", wa_id)
        with business_scope(business_id):
            reply = get_prompt("error_generic")

    if not is_admin and not blocked and wa_id:
        schedule_client_message_log(
            wa_id=wa_id,
            client_message=(body or "").strip(),
            bot_message=reply,
        )

    return {
        "response_text": _reply_to_response_text(reply) if not blocked else "",
        "is_admin": is_admin,
        "blocked": blocked,
        "wa_id": wa_id,
        "business_id": business_id,
        "channel": channel,
        "timestamp": timestamp,
        "deliver_via_rest": use_rest_webhook_replies(),
        "media": None,
        "actions": [],
    }
