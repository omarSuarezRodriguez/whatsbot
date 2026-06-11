"""
REST API for Flutter WhatsBot — Fase 7.

Todas las rutas requieren JWT (claim business_id) salvo que se indique lo contrario.
Sin UI web — solo JSON para la app móvil.

Rutas:
  GET  /whatsbot/conversations
  GET  /whatsbot/conversations/{id}/messages
  POST /whatsbot/messages              — dueño envía al cliente (Twilio línea del bot)
  GET  /whatsbot/orders/pending
  POST /whatsbot/orders/{id}/approve
  POST /whatsbot/orders/{id}/reject
  GET  /whatsbot/business/me
  GET/PUT /whatsbot/business/menu
  GET/PUT /whatsbot/business/intents
  GET/PUT /whatsbot/business/prompts
  POST /whatsbot/device-token          — registrar FCM/APNs (Fase 11.4)
  DELETE /whatsbot/device-token          — quitar token al logout
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from api.middleware.auth import get_current_business_id
from api.schemas import (
    BusinessMeOut,
    ConversationOut,
    DeviceTokenRegister,
    IntentsConfigOut,
    IntentsConfigUpdate,
    MenuAppOut,
    MenuAppUpdate,
    MessageOut,
    OrderActionResponse,
    OrderOut,
    OwnerMessageCreate,
    PromptsConfigOut,
    PromptsConfigUpdate,
)
from chatbot.runtime import get_bot_context
from config.settings import REALTIME_ENABLED
from infrastructure.database import get_db
from infrastructure.twilio_client import send_whatsapp_message
from services import business_service as biz_svc
from services import conversation_service as conv_svc
from services import menu_service as menu_svc
from services import notification_service as notify_svc
from services import order_service as order_svc
from services import device_token_service as token_svc
from services import twilio_sync_service as twilio_sync_svc
from services.realtime_service import (
    emit_message_saved,
    emit_message_status,
    emit_order_updated,
)

router = APIRouter(prefix="/whatsbot", tags=["whatsbot"])


def _parse_since(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return datetime.fromisoformat(raw)

BusinessId = Annotated[str, Depends(get_current_business_id)]


def _require_business(db: Session, business_id: str):
    biz = biz_svc.get_business(db, business_id)
    if not biz:
        raise HTTPException(404, detail="Negocio no encontrado")
    return biz


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    business_id: BusinessId,
    limit: int = 100,
    since: str | None = Query(
        default=None,
        description="ISO8601 — solo conversaciones actualizadas después de esta fecha",
    ),
    db: Session = Depends(get_db),
) -> list[ConversationOut]:
    """Lista chats del negocio (estilo WhatsApp)."""
    _require_business(db, business_id)
    return conv_svc.list_conversations(
        db,
        business_id,
        limit=limit,
        since=_parse_since(since),
    )


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def list_conversation_messages(
    conversation_id: int,
    business_id: BusinessId,
    limit: int = 200,
    after_id: int | None = Query(
        default=None,
        ge=0,
        description="Solo mensajes con id mayor a este (sync incremental)",
    ),
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    """Historial de un chat."""
    _require_business(db, business_id)
    conv = conv_svc.get_conversation_for_business(db, business_id, conversation_id)
    if not conv:
        raise HTTPException(404, detail="Conversación no encontrada")
    return conv_svc.list_messages(db, conv.id, limit=limit, after_id=after_id)


@router.post("/conversations/{conversation_id}/mark-read", status_code=204)
async def mark_conversation_read(
    conversation_id: int,
    business_id: BusinessId,
    db: Session = Depends(get_db),
) -> Response:
    """Marca mensajes como leídos cuando el dueño abre el chat."""
    _require_business(db, business_id)
    conv = conv_svc.get_conversation_for_business(db, business_id, conversation_id)
    if not conv:
        raise HTTPException(404, detail="Conversación no encontrada")
    updated = conv_svc.mark_conversation_read(db, business_id, conversation_id)
    db.commit()
    for msg in updated:
        await emit_message_status(db, business_id, msg)
    return Response(status_code=204)


@router.post("/messages", response_model=MessageOut, status_code=201)
async def send_owner_message(
    body: OwnerMessageCreate,
    business_id: BusinessId,
    db: Session = Depends(get_db),
) -> MessageOut:
    """
    Dueño responde manualmente desde la app.

    Entrada: customer_wa_id + body.
    Salida: mensaje guardado en BD; envío Twilio vía línea del bot (TWILIO_WHATSAPP_FROM).
    """
    _require_business(db, business_id)
    if body.client_id:
        existing = conv_svc.get_message_by_client_id(
            db, business_id, body.client_id
        )
        if existing is not None:
            return existing
    ctx = get_bot_context(start_background=False)
    wa_id = ctx.admin_service.canonical_wa_id(body.customer_wa_id, "") or body.customer_wa_id
    twilio_sid = send_whatsapp_message(wa_id, body.body)
    saved = conv_svc.save_outgoing_message(
        db,
        customer_wa_id=wa_id,
        body=body.body,
        business_id=business_id,
        is_admin=True,
        client_id=body.client_id,
        twilio_sid=twilio_sid,
    )
    db.commit()
    if not saved:
        raise HTTPException(500, detail="No se pudo guardar el mensaje")
    msg = saved[-1]
    await emit_message_saved(db, business_id, msg)
    return msg


@router.post("/sync/twilio")
async def sync_twilio_messages(
    business_id: BusinessId,
    lookback_hours: int = Query(default=48, ge=1, le=168),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    """
    Recupera mensajes faltantes desde Twilio API (dedup por MessageSid).
    Útil tras caída del servidor o webhooks perdidos.
    """
    _require_business(db, business_id)
    result = twilio_sync_svc.sync_messages_from_twilio(
        db,
        business_id,
        lookback_hours=lookback_hours,
    )
    imported = int(result.get("imported", 0))
    if imported > 0 and REALTIME_ENABLED:
        from services.realtime_service import realtime_hub, build_conversation_updated_event
        from services import conversation_service as conv_svc

        convs = conv_svc.list_conversations(db, business_id, limit=50)
        for conv in convs:
            await realtime_hub.emit(business_id, build_conversation_updated_event(conv))
    return result


@router.post("/device-token", status_code=204)
def register_device_token(
    body: DeviceTokenRegister,
    business_id: BusinessId,
    db: Session = Depends(get_db),
) -> Response:
    """Registra o actualiza token FCM/APNs del dispositivo."""
    _require_business(db, business_id)
    token_svc.upsert_device_token(
        db,
        business_id=business_id,
        token=body.token,
        platform=body.platform,
    )
    db.commit()
    return Response(status_code=204)


@router.delete("/device-token", status_code=204)
def unregister_device_token(
    body: DeviceTokenRegister,
    business_id: BusinessId,
    db: Session = Depends(get_db),
) -> Response:
    """Elimina token al cerrar sesión en el dispositivo."""
    _require_business(db, business_id)
    token_svc.delete_device_token(
        db,
        business_id=business_id,
        token=body.token,
    )
    db.commit()
    return Response(status_code=204)


@router.get("/orders/pending", response_model=list[OrderOut])
def list_pending_orders(
    business_id: BusinessId,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[OrderOut]:
    """Pedidos pendientes de aprobación."""
    _require_business(db, business_id)
    return order_svc.list_orders(db, business_id, status="pending", limit=limit)


@router.post("/orders/{order_id}/approve", response_model=OrderActionResponse)
async def approve_order(
    order_id: str,
    business_id: BusinessId,
    db: Session = Depends(get_db),
) -> OrderActionResponse:
    """Aprueba pedido y notifica al cliente (legacy Sheets + Twilio)."""
    result = notify_svc.approve_order_from_app(
        order_id,
        business_id=business_id,
        db=db,
    )
    saved_msg = result.get("saved_message")
    if saved_msg is not None:
        db.commit()
        await emit_message_saved(db, business_id, saved_msg)
    row = order_svc.get_order(db, business_id, order_id.upper().strip())
    if row:
        await emit_order_updated(business_id, row)
    return OrderActionResponse(ok=result.get("ok", False), message=result.get("message", ""))


@router.post("/orders/{order_id}/reject", response_model=OrderActionResponse)
async def reject_order(
    order_id: str,
    business_id: BusinessId,
    reason: str = "",
    db: Session = Depends(get_db),
) -> OrderActionResponse:
    """Rechaza pedido y avisa al cliente."""
    result = notify_svc.reject_order_from_app(
        order_id,
        business_id=business_id,
        reason=reason,
    )
    row = order_svc.get_order(db, business_id, order_id.upper().strip())
    if row:
        await emit_order_updated(business_id, row)
    return OrderActionResponse(ok=result.get("ok", False), message=result.get("message", ""))


@router.get("/business/me", response_model=BusinessMeOut)
def get_business_me(
    business_id: BusinessId,
    db: Session = Depends(get_db),
) -> BusinessMeOut:
    """Perfil del negocio autenticado."""
    return _require_business(db, business_id)


@router.get("/business/menu", response_model=MenuAppOut)
def get_business_menu(
    business_id: BusinessId,
    db: Session = Depends(get_db),
) -> MenuAppOut:
    """Menú del negocio (fuente: BD)."""
    _require_business(db, business_id)
    items = menu_svc.list_menu_items(db, business_id)
    return MenuAppOut(items=items)


@router.put("/business/menu", response_model=MenuAppOut)
def put_business_menu(
    body: MenuAppUpdate,
    business_id: BusinessId,
    db: Session = Depends(get_db),
) -> MenuAppOut:
    """Reemplaza menú completo desde la app."""
    _require_business(db, business_id)
    items = menu_svc.replace_menu_items(db, business_id, body.items)
    db.commit()
    return MenuAppOut(items=items)


@router.get("/business/intents", response_model=IntentsConfigOut)
def get_business_intents(
    business_id: BusinessId,
    db: Session = Depends(get_db),
) -> IntentsConfigOut:
    _require_business(db, business_id)
    return IntentsConfigOut(config=biz_svc.get_business_intents(db, business_id))


@router.put("/business/intents", response_model=IntentsConfigOut)
def put_business_intents(
    body: IntentsConfigUpdate,
    business_id: BusinessId,
    db: Session = Depends(get_db),
) -> IntentsConfigOut:
    _require_business(db, business_id)
    config = biz_svc.set_business_intents(db, business_id, body.config)
    db.commit()
    return IntentsConfigOut(config=config)


@router.get("/business/prompts", response_model=PromptsConfigOut)
def get_business_prompts(
    business_id: BusinessId,
    db: Session = Depends(get_db),
) -> PromptsConfigOut:
    _require_business(db, business_id)
    return PromptsConfigOut(config=biz_svc.get_business_prompts(db, business_id))


@router.put("/business/prompts", response_model=PromptsConfigOut)
def put_business_prompts(
    body: PromptsConfigUpdate,
    business_id: BusinessId,
    db: Session = Depends(get_db),
) -> PromptsConfigOut:
    _require_business(db, business_id)
    config = biz_svc.set_business_prompts(db, business_id, body.config)
    db.commit()
    return PromptsConfigOut(config=config)
