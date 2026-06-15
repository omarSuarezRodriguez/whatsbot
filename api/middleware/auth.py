"""
JWT middleware.

Entrada: Authorization: Bearer <token> (emitido en POST /auth/login).
Salida: business_id del dueño para filtrar chats, pedidos y config del negocio.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from config.settings import (
    JWT_EXPIRE_MINUTES,
    JWT_REFRESH_EXPIRE_DAYS,
    JWT_SECRET_KEY,
    SUPERADMIN_API_KEY,
)

ALGORITHM = "HS256"
_bearer = HTTPBearer(auto_error=False)

# Fail-fast: refuse to start if JWT secret is obviously insecure.
_WEAK_SECRETS = {"", "changeme", "secret", "your-secret-key", "dev", "test"}


def _require_secret() -> str:
    key = (JWT_SECRET_KEY or "").strip()
    if not key or key.lower() in _WEAK_SECRETS:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT_SECRET_KEY no está configurado de forma segura en el servidor",
        )
    return key


def create_access_token(
    *,
    business_id: str,
    subject: str = "owner",
    extra: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "business_id": business_id,
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, _require_secret(), algorithm=ALGORITHM)


def create_refresh_token(
    *,
    business_id: str,
    subject: str = "owner",
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "business_id": business_id,
        "typ": "refresh",
        "jti": uuid4().hex,
        "iat": now,
        "exp": now + timedelta(days=JWT_REFRESH_EXPIRE_DAYS),
    }
    return jwt.encode(payload, _require_secret(), algorithm=ALGORITHM)


def _decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, _require_secret(), algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def decode_access_token(token: str) -> dict[str, Any]:
    payload = _decode_token(token)
    token_type = payload.get("typ")
    if token_type is not None and token_type != "access":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def decode_refresh_token(token: str) -> dict[str, Any]:
    payload = _decode_token(token)
    if payload.get("typ") != "refresh":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


async def get_current_business_id(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer),
    ],
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación requerida",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(credentials.credentials)
    business_id = str(payload.get("business_id", "")).strip()
    if not business_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token sin business_id")
    return business_id


async def require_superadmin(
    x_admin_key: Annotated[str | None, Header(alias="X-Admin-Key")] = None,
) -> None:
    """Protege operaciones cross-tenant (listar/crear negocios).
    Si SUPERADMIN_API_KEY no está configurado, bloquea toda operación."""
    key = (SUPERADMIN_API_KEY or "").strip()
    if not key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SUPERADMIN_API_KEY no configurado — operación deshabilitada",
        )
    if x_admin_key != key:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Clave de administrador inválida",
        )
