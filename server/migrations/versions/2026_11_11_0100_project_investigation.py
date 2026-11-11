"""Add atomic project investigations and durable drafting identities."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "project_investigation_01"
down_revision = "project_research_brief_01"
branch_labels = None
depends_on = None


def timestamps():
    return [sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now()),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now())]


def upgrade():
    op.create_table("project_investigations",
        sa.Column("project_id",sa.UUID(),sa.ForeignKey("project.id",ondelete="CASCADE"),primary_key=True),
        sa.Column("schema_version",sa.Integer(),nullable=False),
        sa.Column("revision",sa.BigInteger(),nullable=False),
        sa.Column("document",JSONB(),nullable=False),
        sa.Column("updated_by",sa.UUID(),sa.ForeignKey("users.id",ondelete="SET NULL")),
        sa.CheckConstraint("schema_version = 1 AND revision > 0",name="ck_investigation_version"),*timestamps())
    op.create_table("project_draft_requests",
        sa.Column("id",sa.UUID(),primary_key=True),
        sa.Column("project_id",sa.UUID(),sa.ForeignKey("project.id",ondelete="CASCADE"),nullable=False),
        sa.Column("requester_id",sa.UUID(),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
        sa.Column("request_hash",sa.String(64),nullable=False),sa.Column("snapshot",JSONB(),nullable=False),
        sa.Column("base_revision",sa.BigInteger(),nullable=False),sa.Column("section_id",sa.UUID(),nullable=False),
        sa.Column("state",sa.String(16),nullable=False),sa.Column("error_code",sa.String(100)),
        sa.Column("conversation_id",sa.UUID(),sa.ForeignKey("conversations.id",ondelete="SET NULL")),
        sa.Column("message_id",sa.UUID(),sa.ForeignKey("messages.id",ondelete="SET NULL")),
        sa.CheckConstraint("state IN ('pending','running','completed','failed','uncertain')",name="ck_draft_request_state"),*timestamps())
    op.create_index("ix_project_draft_requests_project_id","project_draft_requests",["project_id"])


def downgrade():
    # Disposable migration tests only. Application rollback must retain authored data.
    op.drop_table("project_draft_requests")
    op.drop_table("project_investigations")
