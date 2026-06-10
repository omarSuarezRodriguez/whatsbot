"""End-to-end validation — Fase 10 + realtime Fase 11."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{(ROOT / 'data' / 'validate_system.db').as_posix()}",
)
os.environ.setdefault("JWT_SECRET_KEY", "validate-system-jwt")
os.environ.setdefault("WHATSBOT_OWNER_PIN", "validate-pin")
os.environ.setdefault("GOOGLE_SHEETS_ENABLED", "false")
os.environ.setdefault("REALTIME_ENABLED", "true")
os.environ.setdefault("FCM_ENABLED", "false")


def _migrate_message_status() -> None:
    spec = importlib.util.spec_from_file_location(
        "migrate_message_status",
        ROOT / "scripts" / "migrate_message_status.py",
    )
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.main()


def _ok(label: str) -> None:
    print(f"  OK  {label}")


def _fail(label: str, detail: str = "") -> None:
    print(f"  FAIL {label}" + (f" - {detail}" if detail else ""))


def main() -> int:
    print("=== validate_system (Fase 10 + 11 — E2E) ===\n")
    failures = 0
    client = None
    headers: dict[str, str] = {}

    # --- Setup ---
    try:
        from infrastructure.database import init_db, session_scope
        from services.business_service import ensure_default_business
        from chatbot.runtime import reset_bot_context

        init_db()
        _migrate_message_status()
        reset_bot_context()
        with session_scope() as db:
            ensure_default_business(db)
        _ok("init_db + default business")
    except Exception as exc:
        _fail("setup", str(exc))
        print(f"\n=== Resultado: {failures + 1} fallo(s) ===")
        return 1

    # --- 1. Gateway ---
    print("\n--- Gateway ---")
    try:
        from chatbot.gateway import handle_incoming_message

        result = handle_incoming_message(
            {
                "phone": "573009999999",
                "message": "hola",
                "business_id": "default",
            }
        )
        if result.get("response_text") and not result.get("is_admin"):
            _ok("gateway hola -> respuesta cliente")
        else:
            _fail("gateway hola", repr(result))
            failures += 1

        menu = handle_incoming_message(
            {
                "phone": "573009999999",
                "message": "menu",
                "business_id": "default",
            }
        )
        menu_text = str(menu.get("response_text", "")).lower()
        if menu_text and ("menu" in menu_text or "carta" in menu_text or "$" in menu_text):
            _ok("gateway menu -> contenido")
        else:
            _fail("gateway menu", menu_text[:100])
            failures += 1
    except Exception as exc:
        _fail("gateway", str(exc))
        failures += 1

    # --- 2. API webhook + persistencia ---
    print("\n--- API ---")
    try:
        from fastapi.testclient import TestClient
        from api.main import create_app
        from config.settings import TWILIO_WHATSAPP_FROM
        from models.message import Message

        client = TestClient(create_app())

        r = client.get("/health")
        health = r.json() if r.status_code == 200 else {}
        if r.status_code == 200 and health.get("status") == "ok":
            _ok("GET /health")
            if health.get("realtime_enabled"):
                _ok("health realtime_enabled=true")
            else:
                _fail("health realtime_enabled", str(health))
                failures += 1
        else:
            _fail("GET /health", str(r.status_code))
            failures += 1

        r = client.post(
            "/webhook",
            data={
                "WaId": "573008887777",
                "From": "whatsapp:+573008887777",
                "To": TWILIO_WHATSAPP_FROM or "whatsapp:+573242497352",
                "Body": "hola desde validate_system",
                "ProfileName": "Validate E2E",
            },
        )
        if r.status_code == 200:
            _ok("POST /webhook -> TwiML")
        else:
            _fail("POST /webhook", str(r.status_code))
            failures += 1

        with session_scope() as db:
            count = (
                db.query(Message)
                .filter(Message.direction == "incoming")
                .count()
            )
            if count >= 1:
                _ok(f"mensaje entrante en BD (count={count})")
            else:
                _fail("persistencia mensaje webhook")
                failures += 1
    except Exception as exc:
        _fail("API", str(exc))
        failures += 1

    # --- 3. WhatsBot auth + conversaciones ---
    print("\n--- WhatsBot API ---")
    try:
        r = client.post(
            "/auth/login",
            json={"business_id": "default", "pin": "validate-pin"},
        )
        if r.status_code == 200 and r.json().get("access_token"):
            _ok("POST /auth/login")
            token = r.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
        else:
            _fail("POST /auth/login", r.text[:120])
            headers = {}
            failures += 1

        if headers:
            r = client.get("/whatsbot/conversations", headers=headers)
            if r.status_code == 200:
                _ok(f"GET /whatsbot/conversations ({len(r.json())} chats)")
            else:
                _fail("GET /whatsbot/conversations", str(r.status_code))
                failures += 1
    except Exception as exc:
        _fail("WhatsBot API", str(exc))
        failures += 1

    # --- 4. Flujo pedido: notify admin + aprobar desde app ---
    print("\n--- Flujo pedido ---")
    whatsapp_log: list[tuple[str, str]] = []

    def _fake_send(_self, to_number: str, body: str) -> bool:
        whatsapp_log.append((to_number, body))
        return True

    try:
        from app.integrations.google_sheets import GoogleSheetsClient
        from chatbot.runtime import get_bot_context
        from services import notification_service as notify

        ctx = get_bot_context(start_background=False)
        sheets: GoogleSheetsClient = ctx.admin_service.sheets
        order_id = sheets.create_order(
            wa_id="573007776666",
            items=[{"nombre": "Pizza validate", "qty": 1, "subtotal": 12.0}],
            total=12.0,
            status="pending",
            customer_name="Cliente E2E",
        )

        with patch(
            "app.services.admin_service.AdminService._send_whatsapp",
            _fake_send,
        ):
            notify.on_order_pending(
                sheets.get_order(order_id) or {"order_id": order_id},
                business_id="default",
            )
            if any("CONFIRMAR" in body for _, body in whatsapp_log):
                _ok("notify admin -> CONFIRMAR en mensaje")
            else:
                _fail("notify admin", str(whatsapp_log))
                failures += 1

            whatsapp_log.clear()
            r = client.post(
                f"/whatsbot/orders/{order_id}/approve",
                headers=headers,
            )
            if r.status_code == 200 and r.json().get("ok"):
                _ok(f"POST /whatsbot/orders/{order_id}/approve")
            else:
                _fail("approve desde app", r.text[:120])
                failures += 1

            if sheets.get_order(order_id)["status"] == "confirmed":
                _ok("pedido confirmado en Sheets")
            else:
                _fail("estado pedido Sheets", sheets.get_order(order_id).get("status"))
                failures += 1

            if any(
                "573007776666" in to.replace("whatsapp:", "").replace("+", "")
                for to, body in whatsapp_log
                if "confirmado" in body.lower()
            ):
                _ok("cliente notificado tras aprobar desde app")
            else:
                _fail("notificación cliente", str(whatsapp_log))
                failures += 1
    except Exception as exc:
        _fail("flujo pedido", str(exc))
        failures += 1

    # --- 5. Edición menú/prompts desde API → gateway ---
    print("\n--- Edicion BD -> gateway ---")
    try:
        reset_bot_context()
        client.put(
            "/whatsbot/business/menu",
            headers=headers,
            json={
                "items": [
                    {
                        "nombre": "Plato Validate System",
                        "precio": 7.5,
                        "categoria": "Test",
                        "id": "vs-1",
                        "disponible": True,
                    }
                ]
            },
        )
        menu_result = handle_incoming_message(
            {
                "phone": "573009999999",
                "message": "menu",
                "business_id": "default",
            }
        )
        menu_out = str(menu_result.get("response_text", ""))
        if "Plato Validate System" in menu_out or "validate system" in menu_out.lower():
            _ok("menu editado en app visible en gateway")
        else:
            _fail("menu BD -> gateway", menu_out[:120])
            failures += 1

        client.put(
            "/whatsbot/business/prompts",
            headers=headers,
            json={"config": {"empty_body_hint": "BIENVENIDA_VALIDATE_SYSTEM"}},
        )
        with patch(
            "app.core.flow_engine.FlowEngine.process_message",
            return_value="",
        ):
            welcome = handle_incoming_message(
                {
                    "phone": "573009999999",
                    "message": "hola",
                    "business_id": "default",
                }
            )
        if "BIENVENIDA_VALIDATE_SYSTEM" in str(welcome.get("response_text", "")):
            _ok("prompt editado en app visible en gateway")
        else:
            _fail("prompt BD -> gateway", str(welcome.get("response_text", ""))[:120])
            failures += 1
    except Exception as exc:
        _fail("edición BD", str(exc))
        failures += 1

    # --- 6. Realtime WebSocket + estados (Fase 11) ---
    print("\n--- Realtime (Fase 11) ---")
    try:
        if not headers:
            raise RuntimeError("sin JWT de login")

        r = client.post(
            "/whatsbot/device-token",
            headers=headers,
            json={"token": "validate-fcm-token-e2e", "platform": "android"},
        )
        if r.status_code == 204:
            _ok("POST /whatsbot/device-token")
        else:
            _fail("device-token", str(r.status_code))
            failures += 1

        with client.websocket_connect(
            f"/whatsbot/ws?token={headers['Authorization'].split(' ', 1)[1]}"
        ) as ws:
            hello = json.loads(ws.receive_text())
            if hello.get("type") == "connected":
                _ok("WS /whatsbot/ws connected")
            else:
                _fail("WS connected", str(hello))
                failures += 1

            ws.send_text(json.dumps({"type": "ping"}))
            pong = json.loads(ws.receive_text())
            if pong.get("type") == "pong":
                _ok("WS ping/pong")
            else:
                _fail("WS pong", str(pong))
                failures += 1

            with patch("infrastructure.twilio_client.send_whatsapp_message", return_value="SMVS"):
                r = client.post(
                    "/whatsbot/messages",
                    headers=headers,
                    json={
                        "customer_wa_id": "573008887777",
                        "body": "Mensaje realtime validate",
                    },
                )
            if r.status_code != 201:
                _fail("owner message for WS", r.text[:120])
                failures += 1
            else:
                msg_data = r.json()
                if msg_data.get("status") in {"sent", "delivered"}:
                    _ok("mensaje dueño con status")
                else:
                    _fail("message status", str(msg_data.get("status")))
                    failures += 1

                got_new = False
                for _ in range(6):
                    data = json.loads(ws.receive_text())
                    if data.get("type") == "message.new":
                        got_new = True
                        break
                if got_new:
                    _ok("WS message.new tras envío dueño")
                else:
                    _fail("WS message.new")
                    failures += 1

        convs = client.get("/whatsbot/conversations", headers=headers).json()
        if convs:
            conv_id = convs[0]["id"]
            r = client.post(
                f"/whatsbot/conversations/{conv_id}/mark-read",
                headers=headers,
            )
            if r.status_code == 204:
                _ok("POST mark-read")
            else:
                _fail("mark-read", str(r.status_code))
                failures += 1

            from datetime import datetime, timedelta, timezone

            since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            r = client.get(
                "/whatsbot/conversations",
                headers=headers,
                params={"since": since},
            )
            if r.status_code == 200:
                _ok("GET conversations?since=")
            else:
                _fail("conversations since", str(r.status_code))
                failures += 1
        else:
            _fail("conversaciones para mark-read")
            failures += 1
    except Exception as exc:
        _fail("realtime Fase 11", str(exc))
        failures += 1

    print(f"\n=== Resultado: {failures} fallo(s) ===")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
