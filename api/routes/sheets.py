"""
Google Sheets sync API — Fase 8 (opcional).

JWT requerido (mismo dueño que /whatsbot).
PostgreSQL = verdad; Sheets = espejo editable.

Rutas:
  GET  /sheets/status
  PUT  /sheets/settings
  POST /sheets/sync
  POST /sheets/sync/menu
  POST /sheets/sync/orders
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.middleware.auth import get_current_business_id
from api.schemas import (
    SheetsSettingsUpdate,
    SheetsStatusOut,
    SheetsSyncAllOut,
    SheetsSyncResult,
)
from infrastructure.database import get_db
from services import business_service as biz_svc
from services import sheets_sync_service as sheets_svc

router = APIRouter(prefix="/sheets", tags=["sheets"])

BusinessId = Annotated[str, Depends(get_current_business_id)]


def _require_business(db: Session, business_id: str):
    biz = biz_svc.get_business(db, business_id)
    if not biz:
        raise HTTPException(404, detail="Negocio no encontrado")
    return biz


@router.get("/status", response_model=SheetsStatusOut)
def sheets_status(
    business_id: BusinessId,
    db: Session = Depends(get_db),
) -> SheetsStatusOut:
    """Estado global + negocio + conexión (para toggle en Ajustes Flutter)."""
    _require_business(db, business_id)
    return SheetsStatusOut(**sheets_svc.get_status(db, business_id))


@router.put("/settings", response_model=SheetsStatusOut)
def update_sheets_settings(
    body: SheetsSettingsUpdate,
    business_id: BusinessId,
    db: Session = Depends(get_db),
) -> SheetsStatusOut:
    """Activa/desactiva espejo Sheets por negocio."""
    _require_business(db, business_id)
    try:
        sheets_svc.set_business_sheets_settings(
            db,
            business_id,
            sheets_enabled=body.sheets_enabled,
            google_spreadsheet_id=body.google_spreadsheet_id,
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    return SheetsStatusOut(**sheets_svc.get_status(db, business_id))


@router.post("/sync", response_model=SheetsSyncAllOut)
def sync_all(
    business_id: BusinessId,
    db: Session = Depends(get_db),
) -> SheetsSyncAllOut:
    """Sincroniza menú y pedidos BD → Sheets."""
    _require_business(db, business_id)
    result = sheets_svc.sync_all(db, business_id)
    return SheetsSyncAllOut(
        ok=result["ok"],
        skipped=result.get("skipped", False),
        menu=SheetsSyncResult(**result["menu"]),
        orders=SheetsSyncResult(**result["orders"]),
    )


@router.post("/sync/menu", response_model=SheetsSyncResult)
def sync_menu(
    business_id: BusinessId,
    db: Session = Depends(get_db),
) -> SheetsSyncResult:
    """Solo menú BD → hoja MENU."""
    _require_business(db, business_id)
    return SheetsSyncResult(**sheets_svc.sync_menu(db, business_id))


@router.post("/sync/orders", response_model=SheetsSyncResult)
def sync_orders(
    business_id: BusinessId,
    db: Session = Depends(get_db),
) -> SheetsSyncResult:
    """Solo pedidos BD → hoja ORDERS."""
    _require_business(db, business_id)
    return SheetsSyncResult(**sheets_svc.sync_orders(db, business_id))
