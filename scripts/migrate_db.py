"""Create/update schema and seed default business (Fase 5)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--postgres", action="store_true", help="Usar DATABASE_URL del .env")
_args, _ = _parser.parse_known_args()
if not _args.postgres:
    db_file = (ROOT / "data" / "whatsbot.db").resolve()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite:///{db_file.as_posix()}"

from config.settings import BASE_DIR, DATA_DIR  # noqa: E402
from infrastructure.database import init_db, session_scope  # noqa: E402
from services import business_service as biz_svc  # noqa: E402
from services.business_service import ensure_default_business  # noqa: E402
from services import menu_service as menu_svc  # noqa: E402


def _seed_menu_from_cache(db, business_id: str) -> int:
    cache_path = DATA_DIR / "menu_cache.json"
    if not cache_path.exists():
        return 0
    try:
        items = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    if not isinstance(items, list) or not items:
        return 0
    existing = menu_svc.list_menu_items(db, business_id)
    if existing:
        return len(existing)
    normalized = []
    for row in items:
        if not isinstance(row, dict):
            continue
        normalized.append(
            {
                "id": str(row.get("id", "")),
                "nombre": row.get("nombre", row.get("name", "")),
                "precio": row.get("precio", row.get("price", 0)),
                "categoria": row.get("categoria", row.get("category", "")),
                "disponible": row.get("disponible", row.get("available", True)),
            }
        )
    menu_svc.replace_menu_items(db, business_id, normalized)
    return len(normalized)


def main() -> int:
    print("=== migrate_db (Fase 5+) ===\n")
    init_db()
    try:
        import importlib.util

        status_path = ROOT / "scripts" / "migrate_message_status.py"
        spec = importlib.util.spec_from_file_location("migrate_message_status", status_path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.main()
    except Exception as exc:
        print(f"  WARN message status migration: {exc}")
    with session_scope() as db:
        biz = ensure_default_business(db)
        menu_count = _seed_menu_from_cache(db, biz.id)
        print(f"  OK  default business: {biz.id} ({biz.name})")
        print(f"  OK  twilio_whatsapp_from: {biz.twilio_whatsapp_from}")
        if menu_count:
            print(f"  OK  menu items seeded: {menu_count}")
        db.refresh(biz)
        n_intents = len(biz_svc.get_business_intents(db, biz.id))
        n_prompts = len(biz_svc.get_business_prompts(db, biz.id))
        print(f"  OK  business_intents keys: {n_intents}")
        print(f"  OK  business_prompts keys: {n_prompts}")
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
