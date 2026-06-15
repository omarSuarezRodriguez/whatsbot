"""WhatsBot REST API — Fase 7."""

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
    f"sqlite:///{(ROOT / 'data' / 'test_whatsbot_api.db').as_posix()}",
)
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-phase7"
os.environ["WHATSBOT_OWNER_PIN"] = "testpin"


@pytest.fixture(scope="module")
def client():
    from infrastructure.database import init_db
    from api.main import create_app
    from services.business_service import ensure_default_business
    from infrastructure.database import session_scope

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


def test_login_rejects_bad_pin(client: TestClient):
    r = client.post(
        "/auth/login",
        json={"business_id": "default", "pin": "wrong"},
    )
    assert r.status_code == 401


def test_login_returns_refresh_token(client: TestClient):
    r = client.post(
        "/auth/login",
        json={"business_id": "default", "pin": "testpin"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["business_id"] == "default"


def test_refresh_issues_new_access_token(client: TestClient):
    login = client.post(
        "/auth/login",
        json={"business_id": "default", "pin": "testpin"},
    )
    assert login.status_code == 200, login.text
    refresh_token = login.json()["refresh_token"]

    refreshed = client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refreshed.status_code == 200, refreshed.text
    data = refreshed.json()
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["refresh_token"] != refresh_token

    headers = {"Authorization": f"Bearer {data['access_token']}"}
    r = client.get("/whatsbot/conversations", headers=headers)
    assert r.status_code == 200


def test_refresh_rejects_invalid_token(client: TestClient):
    r = client.post(
        "/auth/refresh",
        json={"refresh_token": "not-a-valid-token"},
    )
    assert r.status_code == 401


def test_whatsbot_requires_auth(client: TestClient):
    r = client.get("/whatsbot/conversations")
    assert r.status_code == 401


def test_put_and_get_intents(client: TestClient, auth_headers: dict):
    custom = {"menu": {"phrases": ["carta especial test"], "tokens": ["carta"], "route": "menu_node"}}
    r = client.put(
        "/whatsbot/business/intents",
        headers=auth_headers,
        json={"config": custom},
    )
    assert r.status_code == 200
    r2 = client.get("/whatsbot/business/intents", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["config"]["menu"]["phrases"] == ["carta especial test"]


def test_put_menu(client: TestClient, auth_headers: dict):
    items = [
        {
            "nombre": "Producto Fase7 Test",
            "precio": 9.99,
            "categoria": "Test",
            "id": "f7-1",
            "disponible": True,
        }
    ]
    r = client.put(
        "/whatsbot/business/menu",
        headers=auth_headers,
        json={"items": items},
    )
    assert r.status_code == 200
    names = [i["nombre"] for i in r.json()["items"]]
    assert "Producto Fase7 Test" in names


def test_gateway_uses_db_menu_and_prompts(client: TestClient, auth_headers: dict):
    """Gateway debe leer menú y prompts de BD cuando hay business_id."""
    from chatbot.runtime import reset_bot_context

    reset_bot_context()
    client.put(
        "/whatsbot/business/menu",
        headers=auth_headers,
        json={
            "items": [
                {
                    "nombre": "Sopa Gateway BD",
                    "precio": 5,
                    "categoria": "Platos",
                    "id": "gw-sopa",
                    "disponible": True,
                }
            ]
        },
    )
    client.put(
        "/whatsbot/business/prompts",
        headers=auth_headers,
        json={
            "config": {
                "empty_body_hint": "MENSAJE_CUSTOM_FASE7 vacio",
            }
        },
    )

    from chatbot.gateway import handle_incoming_message
    from services.business_config_loader import get_prompt

    assert "MENSAJE_CUSTOM_FASE7" in get_prompt("default", "empty_body_hint")

    with patch(
        "app.services.blocked_users_cache.BlockedUsersCache.is_blocked",
        return_value=False,
    ), patch(
        "app.core.flow_engine.FlowEngine.process_message",
        return_value="",
    ):
        result = handle_incoming_message(
            {
                "phone": "573009998877",
                "message": "hola",
                "business_id": "default",
            }
        )
    assert "MENSAJE_CUSTOM_FASE7" in str(result.get("response_text", ""))

    with patch(
        "app.services.blocked_users_cache.BlockedUsersCache.is_blocked",
        return_value=False,
    ):
        menu_result = handle_incoming_message(
            {
                "phone": "573009998877",
                "message": "menu",
                "business_id": "default",
            }
        )
    text = str(menu_result.get("response_text", ""))
    assert "Sopa Gateway BD" in text or "sopa gateway" in text.lower()


def test_send_message_client_id_idempotent(client: TestClient, auth_headers: dict):
    """OF-C: reintento con mismo client_id no reenvía Twilio ni duplica fila."""
    import uuid

    import scripts.migrate_client_id as migrate_client_id
    import scripts.migrate_message_status as migrate_message_status

    migrate_message_status.main()
    migrate_client_id.main()

    client_id = f"offline-{uuid.uuid4().hex[:12]}"
    payload = {
        "customer_wa_id": "573009991234",
        "body": "Mensaje idempotente",
        "client_id": client_id,
    }
    with patch("api.routes.whatsbot.send_whatsapp_message", return_value=True) as mock_send:
        r1 = client.post("/whatsbot/messages", headers=auth_headers, json=payload)
        r2 = client.post("/whatsbot/messages", headers=auth_headers, json=payload)

    assert r1.status_code == 201, r1.text
    assert r2.status_code == 201, r2.text
    assert r1.json()["id"] == r2.json()["id"]
    assert r1.json()["client_id"] == client_id
    assert mock_send.call_count == 1


def test_put_prompts_persist(client: TestClient, auth_headers: dict):
    r = client.put(
        "/whatsbot/business/prompts",
        headers=auth_headers,
        json={"config": {"error_generic": "Error personalizado F7"}},
    )
    assert r.status_code == 200
    r2 = client.get("/whatsbot/business/prompts", headers=auth_headers)
    assert r2.json()["config"]["error_generic"] == "Error personalizado F7"
