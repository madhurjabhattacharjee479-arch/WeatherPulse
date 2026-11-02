from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session, sessionmaker

from weatherpulse.db.engine import create_engine_from_settings

SessionLocal = sessionmaker(
    bind=create_engine_from_settings(),
    autoflush=False,
    expire_on_commit=False,
)


def get_session_factory(engine) -> sessionmaker[Session]:
    """Return a session factory bound to the provided engine."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(
    session_factory: sessionmaker[Session] = SessionLocal,
) -> Iterator[Session]:
    """Provide a transactional session that commits or rolls back atomically."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
