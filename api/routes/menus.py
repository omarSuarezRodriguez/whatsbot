"""Menu API per business (Fase 5)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.schemas import MenuItemCreate, MenuItemOut, MenuItemUpdate, MenuReplace
from infrastructure.database import get_db
from services import business_service as biz_svc
from services import menu_service as menu_svc

router = APIRouter(prefix="/businesses/{business_id}/menu", tags=["menus"])


def _require_business(db: Session, business_id: str) -> None:
    if not biz_svc.get_business(db, business_id):
        raise HTTPException(404, detail="Negocio no encontrado")


@router.get("", response_model=list[MenuItemOut])
def list_menu(
    business_id: str,
    available_only: bool = False,
    db: Session = Depends(get_db),
) -> list:
    _require_business(db, business_id)
    return menu_svc.list_menu_items(db, business_id, available_only=available_only)


@router.post("/items", response_model=MenuItemOut, status_code=201)
def create_item(
    business_id: str,
    body: MenuItemCreate,
    db: Session = Depends(get_db),
) -> MenuItemOut:
    _require_business(db, business_id)
    item = menu_svc.create_menu_item(
        db,
        business_id,
        nombre=body.nombre,
        precio=body.precio,
        categoria=body.categoria,
        external_id=body.external_id,
        disponible=body.disponible,
    )
    db.commit()
    return item


@router.put("/items/{item_id}", response_model=MenuItemOut)
def update_item(
    business_id: str,
    item_id: int,
    body: MenuItemUpdate,
    db: Session = Depends(get_db),
) -> MenuItemOut:
    _require_business(db, business_id)
    item = menu_svc.get_menu_item(db, business_id, item_id)
    if not item:
        raise HTTPException(404, detail="Producto no encontrado")
    menu_svc.update_menu_item(db, item, body.model_dump(exclude_unset=True))
    db.commit()
    return item


@router.put("", response_model=list[MenuItemOut])
def replace_menu(
    business_id: str,
    body: MenuReplace,
    db: Session = Depends(get_db),
) -> list:
    _require_business(db, business_id)
    items = menu_svc.replace_menu_items(db, business_id, body.items)
    db.commit()
    return items
