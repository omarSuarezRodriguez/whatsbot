"""Reservation CRUD per business (DB source of truth)."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from models.reservation import Reservation

logger = logging.getLogger(__name__)


def _new_reservation_id() -> str:
    return f"RES-{uuid.uuid4().hex[:8].upper()}"


def list_reservations(
    db: Session,
    business_id: str,
    *,
    status: str | None = None,
    limit: int = 200,
) -> list[Reservation]:
    q = db.query(Reservation).filter(Reservation.business_id == business_id)
    if status:
        q = q.filter(Reservation.status == status)
    return q.order_by(Reservation.created_at.desc()).limit(limit).all()


def create_reservation(
    db: Session,
    business_id: str,
    *,
    wa_id: str,
    personas: int,
    fecha: str,
    hora: str,
    status: str = "pending",
) -> Reservation:
    reservation = Reservation(
        business_id=business_id,
        reservation_id=_new_reservation_id(),
        wa_id=wa_id,
        personas=personas,
        fecha=fecha,
        hora=hora,
        status=status,
    )
    db.add(reservation)
    db.flush()
    return reservation
