"""Orders API per business (Fase 5)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.schemas import OrderCreate, OrderOut
from infrastructure.database import get_db
from services import business_service as biz_svc
from services import order_service as order_svc

router = APIRouter(prefix="/businesses/{business_id}/orders", tags=["orders"])


def _require_business(db: Session, business_id: str) -> None:
    if not biz_svc.get_business(db, business_id):
        raise HTTPException(404, detail="Negocio no encontrado")


@router.get("", response_model=list[OrderOut])
def list_orders(
    business_id: str,
    status: str | None = Query(None),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
) -> list:
    _require_business(db, business_id)
    return order_svc.list_orders(db, business_id, status=status, limit=limit)


@router.get("/{order_id}", response_model=OrderOut)
def get_order(
    business_id: str,
    order_id: str,
    db: Session = Depends(get_db),
) -> OrderOut:
    _require_business(db, business_id)
    order = order_svc.get_order(db, business_id, order_id)
    if not order:
        raise HTTPException(404, detail="Pedido no encontrado")
    return order


@router.post("", response_model=OrderOut, status_code=201)
def create_order(
    business_id: str,
    body: OrderCreate,
    db: Session = Depends(get_db),
) -> OrderOut:
    _require_business(db, business_id)
    if order_svc.get_order(db, business_id, body.order_id):
        raise HTTPException(409, detail="order_id ya existe")
    order = order_svc.create_order(
        db,
        business_id,
        order_id=body.order_id,
        wa_id=body.wa_id,
        items=body.items,
        total=body.total,
        status=body.status,
        customer_name=body.customer_name,
        address=body.address,
        delivery_type=body.delivery_type,
    )
    db.commit()
    return order
