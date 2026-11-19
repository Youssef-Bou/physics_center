"""Add explicit retrieval selections, module assignment, and known chapter labels.

Revision ID: 0003_retrieval
Revises: 0002_evidence

The upgrade preserves existing originals, analyses, links, and review decisions.
It does not infer chapter labels or activate any pre-existing sources.
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_retrieval"
down_revision = "0002_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "modules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("project_id", "id", name="uq_modules_project_id"),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_modules_title"),
    )
    op.create_index("ix_modules_project_id", "modules", ["project_id"])
    op.create_table(
        "module_documents",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("project_id", "module_id", "document_id"),
        sa.ForeignKeyConstraint(
            ["project_id", "module_id"],
            ["modules.project_id", "modules.id"],
            name="fk_module_documents_module",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "document_id"],
            ["documents.project_id", "documents.id"],
            name="fk_module_documents_document",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_module_documents_document_id", "module_documents", ["document_id"])
    op.create_table(
        "retrieval_scopes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("project_id", "id", name="uq_retrieval_scopes_project_id"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_retrieval_scopes_name"),
        sa.CheckConstraint("revision > 0", name="ck_retrieval_scopes_revision"),
    )
    op.create_index("ix_retrieval_scopes_project_id", "retrieval_scopes", ["project_id"])
    op.create_table(
        "retrieval_scope_items",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("scope_id", "document_version_id"),
        sa.ForeignKeyConstraint(
            ["project_id", "scope_id"],
            ["retrieval_scopes.project_id", "retrieval_scopes.id"],
            name="fk_retrieval_scope_items_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "document_version_id"],
            ["document_versions.project_id", "document_versions.id"],
            name="fk_retrieval_scope_items_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "analysis_run_id", "document_version_id"],
            ["analysis_runs.project_id", "analysis_runs.id", "analysis_runs.document_version_id"],
            name="fk_retrieval_scope_items_run_version",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_retrieval_scope_items_project_id", "retrieval_scope_items", ["project_id"])
    op.create_index(
        "ix_retrieval_scope_items_analysis_run_id", "retrieval_scope_items", ["analysis_run_id"]
    )
    op.add_column("document_segments", sa.Column("chapter_label", sa.String(length=128)))
    op.create_check_constraint(
        "ck_segments_chapter_label",
        "document_segments",
        "chapter_label IS NULL OR length(trim(chapter_label)) > 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_segments_chapter_label", "document_segments", type_="check")
    op.drop_column("document_segments", "chapter_label")
    op.drop_table("retrieval_scope_items")
    op.drop_table("retrieval_scopes")
    op.drop_table("module_documents")
    op.drop_table("modules")
