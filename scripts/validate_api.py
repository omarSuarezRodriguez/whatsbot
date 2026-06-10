"""Validate FastAPI webhook + DB (Fase 4)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Use SQLite for validation if postgres not configured
os.environ.setdefault("DATABASE_URL", f"sqlite:///{(ROOT / 'data' / 'validate_api.db').as_posix()}")


def main() -> int:
    print("=== validate_api (Fase 4) ===\n")
    failures = 0

    try:
        from fastapi.testclient import TestClient
        from api.main import create_app
        from infrastructure.database import init_db

        init_db()
        client = TestClient(create_app())
        print("  OK  create_app + init_db")
    except Exception as exc:
        print(f"  FAIL setup - {exc}")
        return 1

    r = client.get("/health")
    if r.status_code == 200 and r.json().get("status") == "ok":
        print("  OK  GET /health")
    else:
        print(f"  FAIL GET /health - {r.status_code}")
        failures += 1

    from config.settings import TWILIO_WHATSAPP_FROM

    r = client.post(
        "/webhook",
        data={
            "WaId": "573009999999",
            "From": "whatsapp:+573009999999",
            "To": TWILIO_WHATSAPP_FROM or "whatsapp:+573242497352",
            "Body": "menu",
            "ProfileName": "API Test",
        },
    )
    if r.status_code == 200 and "xml" in (r.headers.get("content-type") or ""):
        print("  OK  POST /webhook -> TwiML")
    else:
        print(f"  FAIL POST /webhook - {r.status_code}")
        failures += 1

    from infrastructure.database import session_scope
    from models.message import Message

    with session_scope() as db:
        count = db.query(Message).filter(Message.direction == "incoming").count()
        if count >= 1:
            print(f"  OK  incoming message in DB (count={count})")
        else:
            print("  FAIL no incoming messages in DB")
            failures += 1

    print(f"\n=== Resultado: {failures} fallo(s) ===")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
