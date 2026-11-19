"""Persist source-bound tutor dialogues and generation outcomes without secrets.

Revision ID: 0004_tutor
Revises: 0003_retrieval

Existing source selections, citation positions, and scientific review decisions
are preserved. Each turn records the revision and context used for that request.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_tutor"
down_revision = "0003_retrieval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tutor_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.String(length=255), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_id", "scope_id"],
            ["retrieval_scopes.project_id", "retrieval_scopes.id"],
            name="fk_tutor_conversations_scope",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("project_id", "id", name="uq_tutor_conversations_project_id"),
        sa.UniqueConstraint(
            "project_id", "id", "scope_id", name="uq_tutor_conversations_project_id_scope"
        ),
        sa.CheckConstraint("length(trim(owner_id)) > 0", name="ck_tutor_conversations_owner"),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_tutor_conversations_title"),
    )
    op.create_index("ix_tutor_conversations_project_id", "tutor_conversations", ["project_id"])
    op.create_index("ix_tutor_conversations_scope_id", "tutor_conversations", ["scope_id"])
    op.create_table(
        "tutor_turns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("depth", sa.String(length=16), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("scope_revision", sa.Integer(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=True),
        sa.Column(
            "filters", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "context_snapshot",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "answer", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("provider_name", sa.String(length=128), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("prompt_version", sa.String(length=128), nullable=False),
        sa.Column(
            "usage", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="generating", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["project_id", "conversation_id"],
            ["tutor_conversations.project_id", "tutor_conversations.id"],
            name="fk_tutor_turns_conversation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "scope_id"],
            ["retrieval_scopes.project_id", "retrieval_scopes.id"],
            name="fk_tutor_turns_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "conversation_id", "scope_id"],
            [
                "tutor_conversations.project_id",
                "tutor_conversations.id",
                "tutor_conversations.scope_id",
            ],
            name="fk_tutor_turns_conversation_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "module_id"],
            ["modules.project_id", "modules.id"],
            name="fk_tutor_turns_module",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("project_id", "id", name="uq_tutor_turns_project_id"),
        sa.UniqueConstraint("project_id", "request_id", name="uq_tutor_turns_project_request"),
        sa.UniqueConstraint(
            "conversation_id", "sequence", name="uq_tutor_turns_conversation_sequence"
        ),
        sa.CheckConstraint("sequence > 0", name="ck_tutor_turns_sequence"),
        sa.CheckConstraint("scope_revision > 0", name="ck_tutor_turns_scope_revision"),
        sa.CheckConstraint("length(trim(question)) > 0", name="ck_tutor_turns_question"),
        sa.CheckConstraint(
            "mode IN ('SOURCE_MODE','DEEP_PHYSICS_MODE','EXAM_MODE','SOCRATIC_MODE')",
            name="ck_tutor_turns_mode",
        ),
        sa.CheckConstraint("depth IN ('concise','standard','deep')", name="ck_tutor_turns_depth"),
        sa.CheckConstraint(
            "status IN ('generating','completed','failed')", name="ck_tutor_turns_status"
        ),
        sa.CheckConstraint("jsonb_typeof(filters) = 'object'", name="ck_tutor_turns_filters"),
        sa.CheckConstraint(
            "jsonb_typeof(context_snapshot) = 'object'", name="ck_tutor_turns_context_snapshot"
        ),
        sa.CheckConstraint("jsonb_typeof(answer) = 'object'", name="ck_tutor_turns_answer"),
        sa.CheckConstraint("jsonb_typeof(usage) = 'object'", name="ck_tutor_turns_usage"),
    )
    for column in ("project_id", "conversation_id", "scope_id", "module_id"):
        op.create_index(f"ix_tutor_turns_{column}", "tutor_turns", [column])


def downgrade() -> None:
    op.drop_table("tutor_turns")
    op.drop_table("tutor_conversations")
