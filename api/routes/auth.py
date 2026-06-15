"""
JWT auth.

POST /auth/login → { business_id, pin } → access_token + refresh_token.
POST /auth/refresh → { refresh_token } → nuevo par de tokens.
PIN se valida contra el hash bcrypt almacenado en businesses.pin_hash.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.middleware.auth import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from infrastructure.database import get_db
from services import business_service as biz_svc

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    business_id: str = Field(..., min_length=1, max_length=64)
    pin: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    business_id: str
    business_name: str


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    business_id: str
    business_name: str


def _issue_tokens(*, business_id: str, business_name: str) -> tuple[str, str]:
    return (
        create_access_token(business_id=business_id, subject="owner"),
        create_refresh_token(business_id=business_id, subject="owner"),
    )


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """Login del dueño desde la app Flutter.  Valida PIN por negocio (bcrypt)."""
    biz = biz_svc.get_business(db, body.business_id)
    if not biz:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Negocio no encontrado")
    if not biz.pin_hash or not biz_svc.verify_pin(body.pin, biz.pin_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="PIN incorrecto")
    access_token, refresh_token = _issue_tokens(
        business_id=biz.id,
        business_name=biz.name,
    )
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        business_id=biz.id,
        business_name=biz.name,
    )


@router.post("/refresh", response_model=RefreshResponse)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)) -> RefreshResponse:
    """Renueva access token usando refresh token (app móvil, sesión larga)."""
    payload = decode_refresh_token(body.refresh_token)
    business_id = str(payload.get("business_id", "")).strip()
    if not business_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido")
    biz = biz_svc.get_business(db, business_id)
    if not biz:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Negocio no encontrado")
    access_token, refresh_token = _issue_tokens(
        business_id=biz.id,
        business_name=biz.name,
    )
    return RefreshResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        business_id=biz.id,
        business_name=biz.name,
    )
