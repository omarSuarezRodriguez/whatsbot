"""
Twilio WhatsApp outbound + TwiML helpers (Fase 4).

Entrada: destino E.164/whatsapp, cuerpo texto.
Salida: bool entrega REST o XML TwiML para el webhook.
"""

from __future__ import annotations

import logging
from typing import Any, List, Union

import requests
from requests.auth import HTTPBasicAuth
from twilio.rest import Client

from twilio.twiml.messaging_response import MessagingResponse

from config.settings import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_WHATSAPP_FROM,
    is_twilio_whatsapp_sandbox,
)

logger = logging.getLogger(__name__)

Reply = Union[str, List[str]]


def reply_parts(reply: Reply) -> List[str]:
    if isinstance(reply, list):
        return [str(part).strip() for part in reply if part and str(part).strip()]
    if reply and str(reply).strip():
        return [str(reply).strip()]
    return []


def build_twiml_response(reply: Reply) -> str:
    """Build MessagingResponse XML for Twilio webhook."""
    response = MessagingResponse()
    for part in reply_parts(reply):
        response.message(part)
    return str(response)


def send_whatsapp_message(to_number: str, body: str) -> str | None:
    """
    Send via Twilio REST API.
    Returns MessageSid on success, None on failure.
    """
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_FROM):
        logger.info("Twilio outbound not configured; skip send to %s", to_number[:20])
        return None
    if is_twilio_whatsapp_sandbox():
        logger.warning(
            "TWILIO_WHATSAPP_FROM looks like sandbox; production should use Business number."
        )
    try:
        from chatbot.runtime import get_bot_context

        admin = get_bot_context(start_background=False).admin_service
        return admin._send_whatsapp(to_number, body)
    except Exception:
        logger.exception("send_whatsapp_message failed for %s", to_number)
        return None

def send_whatsapp_buttons(
    to_number: str,
    body: str,
    buttons: list[dict[str, Any]],
) -> str | None:
    """
    Crea un contenido interactivo dinámico en Twilio y lo envía.

    Returns MessageSid on success, None on failure.
    """
    if not (
        TWILIO_ACCOUNT_SID
        and TWILIO_AUTH_TOKEN
        and TWILIO_WHATSAPP_FROM
    ):
        logger.info(
            "Twilio outbound not configured; skip interactive send to %s",
            to_number[:20],
        )
        return None

    if not buttons:
        return None

    content = {
        "friendly_name": "whatsbot_dynamic_buttons",
        "language": "es",
        "types": {
            "twilio/quick-reply": {
                "body": body,
                "actions": buttons,
            }
        },
    }

    try:
        response = requests.post(
            "https://content.twilio.com/v1/Content",
            json=content,
            auth=HTTPBasicAuth(
                TWILIO_ACCOUNT_SID,
                TWILIO_AUTH_TOKEN,
            ),
            timeout=15,
        )

        response.raise_for_status()

        content_sid = response.json()["sid"]

        client = Client(
            TWILIO_ACCOUNT_SID,
            TWILIO_AUTH_TOKEN,
        )

        message = client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=to_number,
            content_sid=content_sid,
        )

        return message.sid

    except Exception:
        logger.exception(
            "send_whatsapp_buttons failed for %s",
            to_number,
        )
        return None


def deliver_reply(
    recipient: str,
    reply: Reply,
    *,
    use_rest: bool,
    actions: list[dict[str, Any]] | None = None,
) -> str:
    """
    Envía texto normal o botones interactivos.

    Si hay actions:
        crea contenido interactivo y lo envía por REST.

    Si no hay actions:
        mantiene el comportamiento anterior.
    """
    parts = reply_parts(reply)

    if not parts:
        return build_twiml_response("")

    actions = actions or []

    # --------------------------------------------------------
    # RESPUESTA INTERACTIVA
    # --------------------------------------------------------

    if actions:
        body = "\n".join(parts)

        message_sid = send_whatsapp_buttons(
            to_number=recipient,
            body=body,
            buttons=actions,
        )

        if message_sid:
            return build_twiml_response("")

        logger.warning(
            "Interactive delivery failed for %s; falling back to text",
            recipient,
        )

    # --------------------------------------------------------
    # RESPUESTA NORMAL
    # --------------------------------------------------------

    if use_rest:
        delivered = False

        for part in parts:
            if send_whatsapp_message(recipient, part):
                delivered = True

        if delivered:
            return build_twiml_response("")

        logger.warning(
            "REST delivery failed for %s; falling back to TwiML",
            recipient,
        )

    return build_twiml_response(reply)
