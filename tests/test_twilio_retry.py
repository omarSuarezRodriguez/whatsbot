"""
Punto 3 (Fase 4 fix): reintento con backoff exponencial solo para 429 /
rate-limit en las llamadas a Twilio. Cualquier otro error debe seguir
fallando de inmediato (mismo comportamiento que antes de este fix).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import requests
from twilio.base.exceptions import TwilioRestException

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _http_error(status_code: int, retry_after: str | None = None) -> requests.HTTPError:
    resp = requests.Response()
    resp.status_code = status_code
    if retry_after is not None:
        resp.headers["Retry-After"] = retry_after
    return requests.HTTPError(response=resp)


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    from infrastructure import twilio_client as tc

    monkeypatch.setattr(tc.time, "sleep", lambda _seconds: None)


def test_retries_on_429_then_succeeds():
    from infrastructure import twilio_client as tc

    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(429)
        return "ok"

    result = tc._call_with_rate_limit_retry(flaky, what="test")

    assert result == "ok"
    assert calls["n"] == 3


def test_gives_up_after_max_retries_on_sustained_429():
    from infrastructure import twilio_client as tc

    calls = {"n": 0}

    def always_429():
        calls["n"] += 1
        raise _http_error(429)

    with pytest.raises(requests.HTTPError):
        tc._call_with_rate_limit_retry(always_429, what="test")

    assert calls["n"] == tc._MAX_RETRIES + 1


def test_non_429_http_error_fails_immediately():
    from infrastructure import twilio_client as tc

    calls = {"n": 0}

    def server_error():
        calls["n"] += 1
        raise _http_error(500)

    with pytest.raises(requests.HTTPError):
        tc._call_with_rate_limit_retry(server_error, what="test")

    assert calls["n"] == 1  # sin reintento — mismo comportamiento que antes


def test_twilio_rest_exception_429_retries():
    from infrastructure import twilio_client as tc

    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise TwilioRestException(status=429, uri="x", msg="rate limited")
        return "ok"

    result = tc._call_with_rate_limit_retry(flaky, what="test")

    assert result == "ok"
    assert calls["n"] == 2


def test_twilio_rest_exception_non_429_fails_immediately():
    from infrastructure import twilio_client as tc

    calls = {"n": 0}

    def broken():
        calls["n"] += 1
        raise TwilioRestException(status=400, uri="x", msg="bad request")

    with pytest.raises(TwilioRestException):
        tc._call_with_rate_limit_retry(broken, what="test")

    assert calls["n"] == 1


def test_respects_retry_after_header(monkeypatch):
    from infrastructure import twilio_client as tc

    sleeps: list[float] = []
    monkeypatch.setattr(tc.time, "sleep", lambda seconds: sleeps.append(seconds))

    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise _http_error(429, retry_after="2.5")
        return "ok"

    tc._call_with_rate_limit_retry(flaky, what="test")

    assert sleeps == [2.5]
