"""Adopt the phase-13 schema without rewriting existing records."""
from alembic import op
from sqlalchemy import inspect
from app.migrations.baseline import Base

revision = "001_baseline"
down_revision = None
branch_labels = depends_on = None


def upgrade():
    connection = op.get_bind()
    inspector = inspect(connection)
    for table in Base.metadata.sorted_tables:
        if inspector.has_table(table.name):
            existing = {column["name"] for column in inspector.get_columns(table.name)}
            missing = set(table.columns.keys()) - existing
            if missing:
                raise RuntimeError(f"Cannot adopt incompatible table {table.name}: missing {sorted(missing)}")
    Base.metadata.create_all(connection)


def downgrade():
    raise RuntimeError("Baseline downgrade would delete indexes. Restore a database backup instead.")
