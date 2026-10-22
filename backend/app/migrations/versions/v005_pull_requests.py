"""Persist targeted indexing requests and read-only PR analysis jobs."""
from alembic import op
import sqlalchemy as sa

revision = "005_pull_requests"
down_revision = "004_semantic"
branch_labels = depends_on = None


def upgrade():
    op.create_table("job_targets",
        sa.Column("job_id", sa.String(36), sa.ForeignKey("index_jobs.id"), primary_key=True),
        sa.Column("commit_sha", sa.String(40), nullable=False))
    op.create_table("pull_request_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("repository_id", sa.Integer, sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("delivery_id", sa.String(80), unique=True, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.Text, nullable=True),
        sa.Column("error", sa.Text, nullable=True))
    op.create_index("ix_pull_request_reports_repository_id", "pull_request_reports", ["repository_id"])


def downgrade():
    op.drop_table("pull_request_reports")
    op.drop_table("job_targets")
