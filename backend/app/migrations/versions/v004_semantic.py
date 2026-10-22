"""Portable embedding cache with optional native pgvector storage."""
from alembic import op
import sqlalchemy as sa

revision = "004_semantic"
down_revision = "003_call_origins"
branch_labels = depends_on = None


def upgrade():
    op.create_table("search_documents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("repository_id", sa.Integer, sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("file_id", sa.Integer, sa.ForeignKey("source_files.id"), nullable=False),
        sa.Column("symbol_id", sa.Integer, sa.ForeignKey("symbols.id"), nullable=True),
        sa.Column("unit_key", sa.String(80), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("embedding", sa.Text, nullable=False),
        sa.UniqueConstraint("file_id", "unit_key"))
    op.create_index("ix_search_documents_repository_id", "search_documents", ["repository_id"])
    op.create_index("ix_search_documents_file_id", "search_documents", ["file_id"])
    op.create_table("semantic_snapshots",
        sa.Column("repository_id", sa.Integer, sa.ForeignKey("repositories.id"), primary_key=True),
        sa.Column("commit_sha", sa.String(40), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("document_count", sa.Integer, nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False))
    connection = op.get_bind()
    if connection.dialect.name == "postgresql" and connection.scalar(sa.text(
            "SELECT EXISTS(SELECT 1 FROM pg_available_extensions WHERE name='vector')")):
        op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
        op.execute("CREATE TABLE search_vectors (document_id INTEGER PRIMARY KEY REFERENCES search_documents(id) "
                   "ON DELETE CASCADE, embedding public.vector(256) NOT NULL)")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TABLE IF EXISTS search_vectors")
    op.drop_table("semantic_snapshots")
    op.drop_table("search_documents")
