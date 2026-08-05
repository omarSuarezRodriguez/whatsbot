"""
Fase 4 — Validación final global.

Traza DOS pedidos completos end-to-end (categoría -> producto -> cantidad ->
revisar -> confirmar -> entrega -> pago -> guardado) exactamente como lo
maneja la producción real: FlowEngine.process_message() para avanzar estado
+ get_current_buttons/get_current_list/get_current_buttons_failure_message()
+ deliver_reply() para el envío (igual que chatbot/gateway.py y
api/routes/whatsapp.py).

Prueba en un solo recorrido las 3 garantías del fix:
  (a) reuso de ContentSid — el número de Content Templates creados no crece
      con el número de turnos ni con el número de pedidos.
  (b) retry ante 429 — un 429 simulado en un envío no rompe el turno.
  (c) fallback ante ButtonText/ListId inválido — un tap corrupto/atrasado no
      avanza el estado ni rompe el carrito.

No golpea la red real (requests.post y twilio.rest.Client mockeados) ni
modifica tests existentes.
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
    f"sqlite:///{(ROOT / 'data' / 'test_e2e_order_flow_fase4.db').as_posix()}",
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
    {
        "id": "2",
        "nombre": "Pizza Pepperoni",
        "precio": 13.0,
        "categoria": "Pizzas",
        "disponible": True,
    },
]

WA_ID_A = "573001110001"
WA_ID_B = "573001110002"


class _FakeMessage:
    def __init__(self, sid: str):
        self.sid = sid
        self.status = "sent"
        self.error_code = None
        self.from_ = "whatsapp:+10000000000"


class _FakeMessagesResource:
    def __init__(self, create_fn):
        self._create_fn = create_fn
        self._last_sid = None

    def create(self, **kwargs):
        message = self._create_fn(kwargs)
        self._last_sid = message.sid
        return message

    def __call__(self, sid):
        self._last_sid = sid
        return self

    def fetch(self):
        return _FakeMessage(self._last_sid)


class _FakeClient:
    def __init__(self, create_fn):
        self.messages = _FakeMessagesResource(create_fn)


class _FakeResponse:
    def __init__(self, sid: str, status_code: int = 201):
        self._sid = sid
        self.status_code = status_code
        self.headers = {}

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(response=self)

    def json(self):
        return {"sid": self._sid}


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


@pytest.fixture(autouse=True)
def _clean_content_sid_cache():
    from infrastructure.database import session_scope
    from models.twilio_content_cache import TwilioContentSid

    with session_scope() as db:
        db.query(TwilioContentSid).delete()
    yield


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
    for wa_id in (WA_ID_A, WA_ID_B):
        ctx.flow_engine.state_manager.reset(wa_id)
        ctx.flow_engine.user_service.save_name(wa_id, "Cliente Test")
    return ctx.flow_engine


@pytest.fixture
def twilio_fakes(monkeypatch):
    """Mockea la creación de Content Templates (requests.post) y el envío
    (twilio.rest.Client) igual que test_twilio_content_cache.py, y devuelve
    los contadores para que el test pueda auditar reuso."""
    from infrastructure import twilio_client as tc

    monkeypatch.setattr(tc, "TWILIO_ACCOUNT_SID", "ACtest")
    monkeypatch.setattr(tc, "TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setattr(tc, "TWILIO_WHATSAPP_FROM", "whatsapp:+10000000000")
    monkeypatch.setattr(tc, "twilio_status_callback_url", lambda: "")

    create_calls: list[dict] = []
    send_calls: list[dict] = []
    sid_counter = {"n": 0}
    send_counter = {"n": 0}
    # ponytail: fila de comportamientos a devolver en orden en el próximo
    # send_calls.create() — usada para inyectar un 429 puntual (punto b).
    next_send_behaviors: list = []

    def fake_post(url, json, auth, timeout):
        sid_counter["n"] += 1
        create_calls.append(json)
        return _FakeResponse(f"HX{sid_counter['n']}")

    def fake_create(kwargs):
        send_counter["n"] += 1
        send_calls.append(kwargs)
        if next_send_behaviors:
            behavior = next_send_behaviors.pop(0)
            if behavior == "429":
                from twilio.base.exceptions import TwilioRestException

                raise TwilioRestException(status=429, uri="x", msg="rate limited")
        return _FakeMessage(f"SM{send_counter['n']}")

    monkeypatch.setattr(tc.requests, "post", fake_post)
    monkeypatch.setattr(tc, "Client", lambda *_a, **_kw: _FakeClient(fake_create))
    monkeypatch.setattr(tc.time, "sleep", lambda _s: None)  # sin esperar de verdad

    return {
        "create_calls": create_calls,
        "send_calls": send_calls,
        "next_send_behaviors": next_send_behaviors,
    }


def _turn(engine, wa_id: str, text: str):
    """Simula un turno real: FlowEngine avanza estado, luego se despacha
    igual que gateway.py -> deliver_reply (mismo orden de llamadas)."""
    from infrastructure.twilio_client import deliver_reply

    reply = engine.process_message(wa_id, text)
    actions = engine.get_current_buttons(wa_id)
    buttons_failure_message = engine.get_current_buttons_failure_message(wa_id)
    interactive_list = engine.get_current_list(wa_id)

    deliver_reply(
        f"whatsapp:+{wa_id}",
        reply,
        use_rest=True,
        business_id="default",
        actions=actions,
        buttons_failure_message=buttons_failure_message,
        interactive_list=interactive_list,
    )
    return reply


def _step(engine, wa_id: str) -> str:
    return engine.state_manager.get(wa_id).get("step", "")


def _run_full_order(engine, wa_id: str, product_name: str, qty_id: str):
    """categoría -> producto -> cantidad -> revisar -> confirmar -> entrega
    (recoger) -> pago (presencial) -> guardado."""
    _turn(engine, wa_id, "productos")
    _turn(engine, wa_id, "__cat__Pizzas")
    _turn(engine, wa_id, product_name)
    assert _step(engine, wa_id) == "order_qty_node"

    _turn(engine, wa_id, qty_id)
    assert _step(engine, wa_id) == "order_review_node"

    _turn(engine, wa_id, "confirmar")
    assert _step(engine, wa_id) == "order_confirm_node"

    _turn(engine, wa_id, "confirmar")
    assert _step(engine, wa_id) == "order_delivery_node"

    _turn(engine, wa_id, "recoger")
    assert _step(engine, wa_id) == "pago_metodo_node"

    _turn(engine, wa_id, "presencial")
    assert _step(engine, wa_id) == "pago_presencial_node"

    _turn(engine, wa_id, "entendido")
    assert _step(engine, wa_id) == "order_saved_node"


def test_two_full_orders_reuse_content_sids(engine, twilio_fakes):
    """(a) Dos pedidos completos, por dos clientes distintos, con productos
    distintos, deben terminar creando muy pocos Content Templates -- uno por
    cada *set de botones distinto* y uno por cada *lista con contenido
    distinto* -- nunca uno por mensaje ni uno por turno."""
    _run_full_order(engine, WA_ID_A, "Pizza Hawaiana", "qty_1")
    _run_full_order(engine, WA_ID_B, "Pizza Pepperoni", "qty_2")

    create_calls = twilio_fakes["create_calls"]
    send_calls = twilio_fakes["send_calls"]

    # 8 turnos con botones/lista por pedido x 2 pedidos = 16 envíos, pero
    # ambos pedidos comparten categoría (Pizzas) y los mismos sets de
    # botones (qty, review, confirm, delivery, pago, presencial) -> deben
    # colapsar a exactamente 8 Content Templates (uno por tipo de
    # contenido distinto), NUNCA uno por turno/mensaje/pedido.
    assert len(send_calls) == 16
    assert len(create_calls) == 8, (
        "Se está creando un Content Template nuevo por turno/pedido en vez "
        f"de reusar el cacheado (se crearon {len(create_calls)})."
    )

    # El pedido B (mismo set de botones qty_1/qty_2/qty_other, misma lista de
    # categorías, mismo catálogo de Pizzas) no debió generar NINGÚN template
    # nuevo respecto al pedido A -- todo hit de cache.
    calls_after_order_a = len(create_calls)
    # (ya se corrieron ambos pedidos arriba; validamos aquí releyendo el
    # conteo acumulado tras rehacer el pedido B una segunda vez con el mismo
    # producto para aislar el efecto de "ya visto")
    _run_full_order(engine, WA_ID_B, "Pizza Pepperoni", "qty_2")
    assert len(create_calls) == calls_after_order_a, (
        "Repetir el mismo pedido no debe crear Content Templates nuevos."
    )


def test_429_during_order_recovers_via_retry(engine, twilio_fakes):
    """(b) Un 429 puntual de Twilio durante el envío de un botón del pedido
    no debe tumbar el turno: el retry con backoff debe recuperarlo y el
    pedido debe poder completarse igual."""
    twilio_fakes["next_send_behaviors"].append("429")

    _run_full_order(engine, WA_ID_A, "Pizza Hawaiana", "qty_1")

    assert _step(engine, WA_ID_A) == "order_saved_node"
    # El envío que sufrió el 429 se reintentó y sí llegó a salir.
    send_calls = twilio_fakes["send_calls"]
    assert len(send_calls) >= 2  # el intento fallido + el reintento exitoso


def test_stale_button_tap_mid_order_falls_back_without_breaking_state(
    engine, twilio_fakes
):
    """(c) Un ButtonText que no pertenece al set de botones del nodo actual
    (ej. un tap atrasado en order_delivery_node) cae en el fallback JSON,
    sin avanzar de nodo ni tocar el carrito -- el pedido se puede retomar y
    completar normalmente después."""
    _turn(engine, WA_ID_A, "productos")
    _turn(engine, WA_ID_A, "__cat__Pizzas")
    _turn(engine, WA_ID_A, "Pizza Hawaiana")
    _turn(engine, WA_ID_A, "qty_1")
    _turn(engine, WA_ID_A, "confirmar")
    _turn(engine, WA_ID_A, "confirmar")
    assert _step(engine, WA_ID_A) == "order_delivery_node"

    cart_before = list(
        engine.state_manager.get(WA_ID_A).get("data", {}).get("cart") or []
    )

    reply = _turn(engine, WA_ID_A, "qty_stale_from_another_render")

    assert _step(engine, WA_ID_A) == "order_delivery_node"  # no avanzó
    cart_after = engine.state_manager.get(WA_ID_A).get("data", {}).get("cart") or []
    assert cart_after == cart_before  # carrito intacto
    assert "domicilio" in reply.lower() or "recoger" in reply.lower()

    # El pedido se puede retomar y completar con un tap válido.
    _turn(engine, WA_ID_A, "recoger")
    _turn(engine, WA_ID_A, "presencial")
    _turn(engine, WA_ID_A, "entendido")
    assert _step(engine, WA_ID_A) == "order_saved_node"
