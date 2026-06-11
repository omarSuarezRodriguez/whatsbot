"""Customer CRUD per business (DB source of truth)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from models.customer import Customer

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def list_customers(
    db: Session,
    business_id: str,
    *,
    search: str | None = None,
    limit: int = 500,
) -> list[Customer]:
    q = db.query(Customer).filter(Customer.business_id == business_id)
    if search:
        like = f"%{search.strip()}%"
        q = q.filter((Customer.name.ilike(like)) | (Customer.wa_id.ilike(like)))
    return q.order_by(Customer.name.is_(None), Customer.name, Customer.wa_id).limit(limit).all()


def get_customer(db: Session, business_id: str, customer_id: int) -> Customer | None:
    return (
        db.query(Customer)
        .filter(Customer.business_id == business_id, Customer.id == customer_id)
        .one_or_none()
    )


def get_customer_by_wa_id(db: Session, business_id: str, wa_id: str) -> Customer | None:
    return (
        db.query(Customer)
        .filter(Customer.business_id == business_id, Customer.wa_id == wa_id)
        .one_or_none()
    )


def create_customer(
    db: Session,
    business_id: str,
    *,
    wa_id: str,
    name: str | None = None,
    address: str | None = None,
    notes: str | None = None,
    blocked: bool = False,
) -> Customer:
    customer = Customer(
        business_id=business_id,
        wa_id=wa_id.strip(),
        name=name,
        address=address,
        notes=notes,
        blocked=blocked,
    )
    db.add(customer)
    db.flush()
    return customer


def update_customer(db: Session, customer: Customer, data: dict[str, Any]) -> Customer:
    for key in ("name", "address", "notes", "blocked", "wa_id"):
        if key in data and data[key] is not None:
            setattr(customer, key, data[key])
    db.flush()
    return customer


def delete_customer(db: Session, customer: Customer) -> None:
    db.delete(customer)


def upsert_from_chat(
    db: Session,
    business_id: str,
    *,
    wa_id: str,
    name: str = "",
    address: str = "",
    last_order_items: list[dict[str, Any]] | None = None,
    touch_last_seen: bool = True,
) -> Customer:
    """Create or merge a customer seen via the bot/chat. Empty fields never overwrite."""
    customer = get_customer_by_wa_id(db, business_id, wa_id)
    if customer is None:
        customer = Customer(business_id=business_id, wa_id=wa_id.strip())
        db.add(customer)
    if name:
        customer.name = name
    if address:
        customer.address = address
    if last_order_items is not None:
        customer.last_order_items = last_order_items
    if touch_last_seen:
        customer.last_seen = _utcnow()
    db.flush()
    return customer
