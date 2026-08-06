"""
Reintento de fallback de botones/lista tras fallo async (ej. Twilio 63018):
1er fallo -> agenda a TWILIO_FIRST_RETRY_SECONDS_PER_TRY; 2do fallo -> agenda
a TWILIO_SECOND_RETRY_SECONDS_PER_TRY; 3er fallo (2 intentos ya gastados) ->
se abandona. Éxito en cualquier punto borra la fila y no reintenta más.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{(ROOT / 'data' / 'test_button_fallback_retry.db').as_posix()}",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-tests-only")
os.environ.setdefault("WHATSBOT_OWNER_PIN", "testpin123")


@pytest.fixture(scope="module", autouse=True)
def _init_db():
    from infrastructure.database import init_db, session_scope
    from services.business_service import ensure_default_business

    init_db()
    with session_scope() as db:
        ensure_default_business(db)


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    import services.button_fallback_service as bfs

    monkeypatch.setattr(bfs, "TWILIO_FIRST_RETRY_SECONDS_PER_TRY", 0.05)
    monkeypatch.setattr(bfs, "TWILIO_SECOND_RETRY_SECONDS_PER_TRY", 0.05)


@pytest.fixture(autouse=True)
def _clean_table():
    from infrastructure.database import session_scope
    from models.pending_button_fallback import PendingButtonFallback

    with session_scope() as db:
        db.query(PendingButtonFallback).delete()
    yield


def _register_and_fail(db, sid: str):
    import services.button_fallback_service as bfs

    bfs.register_pending(
        db,
        business_id="default",
        message_sid=sid,
        recipient="+573000000000",
        fallback_body="fallback text",
    )
    bfs.consume_status(db, business_id="default", message_sid=sid, status="failed")


def test_retries_twice_then_gives_up():
    import services.button_fallback_service as bfs
    from infrastructure.database import session_scope
    from models.pending_button_fallback import PendingButtonFallback

    sid = "SM_RETRY_GIVEUP"
    with session_scope() as db:
        _register_and_fail(db, sid)

    with patch("infrastructure.twilio_client.send_whatsapp_message", return_value=None) as mock_send:
        time.sleep(0.1)  # pasar TWILIO_FIRST_RETRY_SECONDS_PER_TRY
        bfs._process_due_retries()
        with session_scope() as db:
            row = db.get(PendingButtonFallback, sid)
            assert row is not None
            assert row.attempts == 1

        time.sleep(0.1)  # pasar TWILIO_SECOND_RETRY_SECONDS_PER_TRY
        bfs._process_due_retries()
        with session_scope() as db:
            row = db.get(PendingButtonFallback, sid)
            assert row is None  # se abandonó tras 2 intentos

    assert mock_send.call_count == 2


def test_success_on_retry_stops_retrying():
    import services.button_fallback_service as bfs
    from infrastructure.database import session_scope
    from models.pending_button_fallback import PendingButtonFallback

    sid = "SM_RETRY_SUCCESS"
    with session_scope() as db:
        _register_and_fail(db, sid)

    with patch(
        "infrastructure.twilio_client.send_whatsapp_message", return_value="SM_FALLBACK_OK"
    ) as mock_send:
        time.sleep(0.1)
        bfs._process_due_retries()

    assert mock_send.call_count == 1
    with session_scope() as db:
        assert db.get(PendingButtonFallback, sid) is None


def test_delivered_status_drops_pending_without_retry():
    import services.button_fallback_service as bfs
    from infrastructure.database import session_scope
    from models.pending_button_fallback import PendingButtonFallback

    sid = "SM_DELIVERED_OK"
    with session_scope() as db:
        bfs.register_pending(
            db,
            business_id="default",
            message_sid=sid,
            recipient="+573000000000",
            fallback_body="fallback text",
        )
        bfs.consume_status(db, business_id="default", message_sid=sid, status="delivered")

    with session_scope() as db:
        assert db.get(PendingButtonFallback, sid) is None
