"""Preserve correction ancestry and provenance of subsequently added evidence.

Revision ID: 0002_evidence
Revises: 0001_knowledge
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_evidence"
down_revision = "0001_knowledge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("topic_relations", sa.Column("corrected_from_id", sa.Uuid(), nullable=True))
    op.create_index(
        "ix_topic_relations_corrected_from_id", "topic_relations", ["corrected_from_id"]
    )
    op.create_foreign_key(
        "fk_topic_relations_corrected_from",
        "topic_relations",
        "topic_relations",
        ["project_id", "corrected_from_id"],
        ["project_id", "id"],
        ondelete="RESTRICT",
    )
    op.add_column("link_evidence", sa.Column("analysis_run_id", sa.Uuid(), nullable=True))
    op.add_column("link_evidence", sa.Column("created_by", sa.String(length=255), nullable=True))
    op.create_index("ix_link_evidence_analysis_run_id", "link_evidence", ["analysis_run_id"])
    op.create_foreign_key(
        "fk_link_evidence_analysis_run",
        "link_evidence",
        "analysis_runs",
        ["project_id", "analysis_run_id"],
        ["project_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_link_evidence_analysis_run", "link_evidence", type_="foreignkey")
    op.drop_index("ix_link_evidence_analysis_run_id", table_name="link_evidence")
    op.drop_column("link_evidence", "created_by")
    op.drop_column("link_evidence", "analysis_run_id")
    op.drop_constraint("fk_topic_relations_corrected_from", "topic_relations", type_="foreignkey")
    op.drop_index("ix_topic_relations_corrected_from_id", table_name="topic_relations")
    op.drop_column("topic_relations", "corrected_from_id")
