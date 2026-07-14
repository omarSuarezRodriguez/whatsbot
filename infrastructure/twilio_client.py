"""
Twilio WhatsApp outbound + TwiML helpers (Fase 4).

Entrada: destino E.164/whatsapp, cuerpo texto.
Salida: bool entrega REST o XML TwiML para el webhook.
"""

from __future__ import annotations

import logging
import time
import uuid
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


def _whatsapp_address(number: str) -> str:
    digits = "".join(ch for ch in (number or "") if ch.isdigit())
    if not digits:
        return (number or "").strip()
    return f"whatsapp:+{digits}"


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


def _message_delivery_ok(client: Client, message_sid: str) -> bool:
    """
    Content/create often returns queued SID that later fails (e.g. 63007).
    Brief poll so webhook can fall back to plain TwiML text.
    """
    # ponytail: ~3s poll budget. ceiling: slower failures need status callback.
    for _ in range(8):
        message = client.messages(message_sid).fetch()
        status = (getattr(message, "status", "") or "").lower()
        error_code = getattr(message, "error_code", None)
        from_addr = getattr(message, "from_", None) or ""
        if error_code or status in {"failed", "undelivered", "canceled"}:
            logger.warning(
                "Interactive message %s not delivered (status=%s code=%s from=%s)",
                message_sid,
                status,
                error_code,
                from_addr,
            )
            return False
        # Twilio sometimes parks Content on a phantom +1555 sender before failing.
        if "+1555" in str(from_addr):
            logger.warning(
                "Interactive message %s using invalid From %s — treating as fail",
                message_sid,
                from_addr,
            )
            return False
        if status in {"sent", "delivered", "read"}:
            return True
        time.sleep(0.4)
    return True


