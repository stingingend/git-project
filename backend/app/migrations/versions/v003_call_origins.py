"""Retain lexical call matches before repository-wide resolution."""
from alembic import op
import sqlalchemy as sa

revision = "003_call_origins"
down_revision = "002_job_history"
branch_labels = depends_on = None


def upgrade():
    op.create_table("call_origins",
        sa.Column("call_id", sa.Integer, sa.ForeignKey("call_sites.id"), primary_key=True),
        sa.Column("target_symbol_id", sa.Integer, sa.ForeignKey("symbols.id"), nullable=True),
        sa.Column("resolution", sa.String(20), nullable=False))


def downgrade():
    op.drop_table("call_origins")
