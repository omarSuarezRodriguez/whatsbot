"""
Persist WhatsApp messages for Flutter (Fase 4).

Entrada: wa_id, body, business_id desde webhook.
Salida: filas en conversations + messages (incoming/outgoing).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Union

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from config.settings import DEFAULT_BUSINESS_ID
from models.conversation import Conversation
from models.message import Message

logger = logging.getLogger(__name__)

ReplyText = Union[str, List[str]]


def _preview_text(body: ReplyText, max_len: int = 120) -> str:
    if isinstance(body, list):
        text = " ".join(str(p) for p in body if p)
    else:
        text = str(body or "")
    text = text.strip()
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _normalize_business_id(business_id: str | None) -> str:
    return (business_id or DEFAULT_BUSINESS_ID or "default").strip() or "default"


def get_or_create_conversation(
    db: Session,
    *,
    customer_wa_id: str,
    business_id: str | None = None,
    customer_name: str | None = None,
) -> Conversation:
    bid = _normalize_business_id(business_id)
    wa = customer_wa_id.strip()
    conv = (
        db.query(Conversation)
        .filter(
            Conversation.business_id == bid,
            Conversation.customer_wa_id == wa,
        )
        .one_or_none()
    )
    if conv is None:
        conv = Conversation(
            business_id=bid,
            customer_wa_id=wa,
            customer_name=customer_name or None,
        )
        db.add(conv)
        db.flush()
        logger.debug("Created conversation id=%s wa_id=%s", conv.id, wa)
    elif customer_name and not conv.customer_name:
        conv.customer_name = customer_name
    return conv


def save_incoming_message(
    db: Session,
    *,
    customer_wa_id: str,
    body: str,
    business_id: str | None = None,
    customer_name: str | None = None,
    is_admin: bool = False,
    channel: str = "whatsapp",
    twilio_sid: str | None = None,
) -> Message:
    """Store client (or admin) message received via Twilio webhook."""
    if twilio_sid:
        existing = get_message_by_twilio_sid(
            db,
            business_id or DEFAULT_BUSINESS_ID,
            twilio_sid,
        )
        if existing is not None:
            logger.info(
                "Duplicate incoming webhook ignored sid=%s msg_id=%s",
                twilio_sid,
                existing.id,
            )
            return existing
    conv = get_or_create_conversation(
        db,
        customer_wa_id=customer_wa_id,
        business_id=business_id,
        customer_name=customer_name,
    )
    now = datetime.now(timezone.utc)
    preview = _preview_text(body)
    msg = Message(
        conversation_id=conv.id,
        direction="incoming",
        body=(body or "").strip(),
        wa_id=customer_wa_id,
        is_admin=is_admin,
        channel=channel,
        twilio_sid=twilio_sid,
        status="delivered",
        delivered_at=now,
        created_at=now,
    )
    db.add(msg)
    conv.last_message_preview = preview
    conv.last_message_at = now
    conv.updated_at = now
    db.flush()
    logger.info(
        "Saved incoming message conv=%s wa_id=%s admin=%s",
        conv.id,
        customer_wa_id,
        is_admin,
    )
    return msg


def get_message_by_twilio_sid(
    db: Session,
    business_id: str,
    twilio_sid: str,
) -> Message | None:
    """Idempotencia webhook Twilio: reutilizar mensaje ya guardado por MessageSid."""
    bid = _normalize_business_id(business_id)
    sid = (twilio_sid or "").strip()
    if not sid:
        return None
    return (
        db.query(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(
            Conversation.business_id == bid,
            Message.twilio_sid == sid,
        )
        .one_or_none()
    )


def get_message_by_client_id(
    db: Session,
    business_id: str,
    client_id: str,
) -> Message | None:
    """Idempotencia app móvil: reutilizar mensaje ya guardado."""
    bid = _normalize_business_id(business_id)
    cid = (client_id or "").strip()
    if not cid:
        return None
    return (
        db.query(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(
            Conversation.business_id == bid,
            Message.client_id == cid,
        )
        .one_or_none()
    )


def save_outgoing_message(
    db: Session,
    *,
    customer_wa_id: str,
    body: ReplyText,
    business_id: str | None = None,
    is_admin: bool = False,
    channel: str = "whatsapp",
    twilio_sid: str | None = None,
    client_id: str | None = None,
) -> list[Message]:
    """Store bot reply (one row per TwiML/REST part)."""
    if not body:
        return []
    parts = body if isinstance(body, list) else [body]
    saved: list[Message] = []
    conv = get_or_create_conversation(
        db,
        customer_wa_id=customer_wa_id,
        business_id=business_id,
    )
    now = datetime.now(timezone.utc)
    for part in parts:
        text = str(part).strip()
        if not text:
            continue
        msg = Message(
            conversation_id=conv.id,
            direction="outgoing",
            body=text,
            wa_id=customer_wa_id,
            is_admin=is_admin,
            channel=channel,
            twilio_sid=twilio_sid,
            client_id=client_id if is_admin and client_id else None,
            status="sent" if is_admin else "delivered",
            delivered_at=None if is_admin else now,
            created_at=now,
        )
        db.add(msg)
        saved.append(msg)
        conv.last_message_preview = _preview_text(text)
        conv.last_message_at = now
    conv.updated_at = now
    db.flush()
    if saved:
        logger.info(
            "Saved %d outgoing message(s) conv=%s wa_id=%s",
            len(saved),
            conv.id,
            customer_wa_id,
        )
    return saved


def list_conversations(
    db: Session,
    business_id: str,
    *,
    limit: int = 100,
    since: datetime | None = None,
) -> list[Conversation]:
    bid = _normalize_business_id(business_id)
    q = db.query(Conversation).filter(Conversation.business_id == bid)
    if since is not None:
        since_utc = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
        q = q.filter(
            (Conversation.updated_at > since_utc)
            | (Conversation.last_message_at > since_utc)
        )
    return (
        q.order_by(Conversation.last_message_at.desc().nullslast(), Conversation.updated_at.desc())
        .limit(limit)
        .all()
    )


def get_conversation_for_business(
    db: Session,
    business_id: str,
    conversation_id: int,
) -> Conversation | None:
    return (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.business_id == _normalize_business_id(business_id),
        )
        .one_or_none()
    )


def list_messages(
    db: Session,
    conversation_id: int,
    *,
    limit: int = 200,
    after_id: int | None = None,
) -> list[Message]:
    q = db.query(Message).filter(Message.conversation_id == conversation_id)
    if after_id is not None:
        q = q.filter(Message.id > after_id)
    return q.order_by(Message.created_at.asc(), Message.id.asc()).limit(limit).all()


_STATUS_RANK = {"sending": 0, "sent": 1, "delivered": 2, "read": 3, "failed": -1}


def _twilio_status_to_local(twilio_status: str) -> str | None:
    """Map Twilio MessageStatus to local status string."""
    raw = (twilio_status or "").strip().lower()
    mapping = {
        "queued": "sent",
        "sending": "sent",
        "sent": "sent",
        "delivered": "delivered",
        "read": "read",
        "failed": "failed",
        "undelivered": "failed",
    }
    return mapping.get(raw)


def apply_twilio_status(
    db: Session,
    *,
    business_id: str,
    message_sid: str,
    twilio_status: str,
) -> Message | None:
    """Update message status from Twilio status callback (source of truth)."""
    msg = get_message_by_twilio_sid(db, business_id, message_sid)
    if msg is None:
        return None

    local_status = _twilio_status_to_local(twilio_status)
    if local_status is None:
        return msg

    current_rank = _STATUS_RANK.get(msg.status, 0)
    new_rank = _STATUS_RANK.get(local_status, 0)
    if local_status != "failed" and new_rank <= current_rank:
        return msg

    now = datetime.now(timezone.utc)
    msg.status = local_status
    if local_status in {"delivered", "read"} and msg.delivered_at is None:
        msg.delivered_at = now
    if local_status == "read":
        msg.read_at = now
    db.flush()
    logger.info(
        "Twilio status sid=%s → %s (msg_id=%s)",
        message_sid,
        local_status,
        msg.id,
    )
    return msg


def mark_outgoing_delivered(db: Session, msg: Message) -> Message:
    """Owner/bot outgoing: sent → delivered when no Twilio SID to track."""
    if msg.direction != "outgoing" or msg.status in {"delivered", "read"}:
        return msg
    if msg.twilio_sid:
        return msg
    now = datetime.now(timezone.utc)
    msg.status = "delivered"
    msg.delivered_at = now
    db.flush()
    return msg


def mark_conversation_read(
    db: Session,
    business_id: str,
    conversation_id: int,
) -> list[Message]:
    """Dueño abrió el chat: incoming → read; salientes del dueño delivered → read."""
    conv = get_conversation_for_business(db, business_id, conversation_id)
    if conv is None:
        return []
    now = datetime.now(timezone.utc)
    updated: list[Message] = []
    rows = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .filter(
            or_(
                and_(Message.direction == "incoming", Message.read_at.is_(None)),
                and_(
                    Message.direction == "outgoing",
                    Message.is_admin.is_(True),
                    Message.status == "delivered",
                ),
            )
        )
        .all()
    )
    for msg in rows:
        msg.status = "read"
        msg.read_at = now
        updated.append(msg)
    if updated:
        db.flush()
    return updated
