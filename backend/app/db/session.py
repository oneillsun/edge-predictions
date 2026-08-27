from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.models import Base


def _connect_args(database_url: str) -> dict[str, object]:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


engine = create_engine(settings.database_url, connect_args=_connect_args(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def ensure_schema() -> None:
    """Create tables if they don't exist yet.

    Convenience for local sqlite dev only — Alembic (alembic/) is the source
    of truth for schema changes and is required once a real Postgres
    environment is in play.
    """
    Base.metadata.create_all(bind=engine)