def _send_content(
    to_number: str,
    content: dict,
) -> str | None:
    """
    Envía cualquier contenido de Twilio Content API
    (botones, listas, etc.)
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

        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        to_addr = _whatsapp_address(to_number)
        from_addr = _whatsapp_address(TWILIO_WHATSAPP_FROM)

        # Pin From to the ONLINE WhatsApp Business sender. Do not rely on
        # Messaging Service alone for Content — it can remap to a dead +1555 channel (63007).
        message = client.messages.create(
            from_=from_addr,
            to=to_addr,
            content_sid=content_sid,
        )
        if not message.sid or not _message_delivery_ok(client, message.sid):
            return None
        return message.sid

    except Exception:
        logger.exception(
            "Interactive content send failed for %s",
            to_number,
        )
        return None


def send_whatsapp_buttons(
    to_number: str,
    body: str,
    buttons: list[dict[str, Any]],
) -> str | None:
    """
    Envía botones interactivos usando Twilio Content API.

    Returns MessageSid on success, None on failure.
    """
    if not buttons:
        return None

    # In-session WhatsApp: max 3 quick replies; title max 20 chars.
    safe_actions = [
        {
            "title": str(b.get("title", ""))[:20],
            "id": str(b.get("id", "")),
        }
        for b in buttons
        if b.get("id") is not None
    ][:3]
    if not safe_actions:
        return None

    content = {
        "friendly_name": f"wb_btn_{uuid.uuid4().hex[:12]}",
        "language": "es",
        "types": {
            "twilio/quick-reply": {
                "body": (body or "")[:1024],
                "actions": safe_actions,
            }
        },
    }

    return _send_content(
        to_number=to_number,
        content=content,
    )


def build_list_content(
    *,
    friendly_name: str,
    body: str,
    button: str,
    rows: list[dict[str, Any]],
) -> dict:

    items = []

    for row in rows:

        items.append({
            "id": row["id"],
            "item": row["title"],
            "description": row["description"],
        })

    return {
        "friendly_name": friendly_name,
        "language": "es",
        "types": {
            "twilio/list-picker": {
                "body": body,
                "button": button,
                "items": items,
            }
        },
    }


def send_whatsapp_list(
    to_number: str,
    body: str,
    rows: list[dict[str, Any]],
) -> str | None:
    """
    Envía una lista interactiva (WhatsApp List Picker)
    usando Twilio Content API.
    """

    content = build_list_content(
        friendly_name=f"wb_list_{uuid.uuid4().hex[:12]}",
        body=(body or "")[:1024],
        button="Elegir",
        rows=rows,
    )

    return _send_content(
        to_number=to_number,
        content=content,
    )


_LIST_PAGE_SIZE = 10
_LIST_DATA_PER_PAGE = 8  # fixed stride; reserves room for both nav buttons (10 - 2 = 8)


def _paginate_rows(
    all_items: list[dict[str, Any]],
    page: int,
    page_size: int = _LIST_PAGE_SIZE,
) -> list[dict[str, Any]]:
    """
    Generic paginator for WhatsApp List Picker.
    Inserts __prev__ / __next__ navigation items respecting the page_size limit.
    ponytail: fixed 8-item stride so page boundaries never overlap regardless of
    which nav buttons are shown.  ceiling: page 0 and last page may show fewer
    than 8 data items (normal for small/remainder slices).
    """
    total = len(all_items)
    if total <= page_size:
        return list(all_items)

    start = page * _LIST_DATA_PER_PAGE
    chunk = all_items[start: start + _LIST_DATA_PER_PAGE]
    has_prev = page > 0
    has_next = start + _LIST_DATA_PER_PAGE < total

    rows: list[dict[str, Any]] = []
    if has_prev:
        rows.append({"id": "__prev__", "title": "⬅️ Anterior", "description": ""})
    rows.extend(chunk)
    if has_next:
        rows.append({"id": "__next__", "title": "➡️ Siguiente", "description": ""})
    return rows


def deliver_reply(
    recipient: str,
    reply: Reply,
    *,
    use_rest: bool,
    actions: list[dict[str, Any]] | None = None,
    interactive_list: dict | None = None,
) -> str:
    """
    Envía texto, botones o listas interactivas.
    """

    parts = reply_parts(reply)

    if not parts:
        return build_twiml_response("")

    actions = actions or []
    interactive_list = interactive_list or {}

    # --------------------------------------------------------
    # RESPUESTA CON LISTA
    # --------------------------------------------------------

    source = interactive_list.get("source")
    page = int(interactive_list.get("page", 0))

    if source in ("menu", "categories", "category_products"):

        from chatbot.runtime import get_bot_context
        from app.core.parser import OrderParser

        svc = get_bot_context(start_background=False).flow_engine.productos_service
        rows: list[dict[str, Any]] = []

        if source == "menu":
            productos = svc.get_available_productos()
            all_items = [
                {
                    "id": str(p["id"]),
                    "title": p["nombre"][:24],
                    "description": f'${OrderParser._fmt_cop(float(p["precio"]))}',
                }
                for p in productos
            ]
            rows = _paginate_rows(all_items, page)

        elif source == "categories":
            categories = svc.get_categories()
            all_items = [
                {"id": f"__cat__{cat}", "title": cat[:24], "description": ""}
                for cat in categories
            ]
            rows = _paginate_rows(all_items, page)

        elif source == "category_products":
            category = interactive_list.get("category", "")
            productos = svc.get_products_by_category(category)
            all_items = [
                {
                    "id": str(p["id"]),
                    "title": p["nombre"][:24],
                    "description": f'${OrderParser._fmt_cop(float(p["precio"]))}',
                }
                for p in productos
            ]
            rows = _paginate_rows(all_items, page)

        if rows:
            body = "\n".join(parts)[:1024]  # Twilio limit: 1024 chars

            message_sid = send_whatsapp_list(
                to_number=recipient,
                body=body,
                rows=rows,
            )

            if message_sid:
                # WhatsApp: one interactive type per message. JSON may declare both
                # list + buttons — send buttons as follow-up (do not drop the map).
                if actions:
                    btn_body = (parts[-1] if parts else "👇")[:1024]
                    btn_sid = send_whatsapp_buttons(
                        to_number=recipient,
                        body=btn_body,
                        buttons=actions,
                    )
                    if not btn_sid:
                        logger.warning(
                            "Interactive buttons follow-up failed for %s",
                            recipient,
                        )
                return build_twiml_response("")

            logger.warning(
                "Interactive list delivery failed for %s; falling back to text",
                recipient,
            )

    # --------------------------------------------------------
    # RESPUESTA CON BOTONES
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
            "Interactive buttons delivery failed for %s; falling back to text",
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
