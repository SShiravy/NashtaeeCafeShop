import sqlite3
from contextlib import closing
from pathlib import Path

from Database.database import engine


def database_file() -> Path | None:
    """The SQLite file behind the engine, or None for other databases."""
    url = engine.url
    if url.get_backend_name() != "sqlite" or url.database in (None, "", ":memory:"):
        return None
    return Path(url.database)


def backup_to(target: Path) -> None:
    """Copy the database to target with SQLite's online backup API."""
    source = database_file()
    if source is None:
        raise RuntimeError(f"only SQLite databases can be backed up, not {engine.url}")
    with (
        closing(sqlite3.connect(source)) as source_db,
        closing(sqlite3.connect(target)) as target_db,
    ):
        source_db.backup(target_db)
