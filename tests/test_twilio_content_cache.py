"""
Puntos 1 y 2 (Fase 4 fix): send_whatsapp_buttons/send_whatsapp_list deben
reutilizar el ContentSid ya creado para el mismo set de botones / mismo
catálogo realizado, en vez de crear un Content Template nuevo en cada envío.

No golpea la red real: se mockean requests.post (creación de template) y
Client.messages.create (envío).
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
    f"sqlite:///{(ROOT / 'data' / 'test_twilio_content_cache.db').as_posix()}",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-tests-only")
os.environ.setdefault("WHATSBOT_OWNER_PIN", "testpin123")


@pytest.fixture(scope="module", autouse=True)
def _init_db():
    from infrastructure.database import init_db

    init_db()


@pytest.fixture(autouse=True)
def _clean_content_sid_cache():
    # ponytail: DATABASE_URL es setdefault por archivo de test — si otro
    # módulo se importa primero en la misma sesión de pytest, este archivo
    # termina compartiendo su sqlite. Limpiar la tabla por test evita que un
    # cache_key persistido de otra corrida/otro archivo dé un falso "hit".
    from infrastructure.database import session_scope
    from models.twilio_content_cache import TwilioContentSid

    with session_scope() as db:
        db.query(TwilioContentSid).delete()
    yield


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


@pytest.fixture
def twilio_env(monkeypatch):
    monkeypatch.setattr("infrastructure.twilio_client.TWILIO_ACCOUNT_SID", "ACtest")
    monkeypatch.setattr("infrastructure.twilio_client.TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setattr(
        "infrastructure.twilio_client.TWILIO_WHATSAPP_FROM", "whatsapp:+10000000000"
    )
    monkeypatch.setattr(
        "infrastructure.twilio_client.twilio_status_callback_url", lambda: ""
    )


def test_buttons_reuse_cached_content_sid(twilio_env, monkeypatch):
    from infrastructure import twilio_client as tc

    create_calls = []
    sid_counter = {"n": 0}

    def fake_post(url, json, auth, timeout):
        sid_counter["n"] += 1
        create_calls.append(json)
        return _FakeResponse(f"HXbtn{sid_counter['n']}")

    monkeypatch.setattr(tc.requests, "post", fake_post)

    send_calls = []

    def fake_create(kwargs):
        send_calls.append(kwargs)
        return _FakeMessage(f"SM{len(send_calls)}")

    monkeypatch.setattr(tc, "Client", lambda *_a, **_kw: _FakeClient(fake_create))

    buttons = [
        {"title": "1", "id": "qty_1"},
        {"title": "2", "id": "qty_2"},
        {"title": "Otra", "id": "qty_other"},
    ]

    sid1 = tc.send_whatsapp_buttons("573000000001", "¿Cuántas Pizza Hawaiana?", buttons)
    sid2 = tc.send_whatsapp_buttons("573000000002", "¿Cuántas Coca Cola?", buttons)

    assert sid1 == "SM1"
    assert sid2 == "SM2"
    # Mismo set de botones -> UN solo Content Template creado, no dos.
    assert len(create_calls) == 1
    # Pero SÍ se enviaron los dos mensajes, cada uno con su propio body via
    # ContentVariables (no quedó "congelado" el texto del primer producto).
    assert len(send_calls) == 2
    assert send_calls[0]["content_variables"] != send_calls[1]["content_variables"]
    assert "Pizza Hawaiana" in send_calls[0]["content_variables"]
    assert "Coca Cola" in send_calls[1]["content_variables"]
    # El mismo content_sid cacheado se reusó en ambos envíos.
    assert send_calls[0]["content_sid"] == send_calls[1]["content_sid"] == "HXbtn1"


def test_different_button_sets_create_different_sids(twilio_env, monkeypatch):
    from infrastructure import twilio_client as tc

    sid_counter = {"n": 0}

    def fake_post(url, json, auth, timeout):
        sid_counter["n"] += 1
        return _FakeResponse(f"HXbtn{sid_counter['n']}")

    monkeypatch.setattr(tc.requests, "post", fake_post)
    monkeypatch.setattr(
        tc, "Client", lambda *_a, **_kw: _FakeClient(lambda kw: _FakeMessage("SMx"))
    )

    set_a = [{"title": "Confirmar", "id": "confirmar"}, {"title": "Modificar", "id": "modificar"}]
    set_b = [{"title": "Domicilio", "id": "domicilio"}, {"title": "Recoger", "id": "recoger"}]

    tc.send_whatsapp_buttons("573000000003", "body a", set_a)
    tc.send_whatsapp_buttons("573000000004", "body b", set_b)

    assert sid_counter["n"] == 2


def test_lists_reuse_sid_while_catalog_unchanged(twilio_env, monkeypatch):
    from infrastructure import twilio_client as tc

    create_calls = []
    sid_counter = {"n": 0}

    def fake_post(url, json, auth, timeout):
        sid_counter["n"] += 1
        create_calls.append(json)
        return _FakeResponse(f"HXlist{sid_counter['n']}")

    monkeypatch.setattr(tc.requests, "post", fake_post)

    send_calls = []

    def fake_create(kwargs):
        send_calls.append(kwargs)
        return _FakeMessage(f"SM{len(send_calls)}")

    monkeypatch.setattr(tc, "Client", lambda *_a, **_kw: _FakeClient(fake_create))

    rows = [
        {"id": "1", "title": "Pizza Hawaiana", "description": "$12.00"},
        {"id": "2", "title": "Coca Cola", "description": "$2.50"},
    ]

    sid1 = tc.send_whatsapp_list(
        "573000000005", "Selecciona un producto", rows, "Elegir producto",
        business_id="biz-1",
    )
    sid2 = tc.send_whatsapp_list(
        "573000000006", "Selecciona un producto", rows, "Elegir producto",
        business_id="biz-1",
    )

    assert sid1 == "SM1"
    assert sid2 == "SM2"
    assert len(create_calls) == 1  # mismo catálogo -> mismo ContentSid

    # Catálogo distinto (nuevo producto) -> nuevo ContentSid.
    rows_changed = rows + [{"id": "3", "title": "Agua", "description": "$1.50"}]
    tc.send_whatsapp_list(
        "573000000007", "Selecciona un producto", rows_changed, "Elegir producto",
        business_id="biz-1",
    )
    assert len(create_calls) == 2

    # Mismo catálogo pero otro negocio -> tampoco reusa el sid del negocio 1.
    tc.send_whatsapp_list(
        "573000000008", "Selecciona un producto", rows, "Elegir producto",
        business_id="biz-2",
    )
    assert len(create_calls) == 3


def test_stale_content_sid_self_heals(twilio_env, monkeypatch):
    """Si Twilio devuelve 404 para un ContentSid cacheado (borrado a mano en
    consola), se invalida el cache y se recrea una vez — no rompe el bot."""
    from twilio.base.exceptions import TwilioRestException

    from infrastructure import twilio_client as tc

    sid_counter = {"n": 0}

    def fake_post(url, json, auth, timeout):
        sid_counter["n"] += 1
        return _FakeResponse(f"HXbtn{sid_counter['n']}")

    monkeypatch.setattr(tc.requests, "post", fake_post)

    attempts = {"n": 0}

    def fake_create(kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise TwilioRestException(status=404, uri="x", msg="not found")
        return _FakeMessage("SMrecovered")

    monkeypatch.setattr(tc, "Client", lambda *_a, **_kw: _FakeClient(fake_create))

    buttons = [{"title": "Sí", "id": "si"}, {"title": "No", "id": "no"}]
    sid = tc.send_whatsapp_buttons("573000000009", "¿Confirmas?", buttons)

    assert sid == "SMrecovered"
    assert attempts["n"] == 2  # 1 fallo (404) + 1 reintento tras invalidar cache
    assert sid_counter["n"] == 2  # template original + recreado tras invalidar
