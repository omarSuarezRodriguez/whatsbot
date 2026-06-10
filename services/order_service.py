"""Order CRUD per business (API/BD — Fase 5)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from models.order import Order

logger = logging.getLogger(__name__)


def list_orders(
    db: Session,
    business_id: str,
    *,
    status: str | None = None,
    limit: int = 100,
) -> list[Order]:
    q = db.query(Order).filter(Order.business_id == business_id)
    if status:
        q = q.filter(Order.status == status)
    return q.order_by(Order.created_at.desc()).limit(limit).all()


def get_order(db: Session, business_id: str, order_id: str) -> Order | None:
    return (
        db.query(Order)
        .filter(
            Order.business_id == business_id,
            Order.order_id == order_id,
        )
        .one_or_none()
    )


def create_order(
    db: Session,
    business_id: str,
    *,
    order_id: str,
    wa_id: str,
    items: list[dict[str, Any]],
    total: float,
    status: str = "pending",
    customer_name: str = "",
    address: str = "",
    delivery_type: str = "",
) -> Order:
    order = Order(
        business_id=business_id,
        order_id=order_id,
        wa_id=wa_id,
        items=items,
        total=total,
        status=status,
        customer_name=customer_name,
        address=address,
        delivery_type=delivery_type,
    )
    db.add(order)
    db.flush()
    return order


def update_order_status(
    db: Session,
    order: Order,
    status: str,
) -> Order:
    order.status = status
    db.flush()
    return order
