"""Menu API per business — JWT required, tenant-scoped."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.middleware.auth import get_current_business_id
from api.schemas import MenuItemCreate, MenuItemOut, MenuItemUpdate, MenuReplace
from infrastructure.database import get_db
from services import business_service as biz_svc
from services import menu_service as menu_svc

router = APIRouter(prefix="/businesses/{business_id}/menu", tags=["menus"])

BusinessId = Annotated[str, Depends(get_current_business_id)]


def _require_business(db: Session, business_id: str, token_business_id: str) -> None:
    if token_business_id != business_id:
        raise HTTPException(403, detail="No autorizado para este negocio")
    if not biz_svc.get_business(db, business_id):
        raise HTTPException(404, detail="Negocio no encontrado")


@router.get("", response_model=list[MenuItemOut])
def list_menu(
    business_id: str,
    token_business_id: BusinessId,
    available_only: bool = False,
    db: Session = Depends(get_db),
) -> list:
    _require_business(db, business_id, token_business_id)
    return menu_svc.list_menu_items(db, business_id, available_only=available_only)


@router.post("/items", response_model=MenuItemOut, status_code=201)
def create_item(
    business_id: str,
    body: MenuItemCreate,
    token_business_id: BusinessId,
    db: Session = Depends(get_db),
) -> MenuItemOut:
    _require_business(db, business_id, token_business_id)
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
    token_business_id: BusinessId,
    db: Session = Depends(get_db),
) -> MenuItemOut:
    _require_business(db, business_id, token_business_id)
    item = menu_svc.get_menu_item(db, business_id, item_id)
    if not item:
        raise HTTPException(404, detail="Producto no encontrado")
    menu_svc.update_menu_item(db, item, body.model_dump(exclude_unset=True))
    db.commit()
    return item


@router.delete("/items/{item_id}", status_code=204, response_model=None)
def delete_item(
    business_id: str,
    item_id: int,
    token_business_id: BusinessId,
    db: Session = Depends(get_db),
) -> None:
    _require_business(db, business_id, token_business_id)
    item = menu_svc.get_menu_item(db, business_id, item_id)
    if not item:
        raise HTTPException(404, detail="Producto no encontrado")
    db.delete(item)
    db.commit()


@router.put("", response_model=list[MenuItemOut])
def replace_menu(
    business_id: str,
    body: MenuReplace,
    token_business_id: BusinessId,
    db: Session = Depends(get_db),
) -> list:
    _require_business(db, business_id, token_business_id)
    items = menu_svc.replace_menu_items(db, business_id, body.items)
    db.commit()
    return items
