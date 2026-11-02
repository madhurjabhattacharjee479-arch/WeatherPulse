from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, make_url
from sqlalchemy.pool import StaticPool

from weatherpulse.config import load_settings


def create_engine_from_settings(**kwargs: Any) -> Engine:
    """Create a SQLAlchemy engine from environment-backed settings."""
    return create_engine_from_url(load_settings().database_url, **kwargs)


def create_engine_from_url(database_url: str, **kwargs: Any) -> Engine:
    """Create an engine for SQLite or PostgreSQL database URLs.

    SQLite file parents are created automatically for local development, and
    SQLite connections are configured to enforce foreign keys.
    """
    url = make_url(database_url)
    connect_args = dict(kwargs.pop("connect_args", {}))

    if url.get_backend_name() == "sqlite":
        if url.database and url.database != ":memory:":
            Path(url.database).expanduser().parent.mkdir(parents=True, exist_ok=True)

        connect_args.setdefault("check_same_thread", False)
        kwargs["connect_args"] = connect_args

        if url.database in (None, "", ":memory:"):
            kwargs.setdefault("poolclass", StaticPool)

    engine = create_engine(url, future=True, **kwargs)

    if url.get_backend_name() == "sqlite":
        _enable_sqlite_foreign_keys(engine)

    return engine


def _enable_sqlite_foreign_keys(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
