"""Index repository job history without changing saved records."""
from alembic import op

revision = "002_job_history"
down_revision = "001_baseline"
branch_labels = depends_on = None


def upgrade():
    op.create_index("ix_index_jobs_repository_created", "index_jobs", ["repository_id", "created_at"])


def downgrade():
    op.drop_index("ix_index_jobs_repository_created", table_name="index_jobs")
