"""
Customers (clients) CRUD for the Flutter owner panel — JWT scoped per business.

The owner manages their own client list (name, phone, notes) as a first-class
entity. The bot also auto-creates customers when people write in.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.middleware.auth import get_current_business_id
from api.schemas import CustomerCreate, CustomerOut, CustomerUpdate
from infrastructure.database import get_db
from services import business_service as biz_svc
from services import customer_service as cust_svc

router = APIRouter(prefix="/whatsbot/customers", tags=["customers"])

BusinessId = Annotated[str, Depends(get_current_business_id)]


def _require_business(db: Session, business_id: str) -> None:
    if not biz_svc.get_business(db, business_id):
        raise HTTPException(404, detail="Negocio no encontrado")


@router.get("", response_model=list[CustomerOut])
def list_customers(
    business_id: BusinessId,
    search: str | None = Query(default=None),
    limit: int = 500,
    db: Session = Depends(get_db),
) -> list[CustomerOut]:
    _require_business(db, business_id)
    return cust_svc.list_customers(db, business_id, search=search, limit=limit)


@router.post("", response_model=CustomerOut, status_code=201)
def create_customer(
    body: CustomerCreate,
    business_id: BusinessId,
    db: Session = Depends(get_db),
) -> CustomerOut:
    _require_business(db, business_id)
    existing = cust_svc.get_customer_by_wa_id(db, business_id, body.wa_id)
    if existing is not None:
        raise HTTPException(409, detail="Ya existe un cliente con ese WhatsApp")
    customer = cust_svc.create_customer(
        db,
        business_id,
        wa_id=body.wa_id,
        name=body.name,
        address=body.address,
        notes=body.notes,
        blocked=body.blocked,
    )
    db.commit()
    return customer


@router.put("/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: int,
    body: CustomerUpdate,
    business_id: BusinessId,
    db: Session = Depends(get_db),
) -> CustomerOut:
    _require_business(db, business_id)
    customer = cust_svc.get_customer(db, business_id, customer_id)
    if customer is None:
        raise HTTPException(404, detail="Cliente no encontrado")
    customer = cust_svc.update_customer(db, customer, body.model_dump(exclude_unset=True))
    db.commit()
    return customer


@router.delete("/{customer_id}", status_code=204)
def delete_customer(
    customer_id: int,
    business_id: BusinessId,
    db: Session = Depends(get_db),
) -> None:
    _require_business(db, business_id)
    customer = cust_svc.get_customer(db, business_id, customer_id)
    if customer is None:
        raise HTTPException(404, detail="Cliente no encontrado")
    cust_svc.delete_customer(db, customer)
    db.commit()
