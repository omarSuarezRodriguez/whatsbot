"""
Twilio WhatsApp outbound + TwiML helpers (Fase 4).

Entrada: destino E.164/whatsapp, cuerpo texto.
Salida: bool entrega REST o XML TwiML para el webhook.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
import unicodedata
from pathlib import Path
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

# Reuse HX templates — creating a new Content SID every send floods Meta and
# stacks dead quick-reply chips (tap shows locally, no Twilio inbound).
_CONTENT_SID_CACHE: dict[str, str] = {}
_CONTENT_CACHE_PATH = Path(__file__).resolve().parents[1] / "data" / "twilio_content_cache.json"
# digits|acct → (fingerprint, unix_ts, message_sid); survives process restart via disk.
_LAST_BUTTON_SEND: dict[str, tuple[str, float, str]] = {}
_ANTISTACK_PATH = Path(__file__).resolve().parents[1] / "data" / "twilio_button_antistack.json"
_ANTISTACK_LOADED = False
# LAW 11.6: ~5 min anti-stack same quick-reply → same to. Persisted to disk.
_BUTTON_ANTISTACK_S = 300.0
_BUTTON_LOCK = threading.Lock()


def _btn_title(raw: str) -> str:
    """Wire title: strip leading emoji/punct, fold accents. Ids unchanged."""
    t = re.sub(r"^[\W_]+", "", (raw or ""), flags=re.UNICODE).strip()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return (t or (raw or ""))[:20]


def _list_row_key(raw: str) -> str:
    """ASCII-safe list item key. Emoji in Twilio list ids → Meta often drops message."""
    t = _btn_title(raw).lower().strip()
    t = re.sub(r"\s+", " ", t)
    return t or "item"


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Crash-safe JSON write (temp + replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    tmp.replace(path)


def _content_fingerprint(kind: str, body: str, actions: list[dict[str, Any]]) -> str:
    raw = json.dumps(
        {"k": kind, "b": body, "a": actions},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def _namespaced_cache_key(fp: str) -> str:
    """Isolate HX cache per Twilio account (multi-tenant / multi-AC safe)."""
    acct = (TWILIO_ACCOUNT_SID or "").strip() or "_"
    return f"{acct}:{fp}"


def _load_content_cache() -> None:
    if _CONTENT_SID_CACHE:
        return
    try:
        if _CONTENT_CACHE_PATH.is_file():
            data = json.loads(_CONTENT_CACHE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                # Drop pre-namespace orphan keys (fp without AC…: prefix).
                cleaned = {
                    str(k): str(v)
                    for k, v in data.items()
                    if k and v and ":" in str(k)
                }
                _CONTENT_SID_CACHE.update(cleaned)
                if len(cleaned) != len(data):
                    _save_content_cache()
    except Exception:
        logger.exception("content cache load failed")


def _save_content_cache() -> None:
    try:
        _atomic_write_json(_CONTENT_CACHE_PATH, _CONTENT_SID_CACHE)
    except Exception:
        logger.exception("content cache save failed")


def _antistack_key(digits: str) -> str:
    return _namespaced_cache_key(digits)


def _ensure_antistack_loaded() -> None:
    """Load anti-stack from disk once; prune expired / orphan keys."""
    global _ANTISTACK_LOADED
    if _ANTISTACK_LOADED:
        return
    _ANTISTACK_LOADED = True
    try:
        if not _ANTISTACK_PATH.is_file():
            return
        data = json.loads(_ANTISTACK_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return
        now = time.time()
        kept = 0
        for key, row in data.items():
            # Only account-namespaced keys (AC…:digits). Drop orphans.
            if not key or ":" not in str(key) or not isinstance(row, dict):
                continue
            fp = str(row.get("fp") or "")
            try:
                ts = float(row.get("ts") or 0)
            except (TypeError, ValueError):
                continue
            sid = str(row.get("sid") or "")
            if not fp or not sid or now - ts >= _BUTTON_ANTISTACK_S:
                continue
            _LAST_BUTTON_SEND[str(key)] = (fp, ts, sid)
            kept += 1
        if kept != len(data):
            _save_antistack()
    except Exception:
        logger.exception("antistack load failed")


def _save_antistack() -> None:
    """Persist in-window anti-stack rows (account-namespaced)."""
    try:
        now = time.time()
        payload = {
            key: {"fp": fp, "ts": ts, "sid": sid}
            for key, (fp, ts, sid) in _LAST_BUTTON_SEND.items()
            if fp and sid and ":" in key and now - ts < _BUTTON_ANTISTACK_S
        }
        _atomic_write_json(_ANTISTACK_PATH, payload)
    except Exception:
        logger.exception("antistack save failed")


def _to_digits(number: str) -> str:
    return "".join(ch for ch in (number or "") if ch.isdigit())

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
    *,
    cache_key: str | None = None,
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
        _load_content_cache()
        content_sid = _CONTENT_SID_CACHE.get(cache_key or "") if cache_key else None
        if content_sid:
            # After Content purge, cached HX may be deleted → dead chips.
            probe = requests.get(
                f"https://content.twilio.com/v1/Content/{content_sid}",
                auth=HTTPBasicAuth(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                timeout=10,
            )
            if probe.ok:
                logger.info("Content reuse hx=%s key=%s", content_sid, (cache_key or "")[:24])
            else:
                # 404 or other clear error: never send a dead SID.
                logger.warning(
                    "Cached HX invalid sid=%s status=%s — drop cache + recreate",
                    content_sid,
                    probe.status_code,
                )
                _CONTENT_SID_CACHE.pop(cache_key or "", None)
                _save_content_cache()
                content_sid = None

        if not content_sid:
            logger.info(
                "Content API CREATE types=%s payload=%s",
                list((content.get("types") or {}).keys()),
                json.dumps(content, ensure_ascii=False)[:500],
            )
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
            if cache_key:
                _CONTENT_SID_CACHE[cache_key] = content_sid
                _save_content_cache()
            logger.info("Content created hx=%s", content_sid)

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
        logger.info(
            "Content outbound account=%s from=%s to=%s sid=%s hx=%s",
            (TWILIO_ACCOUNT_SID or "")[:10],
            from_addr,
            to_addr,
            message.sid,
            content_sid,
        )
        if not message.sid or not _message_delivery_ok(client, message.sid):
            if cache_key:
                _CONTENT_SID_CACHE.pop(cache_key, None)
                _save_content_cache()
            return None
        return message.sid

    except Exception:
        if cache_key:
            _CONTENT_SID_CACHE.pop(cache_key, None)
            _save_content_cache()
        logger.exception(
            "Interactive content send failed for %s",
            to_number,
        )
        return None


def _wire_btn_title(raw: str) -> str:
    """Strip leading emoji/punct only; keep accents (match HX that postbacked both)."""
    t = re.sub(r"^[\W_]+", "", (raw or ""), flags=re.UNICODE).strip()
    return (t or (raw or ""))[:20]


def send_whatsapp_buttons(
    to_number: str,
    body: str,
    buttons: list[dict[str, Any]],
) -> str | None:
    """
    JSON `buttons` → one twilio/quick-reply (body + chips, never list-picker).

    Wire titles: no leading emoji, accents kept — same as Content that delivered
    first-chip `Ver menú` on 2026-07-17T21:42 (HX …99f61f06).
    """
    if not buttons:
        return None

    safe_actions = [
        {
            "title": _wire_btn_title(str(b.get("title", ""))),
            "id": str(b.get("id", "")),
        }
        for b in buttons
        if b.get("id") is not None and str(b.get("id")) != "_pad"
    ][:3]
    if not safe_actions:
        return None

    body_text = (body or "")[:1024]
    digits = _to_digits(to_number)
    stack_key = _antistack_key(digits)
    fp = _content_fingerprint("quick-reply", body_text, safe_actions)

    skip_dup = False
    prev_sid = ""
    with _BUTTON_LOCK:
        _ensure_antistack_loaded()
        now = time.time()
        prev = _LAST_BUTTON_SEND.get(stack_key)
        if (
            prev
            and prev[0] == fp
            and now - prev[1] < _BUTTON_ANTISTACK_S
            and prev[2]
        ):
            logger.info(
                "skip duplicate quick-reply to=%s ids=%s age=%.2fs sid=%s",
                digits,
                [a["id"] for a in safe_actions],
                now - prev[1],
                prev[2],
            )
            skip_dup = True
            prev_sid = prev[2]

    if skip_dup:
        return prev_sid

    logger.info(
        "send_whatsapp_buttons QUICK-REPLY (not list) n=%s ids=%s titles=%s",
        len(safe_actions),
        [a["id"] for a in safe_actions],
        [a["title"] for a in safe_actions],
    )

    content = {
        "friendly_name": f"wb_btn_{fp[:20]}",
        "language": "es",
        "types": {
            "twilio/quick-reply": {
                "body": body_text or "👇",
                "actions": safe_actions,
            }
        },
    }

    sid = _send_content(
        to_number=to_number,
        content=content,
        cache_key=_namespaced_cache_key(fp),
    )
    if sid:
        with _BUTTON_LOCK:
            _LAST_BUTTON_SEND[stack_key] = (fp, time.time(), sid)
            _save_antistack()
    return sid


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
            "description": row.get("description") or "",
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
    body_text = (body or "")[:1024]
    list_actions = [
        {
            "id": str(r.get("id", "")),
            "title": str(r.get("title", "")),
            "description": str(r.get("description") or ""),
        }
        for r in (rows or [])
        if r.get("id") is not None
    ]
    fp = _content_fingerprint("list-picker", body_text, list_actions)
    content = build_list_content(
        friendly_name=f"wb_list_{fp[:20]}",
        body=body_text,
        button="Elegir",
        rows=rows,
    )

    return _send_content(
        to_number=to_number,
        content=content,
        cache_key=_namespaced_cache_key(fp),
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
        rows.append({"id": "__prev__", "title": "Anterior", "description": ""})
    rows.extend(chunk)
    if has_next:
        rows.append({"id": "__next__", "title": "Siguiente", "description": ""})
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
    Deliver by JSON map type (LAW):
      - list source → twilio/list-picker only
      - buttons (actions) → twilio/quick-reply only
      - never treat buttons as a list-picker
    """

    parts = reply_parts(reply)

    if not parts:
        return build_twiml_response("")

    actions = actions or []
    interactive_list = interactive_list or {}

    source = interactive_list.get("source")
    page = int(interactive_list.get("page", 0))
    has_list = source in ("menu", "categories", "category_products", "static")
    has_buttons = bool(actions)

    # --------------------------------------------------------
    # LIST (JSON `list` only) → list-picker
    # --------------------------------------------------------
    if has_list:

        from chatbot.runtime import get_bot_context
        from app.core.parser import OrderParser

        svc = get_bot_context(start_background=False).flow_engine.productos_service
        rows: list[dict[str, Any]] = []

        if source == "menu":
            productos = svc.get_available_productos()
            all_items = [
                {
                    "id": str(p["id"]),
                    "title": str(p["nombre"])[:24],
                    "description": f'${OrderParser._fmt_cop(float(p["precio"]))}',
                }
                for p in productos
            ]
            rows = _paginate_rows(all_items, page)

        elif source == "categories":
            categories = svc.get_categories()
            all_items = [
                {
                    "id": f"__cat__{_list_row_key(cat)}",
                    "title": str(cat)[:24],
                    "description": "",
                }
                for cat in categories
            ]
            rows = _paginate_rows(all_items, page)

        elif source == "category_products":
            category = interactive_list.get("category", "")
            productos = svc.get_products_by_category(category)
            all_items = [
                {
                    "id": str(p["id"]),
                    "title": str(p["nombre"])[:24],
                    "description": f'${OrderParser._fmt_cop(float(p["precio"]))}',
                }
                for p in productos
            ]
            rows = _paginate_rows(all_items, page)

        elif source == "static":
            # JSON-declared rows (home choices). Not a buttons→list conversion:
            # map says list; transport only delivers.
            rows = [
                {
                    "id": str(r.get("id", "")),
                    "title": str(r.get("title", ""))[:24],
                    "description": str(r.get("description") or "")[:72],
                }
                for r in (interactive_list.get("rows") or [])
                if r.get("id") is not None
            ][:10]

        if rows:
            text_sent = False
            if use_rest:
                for part in parts:
                    if send_whatsapp_message(recipient, part):
                        text_sent = True
                list_body = "👇 Selecciona una opción de la lista."[:1024]
            else:
                list_body = "\n".join(parts)[:1024]

            logger.info(
                "deliver_reply LIST-PICKER source=%s rows=%s (JSON list)",
                source,
                len(rows),
            )
            message_sid = send_whatsapp_list(
                to_number=recipient,
                body=list_body,
                rows=rows,
            )

            if message_sid:
                # LAW 11.2: list + buttons → second message (quick-reply), not merge.
                if has_buttons:
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
            if text_sent:
                return build_twiml_response("")

    # --------------------------------------------------------
    # BUTTONS (JSON `buttons` only) → quick-reply — never list-picker
    # --------------------------------------------------------
    if has_buttons and not has_list:
        logger.info(
            "deliver_reply QUICK-REPLY buttons=%s (JSON buttons, not list)",
            [str(a.get("id")) for a in actions],
        )
        # Body + chips in ONE Content (one WhatsApp bubble). Not twin types.
        body = "\n".join(parts)[:1024]
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
    # TEXT
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
