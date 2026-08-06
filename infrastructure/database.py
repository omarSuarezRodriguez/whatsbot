"""SQLAlchemy engine, session factory and schema bootstrap."""

from __future__ import annotations

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config.settings import DATABASE_URL, DATA_DIR

logger = logging.getLogger(__name__)

Base = declarative_base()

_engine = None
_SessionLocal: sessionmaker[Session] | None = None

_PRODUCTION_DB_PATH = (DATA_DIR / "whatsbot.db").resolve()


def _resolve_database_url() -> str:
    url = (DATABASE_URL or "").strip()
    if url:
        return url
    path = _PRODUCTION_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.as_posix()}"


def _assert_not_real_db_in_test_mode(url: str) -> None:
    """Cinturon de seguridad (incidente 2026-08-05): si algun test alguna vez
    vuelve a resolver contra la BD real de produccion, aborta ruidoso en vez
    de escribir basura de prueba encima de datos reales."""
    if os.environ.get("WHATSBOT_TEST_MODE") != "1":
        return
    if not url.startswith("sqlite:///"):
        return
    from pathlib import Path as _Path

    resolved = _Path(url[len("sqlite:///") :]).resolve()
    if resolved == _PRODUCTION_DB_PATH:
        raise RuntimeError(
            "BLOQUEADO: un test intento usar la base de datos REAL de "
            f"produccion ({_PRODUCTION_DB_PATH}). Cada test debe fijar su "
            "propio DATABASE_URL con os.environ.setdefault(...) ANTES de "
            "importar infrastructure.database / config.settings."
        )


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        url = _resolve_database_url()
        _assert_not_real_db_in_test_mode(url)
        connect_args = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False

        _engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)

        # Enable FK enforcement for SQLite (no-op on PostgreSQL)
        if url.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def _set_sqlite_pragma(dbapi_conn, _connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                # Incident 2026-08-05: concurrent webhook requests writing to
                # the same SQLite file can hit "database is locked". Without
                # busy_timeout, SQLite raises immediately instead of waiting
                # for the other writer to finish — busy_timeout makes it
                # retry internally for up to 5s before giving up.
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.close()

        _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
        logger.info("Database engine ready (%s)", url.split("@")[-1][:80])
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def init_db() -> None:
    """Create tables for all registered models (idempotent — safe for dev/SQLite)."""
    import models  # noqa: F401 — registers all tables

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _apply_schema_patches(engine)
    logger.info("Database tables ensured (%d tables).", len(Base.metadata.tables))


def _apply_schema_patches(engine) -> None:
    """Add columns missing on DBs created before model updates (no-op if present)."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    statements: list[str] = []

    if "businesses" in tables:
        cols = {col["name"] for col in inspector.get_columns("businesses")}
        if "pin_hash" not in cols:
            statements.append("ALTER TABLE businesses ADD COLUMN pin_hash VARCHAR(128)")

    if "customers" in tables:
        cols = {col["name"] for col in inspector.get_columns("customers")}
        if "phone" not in cols:
            statements.append("ALTER TABLE customers ADD COLUMN phone VARCHAR(32)")
        if "notes" not in cols:
            statements.append("ALTER TABLE customers ADD COLUMN notes TEXT")
        if "blocked" not in cols:
            statements.append(
                "ALTER TABLE customers ADD COLUMN blocked BOOLEAN NOT NULL DEFAULT 0"
            )
        if "last_order_items" not in cols:
            statements.append("ALTER TABLE customers ADD COLUMN last_order_items JSON")
        if "updated_at" not in cols:
            statements.append(
                "ALTER TABLE customers ADD COLUMN updated_at DATETIME "
                "NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )

    for sql in statements:
        with engine.begin() as conn:
            conn.execute(text(sql))
        logger.info("Schema patch applied: %s", sql)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a DB session."""
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager for scripts and services."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
