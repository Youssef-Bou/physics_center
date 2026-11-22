"""PostgreSQL persistence for provenance-preserving knowledge proposals.

All endpoint foreign keys include the project so a guessed UUID cannot create a
cross-project edge. These records do not assert scientific correctness: generated
links start as proposals, while review decisions provide an append-only audit.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Identified:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Project(Identified, Timestamped, Base):
    __tablename__ = "projects"

    owner_id: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(500))

    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="ck_projects_title"),
        CheckConstraint("length(trim(owner_id)) > 0", name="ck_projects_owner"),
    )


class Topic(Identified, Timestamped, Base):
    __tablename__ = "topics"

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(500))
    aliases: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=sql_text("'[]'::jsonb")
    )

    __table_args__ = (
        UniqueConstraint("project_id", "id", name="uq_topics_project_id"),
        UniqueConstraint("project_id", "name", name="uq_topics_project_name"),
        CheckConstraint("length(trim(name)) > 0", name="ck_topics_name"),
        CheckConstraint("jsonb_typeof(aliases) = 'array'", name="ck_topics_aliases"),
    )


class Module(Identified, Timestamped, Base):
    __tablename__ = "modules"

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(500))

    __table_args__ = (
        UniqueConstraint("project_id", "id", name="uq_modules_project_id"),
        CheckConstraint("length(trim(title)) > 0", name="ck_modules_title"),
    )


class Document(Identified, Timestamped, Base):
    __tablename__ = "documents"

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(500))
    source_type: Mapped[str] = mapped_column(String(32))

    __table_args__ = (
        UniqueConstraint("project_id", "id", name="uq_documents_project_id"),
        CheckConstraint("length(trim(title)) > 0", name="ck_documents_title"),
        CheckConstraint(
            "source_type IN ('textbook','lecture_notes','exercise_sheet','worked_solution',"
            "'past_exam','paper','website','other')",
            name="ck_documents_source_type",
        ),
    )


class ModuleDocument(Base):
    __tablename__ = "module_documents"

    project_id: Mapped[UUID] = mapped_column(primary_key=True)
    module_id: Mapped[UUID] = mapped_column(primary_key=True)
    document_id: Mapped[UUID] = mapped_column(primary_key=True, index=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "module_id"],
            ["modules.project_id", "modules.id"],
            name="fk_module_documents_module",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_id", "document_id"],
            ["documents.project_id", "documents.id"],
            name="fk_module_documents_document",
            ondelete="RESTRICT",
        ),
    )


class DocumentVersion(Identified, Timestamped, Base):
    __tablename__ = "document_versions"

    project_id: Mapped[UUID] = mapped_column(index=True)
    document_id: Mapped[UUID] = mapped_column(index=True)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(255))
    page_count: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "document_id"],
            ["documents.project_id", "documents.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("project_id", "id", name="uq_versions_project_id"),
        UniqueConstraint("document_id", "sha256", name="uq_versions_document_hash"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_versions_hash"),
        CheckConstraint("page_count > 0", name="ck_versions_page_count"),
        CheckConstraint("length(storage_key) > 0", name="ck_versions_storage_key"),
    )


class AnalysisRun(Identified, Timestamped, Base):
    __tablename__ = "analysis_runs"

    project_id: Mapped[UUID] = mapped_column(index=True)
    document_version_id: Mapped[UUID] = mapped_column(index=True)
    identity_key: Mapped[str] = mapped_column(String(64))
    extractor_version: Mapped[str] = mapped_column(String(255))
    analyzer_version: Mapped[str] = mapped_column(String(255))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    issues: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=sql_text("'[]'::jsonb")
    )
    result: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=sql_text("'{}'::jsonb")
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "document_version_id"],
            ["document_versions.project_id", "document_versions.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("project_id", "id", name="uq_runs_project_id"),
        UniqueConstraint(
            "project_id", "id", "document_version_id", name="uq_runs_project_id_version"
        ),
        UniqueConstraint("document_version_id", "identity_key", name="uq_runs_version_identity"),
    )


class DocumentSegment(Identified, Timestamped, Base):
    __tablename__ = "document_segments"

    project_id: Mapped[UUID] = mapped_column(index=True)
    document_version_id: Mapped[UUID] = mapped_column(index=True)
    analysis_run_id: Mapped[UUID] = mapped_column(index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    page_number: Mapped[int] = mapped_column(Integer)
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    chapter_label: Mapped[str | None] = mapped_column(String(128))
    issues: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=sql_text("'[]'::jsonb")
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "analysis_run_id", "document_version_id"],
            ["analysis_runs.project_id", "analysis_runs.id", "analysis_runs.document_version_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("project_id", "id", name="uq_segments_project_id"),
        UniqueConstraint(
            "project_id", "id", "document_version_id", name="uq_segments_project_id_version"
        ),
        UniqueConstraint(
            "document_version_id", "fingerprint", name="uq_segments_version_fingerprint"
        ),
        CheckConstraint("page_number > 0", name="ck_segments_page"),
        CheckConstraint(
            "start_offset >= 0 AND end_offset > start_offset", name="ck_segments_offsets"
        ),
        CheckConstraint("length(text) = end_offset - start_offset", name="ck_segments_text_span"),
        CheckConstraint(
            "chapter_label IS NULL OR length(trim(chapter_label)) > 0",
            name="ck_segments_chapter_label",
        ),
    )


class RetrievalScope(Identified, Timestamped, Base):
    """Explicit project-bound source selection; a later chat can reference it."""

    __tablename__ = "retrieval_scopes"

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(300))
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    __table_args__ = (
        UniqueConstraint("project_id", "id", name="uq_retrieval_scopes_project_id"),
        CheckConstraint("length(trim(name)) > 0", name="ck_retrieval_scopes_name"),
        CheckConstraint("revision > 0", name="ck_retrieval_scopes_revision"),
    )


class RetrievalScopeItem(Base):
    """A pinned document version and analysis, never an implicit latest version."""

    __tablename__ = "retrieval_scope_items"

    project_id: Mapped[UUID] = mapped_column(index=True)
    scope_id: Mapped[UUID] = mapped_column(primary_key=True)
    document_version_id: Mapped[UUID] = mapped_column(primary_key=True)
    analysis_run_id: Mapped[UUID] = mapped_column(index=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "scope_id"],
            ["retrieval_scopes.project_id", "retrieval_scopes.id"],
            name="fk_retrieval_scope_items_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_id", "document_version_id"],
            ["document_versions.project_id", "document_versions.id"],
            name="fk_retrieval_scope_items_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_id", "analysis_run_id", "document_version_id"],
            ["analysis_runs.project_id", "analysis_runs.id", "analysis_runs.document_version_id"],
            name="fk_retrieval_scope_items_run_version",
            ondelete="RESTRICT",
        ),
    )


class Exercise(Identified, Timestamped, Base):
    __tablename__ = "exercises"

    project_id: Mapped[UUID] = mapped_column(index=True)
    document_version_id: Mapped[UUID] = mapped_column(index=True)
    analysis_run_id: Mapped[UUID] = mapped_column(index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(128))
    issues: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=sql_text("'[]'::jsonb")
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "analysis_run_id", "document_version_id"],
            ["analysis_runs.project_id", "analysis_runs.id", "analysis_runs.document_version_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("project_id", "id", name="uq_exercises_project_id"),
        UniqueConstraint(
            "project_id", "id", "document_version_id", name="uq_exercises_project_id_version"
        ),
        UniqueConstraint(
            "document_version_id", "fingerprint", name="uq_exercises_version_fingerprint"
        ),
        CheckConstraint("length(trim(label)) > 0", name="ck_exercises_label"),
    )


class ExerciseSegment(Base):
    __tablename__ = "exercise_segments"

    project_id: Mapped[UUID] = mapped_column(primary_key=True)
    exercise_id: Mapped[UUID] = mapped_column(primary_key=True)
    segment_id: Mapped[UUID] = mapped_column(primary_key=True)
    document_version_id: Mapped[UUID] = mapped_column()

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "exercise_id", "document_version_id"],
            ["exercises.project_id", "exercises.id", "exercises.document_version_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_id", "segment_id", "document_version_id"],
            [
                "document_segments.project_id",
                "document_segments.id",
                "document_segments.document_version_id",
            ],
            ondelete="RESTRICT",
        ),
    )


class SourceLink(Identified, Timestamped, Base):
    __tablename__ = "source_links"

    project_id: Mapped[UUID] = mapped_column(index=True)
    analysis_run_id: Mapped[UUID | None] = mapped_column(index=True)
    segment_id: Mapped[UUID | None] = mapped_column(index=True)
    exercise_id: Mapped[UUID | None] = mapped_column(index=True)
    topic_id: Mapped[UUID] = mapped_column(index=True)
    relation_type: Mapped[str] = mapped_column(String(32))
    identity_key: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    basis: Mapped[str] = mapped_column(String(32))
    score: Mapped[float | None] = mapped_column(Float)
    confidence_kind: Mapped[str] = mapped_column(String(32), default="none", server_default="none")
    issues: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=sql_text("'[]'::jsonb")
    )
    review_status: Mapped[str] = mapped_column(
        String(16), default="proposed", server_default="proposed"
    )
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    corrected_from_id: Mapped[UUID | None] = mapped_column(index=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "analysis_run_id"],
            ["analysis_runs.project_id", "analysis_runs.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_id", "segment_id"],
            ["document_segments.project_id", "document_segments.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_id", "exercise_id"],
            ["exercises.project_id", "exercises.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_id", "topic_id"], ["topics.project_id", "topics.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["project_id", "corrected_from_id"],
            ["source_links.project_id", "source_links.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("project_id", "id", name="uq_links_project_id"),
        UniqueConstraint("project_id", "identity_key", name="uq_links_project_identity"),
        CheckConstraint("(segment_id IS NULL) <> (exercise_id IS NULL)", name="ck_links_subject"),
        CheckConstraint(
            "relation_type IN ('EXPLAINS','APPLIES','EXAMINES','RELATED_TO')",
            name="ck_links_relation",
        ),
        CheckConstraint(
            "relation_type <> 'EXPLAINS' OR segment_id IS NOT NULL",
            name="ck_links_explains_subject",
        ),
        CheckConstraint(
            "relation_type NOT IN ('APPLIES','EXAMINES') OR exercise_id IS NOT NULL",
            name="ck_links_exercise_subject",
        ),
        CheckConstraint(
            "basis IN ('explicit_statement','lexical_match','semantic_similarity','manual')",
            name="ck_links_basis",
        ),
        CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 1 AND score <> 'NaN'::float8)",
            name="ck_links_score",
        ),
        CheckConstraint(
            "(score IS NULL AND confidence_kind = 'none') OR (score IS NOT NULL AND confidence_kind = 'heuristic_uncalibrated')",
            name="ck_links_confidence",
        ),
        CheckConstraint(
            "review_status IN ('proposed','accepted','rejected')", name="ck_links_review"
        ),
        CheckConstraint("revision > 0", name="ck_links_revision"),
        CheckConstraint("length(trim(reason)) > 0", name="ck_links_reason"),
    )


class TopicRelation(Identified, Timestamped, Base):
    __tablename__ = "topic_relations"

    project_id: Mapped[UUID] = mapped_column(index=True)
    analysis_run_id: Mapped[UUID | None] = mapped_column(index=True)
    source_topic_id: Mapped[UUID] = mapped_column(index=True)
    target_topic_id: Mapped[UUID] = mapped_column(index=True)
    relation_type: Mapped[str] = mapped_column(String(32))
    identity_key: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    basis: Mapped[str] = mapped_column(String(32))
    score: Mapped[float | None] = mapped_column(Float)
    confidence_kind: Mapped[str] = mapped_column(String(32), default="none", server_default="none")
    issues: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=sql_text("'[]'::jsonb")
    )
    review_status: Mapped[str] = mapped_column(
        String(16), default="proposed", server_default="proposed"
    )
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    corrected_from_id: Mapped[UUID | None] = mapped_column(index=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "analysis_run_id"],
            ["analysis_runs.project_id", "analysis_runs.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_id", "source_topic_id"],
            ["topics.project_id", "topics.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_id", "target_topic_id"],
            ["topics.project_id", "topics.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_id", "corrected_from_id"],
            ["topic_relations.project_id", "topic_relations.id"],
            name="fk_topic_relations_corrected_from",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("project_id", "id", name="uq_topic_relations_project_id"),
        UniqueConstraint("project_id", "identity_key", name="uq_topic_relations_project_identity"),
        CheckConstraint("source_topic_id <> target_topic_id", name="ck_topic_relations_distinct"),
        CheckConstraint(
            "relation_type IN ('IS_PREREQUISITE_OF','RELATED_TO')", name="ck_topic_relations_type"
        ),
        CheckConstraint(
            "basis IN ('explicit_statement','lexical_match','semantic_similarity','manual')",
            name="ck_topic_relations_basis",
        ),
        CheckConstraint(
            "relation_type <> 'IS_PREREQUISITE_OF' OR basis IN ('explicit_statement','manual')",
            name="ck_topic_relations_prerequisite_basis",
        ),
        CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 1 AND score <> 'NaN'::float8)",
            name="ck_topic_relations_score",
        ),
        CheckConstraint(
            "(score IS NULL AND confidence_kind = 'none') OR (score IS NOT NULL AND confidence_kind = 'heuristic_uncalibrated')",
            name="ck_topic_relations_confidence",
        ),
        CheckConstraint(
            "review_status IN ('proposed','accepted','rejected')", name="ck_topic_relations_review"
        ),
        CheckConstraint("revision > 0", name="ck_topic_relations_revision"),
        CheckConstraint("length(trim(reason)) > 0", name="ck_topic_relations_reason"),
    )


class LinkEvidence(Identified, Timestamped, Base):
    __tablename__ = "link_evidence"

    project_id: Mapped[UUID] = mapped_column(index=True)
    source_link_id: Mapped[UUID | None] = mapped_column(index=True)
    topic_relation_id: Mapped[UUID | None] = mapped_column(index=True)
    segment_id: Mapped[UUID] = mapped_column(index=True)
    analysis_run_id: Mapped[UUID | None] = mapped_column(index=True)
    created_by: Mapped[str | None] = mapped_column(String(255))
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text)
    evidence_status: Mapped[str] = mapped_column(
        String(16), default="extracted", server_default="extracted"
    )
    identity_key: Mapped[str] = mapped_column(String(64))

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "source_link_id"],
            ["source_links.project_id", "source_links.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_id", "topic_relation_id"],
            ["topic_relations.project_id", "topic_relations.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_id", "segment_id"],
            ["document_segments.project_id", "document_segments.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_id", "analysis_run_id"],
            ["analysis_runs.project_id", "analysis_runs.id"],
            name="fk_link_evidence_analysis_run",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("project_id", "id", name="uq_evidence_project_id"),
        UniqueConstraint("project_id", "identity_key", name="uq_evidence_project_identity"),
        CheckConstraint(
            "(source_link_id IS NULL) <> (topic_relation_id IS NULL)", name="ck_evidence_target"
        ),
        CheckConstraint(
            "start_offset >= 0 AND end_offset > start_offset", name="ck_evidence_offsets"
        ),
        CheckConstraint("length(quote) = end_offset - start_offset", name="ck_evidence_quote_span"),
        CheckConstraint(
            "evidence_status IN ('extracted','uncertain','manually_checked')",
            name="ck_evidence_status",
        ),
    )


class ReviewDecision(Identified, Timestamped, Base):
    __tablename__ = "review_decisions"

    project_id: Mapped[UUID] = mapped_column(index=True)
    source_link_id: Mapped[UUID | None] = mapped_column(index=True)
    topic_relation_id: Mapped[UUID | None] = mapped_column(index=True)
    actor_id: Mapped[str] = mapped_column(String(255))
    evidence_checked: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sql_text("false")
    )
    decision: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "source_link_id"],
            ["source_links.project_id", "source_links.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_id", "topic_relation_id"],
            ["topic_relations.project_id", "topic_relations.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("source_link_id", "revision", name="uq_decisions_link_revision"),
        UniqueConstraint("topic_relation_id", "revision", name="uq_decisions_relation_revision"),
        CheckConstraint(
            "(source_link_id IS NULL) <> (topic_relation_id IS NULL)", name="ck_decisions_target"
        ),
        CheckConstraint("decision IN ('accept','reject','correct')", name="ck_decisions_decision"),
        CheckConstraint("revision > 0", name="ck_decisions_revision"),
        CheckConstraint("length(trim(actor_id)) > 0", name="ck_decisions_actor"),
    )


class TutorConversation(Identified, Timestamped, Base):
    """A project-owned dialogue bound to one explicit retrieval selection."""

    __tablename__ = "tutor_conversations"

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    owner_id: Mapped[str] = mapped_column(String(255))
    scope_id: Mapped[UUID] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(300))

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "scope_id"],
            ["retrieval_scopes.project_id", "retrieval_scopes.id"],
            name="fk_tutor_conversations_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("project_id", "id", name="uq_tutor_conversations_project_id"),
        UniqueConstraint(
            "project_id", "id", "scope_id", name="uq_tutor_conversations_project_id_scope"
        ),
        CheckConstraint("length(trim(owner_id)) > 0", name="ck_tutor_conversations_owner"),
        CheckConstraint("length(trim(title)) > 0", name="ck_tutor_conversations_title"),
    )


class TutorTurn(Identified, Timestamped, Base):
    """An idempotent request and its exact source snapshot and generation metadata."""

    __tablename__ = "tutor_turns"

    project_id: Mapped[UUID] = mapped_column(index=True)
    conversation_id: Mapped[UUID] = mapped_column(index=True)
    request_id: Mapped[UUID] = mapped_column()
    sequence: Mapped[int] = mapped_column(Integer)
    question: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(32))
    depth: Mapped[str] = mapped_column(String(16))
    scope_id: Mapped[UUID] = mapped_column(index=True)
    scope_revision: Mapped[int] = mapped_column(Integer)
    module_id: Mapped[UUID | None] = mapped_column(index=True)
    filters: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=sql_text("'{}'::jsonb")
    )
    context_snapshot: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=sql_text("'{}'::jsonb")
    )
    answer: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=sql_text("'{}'::jsonb")
    )
    provider_name: Mapped[str] = mapped_column(String(128))
    model_name: Mapped[str] = mapped_column(String(255))
    prompt_version: Mapped[str] = mapped_column(String(128))
    usage: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=sql_text("'{}'::jsonb"))
    error_code: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(
        String(16), default="generating", server_default="generating"
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "conversation_id"],
            ["tutor_conversations.project_id", "tutor_conversations.id"],
            name="fk_tutor_turns_conversation",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_id", "scope_id"],
            ["retrieval_scopes.project_id", "retrieval_scopes.id"],
            name="fk_tutor_turns_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_id", "conversation_id", "scope_id"],
            [
                "tutor_conversations.project_id",
                "tutor_conversations.id",
                "tutor_conversations.scope_id",
            ],
            name="fk_tutor_turns_conversation_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_id", "module_id"],
            ["modules.project_id", "modules.id"],
            name="fk_tutor_turns_module",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("project_id", "id", name="uq_tutor_turns_project_id"),
        UniqueConstraint("project_id", "request_id", name="uq_tutor_turns_project_request"),
        UniqueConstraint(
            "conversation_id", "sequence", name="uq_tutor_turns_conversation_sequence"
        ),
        CheckConstraint("sequence > 0", name="ck_tutor_turns_sequence"),
        CheckConstraint("scope_revision > 0", name="ck_tutor_turns_scope_revision"),
        CheckConstraint("length(trim(question)) > 0", name="ck_tutor_turns_question"),
        CheckConstraint(
            "mode IN ('SOURCE_MODE','DEEP_PHYSICS_MODE','EXAM_MODE','SOCRATIC_MODE')",
            name="ck_tutor_turns_mode",
        ),
        CheckConstraint("depth IN ('concise','standard','deep')", name="ck_tutor_turns_depth"),
        CheckConstraint(
            "status IN ('generating','completed','failed')", name="ck_tutor_turns_status"
        ),
        CheckConstraint("jsonb_typeof(filters) = 'object'", name="ck_tutor_turns_filters"),
        CheckConstraint(
            "jsonb_typeof(context_snapshot) = 'object'", name="ck_tutor_turns_context_snapshot"
        ),
        CheckConstraint("jsonb_typeof(answer) = 'object'", name="ck_tutor_turns_answer"),
        CheckConstraint("jsonb_typeof(usage) = 'object'", name="ck_tutor_turns_usage"),
    )
