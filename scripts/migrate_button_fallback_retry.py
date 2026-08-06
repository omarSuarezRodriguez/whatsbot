"""Add pending_button_fallbacks.attempts / next_retry_at (retry scheduling)."""

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

TABLE = "pending_button_fallbacks"


def _column_names(table: str) -> set[str]:
    inspector = inspect(get_engine())
    return {col["name"] for col in inspector.get_columns(table)}


def main() -> int:
    print("=== migrate_button_fallback_retry ===\n")
    init_db()
    engine = get_engine()
    existing = _column_names(TABLE)
    statements: list[str] = []

    if "attempts" not in existing:
        statements.append(
            f"ALTER TABLE {TABLE} ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0"
        )
    if "next_retry_at" not in existing:
        statements.append(f"ALTER TABLE {TABLE} ADD COLUMN next_retry_at DATETIME")

    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))
            print(f"  OK  {sql}")
        if "next_retry_at" not in existing:
            conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_next_retry_at "
                    f"ON {TABLE} (next_retry_at)"
                )
            )
            print(f"  OK  index ix_{TABLE}_next_retry_at")

    if not statements:
        print("  OK  columns already present")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
