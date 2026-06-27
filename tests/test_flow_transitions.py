"""Tests for JSON-driven flow transitions (states format)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
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

SAMPLE_PRODUCTOS = [
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
        "app.services.productos_service.ProductosService.get_available_productos",
        lambda self: SAMPLE_PRODUCTOS,
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


def _step(engine, wa_id: str) -> str:
    return engine.state_manager.get(wa_id).get("step", "")


@pytest.mark.parametrize(
    "wa_id,message",
    [
        ("573011110001", "hola"),
        ("573011110002", "productos"),
        ("573011110003", "pedido"),
        ("573011110004", "ayuda"),
        ("573011110005", ""),
        ("573011110006", "xyz basura"),
    ],
)
def test_process_message_always_returns_str(engine, wa_id, message):
    reply = engine.process_message(wa_id, message)
    assert isinstance(reply, str)
    assert reply.strip()


def test_cancelar_mid_order(engine):
    wa_id = "573011110010"
    engine.process_message(wa_id, "pedido")
    engine.process_message(wa_id, "1 pizza hawaiana")
    assert _step(engine, wa_id) == "order_review_node"

    reply = engine.process_message(wa_id, "cancelar")

    assert isinstance(reply, str)
    assert "cancel" in reply.lower()
    assert _step(engine, wa_id) == "home_node"
    assert not engine.state_manager.get(wa_id).get("data", {}).get("cart")


def test_abandon_confirm_reject_continues_order(engine):
    wa_id = "573011110011"
    engine.process_message(wa_id, "pedido")
    engine.process_message(wa_id, "1 pizza hawaiana")
    assert _step(engine, wa_id) == "order_review_node"

    prompt = engine.process_message(wa_id, "inicio")
    assert "pedido en curso" in prompt.lower()
    assert engine.state_manager.get(wa_id).get("data", {}).get(
        "awaiting_abandon_confirm"
    )

    reply = engine.process_message(wa_id, "no")
    assert "continuamos" in reply.lower()
    assert not engine.state_manager.get(wa_id).get("data", {}).get(
        "awaiting_abandon_confirm"
    )
    assert _step(engine, wa_id) == "order_review_node"


def test_idle_start_no_productos_catalog(engine):
    wa_id = "573009998875"
    reply = engine.process_message(wa_id, "hola")

    assert isinstance(reply, str)
    assert "pizza hawaiana" not in reply.lower()
    assert "hamburguesa" not in reply.lower()
    assert "¿Qué necesitas hoy?" in reply


def test_productos_shows_catalog(engine):
    wa_id = "573009998874"
    reply = engine.process_message(wa_id, "productos")

    assert isinstance(reply, str)
    assert "pizza" in reply.lower()
    assert _step(engine, wa_id) == "productos_node"


def test_idle_start_returns_single_string(engine):
    wa_id = "573009998877"
    reply = engine.process_message(wa_id, "hola")

    assert isinstance(reply, str), f"expected str, got {type(reply).__name__}"
    assert "Bienvenido" in reply or "bienvenido" in reply.lower()
    assert _step(engine, wa_id) == "home_node"


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
    assert "¿Qué necesitas hoy?" in reply
    assert "repetir" not in reply.lower()
    assert _step(engine, wa_id) == "home_node"


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
    assert _step(engine, wa_id) == "home_node"
    state = engine.state_manager.get(wa_id)
    assert not state.get("data", {}).get("cart")


def test_order_modify_then_confirm(engine):
    wa_id = "573002223344"
    engine.user_service.save_name(wa_id, "Luis Test")

    engine.process_message(wa_id, "pedido")
    engine.process_message(wa_id, "1 pizza hawaiana")
    engine.process_message(wa_id, "no")
    assert _step(engine, wa_id) == "order_modify_node"

    engine.process_message(wa_id, "agrega 1 coca cola")
    engine.process_message(wa_id, "si")
    reply = engine.process_message(wa_id, "recoger")
    body = _text(reply).lower()
    assert "registrado" in body or "pedido" in body
    assert _step(engine, wa_id) == "home_node"


def test_ayuda_full(engine):
    wa_id = "573003334455"

    engine.process_message(wa_id, "ayuda")
    engine.process_message(wa_id, "4")
    engine.process_message(wa_id, "25/07/2027")
    engine.process_message(wa_id, "19:30")
    reply = engine.process_message(wa_id, "si")

    body = _text(reply).lower()
    assert "solicitud" in body or "confirmad" in body or "registrad" in body
    assert _step(engine, wa_id) == "home_node"


def test_ayuda_rejected_restarts(engine):
    wa_id = "573004445566"

    engine.process_message(wa_id, "ayuda")
    engine.process_message(wa_id, "2")
    engine.process_message(wa_id, "25/07/2027")
    engine.process_message(wa_id, "20:00")
    engine.process_message(wa_id, "no")

    assert _step(engine, wa_id) == "ayuda_start_node"
    state = engine.state_manager.get(wa_id)
    assert state.get("data", {}).get("ayuda") == {}


def test_global_productos_from_order(engine):
    wa_id = "573005556677"

    engine.process_message(wa_id, "pedido")
    engine.process_message(wa_id, "1 pizza hawaiana")
    reply = engine.process_message(wa_id, "productos")

    body = _text(reply).lower()
    assert "productos" in body or "pizza" in body
    assert _step(engine, wa_id) == "productos_node"


def test_implicit_order_from_idle(engine):
    wa_id = "573006667788"
    reply = engine.process_message(wa_id, "2 pizza hawaiana")

    body = _text(reply).lower()
    assert "pizza" in body or "carrito" in body or "pedido" in body
    assert _step(engine, wa_id) in {"order_review_node", "order_start_node"}


def test_order_greeting_while_modifying(engine):
    wa_id = "573007778899"
    engine.process_message(wa_id, "pedido")
    engine.process_message(wa_id, "1 pizza hawaiana")
    engine.process_message(wa_id, "no")
    assert _step(engine, wa_id) == "order_modify_node"

    reply = engine.process_message(wa_id, "buenos dias")
    assert "ordenar" in reply.lower() or "hamburguesa" in reply.lower()
    assert _step(engine, wa_id) == "order_modify_node"


def test_idle_greeting_from_productos_navigates_to_start(engine):
    wa_id = "573008889900"
    engine.process_message(wa_id, "productos")
    assert _step(engine, wa_id) == "productos_node"

    reply = engine.process_message(wa_id, "inicio")
    assert "Bienvenido" in reply or "bienvenido" in reply.lower()
    assert _step(engine, wa_id) == "home_node"


def test_idle_start_second_hola_fallback(engine):
    wa_id = "573009998878"
    first = engine.process_message(wa_id, "hola")

    assert "Bienvenido" in first or "bienvenido" in first.lower()
    assert "¿Qué necesitas hoy?" in first
    assert _step(engine, wa_id) == "home_node"
    assert engine.state_manager.get(wa_id).get("data", {}).get("shown_steps", {}).get(
        "home_node"
    )

    second = engine.process_message(wa_id, "xyz basura")
    assert "no logré entenderte" in second.lower()
    assert _step(engine, wa_id) == "home_node"
