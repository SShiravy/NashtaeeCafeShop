from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateColumn
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
    _add_new_columns()


def _add_new_columns() -> None:
    """Add the columns, and their indexes, added to a table after the db was made.

    create_all() leaves tables that already exist as they are. A new column must be
    nullable or have a server_default, for the rows already in its table.
    """
    with engine.begin() as connection:
        database = inspect(connection)
        for table in SQLModel.metadata.sorted_tables:
            existing = {column["name"] for column in database.get_columns(table.name)}
            for column in table.columns:
                if column.name not in existing:
                    definition = CreateColumn(column).compile(dialect=engine.dialect)
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table.name} ADD COLUMN {definition}"
                    )
            for index in table.indexes:
                index.create(connection, checkfirst=True)


def get_session() -> Session:
    return Session(engine)
