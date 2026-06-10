"""Message status + mark-read — Fase 11.5."""

from __future__ import annotations

import importlib.util
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
    f"sqlite:///{(ROOT / 'data' / 'test_message_status.db').as_posix()}",
)
os.environ["JWT_SECRET_KEY"] = "test-jwt-status"
os.environ["WHATSBOT_OWNER_PIN"] = "testpin"
os.environ["REALTIME_ENABLED"] = "true"
os.environ["FCM_ENABLED"] = "false"


def _run_status_migration() -> None:
    spec = importlib.util.spec_from_file_location(
        "migrate_message_status",
        ROOT / "scripts" / "migrate_message_status.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()


@pytest.fixture(scope="module")
def client():
    from infrastructure.database import init_db, session_scope
    from api.main import create_app
    from services.business_service import ensure_default_business

    init_db()
    _run_status_migration()
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


def test_owner_message_has_delivered_status(
    client: TestClient,
    auth_headers: dict,
):
    with patch("infrastructure.twilio_client.send_whatsapp_message", return_value="SM1"):
        r = client.post(
            "/whatsbot/messages",
            headers=auth_headers,
            json={"customer_wa_id": "573001112233", "body": "Con ticks"},
        )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["status"] in {"sent", "delivered"}
    assert data.get("is_admin") is True


def test_mark_read_updates_incoming(client: TestClient, auth_headers: dict):
    with patch("chatbot.gateway.handle_incoming_message") as mock_gw:
        mock_gw.return_value = {
            "response_text": "",
            "wa_id": "573005556677",
            "is_admin": False,
            "blocked": False,
        }
        client.post(
            "/webhook",
            data={
                "WaId": "573005556677",
                "From": "whatsapp:+573005556677",
                "To": "whatsapp:+14155238886",
                "Body": "Mensaje para leer",
            },
        )

    convs = client.get("/whatsbot/conversations", headers=auth_headers).json()
    conv_id = next(c["id"] for c in convs if "573005556677" in c["customer_wa_id"])

    r = client.post(
        f"/whatsbot/conversations/{conv_id}/mark-read",
        headers=auth_headers,
    )
    assert r.status_code == 204

    messages = client.get(
        f"/whatsbot/conversations/{conv_id}/messages",
        headers=auth_headers,
    ).json()
    incoming = [m for m in messages if m["direction"] == "incoming"]
    assert incoming
    assert incoming[-1]["status"] == "read"
    assert incoming[-1]["read_at"] is not None
