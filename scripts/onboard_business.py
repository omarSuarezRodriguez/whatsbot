"""Onboard a business with config seed from config/* (Fase 5)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from infrastructure.database import init_db, session_scope  # noqa: E402
from services.business_service import create_business, ensure_default_business  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Alta de negocio WhatsBot")
    parser.add_argument("--default", action="store_true", help="Solo asegurar negocio default")
    parser.add_argument("--id", default="", help="business_id")
    parser.add_argument("--name", default="")
    parser.add_argument("--twilio-from", default="", dest="twilio_from")
    parser.add_argument("--admin", default="", help="ADMIN whatsapp")
    args = parser.parse_args()

    init_db()
    with session_scope() as db:
        if args.default or not args.id:
            biz = ensure_default_business(db)
            print(f"Default business ready: {biz.id}")
            return 0
        biz = create_business(
            db,
            business_id=args.id,
            name=args.name or args.id,
            twilio_whatsapp_from=args.twilio_from,
            admin_whatsapp_number=args.admin,
            seed_from_config=True,
        )
        print(f"Created business: {biz.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
