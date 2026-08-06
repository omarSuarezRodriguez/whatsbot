"""
Fix pacing por destinatario (limite "por par" de Meta): antes de cada envio
real a Twilio, esperar un intervalo minimo desde el ultimo envio a ESE MISMO
numero. Numeros distintos nunca deben bloquearse entre si.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _isolated_pacing_state(monkeypatch):
    from infrastructure import twilio_client as tc

    monkeypatch.setattr(tc, "_recipient_last_sent", {})
    monkeypatch.setattr(tc, "_recipient_locks", {})
    monkeypatch.setattr(tc, "TWILIO_MIN_SECONDS_PER_RECIPIENT", 0.3)


def test_same_recipient_gets_spaced_out():
    from infrastructure import twilio_client as tc

    tc._pace_recipient("+573001112222")
    start = time.monotonic()
    tc._pace_recipient("+573001112222")
    elapsed = time.monotonic() - start

    assert elapsed >= 0.25  # ~TWILIO_MIN_SECONDS_PER_RECIPIENT, con margen


def test_different_recipients_do_not_block_each_other():
    from infrastructure import twilio_client as tc

    tc._pace_recipient("+573001112222")  # arranca el reloj para A

    b_elapsed: list[float] = []

    def _pace_b():
        start = time.monotonic()
        tc._pace_recipient("+573009998888")  # primer envio a B: sin espera
        b_elapsed.append(time.monotonic() - start)

    thread = threading.Thread(target=_pace_b)
    thread.start()
    thread.join(timeout=2)

    assert b_elapsed and b_elapsed[0] < 0.1  # B no esperó por el pacing de A
