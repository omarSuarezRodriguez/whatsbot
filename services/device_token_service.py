"""Persist FCM/APNs tokens for push notifications — Fase 11.4."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models.device_token import DeviceToken

logger = logging.getLogger(__name__)


def _normalize_platform(platform: str) -> str:
    value = (platform or "android").strip().lower()
    return value if value in {"android", "ios"} else "android"


def upsert_device_token(
    db: Session,
    *,
    business_id: str,
    token: str,
    platform: str = "android",
) -> DeviceToken:
    """Register or refresh a device token for the business."""
    clean_token = token.strip()
    plat = _normalize_platform(platform)
    now = datetime.now(timezone.utc)
    row = (
        db.query(DeviceToken)
        .filter(
            DeviceToken.business_id == business_id,
            DeviceToken.token == clean_token,
        )
        .one_or_none()
    )
    if row is None:
        row = DeviceToken(
            business_id=business_id,
            token=clean_token,
            platform=plat,
            updated_at=now,
        )
        db.add(row)
    else:
        row.platform = plat
        row.updated_at = now
    db.flush()
    logger.info("Device token upserted business=%s platform=%s", business_id, plat)
    return row


def delete_device_token(
    db: Session,
    *,
    business_id: str,
    token: str,
) -> bool:
    clean_token = token.strip()
    deleted = (
        db.query(DeviceToken)
        .filter(
            DeviceToken.business_id == business_id,
            DeviceToken.token == clean_token,
        )
        .delete(synchronize_session=False)
    )
    if deleted:
        logger.info("Device token removed business=%s", business_id)
    return bool(deleted)


def list_device_tokens(db: Session, business_id: str) -> list[DeviceToken]:
    return (
        db.query(DeviceToken)
        .filter(DeviceToken.business_id == business_id)
        .order_by(DeviceToken.updated_at.desc())
        .all()
    )
