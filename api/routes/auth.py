"""
JWT auth — Fase 7.

Entrada: business_id + PIN del dueño (WHATSBOT_OWNER_PIN en .env).
Salida: access_token JWT con business_id para rutas /whatsbot/*.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.middleware.auth import create_access_token
from config.settings import WHATSBOT_OWNER_PIN
from infrastructure.database import get_db
from services import business_service as biz_svc

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    business_id: str = Field(..., min_length=1, max_length=64)
    pin: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    business_id: str
    business_name: str


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """
    Login dueño para app Flutter.

    Entrada: { business_id, pin }.
    Salida: JWT Bearer (claim business_id).
    """
    if body.pin != WHATSBOT_OWNER_PIN:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="PIN incorrecto")
    biz = biz_svc.get_business(db, body.business_id)
    if not biz:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Negocio no encontrado")
    token = create_access_token(business_id=biz.id, subject="owner")
    return LoginResponse(
        access_token=token,
        business_id=biz.id,
        business_name=biz.name,
    )
