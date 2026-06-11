"""
Flujo confirmación admin (DB-backed, sin Sheets).

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
sys.path.insert(0, str(ROOT / "chatbot"))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{(ROOT / 'data' / 'test_orders.db').as_posix()}",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-tests-only")
os.environ.setdefault("WHATSBOT_OWNER_PIN", "testpin123")


@pytest.fixture(autouse=True)
def reset_context():
    from chatbot.runtime import reset_bot_context

    reset_bot_context()
    yield
    reset_bot_context()


@pytest.fixture
def whatsapp_log(monkeypatch):
    log: list[tuple[str, str]] = []

    def _fake_send(_self, to_number: str, body: str) -> bool:
        log.append((to_number, body))
        return True

    monkeypatch.setattr(
        "app.services.admin_service.AdminService._send_whatsapp",
        _fake_send,
    )
    return log


@pytest.fixture(scope="session", autouse=True)
def _init_db():
    from infrastructure.database import init_db
    from services.business_service import ensure_default_business
    from infrastructure.database import session_scope

    init_db()
    with session_scope() as db:
        ensure_default_business(db)


def _get_store():
    from chatbot.runtime import get_bot_context
    return get_bot_context(start_background=False).admin_service.sheets


def test_notify_admin_sends_confirmar(whatsapp_log):
    from config.settings import ADMIN_WHATSAPP_NUMBER
    from services import notification_service as notify

    order = {
        "order_id": "ORD-TEST0001",
        "wa_id": "573001234567",
        "customer_name": "Cliente Test",
        "items": [{"nombre": "Empanada", "qty": 1, "subtotal": 3.0}],
        "total": 3.0,
        "address": "Calle 1",
        "delivery_type": "domicilio",
        "status": "pending",
    }
    notify.notify_admin_new_order(order)

    assert len(whatsapp_log) >= 1
    assert "ORD-TEST0001" in whatsapp_log[0][1]
    assert "CONFIRMAR" in whatsapp_log[0][1]


def test_admin_confirm_notifies_customer(whatsapp_log):
    from services import notification_service as notify
    from infrastructure.database import session_scope
    from services import order_service as order_svc

    store = _get_store()
    order_id = store.create_order(
        wa_id="573009998877",
        items=[{"nombre": "Coca", "qty": 1, "subtotal": 2.5}],
        total=2.5,
        status="pending",
        customer_name="Cliente Confirm",
    )

    reply = notify.handle_admin_confirmation(f"CONFIRMAR {order_id}")
    assert "confirmado" in reply.lower()

    with session_scope() as db:
        row = order_svc.get_order(db, "default", order_id)
    assert row and row.status == "confirmed"


def test_approve_from_app_notifies_customer(whatsapp_log):
    from services import notification_service as notify
    from infrastructure.database import session_scope
    from services import order_service as order_svc

    store = _get_store()
    order_id = store.create_order(
        wa_id="573004445566",
        items=[{"nombre": "Tacos", "qty": 2, "subtotal": 8.0}],
        total=8.0,
        status="pending",
        customer_name="Cliente App",
    )

    with session_scope() as db:
        result = notify.approve_order_from_app(order_id, business_id="default", db=db)

    assert result["ok"] is True

    with session_scope() as db:
        row = order_svc.get_order(db, "default", order_id)
    assert row and row.status == "confirmed"

    customer_notified = any(
        "573004445566" in to.replace("whatsapp:", "").replace("+", "")
        for to, body in whatsapp_log
        if "confirmado" in body.lower()
    )
    assert customer_notified, f"Expected customer WhatsApp in {whatsapp_log}"


def test_approve_from_app_reports_twilio_failure(whatsapp_log):
    from services import notification_service as notify
    from infrastructure.database import session_scope
    from services import order_service as order_svc

    store = _get_store()
    order_id = store.create_order(
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
        with session_scope() as db:
            result = notify.approve_order_from_app(order_id, business_id="default", db=db)

    assert result["ok"] is False

    with session_scope() as db:
        row = order_svc.get_order(db, "default", order_id)
    assert row and row.status == "confirmed"
