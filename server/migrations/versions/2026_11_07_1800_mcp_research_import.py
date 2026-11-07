"""Durable, per-source deduplication for MCP research PDF imports."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "mcp_research_import_01"
down_revision = "mcp_project_requests_01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mcp_paper_import_requests",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("request_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_key", sa.String(600), nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("upload_job_id", UUID(as_uuid=True), nullable=True),
        sa.Column("paper_id", UUID(as_uuid=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.UniqueConstraint("user_id", "project_id", "source_key", name="uq_mcp_import_source"),
    )


def downgrade():
    op.drop_table("mcp_paper_import_requests")
