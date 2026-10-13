from sqlmodel import SQLModel

from Database import create_db_and_tables, engine

create_db_and_tables()
print(f"tables {list(SQLModel.metadata.tables)} created in {engine.url}")
