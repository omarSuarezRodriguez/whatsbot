"""Add message status columns (Fase 11.5) — safe for existing SQLite/PostgreSQL."""

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
    print("=== migrate_message_status (Fase 11.5) ===\n")
    init_db()
    engine = get_engine()
    existing = _column_names("messages")
    statements: list[str] = []

    if "status" not in existing:
        if engine.dialect.name == "sqlite":
            statements.append(
                "ALTER TABLE messages ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'delivered'"
            )
        else:
            statements.append(
                "ALTER TABLE messages ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'delivered'"
            )
    if "delivered_at" not in existing:
        statements.append("ALTER TABLE messages ADD COLUMN delivered_at DATETIME")
    if "read_at" not in existing:
        statements.append("ALTER TABLE messages ADD COLUMN read_at DATETIME")

    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))
            print(f"  OK  {sql}")

    if not statements:
        print("  OK  columns already present")
    else:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE messages SET status = 'delivered', delivered_at = created_at "
                    "WHERE status IS NULL OR status = '' OR status = 'delivered'"
                )
            )
            conn.execute(
                text(
                    "UPDATE messages SET status = 'sent' "
                    "WHERE direction = 'outgoing' AND delivered_at IS NULL"
                )
            )

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
