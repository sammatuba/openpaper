"""Keep a project's folded research brief separate from its description."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "project_research_brief_01"
down_revision = "mcp_research_import_01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("project", sa.Column("research_brief", JSONB(), nullable=True))


def downgrade():
    op.drop_column("project", "research_brief")
