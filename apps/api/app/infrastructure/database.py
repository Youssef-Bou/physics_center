"""Database construction is explicit; importing the app never mutates its schema."""

import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker


def make_engine(url: str | URL | None = None) -> Engine:
    database_url = url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is required")
    parsed = make_url(database_url)
    if parsed.drivername != "postgresql+psycopg":
        raise ValueError("Use a PostgreSQL URL with the psycopg driver")
    return create_engine(parsed, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
