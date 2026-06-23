"""Tests for JSON-driven flow transitions (states format)."""

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
    f"sqlite:///{(ROOT / 'data' / 'test_flow_transitions.db').as_posix()}",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-tests-only")
os.environ.setdefault("WHATSBOT_OWNER_PIN", "testpin123")

SAMPLE_MENU = [
    {
        "nombre": "Pizza Hawaiana",
        "precio": 12.0,
        "categoria": "Pizzas",
        "disponible": True,
    },
    {
        "nombre": "Coca Cola",
        "precio": 2.5,
        "categoria": "Bebidas",
        "disponible": True,
    },
    {
        "nombre": "Hamburguesa Clasica",
        "precio": 10.0,
        "categoria": "Hamburguesas",
        "disponible": True,
    },
]


@pytest.fixture(autouse=True)
def reset_context():
    from chatbot.runtime import reset_bot_context

    reset_bot_context()
    yield
    reset_bot_context()


@pytest.fixture(scope="session", autouse=True)
def _init_db():
    from infrastructure.database import init_db
    from infrastructure.database import session_scope
    from services.business_service import ensure_default_business

    init_db()
    with session_scope() as db:
        ensure_default_business(db)


@pytest.fixture
def engine(monkeypatch):
    from chatbot.runtime import get_bot_context

    monkeypatch.setattr(
        "app.services.menu_service.MenuService.get_available_menu",
        lambda self: SAMPLE_MENU,
    )
    monkeypatch.setattr(
        "services.notification_service.on_order_pending",
        lambda _order: None,
    )

    ctx = get_bot_context(start_background=False)
    ctx.flow_engine.reload_flow()
    return ctx.flow_engine


def _text(reply) -> str:
    if isinstance(reply, list):
        return "\n".join(str(part) for part in reply)
    return str(reply)


def test_idle_start_no_menu_catalog(engine):
    wa_id = "573009998875"
    reply = engine.process_message(wa_id, "hola")

    assert isinstance(reply, str)
    assert "pizza hawaiana" not in reply.lower()
    assert "hamburguesa" not in reply.lower()
    assert "¿Qué te gustaría hacer hoy?" in reply


def test_menu_shows_catalog(engine):
    wa_id = "573009998874"
    reply = engine.process_message(wa_id, "menu")

    assert isinstance(reply, str)
    assert "pizza" in reply.lower()
    assert _step(engine, wa_id) == "menu_node"


def test_idle_start_returns_single_string(engine):
    wa_id = "573009998877"
    reply = engine.process_message(wa_id, "hola")

    assert isinstance(reply, str), f"expected str, got {type(reply).__name__}"
    assert "Bienvenido" in reply or "bienvenido" in reply.lower()
    assert _step(engine, wa_id) == "start"


def test_idle_start_ignores_last_order_items(engine):
    wa_id = "573009998876"
    engine.user_service.sheets.upsert_user(
        wa_id,
        name="",
        address="",
        last_order_items=[{"nombre": "Pizza Hawaiana", "cantidad": 1, "precio": 12.0}],
    )
    reply = engine.process_message(wa_id, "hola")

    assert isinstance(reply, str)
    assert "Bienvenido" in reply or "bienvenido" in reply.lower()
    assert "¿Qué te gustaría hacer hoy?" in reply
    assert "repetir" not in reply.lower()
    assert _step(engine, wa_id) == "start"

def _step(engine, wa_id: str) -> str:
    return engine.state_manager.get(wa_id).get("step", "")


def test_order_happy_path_domicilio(engine):
    wa_id = "573001112233"
    engine.user_service.save_name(wa_id, "Ana Test")

    engine.process_message(wa_id, "pedido")
    engine.process_message(wa_id, "2 pizza hawaiana, 1 coca cola")
    engine.process_message(wa_id, "si")
    engine.process_message(wa_id, "domicilio")
    reply = engine.process_message(wa_id, "Calle 100 # 20-30")

    body = _text(reply).lower()
    assert "registrado" in body or "pedido" in body
    assert _step(engine, wa_id) == "start"
    state = engine.state_manager.get(wa_id)
    assert not state.get("data", {}).get("cart")


def test_order_modify_then_confirm(engine):
    wa_id = "573002223344"
    engine.user_service.save_name(wa_id, "Luis Test")

    engine.process_message(wa_id, "pedido")
    engine.process_message(wa_id, "1 pizza hawaiana")
    engine.process_message(wa_id, "no")
    assert _step(engine, wa_id) == "order_modify"

    engine.process_message(wa_id, "agrega 1 coca cola")
    engine.process_message(wa_id, "si")
    reply = engine.process_message(wa_id, "recoger")
    body = _text(reply).lower()
    assert "registrado" in body or "pedido" in body
    assert _step(engine, wa_id) == "start"


def test_reservation_full(engine):
    wa_id = "573003334455"

    engine.process_message(wa_id, "reservar")
    engine.process_message(wa_id, "4")
    engine.process_message(wa_id, "25/06/2026")
    engine.process_message(wa_id, "19:30")
    reply = engine.process_message(wa_id, "si")

    body = _text(reply).lower()
    assert "reserva" in body
    assert "confirmad" in body or "registrad" in body
    assert _step(engine, wa_id) == "start"


def test_reservation_rejected_restarts(engine):
    wa_id = "573004445566"

    engine.process_message(wa_id, "reservar")
    engine.process_message(wa_id, "2")
    engine.process_message(wa_id, "25/06/2026")
    engine.process_message(wa_id, "20:00")
    engine.process_message(wa_id, "no")

    assert _step(engine, wa_id) == "reservation_start"
    state = engine.state_manager.get(wa_id)
    assert state.get("data", {}).get("reservation") == {}


def test_global_menu_from_order(engine):
    wa_id = "573005556677"

    engine.process_message(wa_id, "pedido")
    engine.process_message(wa_id, "1 pizza hawaiana")
    reply = engine.process_message(wa_id, "menu")

    body = _text(reply).lower()
    assert "menú" in body or "menu" in body or "pizza" in body
    assert _step(engine, wa_id) == "menu_node"
