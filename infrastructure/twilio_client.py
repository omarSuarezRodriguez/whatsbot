"""
Twilio WhatsApp outbound + TwiML helpers (Fase 4).

Entrada: destino E.164/whatsapp, cuerpo texto.
Salida: bool entrega REST o XML TwiML para el webhook.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from typing import Any, Callable, List, Union

import requests
from requests.auth import HTTPBasicAuth
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from twilio.twiml.messaging_response import MessagingResponse

from config.settings import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_WHATSAPP_FROM,
    is_twilio_whatsapp_sandbox,
    twilio_status_callback_url,
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


def register_button_fallback(
    message_sid: str,
    business_id: str,
    recipient: str,
    fallback_body: str,
) -> None:
    if not message_sid or not business_id or not fallback_body:
        return
    try:
        from infrastructure.database import session_scope
        from services.button_fallback_service import register_pending

        with session_scope() as db:
            register_pending(
                db,
                business_id=business_id,
                message_sid=message_sid,
                recipient=recipient,
                fallback_body=fallback_body,
            )
    except Exception:
        logger.exception(
            "Could not persist button fallback sid=%s business=%s",
            message_sid,
            business_id,
        )


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


# ---------------------------------------------------------------------------
# Rate-limit retry (Fase 4 fix, punto 3)
# ---------------------------------------------------------------------------

_RETRYABLE_STATUS = 429
_MAX_RETRIES = 2
_RETRY_BASE_DELAY = 0.4


def _retry_after_seconds(headers: Any) -> float | None:
    value = (headers or {}).get("Retry-After")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _call_with_rate_limit_retry(fn: Callable[[], Any], *, what: str) -> Any:
    """
    Runs fn() with bounded retry on 429/rate-limit only — every other error
    keeps failing immediately, same as before this fix (falls to the existing
    text fallback).
    ponytail: fixed 2 retries, short backoff. ceiling: webhook latency budget
    is small; a sustained rate-limit outage still ends in fallback, by design.
    """
    delay = _RETRY_BASE_DELAY
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return fn()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status != _RETRYABLE_STATUS or attempt == _MAX_RETRIES:
                raise
            wait = _retry_after_seconds(exc.response.headers) or delay
            logger.warning(
                "%s got 429; retry %d/%d in %.1fs", what, attempt + 1, _MAX_RETRIES, wait
            )
            time.sleep(wait)
            delay *= 2
        except TwilioRestException as exc:
            if getattr(exc, "status", None) != _RETRYABLE_STATUS or attempt == _MAX_RETRIES:
                raise
            logger.warning(
                "%s got 429 (Twilio); retry %d/%d in %.1fs",
                what, attempt + 1, _MAX_RETRIES, delay,
            )
            time.sleep(delay)
            delay *= 2


# ---------------------------------------------------------------------------
# ContentSid cache (Fase 4 fix, puntos 1 y 2)
# ---------------------------------------------------------------------------


def _stable_cache_key(content_type: str, payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(f"{content_type}:{canonical}".encode("utf-8")).hexdigest()
    return digest[:48]


def _create_content_template(content: dict) -> str:
    """POST a new Content Template to Twilio. Raises on failure (caller decides fallback)."""

    def _do() -> str:
        response = requests.post(
            "https://content.twilio.com/v1/Content",
            json=content,
            auth=HTTPBasicAuth(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            timeout=15,
        )
        response.raise_for_status()
        return response.json()["sid"]

    return _call_with_rate_limit_retry(_do, what="Content template create")


def _get_or_create_content_sid(
    cache_key: str,
    content_type: str,
    build_content: Callable[[], dict],
) -> str | None:
    """Reuse a cached ContentSid for this key, or create+cache one (Twilio's
    documented pattern: crear una vez, guardar el ContentSid, reutilizarlo)."""
    from infrastructure.database import session_scope
    from services.twilio_content_cache_service import get_cached_sid, upsert_cached_sid

    try:
        with session_scope() as db:
            cached = get_cached_sid(db, cache_key)
        if cached:
            return cached
    except Exception:
        logger.exception("ContentSid cache lookup failed for key=%s", cache_key)

    try:
        content_sid = _create_content_template(build_content())
    except Exception:
        logger.exception("Content template create failed for key=%s", cache_key)
        return None

    try:
        with session_scope() as db:
            upsert_cached_sid(
                db,
                cache_key=cache_key,
                content_type=content_type,
                content_sid=content_sid,
            )
    except Exception:
        logger.exception("ContentSid cache store failed for key=%s", cache_key)

    return content_sid


def _invalidate_cache_entry(cache_key: str) -> None:
    try:
        from infrastructure.database import session_scope
        from services.twilio_content_cache_service import invalidate_cached_sid

        with session_scope() as db:
            invalidate_cached_sid(db, cache_key)
    except Exception:
        logger.exception("ContentSid cache invalidate failed for key=%s", cache_key)


def _send_with_content_sid(
    to_number: str,
    content_sid: str,
    content_variables: dict[str, str] | None = None,
) -> tuple[str, str | None]:
    """Returns (status, message_sid). status is 'ok', 'invalid_sid' or 'error'."""
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    to_addr = _whatsapp_address(to_number)
    from_addr = _whatsapp_address(TWILIO_WHATSAPP_FROM)

    # Pin From to the ONLINE WhatsApp Business sender. Do not rely on
    # Messaging Service alone for Content — it can remap to a dead +1555 channel (63007).
    create_kwargs: dict[str, Any] = {
        "from_": from_addr,
        "to": to_addr,
        "content_sid": content_sid,
    }
    if content_variables:
        create_kwargs["content_variables"] = json.dumps(content_variables)
    status_url = twilio_status_callback_url()
    if status_url:
        create_kwargs["status_callback"] = status_url

    def _do():
        return client.messages.create(**create_kwargs)

    try:
        message = _call_with_rate_limit_retry(_do, what="Content message send")
    except TwilioRestException as exc:
        # ponytail: 404 = best-effort heuristic for "stale/deleted ContentSid".
        # ceiling: not every Twilio error code for invalid content is enumerated
        # here — add specific codes if they show up in logs.
        if getattr(exc, "status", None) == 404:
            logger.warning(
                "ContentSid %s not found on send — treating as stale", content_sid
            )
            return "invalid_sid", None
        logger.exception("Content message send failed sid=%s", content_sid)
        return "error", None
    except Exception:
        logger.exception("Content message send failed sid=%s", content_sid)
        return "error", None

    logger.info(
        "Content outbound account=%s from=%s to=%s sid=%s",
        (TWILIO_ACCOUNT_SID or "")[:10],
        from_addr,
        to_addr,
        message.sid,
    )
    if not message.sid or not _message_delivery_ok(client, message.sid):
        return "error", None
    return "ok", message.sid


def _send_content_via_cache(
    *,
    to_number: str,
    cache_key: str,
    content_type: str,
    build_content: Callable[[], dict],
    content_variables: dict[str, str] | None = None,
) -> str | None:
    """
    Envía contenido interactivo de Twilio Content API (botones/listas)
    reutilizando el ContentSid cacheado para esta clave; crea uno nuevo solo
    si no existe o si Twilio lo reporta como inválido (self-heal, un reintento).
    """
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_FROM):
        logger.info(
            "Twilio outbound not configured; skip interactive send to %s",
            to_number[:20],
        )
        return None

    content_sid = _get_or_create_content_sid(cache_key, content_type, build_content)
    if not content_sid:
        return None

    status, sid = _send_with_content_sid(to_number, content_sid, content_variables)
    if status == "invalid_sid":
        _invalidate_cache_entry(cache_key)
        fresh_sid = _get_or_create_content_sid(cache_key, content_type, build_content)
        if not fresh_sid:
            return None
        status, sid = _send_with_content_sid(to_number, fresh_sid, content_variables)

    return sid if status == "ok" else None


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

    logger.info(
        "send_whatsapp_buttons n=%s ids=%s",
        len(safe_actions),
        [a["id"] for a in safe_actions],
    )

    # Cache key = button set only (id+title+order). El body va como
    # ContentVariable: el mismo set de botones (ej. qty_1/qty_2/qty_other) se
    # reusa aunque el texto cambie por producto/carrito en cada envío.
    cache_key = _stable_cache_key("quick_reply", safe_actions)

    def _build() -> dict:
        return {
            "friendly_name": f"wb_btn_{uuid.uuid4().hex[:12]}",
            "language": "es",
            "types": {
                "twilio/quick-reply": {
                    "body": "{{1}}",
                    "actions": safe_actions,
                }
            },
        }

    return _send_content_via_cache(
        to_number=to_number,
        cache_key=cache_key,
        content_type="quick_reply",
        build_content=_build,
        content_variables={"1": (body or "")[:1024]},
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
    button: str,
    business_id: str = "",
) -> str | None:
    """
    Envía una lista interactiva (WhatsApp List Picker) usando Twilio Content API.

    Reutiliza el mismo ContentSid mientras el contenido realizado (negocio +
    body + botón + items) no cambie; un catálogo distinto produce un hash
    distinto y crea un ContentSid nuevo automáticamente.
    """
    safe_body = (body or "")[:1024]
    safe_button = button[:20]

    cache_key = _stable_cache_key(
        "list_picker",
        {
            "business_id": business_id or "",
            "body": safe_body,
            "button": safe_button,
            "rows": rows,
        },
    )

    def _build() -> dict:
        return build_list_content(
            friendly_name=f"wb_list_{uuid.uuid4().hex[:12]}",
            body=safe_body,
            button=safe_button,
            rows=rows,
        )

    return _send_content_via_cache(
        to_number=to_number,
        cache_key=cache_key,
        content_type="list_picker",
        build_content=_build,
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
    business_id: str = "",
    actions: list[dict[str, Any]] | None = None,
    buttons_failure_message: str = "",
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

    if source in ("menu", "categories", "category_products", "cart_items"):

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

        elif source == "cart_items":
            all_items = list(interactive_list.get("rows") or [])
            rows = _paginate_rows(all_items, page)

        if rows:
            body = "\n".join(parts)[:1024]  # Twilio limit: 1024 chars
            button = str(interactive_list.get("button") or "").strip()
            if not button:
                logger.error(
                    "list.button missing in flow for source=%s",
                    source,
                )
                return build_twiml_response(body)

            message_sid = send_whatsapp_list(
                to_number=recipient,
                body=body,
                rows=rows,
                button=button,
                business_id=business_id,
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
            if buttons_failure_message:
                fallback_body = f"{body}\n\n{buttons_failure_message}".strip()
                register_button_fallback(
                    message_sid,
                    business_id,
                    recipient,
                    fallback_body,
                )
            return build_twiml_response("")

        logger.warning(
            "Interactive buttons delivery failed for %s; falling back to text",
            recipient,
        )
        if buttons_failure_message:
            reply = f"{body}\n\n{buttons_failure_message}".strip()
            parts = [reply]

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
