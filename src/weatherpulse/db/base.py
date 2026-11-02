from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Dialect, MetaData, TypeDecorator
from sqlalchemy.orm import DeclarativeBase


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class UTCDateTime(TypeDecorator[datetime]):
    """DateTime type that ensures timezone-awareness across database dialects.

    SQLite stores DATETIME as a string without timezone offset. This decorator
    ensures naive datetime values read back from SQLite are attached with UTC
    tzinfo, preserving timezone-aware semantics.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is not None and isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=UTC)
            return value.astimezone(UTC)
        return value

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is not None and isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=UTC)
        return value


class Base(DeclarativeBase):
    """Base class for SQLAlchemy declarative models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        datetime: UTCDateTime,
    }
