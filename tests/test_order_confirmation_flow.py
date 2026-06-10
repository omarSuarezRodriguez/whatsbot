"""
Flujo confirmación admin legacy (Fase 6).

Cliente pide → notify admin → CONFIRMAR → cliente notificado.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{(ROOT / 'data' / 'test_orders.db').as_posix()}",
)


@pytest.fixture(autouse=True)
def reset_context():
    from chatbot.runtime import reset_bot_context

    reset_bot_context()
    yield
    reset_bot_context()


@pytest.fixture
def whatsapp_log():
    """Registra destinos y cuerpos de _send_whatsapp sin Twilio real."""
    sent: list[tuple[str, str]] = []

    def _fake_send(_self, to_number: str, body: str) -> bool:
        sent.append((to_number, body))
        return True

    with patch(
        "app.services.admin_service.AdminService._send_whatsapp",
        _fake_send,
    ):
        yield sent


def test_notify_admin_on_pending_order(whatsapp_log):
    from config.settings import ADMIN_WHATSAPP_NUMBER
    from services import notification_service as notify

    order = {
        "order_id": "ORD-TEST0001",
        "wa_id": "573001112233",
        "items": [{"nombre": "Pizza", "qty": 1, "subtotal": 10.0}],
        "total": 10.0,
        "customer_name": "Test Cliente",
        "address": "Calle 1",
        "delivery_type": "domicilio",
        "status": "pending",
    }
    notify.notify_admin_new_order(order)

    assert len(whatsapp_log) >= 1
    admin_msg = whatsapp_log[0]
    assert ADMIN_WHATSAPP_NUMBER.replace("whatsapp:", "") in admin_msg[0].replace("+", "") or admin_msg[0]
    assert "ORD-TEST0001" in admin_msg[1]
    assert "CONFIRMAR" in admin_msg[1]


def test_admin_confirm_notifies_customer(whatsapp_log):
    from app.integrations.google_sheets import GoogleSheetsClient
    from chatbot.runtime import get_bot_context
    from config.settings import ADMIN_WHATSAPP_NUMBER
    from services import notification_service as notify

    ctx = get_bot_context(start_background=False)
    sheets: GoogleSheetsClient = ctx.admin_service.sheets
    order_id = sheets.create_order(
        wa_id="573009998877",
        items=[{"nombre": "Coca", "qty": 1, "unit_price": 2.5, "subtotal": 2.5}],
        total=2.5,
        status="pending",
        customer_name="Cliente Confirm",
    )

    reply = notify.handle_admin_confirmation(f"CONFIRMAR {order_id}")

    assert "confirmado" in reply.lower()
    assert sheets.get_order(order_id)["status"] == "confirmed"

    assert len(whatsapp_log) >= 1
    customer_notified = any(
        "573009998877" in to.replace("whatsapp:", "").replace("+", "")
        for to, body in whatsapp_log
        if "confirmado" in body.lower() or "confirmada" in body.lower()
    )
    assert customer_notified, f"Expected customer WhatsApp in {whatsapp_log}"


def test_approve_from_app_notifies_customer(whatsapp_log):
    from app.integrations.google_sheets import GoogleSheetsClient
    from chatbot.runtime import get_bot_context
    from services import notification_service as notify

    ctx = get_bot_context(start_background=False)
    sheets: GoogleSheetsClient = ctx.admin_service.sheets
    order_id = sheets.create_order(
        wa_id="573004445566",
        items=[{"nombre": "Tacos", "qty": 2, "subtotal": 8.0}],
        total=8.0,
        status="pending",
        customer_name="Cliente App",
    )

    result = notify.approve_order_from_app(order_id, business_id="default")

    assert result["ok"] is True
    assert sheets.get_order(order_id)["status"] == "confirmed"
    assert any(
        "573004445566" in to.replace("whatsapp:", "").replace("+", "")
        for to, body in whatsapp_log
        if "confirmado" in body.lower()
    ), f"Expected customer WhatsApp in {whatsapp_log}"


def test_approve_from_app_reports_twilio_failure(whatsapp_log):
    from app.integrations.google_sheets import GoogleSheetsClient
    from chatbot.runtime import get_bot_context
    from services import notification_service as notify

    ctx = get_bot_context(start_background=False)
    sheets: GoogleSheetsClient = ctx.admin_service.sheets
    order_id = sheets.create_order(
        wa_id="573003332211",
        items=[{"nombre": "Ensalada", "qty": 1, "subtotal": 5.0}],
        total=5.0,
        status="pending",
    )

    def _fail_send(_self, _to: str, _body: str) -> bool:
        return False

    with patch(
        "app.services.admin_service.AdminService._send_whatsapp",
        _fail_send,
    ):
        result = notify.approve_order_from_app(order_id, business_id="default")

    assert result["ok"] is False
    assert sheets.get_order(order_id)["status"] == "confirmed"


def test_full_flow_via_gateway(whatsapp_log):
    """Simula: cliente guarda pedido (notify) + admin confirma (gateway)."""
    from app.integrations.google_sheets import GoogleSheetsClient
    from chatbot.gateway import handle_incoming_message
    from chatbot.runtime import get_bot_context
    from config.settings import ADMIN_WHATSAPP_NUMBER

    ctx = get_bot_context(start_background=False)
    sheets: GoogleSheetsClient = ctx.admin_service.sheets

    order_id = sheets.create_order(
        wa_id="573001110099",
        items=[{"nombre": "Hamburguesa", "qty": 1, "subtotal": 9.5}],
        total=9.5,
        status="pending",
    )
    from services.notification_service import on_order_pending

    on_order_pending(
        sheets.get_order(order_id) or {"order_id": order_id, "wa_id": "573001110099"},
    )
    assert any("ORD-" in body for _, body in whatsapp_log)

    admin_digits = "".join(c for c in ADMIN_WHATSAPP_NUMBER if c.isdigit())
    result = handle_incoming_message(
        {
            "phone": admin_digits,
            "message": f"CONFIRMAR {order_id}",
            "business_id": "default",
        }
    )
    assert result.get("is_admin") is True
    assert "confirmado" in str(result.get("response_text", "")).lower()
    assert sheets.get_order(order_id)["status"] == "confirmed"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
