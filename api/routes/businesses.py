"""Business CRUD + intents/prompts config.

- list/create: require superadmin key (cross-tenant ops).
- get/intents/prompts: require JWT scoped to that business.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.middleware.auth import get_current_business_id, require_superadmin
from api.schemas import BusinessCreate, BusinessOut
from infrastructure.database import get_db
from services import business_service as biz_svc

router = APIRouter(prefix="/businesses", tags=["businesses"])

BusinessId = Annotated[str, Depends(get_current_business_id)]


def _require_same_tenant(token_business_id: str, path_business_id: str) -> None:
    if token_business_id != path_business_id:
        raise HTTPException(403, detail="No autorizado para este negocio")


@router.get("", response_model=list[BusinessOut], dependencies=[Depends(require_superadmin)])
def list_businesses(db: Session = Depends(get_db)) -> list:
    return biz_svc.list_businesses(db)


@router.post("", response_model=BusinessOut, status_code=201, dependencies=[Depends(require_superadmin)])
def create_business(body: BusinessCreate, db: Session = Depends(get_db)) -> BusinessOut:
    if biz_svc.get_business(db, body.id):
        raise HTTPException(409, detail="business_id ya existe")
    biz = biz_svc.create_business(
        db,
        business_id=body.id,
        name=body.name,
        twilio_whatsapp_from=body.twilio_whatsapp_from,
        admin_whatsapp_number=body.admin_whatsapp_number,
        pin=body.pin,
        is_default=body.is_default,
        seed_from_config=True,
    )
    db.commit()
    return biz


@router.get("/{business_id}", response_model=BusinessOut)
def get_business(
    business_id: str,
    token_business_id: BusinessId,
    db: Session = Depends(get_db),
) -> BusinessOut:
    _require_same_tenant(token_business_id, business_id)
    biz = biz_svc.get_business(db, business_id)
    if not biz:
        raise HTTPException(404, detail="Negocio no encontrado")
    return biz


@router.get("/{business_id}/intents")
def get_intents(
    business_id: str,
    token_business_id: BusinessId,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_same_tenant(token_business_id, business_id)
    if not biz_svc.get_business(db, business_id):
        raise HTTPException(404, detail="Negocio no encontrado")
    return biz_svc.get_business_intents(db, business_id)


@router.get("/{business_id}/prompts")
def get_prompts(
    business_id: str,
    token_business_id: BusinessId,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    _require_same_tenant(token_business_id, business_id)
    if not biz_svc.get_business(db, business_id):
        raise HTTPException(404, detail="Negocio no encontrado")
    return biz_svc.get_business_prompts(db, business_id)
