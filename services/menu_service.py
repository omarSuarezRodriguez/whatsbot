"""Menu CRUD per business (API layer — Fase 5)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from models.menu import MenuItem

logger = logging.getLogger(__name__)


def list_menu_items(db: Session, business_id: str, *, available_only: bool = False) -> list[MenuItem]:
    q = db.query(MenuItem).filter(MenuItem.business_id == business_id)
    if available_only:
        q = q.filter(MenuItem.disponible.is_(True))
    return q.order_by(MenuItem.categoria, MenuItem.nombre).all()


def get_menu_item(db: Session, business_id: str, item_id: int) -> MenuItem | None:
    return (
        db.query(MenuItem)
        .filter(MenuItem.business_id == business_id, MenuItem.id == item_id)
        .one_or_none()
    )


def create_menu_item(
    db: Session,
    business_id: str,
    *,
    nombre: str,
    precio: float,
    categoria: str = "",
    external_id: str = "",
    disponible: bool = True,
) -> MenuItem:
    item = MenuItem(
        business_id=business_id,
        external_id=external_id or str(db.query(MenuItem).count() + 1),
        nombre=nombre,
        precio=precio,
        categoria=categoria,
        disponible=disponible,
    )
    db.add(item)
    db.flush()
    return item


def update_menu_item(
    db: Session,
    item: MenuItem,
    data: dict[str, Any],
) -> MenuItem:
    for key in ("nombre", "precio", "categoria", "external_id", "disponible"):
        if key in data and data[key] is not None:
            setattr(item, key, data[key])
    db.flush()
    return item


def delete_menu_item(db: Session, item: MenuItem) -> None:
    db.delete(item)


def replace_menu_items(
    db: Session,
    business_id: str,
    items: list[dict[str, Any]],
) -> list[MenuItem]:
    db.query(MenuItem).filter(MenuItem.business_id == business_id).delete()
    created: list[MenuItem] = []
    for raw in items:
        created.append(
            create_menu_item(
                db,
                business_id,
                nombre=str(raw.get("nombre", "")),
                precio=float(raw.get("precio", 0)),
                categoria=str(raw.get("categoria", "")),
                external_id=str(raw.get("id", raw.get("external_id", ""))),
                disponible=bool(raw.get("disponible", True)),
            )
        )
    return created
