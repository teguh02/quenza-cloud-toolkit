"""Database engine, session factory, and declarative base.

Phase 1 only bootstraps the SQLite engine and creates tables on startup.
The full schema (Projects, Sources, Destinations, Schedules, Logs) is
expanded in later phases.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""


# SQLite requires `check_same_thread=False` when used across threads
# (e.g. FastAPI's threadpool for sync endpoints).
_connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def init_db() -> None:
    """Create all tables that do not yet exist.

    Imports models so they are registered on the metadata before
    `create_all` runs.
    """
    # Imported for side effect: registers models on Base.metadata.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
