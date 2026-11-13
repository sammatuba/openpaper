"""Add versioned research identity, review mappings, proposals and metered admission core."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "research_core_01"
down_revision = "project_investigation_01"
branch_labels = None
depends_on = None


def timestamps():
    return [sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now()),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now())]


def upgrade():
    op.create_table("research_projects",
        sa.Column("project_id",sa.UUID(),sa.ForeignKey("project.id",ondelete="CASCADE"),primary_key=True),
        sa.Column("storage_generation",sa.String(4),nullable=False,server_default="v1"),
        sa.Column("change_sequence",sa.BigInteger(),nullable=False,server_default="0"),
        sa.Column("conversion_manifest",JSONB()),
        sa.CheckConstraint("storage_generation IN ('v1','v2')",name="ck_research_generation"),*timestamps())
    op.create_table("research_source_versions",
        sa.Column("id",sa.UUID(),primary_key=True),
        sa.Column("project_id",sa.UUID(),sa.ForeignKey("project.id",ondelete="CASCADE"),nullable=False),
        sa.Column("paper_id",sa.UUID(),sa.ForeignKey("papers.id",ondelete="SET NULL")),
        sa.Column("kind",sa.String(20),nullable=False,server_default="paper_text"),
        sa.Column("extractor",sa.String(100),nullable=False),
        sa.Column("text_sha256",sa.String(64),nullable=False),
        sa.Column("line_count",sa.Integer()),sa.Column("byte_size",sa.Integer()),
        sa.Column("metadata",JSONB(),nullable=False,server_default="{}"),*timestamps())
    op.create_index("ix_research_source_versions_project_id","research_source_versions",["project_id"])
    op.create_index("ix_research_source_versions_text_sha256","research_source_versions",["text_sha256"])
    op.create_index("ix_research_source_versions_paper_id","research_source_versions",["paper_id"])
    op.create_table("research_entities",
        sa.Column("id",sa.UUID(),primary_key=True),
        sa.Column("project_id",sa.UUID(),sa.ForeignKey("project.id",ondelete="CASCADE"),nullable=False),
        sa.Column("type",sa.String(20),nullable=False),
        sa.Column("revision",sa.Integer(),nullable=False,server_default="1"),
        sa.Column("payload",JSONB(),nullable=False),
        sa.Column("archived",sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column("created_by",sa.UUID(),sa.ForeignKey("users.id",ondelete="SET NULL")),
        sa.CheckConstraint("type IN ('question','claim','finding','assumption','decision','gap')",name="ck_research_entity_type"),
        sa.CheckConstraint("revision > 0",name="ck_research_entity_revision"),*timestamps())
    op.create_index("ix_research_entities_project_type","research_entities",["project_id","type"])
    op.create_table("research_entity_revisions",
        sa.Column("id",sa.UUID(),primary_key=True),
        sa.Column("entity_id",sa.UUID(),sa.ForeignKey("research_entities.id",ondelete="CASCADE"),nullable=False),
        sa.Column("revision",sa.Integer(),nullable=False),
        sa.Column("payload",JSONB(),nullable=False),
        sa.Column("origin",sa.String(20),nullable=False),
        sa.Column("provenance",JSONB(),nullable=False,server_default="{}"),
        sa.Column("actor_id",sa.UUID(),sa.ForeignKey("users.id",ondelete="SET NULL")),
        sa.Column("derived_from",JSONB()),
        sa.UniqueConstraint("entity_id","revision",name="uq_research_entity_revision"),
        sa.CheckConstraint("origin IN ('human','assembled','assistant','imported','external_ai')",name="ck_research_revision_origin"),*timestamps())
    op.create_index("ix_research_entity_revisions_entity_id","research_entity_revisions",["entity_id"])
    op.create_table("research_relations",
        sa.Column("id",sa.UUID(),primary_key=True),
        sa.Column("project_id",sa.UUID(),sa.ForeignKey("project.id",ondelete="CASCADE"),nullable=False),
        sa.Column("relation_type",sa.String(20),nullable=False),
        sa.Column("source_id",sa.UUID(),sa.ForeignKey("research_entities.id",ondelete="CASCADE"),nullable=False),
        sa.Column("target_id",sa.UUID(),sa.ForeignKey("research_entities.id",ondelete="CASCADE"),nullable=False),
        sa.Column("rationale",sa.Text(),nullable=False),
        sa.Column("revision",sa.Integer(),nullable=False,server_default="1"),
        sa.Column("archived",sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.CheckConstraint("relation_type IN ('supports','challenges','qualifies','assumes','motivates','tests','measures','derived_from','cites')",name="ck_research_relation_type"),
        sa.CheckConstraint("revision > 0",name="ck_research_relation_revision"),*timestamps())
    op.create_index("ix_research_relations_project_id","research_relations",["project_id"])
    op.create_table("review_protocols",
        sa.Column("id",sa.UUID(),primary_key=True),
        sa.Column("project_id",sa.UUID(),sa.ForeignKey("project.id",ondelete="CASCADE"),nullable=False),
        sa.Column("version",sa.Integer(),nullable=False),
        sa.Column("mode",sa.String(16),nullable=False,server_default="literature"),
        sa.Column("unit_of_analysis",sa.String(30),nullable=False,server_default="report"),
        sa.Column("count_policy",JSONB(),nullable=False,server_default="{}"),
        sa.Column("criteria",JSONB(),nullable=False,server_default="[]"),
        sa.Column("screening_modes",JSONB(),nullable=False,server_default="{}"),
        sa.Column("status",sa.String(16),nullable=False,server_default="draft"),
        sa.Column("parent_version_id",sa.UUID(),sa.ForeignKey("review_protocols.id",ondelete="SET NULL")),
        sa.UniqueConstraint("project_id","version",name="uq_review_protocol_version"),
        sa.CheckConstraint("mode IN ('systematic','scoping','literature')",name="ck_review_protocol_mode"),*timestamps())
    op.create_index("ix_review_protocols_project_id","review_protocols",["project_id"])
    op.create_table("review_reports",
        sa.Column("id",sa.UUID(),primary_key=True),
        sa.Column("project_id",sa.UUID(),sa.ForeignKey("project.id",ondelete="CASCADE"),nullable=False),
        sa.Column("identity_state",sa.String(16),nullable=False,server_default="unreviewed"),
        sa.Column("merged_into",sa.UUID(),sa.ForeignKey("review_reports.id",ondelete="SET NULL")),*timestamps())
    op.create_index("ix_review_reports_project_id","review_reports",["project_id"])
    op.create_table("review_report_versions",
        sa.Column("id",sa.UUID(),primary_key=True),
        sa.Column("report_id",sa.UUID(),sa.ForeignKey("review_reports.id",ondelete="CASCADE"),nullable=False),
        sa.Column("version_label",sa.String(50),nullable=False,server_default="v1"),
        sa.Column("source_version_id",sa.UUID(),sa.ForeignKey("research_source_versions.id",ondelete="SET NULL")),
        sa.Column("sha256",sa.String(64)),sa.Column("bibliographic",JSONB(),nullable=False,server_default="{}"),*timestamps())
    op.create_index("ix_review_report_versions_report_id","review_report_versions",["report_id"])
    op.create_table("review_occurrences",
        sa.Column("id",sa.UUID(),primary_key=True),
        sa.Column("project_id",sa.UUID(),sa.ForeignKey("project.id",ondelete="CASCADE"),nullable=False),
        sa.Column("provider",sa.String(50),nullable=False),
        sa.Column("search_ref",sa.String(200),nullable=False),
        sa.Column("external_hit_id",sa.String(200),nullable=False),
        sa.Column("report_id",sa.UUID(),sa.ForeignKey("review_reports.id",ondelete="SET NULL")),
        sa.Column("version_id",sa.UUID(),sa.ForeignKey("review_report_versions.id",ondelete="SET NULL")),*timestamps())
    op.create_index("ix_review_occurrences_project_id","review_occurrences",["project_id"])
    op.create_table("review_studies",
        sa.Column("id",sa.UUID(),primary_key=True),
        sa.Column("project_id",sa.UUID(),sa.ForeignKey("project.id",ondelete="CASCADE"),nullable=False),
        sa.Column("description",sa.Text(),nullable=False,server_default=""),*timestamps())
    op.create_index("ix_review_studies_project_id","review_studies",["project_id"])
    op.create_table("review_report_studies",
        sa.Column("report_id",sa.UUID(),sa.ForeignKey("review_reports.id",ondelete="CASCADE"),primary_key=True),
        sa.Column("study_id",sa.UUID(),sa.ForeignKey("review_studies.id",ondelete="CASCADE"),primary_key=True),
        sa.Column("linkage_state",sa.String(16),nullable=False,server_default="proposed"),
        sa.Column("rationale",sa.Text(),nullable=False,server_default=""),*timestamps())
    op.create_table("review_candidates",
        sa.Column("id",sa.UUID(),primary_key=True),
        sa.Column("project_id",sa.UUID(),sa.ForeignKey("project.id",ondelete="CASCADE"),nullable=False),
        sa.Column("report_id",sa.UUID(),sa.ForeignKey("review_reports.id",ondelete="CASCADE"),nullable=False),
        sa.Column("selected_version_id",sa.UUID(),sa.ForeignKey("review_report_versions.id",ondelete="SET NULL")),
        sa.Column("retained",sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.Column("prescreen_category",sa.String(30)),
        sa.UniqueConstraint("project_id","report_id",name="uq_review_candidate_report"),*timestamps())
    op.create_index("ix_review_candidates_project_id","review_candidates",["project_id"])
    op.create_table("review_decisions",
        sa.Column("id",sa.UUID(),primary_key=True),
        sa.Column("candidate_id",sa.UUID(),sa.ForeignKey("review_candidates.id",ondelete="CASCADE"),nullable=False),
        sa.Column("stage",sa.String(16),nullable=False),
        sa.Column("protocol_version",sa.Integer(),nullable=False),
        sa.Column("actor_id",sa.UUID(),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
        sa.Column("decision",sa.String(12),nullable=False),
        sa.Column("role",sa.String(16),nullable=False,server_default="primary"),
        sa.Column("reason",sa.Text(),nullable=False,server_default=""),
        sa.Column("cited_text",sa.Text()),sa.Column("criterion_judgments",JSONB(),nullable=False,server_default="[]"),
        sa.CheckConstraint("decision IN ('included','excluded','unclear')",name="ck_review_decision_value"),
        sa.CheckConstraint("stage IN ('title_abstract','fulltext')",name="ck_review_decision_stage"),
        sa.CheckConstraint("role IN ('primary','secondary','adjudication')",name="ck_review_decision_role"),*timestamps())
    op.create_index("ix_review_decisions_candidate_id","review_decisions",["candidate_id"])
    op.create_table("review_mapping_events",
        sa.Column("id",sa.UUID(),primary_key=True),
        sa.Column("project_id",sa.UUID(),sa.ForeignKey("project.id",ondelete="CASCADE"),nullable=False),
        sa.Column("kind",sa.String(20),nullable=False),
        sa.Column("payload",JSONB(),nullable=False),
        sa.Column("actor_id",sa.UUID(),sa.ForeignKey("users.id",ondelete="SET NULL")),
        sa.CheckConstraint("kind IN ('occurrence_map','report_merge','report_split','version_replace','protocol_amend','study_link')",name="ck_review_mapping_kind"),*timestamps())
    op.create_index("ix_review_mapping_events_project_id","review_mapping_events",["project_id"])
    op.create_table("research_proposals",
        sa.Column("id",sa.UUID(),primary_key=True),
        sa.Column("project_id",sa.UUID(),sa.ForeignKey("project.id",ondelete="CASCADE"),nullable=False),
        sa.Column("origin",sa.String(20),nullable=False),
        sa.Column("payload",JSONB(),nullable=False),
        sa.Column("payload_sha256",sa.String(64),nullable=False),
        sa.Column("targets",JSONB(),nullable=False),
        sa.Column("state",sa.String(16),nullable=False,server_default="pending"),
        sa.Column("approval",JSONB()),sa.Column("receipt",JSONB()),sa.Column("idempotency_key",sa.String(100)),
        sa.Column("created_by",sa.UUID(),sa.ForeignKey("users.id",ondelete="SET NULL")),
        sa.UniqueConstraint("project_id","idempotency_key",name="uq_research_proposal_key"),
        sa.CheckConstraint("state IN ('pending','approved','applied','discarded','expired','stale')",name="ck_research_proposal_state"),
        sa.CheckConstraint("origin IN ('human','assembled','assistant','imported','external_ai')",name="ck_research_proposal_origin"),*timestamps())
    op.create_table("metered_price_tables",
        sa.Column("version",sa.Integer(),primary_key=True,autoincrement=False),
        sa.Column("prices",JSONB(),nullable=False),*timestamps())
    op.create_table("metered_operations",
        sa.Column("id",sa.UUID(),primary_key=True),
        sa.Column("project_id",sa.UUID(),sa.ForeignKey("project.id",ondelete="CASCADE"),nullable=False),
        sa.Column("actor_id",sa.UUID(),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
        sa.Column("operation_type",sa.String(60),nullable=False),
        sa.Column("price_table_version",sa.Integer()),
        sa.Column("payload_sha256",sa.String(64),nullable=False),
        sa.Column("estimate",JSONB(),nullable=False),
        sa.Column("reservation",JSONB(),nullable=False,server_default="{}"),
        sa.Column("state",sa.String(16),nullable=False,server_default="reserved"),
        sa.Column("usage",JSONB()),sa.Column("error_code",sa.String(100)),sa.Column("idempotency_key",sa.String(100)),
        sa.UniqueConstraint("project_id","operation_type","idempotency_key",name="uq_metered_operation_key"),
        sa.CheckConstraint("state IN ('reserved','admitted','running','completed','failed','uncertain','cancelled','expired')",name="ck_metered_operation_state"),*timestamps())
    op.create_index("ix_metered_operations_project_id","metered_operations",["project_id"])


def downgrade():
    # Disposable migration tests only. Application rollback must retain authored data.
    op.drop_table("metered_operations")
    op.drop_table("metered_price_tables")
    op.drop_table("research_proposals")
    op.drop_table("review_mapping_events")
    op.drop_table("review_decisions")
    op.drop_table("review_candidates")
    op.drop_table("review_report_studies")
    op.drop_table("review_studies")
    op.drop_table("review_occurrences")
    op.drop_table("review_report_versions")
    op.drop_table("review_reports")
    op.drop_table("review_protocols")
    op.drop_table("research_relations")
    op.drop_table("research_entity_revisions")
    op.drop_table("research_entities")
    op.drop_table("research_source_versions")
    op.drop_table("research_projects")
