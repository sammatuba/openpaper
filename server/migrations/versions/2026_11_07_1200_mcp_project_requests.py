"""Keep project creation retries independent of mutable project state."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "mcp_project_requests_01"
down_revision = "mcp_note_requests_01"
branch_labels = None
depends_on = None


def upgrade():
    # Old browser races could insert identical associations. Preserve one row
    # for every logical link; never touch papers, notes, highlights or annotations.
    # Hold the write lock through uniqueness creation, including against old code.
    op.execute("LOCK TABLE project_paper IN SHARE ROW EXCLUSIVE MODE")
    op.execute("DELETE FROM project_paper a USING project_paper b "
               "WHERE a.project_id=b.project_id AND a.paper_id=b.paper_id AND a.id>b.id")
    op.create_unique_constraint("uq_project_paper_project_id_paper_id", "project_paper", ["project_id", "paper_id"])
    op.create_table(
        "mcp_project_requests",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("request_id", UUID(as_uuid=True), primary_key=True),
        # Deliberately no project FK: deletion must not erase replay history.
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("mcp_project_requests")
    op.drop_constraint("uq_project_paper_project_id_paper_id", "project_paper", type_="unique")
