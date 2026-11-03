"""Record MCP note append request IDs atomically with the note."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "mcp_note_requests_01"
down_revision = "9b8653fb667e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("mcp_oauth_store",
        sa.Column("collection", sa.Text(), primary_key=True),
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("ttl", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.create_index("idx_mcp_oauth_store_expires_at", "mcp_oauth_store", ["expires_at"])
    op.create_table("mcp_note_requests",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("request_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("paper_id", UUID(as_uuid=True), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade():
    op.drop_table("mcp_note_requests")
    op.drop_index("idx_mcp_oauth_store_expires_at", table_name="mcp_oauth_store")
    op.drop_table("mcp_oauth_store")
