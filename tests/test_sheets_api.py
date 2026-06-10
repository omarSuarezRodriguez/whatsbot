"""Google Sheets optional API — Fase 8."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite:///{(ROOT / 'data' / 'test_sheets_api.db').as_posix()}",
)
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-phase8"
os.environ["WHATSBOT_OWNER_PIN"] = "testpin"
os.environ["GOOGLE_SHEETS_ENABLED"] = "false"


@pytest.fixture(scope="module")
def client():
    from infrastructure.database import init_db
    from api.main import create_app
    from services.business_service import ensure_default_business
    from infrastructure.database import session_scope

    init_db()
    with session_scope() as db:
        ensure_default_business(db)
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    r = client.post(
        "/auth/login",
        json={"business_id": "default", "pin": "testpin"},
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_sheets_requires_auth(client: TestClient):
    r = client.get("/sheets/status")
    assert r.status_code == 401


def test_sheets_status_disabled_by_default(client: TestClient, auth_headers: dict):
    r = client.get("/sheets/status", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["global_enabled"] is False
    assert data["active"] is False


def test_sheets_sync_skipped_when_disabled(client: TestClient, auth_headers: dict):
    r = client.post("/sheets/sync", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["skipped"] is True
    assert body["menu"]["skipped"] is True
    assert body["orders"]["skipped"] is True


def test_sheets_settings_rejects_enable_when_global_off(
    client: TestClient,
    auth_headers: dict,
):
    r = client.put(
        "/sheets/settings",
        headers=auth_headers,
        json={"sheets_enabled": True},
    )
    assert r.status_code == 400
    assert "GOOGLE_SHEETS_ENABLED" in r.json()["detail"]


def test_sheets_sync_menu_endpoint(client: TestClient, auth_headers: dict):
    r = client.post("/sheets/sync/menu", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["skipped"] is True


def test_sheets_sync_service_module():
    from services import sheets_sync_service as svc

    assert svc.is_globally_enabled() is False
