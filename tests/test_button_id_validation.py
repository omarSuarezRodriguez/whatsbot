"""
Punto 4 (Fase 4 fix — Twilio buttons/list rate-limit): un id/title de botón
que NO corresponde a ninguna opción declarada en el nodo conversacional
actual debe caer en el fallback declarado en el JSON de ese nodo — nunca en
un routing nuevo hardcodeado en Python.

No modifica tests existentes; agrega cobertura dirigida a un hueco
identificado en la auditoría (infrastructure/twilio_client.py no valida
esto, FlowEngine ya lo hace vía _node_fallback_message).
"""

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
    f"sqlite:///{(ROOT / 'data' / 'test_button_id_validation.db').as_posix()}",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-tests-only")
os.environ.setdefault("WHATSBOT_OWNER_PIN", "testpin123")

SAMPLE_PRODUCTOS = [
    {
        "id": "1",
        "nombre": "Pizza Hawaiana",
        "precio": 12.0,
        "categoria": "Pizzas",
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
    from infrastructure.database import init_db, session_scope
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
    # ponytail: STATE_PERSIST_PATH (data/user_states.json) es un archivo fijo
    # compartido entre corridas de pytest, no por-archivo-de-test como
    # DATABASE_URL. Sin este reset, reejecutar este archivo repetidas veces
    # con los mismos wa_id arrastra estado de una corrida anterior.
    for wa_id in ("573009990001", "573009990002"):
        ctx.flow_engine.state_manager.reset(wa_id)
    return ctx.flow_engine


def _step(engine, wa_id: str) -> str:
    return engine.state_manager.get(wa_id).get("step", "")


def test_unrecognized_qty_tap_falls_back_to_json_fallback(engine):
    """order_qty_node reusa siempre los mismos ids qty_1/qty_2/qty_other
    para cualquier producto — un id que no pertenece a ese set (ej. un tap
    atrasado/corrupto) debe quedarse en el mismo nodo y mostrar el fallback
    declarado en JSON, sin tocar el carrito."""
    wa_id = "573009990001"

    engine.process_message(wa_id, "productos")
    engine.process_message(wa_id, "__cat__Pizzas")
    engine.process_message(wa_id, "Pizza Hawaiana")
    assert _step(engine, wa_id) == "order_qty_node"

    reply = engine.process_message(wa_id, "qty_stale_from_another_render")

    assert _step(engine, wa_id) == "order_qty_node"
    assert "elige" in reply.lower()
    cart = engine.state_manager.get(wa_id).get("data", {}).get("cart") or []
    assert cart == []


def test_recognized_qty_tap_still_advances(engine):
    """Control: un id válido del set actual sí debe avanzar (no romper el
    camino feliz al blindar el caso anterior)."""
    wa_id = "573009990002"

    engine.process_message(wa_id, "productos")
    engine.process_message(wa_id, "__cat__Pizzas")
    engine.process_message(wa_id, "Pizza Hawaiana")
    assert _step(engine, wa_id) == "order_qty_node"

    engine.process_message(wa_id, "qty_1")

    assert _step(engine, wa_id) == "order_review_node"
    cart = engine.state_manager.get(wa_id).get("data", {}).get("cart") or []
    assert len(cart) == 1
    assert cart[0]["qty"] == 1
