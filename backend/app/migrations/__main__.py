import os
from sqlalchemy import text
from app.database import create_database
from . import upgrade_database

engine, _ = create_database(os.getenv("DATABASE_URL", "sqlite:///./codeatlas-metadata.db"))
try:
    upgrade_database(engine)
    with engine.connect() as connection:
        print("Database schema:", connection.scalar(text("SELECT version_num FROM alembic_version")))
finally:
    engine.dispose()
