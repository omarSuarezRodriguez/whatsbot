"""FCM device tokens + push hooks — Fase 11.4."""

from __future__ import annotations

import asyncio
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{(ROOT / 'data' / 'test_push_api.db').as_posix()}",
)
os.environ["JWT_SECRET_KEY"] = "test-jwt-push"
os.environ["WHATSBOT_OWNER_PIN"] = "testpin"
os.environ["REALTIME_ENABLED"] = "true"
os.environ["FCM_ENABLED"] = "true"


@pytest.fixture(scope="module")
def client():
    from infrastructure.database import init_db, session_scope
    from api.main import create_app
    from services.business_service import ensure_default_business

    init_db()
    with session_scope() as db:
        ensure_default_business(db)
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    r = client.post(
        "/auth/login",
        json={"business_id": "default", "pin": "testpin"},
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_register_device_token(client: TestClient, auth_headers: dict):
    r = client.post(
        "/whatsbot/device-token",
        headers=auth_headers,
        json={"token": "fcm-test-token-abc123", "platform": "android"},
    )
    assert r.status_code == 204

    from infrastructure.database import session_scope
    from services import device_token_service as token_svc

    with session_scope() as db:
        rows = token_svc.list_device_tokens(db, "default")
        tokens = [row.token for row in rows]
    assert "fcm-test-token-abc123" in tokens


def test_unregister_device_token(client: TestClient, auth_headers: dict):
    token = "fcm-test-token-remove"
    client.post(
        "/whatsbot/device-token",
        headers=auth_headers,
        json={"token": token, "platform": "ios"},
    )
    r = client.request(
        "DELETE",
        "/whatsbot/device-token",
        headers=auth_headers,
        json={"token": token, "platform": "ios"},
    )
    assert r.status_code == 204

    from infrastructure.database import session_scope
    from services import device_token_service as token_svc

    with session_scope() as db:
        rows = token_svc.list_device_tokens(db, "default")
        tokens = [row.token for row in rows]
    assert token not in tokens


def test_push_when_no_websocket():
    asyncio.run(_test_push_when_no_websocket())


async def _test_push_when_no_websocket():
    from infrastructure.database import init_db, session_scope
    from models.conversation import Conversation
    from models.message import Message
    from services.push_service import maybe_push_incoming_message

    init_db()
    now_import = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)

    msg = Message(
        id=1,
        conversation_id=10,
        direction="incoming",
        body="Hola push test",
        wa_id="573001234567",
        is_admin=False,
        channel="whatsapp",
        created_at=now_import,
    )
    conv = Conversation(
        id=10,
        business_id="default",
        customer_wa_id="573001234567",
        customer_name="Cliente Push",
        last_message_preview="Hola push test",
        last_message_at=now_import,
        created_at=now_import,
        updated_at=now_import,
    )

    from services import device_token_service as token_svc_mod
    from models.device_token import DeviceToken

    with session_scope() as db:
        db.query(DeviceToken).filter(DeviceToken.business_id == "default").delete(
            synchronize_session=False
        )
        token_svc_mod.upsert_device_token(
            db,
            business_id="default",
            token="device-push-mock",
            platform="android",
        )
        db.commit()

    messaging_mod = types.ModuleType("firebase_admin.messaging")
    mock_send = MagicMock(return_value="projects/test/messages/1")
    messaging_mod.send = mock_send
    messaging_mod.Message = MagicMock(return_value=MagicMock())
    messaging_mod.Notification = MagicMock()
    messaging_mod.AndroidConfig = MagicMock()
    messaging_mod.AndroidNotification = MagicMock()
    messaging_mod.APNSConfig = MagicMock()
    messaging_mod.APNSPayload = MagicMock()
    messaging_mod.Aps = MagicMock()
    firebase_mod = types.ModuleType("firebase_admin")

    with patch.dict(
        sys.modules,
        {
            "firebase_admin": firebase_mod,
            "firebase_admin.messaging": messaging_mod,
        },
    ), patch("services.push_service._init_firebase", return_value=True):
        with session_scope() as db:
            sent = await maybe_push_incoming_message(
                db,
                "default",
                msg,
                conv,
                ws_delivered=0,
            )
    assert sent == 1
    mock_send.assert_called_once()


def test_no_push_when_websocket_delivered():
    asyncio.run(_test_no_push_when_websocket_delivered())


async def _test_no_push_when_websocket_delivered():
    from services.push_service import maybe_push_incoming_message
    from infrastructure.database import session_scope
    from models.conversation import Conversation
    from models.message import Message

    tz = __import__("datetime").timezone.utc
    now = __import__("datetime").datetime.now(tz)
    msg = Message(
        id=2,
        conversation_id=11,
        direction="incoming",
        body="No push",
        wa_id="573009999999",
        is_admin=False,
        channel="whatsapp",
        created_at=now,
    )
    conv = Conversation(
        id=11,
        business_id="default",
        customer_wa_id="573009999999",
        created_at=now,
        updated_at=now,
    )

    with patch("services.push_service._init_firebase") as mock_init:
        with session_scope() as db:
            sent = await maybe_push_incoming_message(
                db,
                "default",
                msg,
                conv,
                ws_delivered=2,
            )
    assert sent == 0
    mock_init.assert_not_called()
