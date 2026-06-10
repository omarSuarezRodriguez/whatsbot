"""SQLAlchemy engine, session factory and schema bootstrap."""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config.settings import BASE_DIR, DATABASE_URL, DATA_DIR

logger = logging.getLogger(__name__)

Base = declarative_base()

_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def _resolve_database_url() -> str:
    url = (DATABASE_URL or "").strip()
    if url:
        return url
    path = (DATA_DIR / "whatsbot.db").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.as_posix()}"


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        url = _resolve_database_url()
        connect_args = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
        _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
        logger.info("Database engine ready (%s)", url.split("@")[-1][:80])
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def init_db() -> None:
    """Create tables for all registered models."""
    import models  # noqa: F401 — registers all tables

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ensured (%d tables).", len(Base.metadata.tables))


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
