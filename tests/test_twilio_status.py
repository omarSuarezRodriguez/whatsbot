"""Tests for Twilio status callback webhook."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{(ROOT / 'data' / 'test_twilio_status.db').as_posix()}",
)
os.environ["JWT_SECRET_KEY"] = "test-jwt-twilio-status"
os.environ["WHATSBOT_OWNER_PIN"] = "testpin"
os.environ["REALTIME_ENABLED"] = "true"


@pytest.fixture(scope="module")
def client():
    from infrastructure.database import init_db, session_scope
    from api.main import create_app
    from services.business_service import ensure_default_business

    test_db = ROOT / "data" / "test_twilio_status.db"
    if test_db.exists():
        test_db.unlink()
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


def test_status_callback_updates_owner_message(
    client: TestClient,
    auth_headers: dict,
):
    with patch(
        "api.routes.whatsbot.send_whatsapp_message",
        return_value="SM_STATUS_TEST",
    ):
        r = client.post(
            "/whatsbot/messages",
            headers=auth_headers,
            json={"customer_wa_id": "573009998877", "body": "Con callback"},
        )
    assert r.status_code == 201, r.text
    msg_id = r.json()["id"]
    assert r.json().get("twilio_sid") == "SM_STATUS_TEST"
    assert r.json()["status"] == "sent"

    status_r = client.post(
        "/webhook/status",
        data={
            "MessageSid": "SM_STATUS_TEST",
            "MessageStatus": "delivered",
            "To": "whatsapp:+573009998877",
            "From": "whatsapp:+14155238886",
        },
    )
    assert status_r.status_code == 204

    convs = client.get("/whatsbot/conversations", headers=auth_headers).json()
    conv_id = next(c["id"] for c in convs if "573009998877" in c["customer_wa_id"])
    messages = client.get(
        f"/whatsbot/conversations/{conv_id}/messages",
        headers=auth_headers,
    ).json()
    owner = next(m for m in messages if m["id"] == msg_id)
    assert owner["status"] == "delivered"
    assert owner["delivered_at"] is not None


def test_incoming_webhook_dedup_by_sid(client: TestClient, auth_headers: dict):
    with patch("chatbot.gateway.handle_incoming_message") as mock_gw:
        mock_gw.return_value = {
            "response_text": "",
            "wa_id": "573006665544",
            "is_admin": False,
            "blocked": False,
        }
        payload = {
            "WaId": "573006665544",
            "From": "whatsapp:+573006665544",
            "To": "whatsapp:+14155238886",
            "Body": "Mensaje dedup",
            "MessageSid": "SM_DEDUP_1",
        }
        r1 = client.post("/webhook", data=payload)
        r2 = client.post("/webhook", data=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200

    convs = client.get("/whatsbot/conversations", headers=auth_headers).json()
    conv_id = next(c["id"] for c in convs if "573006665544" in c["customer_wa_id"])
    messages = client.get(
        f"/whatsbot/conversations/{conv_id}/messages",
        headers=auth_headers,
    ).json()
    deduped = [m for m in messages if m.get("twilio_sid") == "SM_DEDUP_1"]
    assert len(deduped) == 1
