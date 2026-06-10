"""
JWT middleware — Fase 7.

Entrada: Authorization: Bearer <token> (emitido en POST /auth/login).
Salida: business_id del dueño para filtrar chats, pedidos y config del negocio.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from config.settings import JWT_EXPIRE_MINUTES, JWT_SECRET_KEY

ALGORITHM = "HS256"
_bearer = HTTPBearer(auto_error=False)


def _require_secret() -> str:
    key = (JWT_SECRET_KEY or "").strip()
    if not key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT_SECRET_KEY no configurado en el servidor",
        )
    return key


def create_access_token(
    *,
    business_id: str,
    subject: str = "owner",
    extra: dict[str, Any] | None = None,
) -> str:
    """Emite JWT con business_id para la app Flutter."""
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "business_id": business_id,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, _require_secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, _require_secret(), algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


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
