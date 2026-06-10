"""Add messages.client_id for outbound idempotency (OF-C)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--postgres", action="store_true")
_args, _ = _parser.parse_known_args()
if not _args.postgres:
    import os

    db_file = (ROOT / "data" / "whatsbot.db").resolve()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite:///{db_file.as_posix()}"

from sqlalchemy import inspect, text  # noqa: E402

from infrastructure.database import get_engine, init_db  # noqa: E402


def _column_names(table: str) -> set[str]:
    inspector = inspect(get_engine())
    return {col["name"] for col in inspector.get_columns(table)}


def main() -> int:
    print("=== migrate_client_id (OF-C) ===\n")
    init_db()
    engine = get_engine()
    existing = _column_names("messages")

    if "client_id" not in existing:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE messages ADD COLUMN client_id VARCHAR(64)"))
            print("  OK  ALTER TABLE messages ADD COLUMN client_id VARCHAR(64)")
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_messages_client_id "
                    "ON messages (client_id) WHERE client_id IS NOT NULL"
                )
            )
            print("  OK  unique index ix_messages_client_id")
    else:
        print("  OK  client_id already present")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
