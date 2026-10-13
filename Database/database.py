from pathlib import Path

from sqlalchemy.engine import make_url
from sqlmodel import Session, SQLModel, create_engine

from Settings.config import settings
from Database import tables  # noqa: F401  registers the tables on SQLModel.metadata

_url = make_url(settings.DB_NAME)
_is_sqlite = _url.get_backend_name() == "sqlite"

engine = create_engine(
    _url,
    # telegram handlers may touch the db from different threads
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)


def create_db_and_tables() -> None:
    if _is_sqlite and _url.database not in (None, "", ":memory:"):
        Path(_url.database).parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)
