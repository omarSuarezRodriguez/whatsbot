"""DB-only multi-tenant: add pin_hash, customer columns, reservations table.

Revision ID: 001
Revises: 
Create Date: 2026-06-11

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _existing_columns(table: str) -> set[str]:
    return {c["name"] for c in _inspector().get_columns(table)}


def _existing_tables() -> set[str]:
    return set(_inspector().get_table_names())


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _add_column_if_missing(table: str, column_name: str, col_type, **kwargs):
    if column_name not in _existing_columns(table):
        op.add_column(table, sa.Column(column_name, col_type, **kwargs))


def _drop_column_if_exists(table: str, column_name: str):
    if column_name not in _existing_columns(table):
        return
    if _is_sqlite():
        import sqlite3
        if sqlite3.sqlite_version_info < (3, 35, 0):
            return  # Too old to drop columns; leave as-is
    op.drop_column(table, column_name)


def upgrade() -> None:
    # ---- businesses: add pin_hash, remove Sheets columns ----
    _add_column_if_missing("businesses", "pin_hash", sa.String(128), nullable=True)
    _drop_column_if_exists("businesses", "google_spreadsheet_id")
    _drop_column_if_exists("businesses", "sheets_enabled")

    # ---- customers: add new columns ----
    _add_column_if_missing("customers", "phone", sa.String(32), nullable=True)
    _add_column_if_missing("customers", "notes", sa.Text(), nullable=True)
    _add_column_if_missing(
        "customers", "blocked", sa.Boolean(), nullable=False, server_default="0"
    )
    _add_column_if_missing("customers", "last_order_items", sa.JSON(), nullable=True)
    _add_column_if_missing(
        "customers",
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )

    # ---- conversations: add FK (PostgreSQL only) ----
    if _is_pg():
        existing_fks = {
            fk["name"]
            for fk in _inspector().get_foreign_keys("conversations")
        }
        if "fk_conversations_business_id" not in existing_fks:
            op.create_foreign_key(
                "fk_conversations_business_id",
                "conversations",
                "businesses",
                ["business_id"],
                ["id"],
                ondelete="CASCADE",
            )

    # ---- reservations: new table (skip if already exists via create_all) ----
    if "reservations" not in _existing_tables():
        op.create_table(
            "reservations",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("business_id", sa.String(64), nullable=False),
            sa.Column("reservation_id", sa.String(32), nullable=False),
            sa.Column("wa_id", sa.String(32), nullable=False),
            sa.Column("personas", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("fecha", sa.String(16), nullable=False, server_default=""),
            sa.Column("hora", sa.String(8), nullable=False, server_default=""),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.ForeignKeyConstraint(
                ["business_id"],
                ["businesses.id"],
                ondelete="CASCADE",
                name="fk_reservations_business_id",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "business_id", "reservation_id", name="uq_reservation_business_rid"
            ),
        )
        op.create_index("ix_reservations_business_id", "reservations", ["business_id"])
        op.create_index(
            "ix_reservations_reservation_id", "reservations", ["reservation_id"]
        )
        op.create_index("ix_reservations_wa_id", "reservations", ["wa_id"])


def downgrade() -> None:
    if "reservations" in _existing_tables():
        op.drop_table("reservations")
    _add_column_if_missing(
        "businesses", "google_spreadsheet_id", sa.String(128), nullable=True
    )
    _add_column_if_missing(
        "businesses", "sheets_enabled", sa.Boolean(), nullable=False, server_default="0"
    )
    _drop_column_if_exists("businesses", "pin_hash")
    _drop_column_if_exists("customers", "phone")
    _drop_column_if_exists("customers", "notes")
    _drop_column_if_exists("customers", "blocked")
    _drop_column_if_exists("customers", "last_order_items")
    _drop_column_if_exists("customers", "updated_at")
