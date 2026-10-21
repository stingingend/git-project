"""Apply packaged Alembic revisions to new and pre-migration databases."""
from pathlib import Path
from alembic import command
from alembic.config import Config


def upgrade_database(engine):
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent))
    with engine.begin() as connection:
        if connection.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN")
        elif connection.dialect.name == "postgresql":
            connection.exec_driver_sql("SELECT pg_advisory_xact_lock(1145262675)")
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
