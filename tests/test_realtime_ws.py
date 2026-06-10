"""WebSocket realtime — Fase 11.2."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{(ROOT / 'data' / 'test_realtime_ws.db').as_posix()}",
)
os.environ["JWT_SECRET_KEY"] = "test-jwt-realtime"
os.environ["WHATSBOT_OWNER_PIN"] = "testpin"
os.environ["REALTIME_ENABLED"] = "true"


def _fresh_test_database() -> None:
    """Stale SQLite test files skip new columns; recreate from current models."""
    import infrastructure.database as db_mod

    test_db = ROOT / "data" / "test_realtime_ws.db"
    if test_db.exists():
        test_db.unlink()
    db_mod._engine = None
    db_mod._SessionLocal = None
    db_mod.init_db()


@pytest.fixture(scope="module")
def client():
    from infrastructure.database import session_scope
    from api.main import create_app
    from services.business_service import ensure_default_business

    _fresh_test_database()
    with session_scope() as db:
        ensure_default_business(db)
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_token(client: TestClient) -> str:
    r = client.post(
        "/auth/login",
        json={"business_id": "default", "pin": "testpin"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _recv_json(ws) -> dict:
    return json.loads(ws.receive_text())


def test_ws_rejects_missing_token(client: TestClient):
    with pytest.raises(Exception):
        with client.websocket_connect("/whatsbot/ws"):
            pass


def test_ws_rejects_invalid_token(client: TestClient):
    with pytest.raises(Exception):
        with client.websocket_connect("/whatsbot/ws?token=not-a-jwt"):
            pass


def test_ws_connects_and_pong(client: TestClient, auth_token: str):
    with client.websocket_connect(f"/whatsbot/ws?token={auth_token}") as ws:
        hello = _recv_json(ws)
        assert hello["type"] == "connected"
        assert hello["business_id"] == "default"

        ws.send_text(json.dumps({"type": "ping"}))
        pong = _recv_json(ws)
        assert pong["type"] == "pong"


def test_owner_message_emits_message_new(client: TestClient, auth_token: str):
    with patch("infrastructure.twilio_client.send_whatsapp_message", return_value="SM123"):
        with client.websocket_connect(f"/whatsbot/ws?token={auth_token}") as ws:
            _recv_json(ws)  # connected

            r = client.post(
                "/whatsbot/messages",
                headers={"Authorization": f"Bearer {auth_token}"},
                json={
                    "customer_wa_id": "573001112233",
                    "body": "Hola desde test realtime",
                },
            )
            assert r.status_code == 201, r.text
            saved_id = r.json()["id"]

            events = []
            for _ in range(4):
                data = _recv_json(ws)
                events.append(data)
                if data.get("type") == "message.new":
                    break

            msg_events = [e for e in events if e.get("type") == "message.new"]
            assert msg_events, f"expected message.new, got {events}"
            assert msg_events[0]["message"]["id"] == saved_id
            assert msg_events[0]["message"]["body"] == "Hola desde test realtime"
            assert msg_events[0]["conversation"]["customer_wa_id"]


def test_two_clients_same_business_receive_broadcast(
    client: TestClient,
    auth_token: str,
):
    with patch("infrastructure.twilio_client.send_whatsapp_message", return_value="SM456"):
        with client.websocket_connect(f"/whatsbot/ws?token={auth_token}") as ws1:
            with client.websocket_connect(f"/whatsbot/ws?token={auth_token}") as ws2:
                _recv_json(ws1)
                _recv_json(ws2)

                r = client.post(
                    "/whatsbot/messages",
                    headers={"Authorization": f"Bearer {auth_token}"},
                    json={
                        "customer_wa_id": "573004445566",
                        "body": "Multidispositivo",
                    },
                )
                assert r.status_code == 201

                def wait_message_new(ws):
                    for _ in range(6):
                        data = _recv_json(ws)
                        if data.get("type") == "message.new":
                            return data
                    return None

                e1 = wait_message_new(ws1)
                e2 = wait_message_new(ws2)
                assert e1 is not None
                assert e2 is not None
                assert e1["message"]["body"] == "Multidispositivo"
                assert e2["message"]["body"] == "Multidispositivo"


def test_webhook_incoming_emits_message_new(client: TestClient, auth_token: str):
    with patch("chatbot.gateway.handle_incoming_message") as mock_gw:
        mock_gw.return_value = {
            "response_text": "",
            "wa_id": "573007778899",
            "is_admin": False,
            "blocked": False,
        }
        with client.websocket_connect(f"/whatsbot/ws?token={auth_token}") as ws:
            _recv_json(ws)

            r = client.post(
                "/webhook",
                data={
                    "WaId": "573007778899",
                    "From": "whatsapp:+573007778899",
                    "To": "whatsapp:+14155238886",
                    "Body": "Mensaje cliente WS test",
                    "ProfileName": "Cliente Test",
                },
            )
            assert r.status_code == 200

            event = None
            for _ in range(6):
                data = _recv_json(ws)
                if data.get("type") == "message.new":
                    event = data
                    break
            assert event is not None
            assert event["message"]["direction"] == "incoming"
            assert "Mensaje cliente WS test" in event["message"]["body"]


def test_conversations_since_filter(client: TestClient, auth_token: str):
    headers = {"Authorization": f"Bearer {auth_token}"}
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    r = client.get("/whatsbot/conversations", headers=headers, params={"since": future})
    assert r.status_code == 200
    assert r.json() == []

    with patch("infrastructure.twilio_client.send_whatsapp_message", return_value="SM789"):
        client.post(
            "/whatsbot/messages",
            headers=headers,
            json={"customer_wa_id": "573008889900", "body": "Para filtro since"},
        )

    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    r2 = client.get("/whatsbot/conversations", headers=headers, params={"since": past})
    assert r2.status_code == 200
    wa_ids = [c["customer_wa_id"] for c in r2.json()]
    assert any("573008889900" in w for w in wa_ids)


def test_messages_after_id_filter(client: TestClient, auth_token: str):
    headers = {"Authorization": f"Bearer {auth_token}"}
    with patch("infrastructure.twilio_client.send_whatsapp_message", return_value="SM999"):
        r1 = client.post(
            "/whatsbot/messages",
            headers=headers,
            json={"customer_wa_id": "573001110000", "body": "Primero"},
        )
        r2 = client.post(
            "/whatsbot/messages",
            headers=headers,
            json={"customer_wa_id": "573001110000", "body": "Segundo"},
        )
    assert r1.status_code == 201 and r2.status_code == 201
    first_id = r1.json()["id"]
    convs = client.get("/whatsbot/conversations", headers=headers).json()
    conv_id = next(c["id"] for c in convs if "573001110000" in c["customer_wa_id"])

    all_msgs = client.get(
        f"/whatsbot/conversations/{conv_id}/messages",
        headers=headers,
    ).json()
    incremental = client.get(
        f"/whatsbot/conversations/{conv_id}/messages",
        headers=headers,
        params={"after_id": first_id},
    ).json()
    assert len(incremental) == 1
    assert incremental[0]["body"] == "Segundo"
    assert len(all_msgs) >= 2
