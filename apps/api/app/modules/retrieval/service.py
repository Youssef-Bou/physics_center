"""Scope-first scientific retrieval and verifiable locators, without answer generation."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from uuid import UUID

from sqlalchemy import and_, case, exists, false, func, literal_column, or_, select

from app.infrastructure.models import (
    AnalysisRun,
    DocumentSegment,
    Exercise,
    ExerciseSegment,
    LinkEvidence,
    SourceLink,
    Topic,
    TopicRelation,
)
from app.modules.knowledge.service import KnowledgeError, KnowledgeService
from app.modules.retrieval.contracts import (
    EmbeddingProvider,
    ResolvedScope,
    RetrievalFilters,
    ScopedVersion,
)
from app.modules.retrieval.scope import ScopeService


class RetrievalService:
    """Only resolved scopes may reach matching, ranking, or an embedding adapter."""

    schema_version = "retrieval.v1"
    semantic_candidate_limit = 2000

    def __init__(
        self, knowledge: KnowledgeService, embedding_provider: EmbeddingProvider | None = None
    ):
        self.knowledge = knowledge
        self.session = knowledge.session
        self.scope = ScopeService(knowledge)
        self.embedding_provider = embedding_provider
        self._runs = {}

    @staticmethod
    def _validate(query: str, k: int, mode: str, filters: RetrievalFilters) -> str:
        query = query.strip()
        if not query or len(query) > 1000:
            raise KnowledgeError(
                422, "invalid_query", "Use a non-empty query of at most 1000 characters."
            )
        if not 1 <= k <= 50:
            raise KnowledgeError(422, "invalid_limit", "k must be between 1 and 50.")
        if mode not in {"lexical", "semantic", "hybrid"}:
            raise KnowledgeError(
                422, "invalid_search_mode", "Choose lexical, semantic or hybrid search."
            )
        if (
            (filters.page_start is not None and filters.page_start < 1)
            or (filters.page_end is not None and filters.page_end < 1)
            or (
                filters.page_start is not None
                and filters.page_end is not None
                and filters.page_end < filters.page_start
            )
        ):
            raise KnowledgeError(
                422, "invalid_page_range", "Physical pages are one-based and ordered."
            )
        return query

    def _allowed(self, project_id: UUID, resolved: ResolvedScope, filters: RetrievalFilters):
        """A materialized relation enforces the boundary before text matching/ranking.

        Run result membership is essential: a later extraction of the same version
        must not silently replace the selected source passages.
        """
        memberships = [
            and_(
                DocumentSegment.document_version_id == item.version_id,
                DocumentSegment.id.in_(item.segment_ids),
            )
            for item in resolved.items
            if item.segment_ids
        ]
        statement = select(DocumentSegment).where(
            DocumentSegment.project_id == project_id,
            or_(*memberships) if memberships else false(),
        )
        if filters.page_start is not None:
            statement = statement.where(DocumentSegment.page_number >= filters.page_start)
        if filters.page_end is not None:
            statement = statement.where(DocumentSegment.page_number <= filters.page_end)
        if filters.chapter is not None:
            statement = statement.where(DocumentSegment.chapter_label == filters.chapter)
        if filters.exercise_label is not None:
            exercise_ids = tuple(
                exercise_id for item in resolved.items for exercise_id in item.exercise_ids
            )
            matching_exercise = (
                select(ExerciseSegment.segment_id)
                .join(
                    Exercise,
                    and_(
                        Exercise.project_id == ExerciseSegment.project_id,
                        Exercise.id == ExerciseSegment.exercise_id,
                    ),
                )
                .where(
                    ExerciseSegment.project_id == project_id,
                    ExerciseSegment.segment_id == DocumentSegment.id,
                    ExerciseSegment.document_version_id == DocumentSegment.document_version_id,
                    Exercise.id.in_(exercise_ids),
                    Exercise.label == filters.exercise_label,
                )
            )
            statement = statement.where(exists(matching_exercise))
        return statement.cte("allowed_segments").prefix_with("MATERIALIZED")

    @staticmethod
    def _order(columns):
        return (columns.document_version_id, columns.page_number, columns.start_offset, columns.id)

    def _lexical(self, allowed, query: str, limit: int):
        config = literal_column("'simple'::regconfig")
        vector = func.to_tsvector(config, allowed.c.text)
        parsed_query = func.websearch_to_tsquery(config, query)
        literal_match = func.strpos(func.lower(allowed.c.text), query.lower()) > 0
        score = (
            func.ts_rank_cd(vector, parsed_query) + case((literal_match, 1.0), else_=0.0)
        ).label("rank_score")
        statement = (
            select(allowed, score)
            .where(or_(vector.op("@@")(parsed_query), literal_match))
            .order_by(score.desc(), *self._order(allowed.c))
            .limit(limit)
        )
        return list(self.session.execute(statement).mappings())

    def _semantic(self, allowed, query: str, by_version):
        provider = self.embedding_provider
        if provider is None:
            raise KnowledgeError(
                501, "semantic_unavailable", "No semantic embedding provider is configured."
            )
        if getattr(provider, "is_local", False) is not True:
            raise KnowledgeError(
                409,
                "external_processing_disabled",
                "This retrieval engine only permits explicitly local embedding providers.",
            )
        if not getattr(provider, "model_id", ""):
            raise KnowledgeError(
                422,
                "invalid_embedding_provider",
                "The embedding provider must declare its model version.",
            )
        candidates = list(
            self.session.execute(
                select(allowed)
                .order_by(*self._order(allowed.c))
                .limit(self.semantic_candidate_limit + 1)
            ).mappings()
        )
        if len(candidates) > self.semantic_candidate_limit:
            raise KnowledgeError(
                422,
                "semantic_candidate_limit",
                "Narrow the source scope before semantic search; at most 2000 passages are supported.",
            )
        valid_candidates = []
        excluded = False
        for row in candidates:
            try:
                self._locator(row, by_version[row["document_version_id"]])
            except KnowledgeError:
                excluded = True
                continue
            valid_candidates.append(row)
        candidates = valid_candidates
        if not candidates:
            return [], excluded
        try:
            vectors = provider.embed((query, *(row["text"] for row in candidates)))
        except Exception as exc:
            raise KnowledgeError(
                503, "embedding_unavailable", "The local embedding provider failed."
            ) from exc
        if not isinstance(vectors, Sequence) or len(vectors) != len(candidates) + 1:
            raise KnowledgeError(
                422, "invalid_embeddings", "The provider returned an invalid embedding batch."
            )
        normalized = []
        dimensions = None
        for vector in vectors:
            if not isinstance(vector, Sequence) or not 1 <= len(vector) <= 8192:
                raise KnowledgeError(
                    422, "invalid_embeddings", "Embeddings must be bounded non-empty vectors."
                )
            if dimensions is None:
                dimensions = len(vector)
            if len(vector) != dimensions:
                raise KnowledgeError(422, "invalid_embeddings", "Embedding dimensions must agree.")
            try:
                numbers = tuple(float(value) for value in vector)
                norm = math.sqrt(sum(value * value for value in numbers))
            except (TypeError, ValueError, OverflowError) as exc:
                raise KnowledgeError(
                    422, "invalid_embeddings", "Embedding values must be finite numbers."
                ) from exc
            if (
                not all(math.isfinite(value) for value in numbers)
                or not math.isfinite(norm)
                or norm <= 0
            ):
                raise KnowledgeError(
                    422, "invalid_embeddings", "Embedding vectors must be finite and nonzero."
                )
            normalized.append(tuple(value / norm for value in numbers))
        query_vector = normalized[0]
        ranked = [
            {**row, "rank_score": sum(a * b for a, b in zip(query_vector, vector, strict=True))}
            for row, vector in zip(candidates, normalized[1:], strict=True)
        ]
        return sorted(ranked, key=lambda row: (-row["rank_score"], *self._row_order(row))), excluded

    @staticmethod
    def _row_order(row: Mapping):
        return (
            str(row["document_version_id"]),
            row["page_number"],
            row["start_offset"],
            str(row["id"]),
        )

    def _locator(self, row: Mapping, item: ScopedVersion) -> dict:
        page_number = row["page_number"]
        page = next((page for page in item.pages if page.get("page_number") == page_number), None)
        start, end = row["start_offset"], row["end_offset"]
        if (
            row["id"] not in item.segment_ids
            or row["document_version_id"] != item.version_id
            or not isinstance(page_number, int)
            or not 1 <= page_number <= item.page_count
            or page is None
            or not isinstance(page.get("text"), str)
            or not 0 <= start < end <= len(page["text"])
            or page["text"][start:end] != row["text"]
        ):
            raise KnowledgeError(
                409,
                "citation_invalid",
                "The source position does not match the selected stored page text.",
            )
        if item.analysis_run_id not in self._runs:
            self._runs[item.analysis_run_id] = self.session.get(AnalysisRun, item.analysis_run_id)
        run = self._runs[item.analysis_run_id]
        issues = list(dict.fromkeys((*row["issues"], *page.get("issues", ()))))
        return {
            "citation_id": row["id"],
            "segment_id": row["id"],
            "document_id": item.document_id,
            "document_title": item.document_title,
            "source_type": item.source_type,
            "document_version_id": item.version_id,
            "sha256": item.sha256,
            "analysis_run_id": item.analysis_run_id,
            "extraction_version": run.extractor_version if run else None,
            "page_number": page_number,
            "start_offset": start,
            "end_offset": end,
            "original_text": row["text"],
            "chapter": row.get("chapter_label"),
            "issues": issues,
            "extraction_uncertain": bool(issues),
            "locator_verified": True,
            "verification_scope": "stored_extraction_and_original_hash",
            "scientific_verification": False,
        }

    def _base_output(self, resolved, query, mode):
        return {
            "schema_version": self.schema_version,
            "scope_id": resolved.scope_id,
            "scope_revision": resolved.revision,
            "query": query,
            "mode": mode,
            "effective_sources": [
                {
                    "document_id": item.document_id,
                    "document_version_id": item.version_id,
                    "analysis_run_id": item.analysis_run_id,
                }
                for item in resolved.items
            ],
            "hits": [],
            "warnings": list(
                dict.fromkeys(issue for item in resolved.items for issue in item.issues)
            ),
        }

    def search(
        self,
        project_id,
        actor_id,
        scope_id,
        scope_revision,
        query,
        filters: RetrievalFilters = RetrievalFilters(),
        k=10,
        mode="lexical",
    ) -> dict:
        query = self._validate(query, k, mode, filters)
        resolved = self.scope.resolve(project_id, actor_id, scope_id, scope_revision, filters)
        output = self._base_output(resolved, query, mode)
        if not resolved.items:
            output["warnings"].extend(["empty_source_selection", "no_matching_passages"])
            return output
        allowed = self._allowed(project_id, resolved, filters)
        by_version = {item.version_id: item for item in resolved.items}
        if mode == "lexical":
            ranked = self._lexical(allowed, query, 50)
        else:
            semantic, excluded = self._semantic(allowed, query, by_version)
            if excluded:
                output["warnings"].append("invalid_citations_excluded")
            if mode == "semantic":
                ranked = semantic
            else:
                lexical = self._lexical(allowed, query, self.semantic_candidate_limit)
                merged = {}
                for ranking in (lexical, semantic):
                    for position, row in enumerate(ranking, 1):
                        entry = merged.setdefault(row["id"], {**row, "rank_score": 0.0})
                        entry["rank_score"] += 1.0 / (60 + position)
                ranked = sorted(
                    merged.values(), key=lambda row: (-row["rank_score"], *self._row_order(row))
                )
            output["embedding_model"] = self.embedding_provider.model_id
        by_version = {item.version_id: item for item in resolved.items}
        for row in ranked:
            try:
                hit = self._locator(row, by_version[row["document_version_id"]])
            except KnowledgeError:
                output["warnings"].append("invalid_citations_excluded")
                continue
            hit["rank_score"] = float(row["rank_score"])
            hit["score_kind"] = "ranking_signal_not_probability"
            output["hits"].append(hit)
            if len(output["hits"]) == k:
                break
        allowed_ids = set(self.session.scalars(select(allowed.c.id)))
        self._enrich(output["hits"], project_id, resolved, allowed_ids, output["warnings"])
        if not output["hits"]:
            output["warnings"].append("no_matching_passages")
        if filters.chapter and not allowed_ids:
            output["warnings"].append("chapter_metadata_missing_or_unmatched")
        output["warnings"] = list(dict.fromkeys(output["warnings"]))
        return output

    def citation(
        self,
        project_id,
        actor_id,
        scope_id,
        scope_revision,
        segment_id,
        filters: RetrievalFilters = RetrievalFilters(),
    ) -> dict:
        # A tutor must reuse the original retrieval filters. Active source scope
        # alone is insufficient when a turn explicitly excluded a page or task.
        self._validate("citation", 1, "lexical", filters)
        resolved = self.scope.resolve(project_id, actor_id, scope_id, scope_revision, filters)
        item = next((item for item in resolved.items if segment_id in item.segment_ids), None)
        if item is None:
            raise KnowledgeError(
                409, "source_conflict", "This citation is outside the effective source selection."
            )
        allowed = self._allowed(project_id, resolved, filters)
        row = (
            self.session.execute(select(allowed).where(allowed.c.id == segment_id))
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise KnowledgeError(
                409,
                "source_conflict",
                "This citation is unavailable under the original retrieval filters.",
            )
        result = self._locator(row, item)
        return {
            "schema_version": self.schema_version,
            "scope_id": resolved.scope_id,
            "scope_revision": resolved.revision,
            **result,
        }

    def _checked_link_evidence(self, obj_id, project_id, kind, rows, by_version):
        column = LinkEvidence.source_link_id if kind == "source" else LinkEvidence.topic_relation_id
        evidence = list(
            self.session.scalars(
                select(LinkEvidence)
                .where(
                    LinkEvidence.project_id == project_id,
                    column == obj_id,
                )
                .order_by(LinkEvidence.created_at, LinkEvidence.id)
            )
        )
        if not evidence:
            return None
        result = []
        for item in evidence:
            if item.segment_id not in rows or item.evidence_status != "manually_checked":
                return None
            segment = self.session.scalar(
                select(DocumentSegment).where(
                    DocumentSegment.project_id == project_id,
                    DocumentSegment.id == item.segment_id,
                )
            )
            if segment is None:
                return None
            row = {
                column.name: getattr(segment, column.name) for column in segment.__table__.columns
            }
            start, end = (
                item.start_offset - row["start_offset"],
                item.end_offset - row["start_offset"],
            )
            if not 0 <= start < end <= len(row["text"]) or row["text"][start:end] != item.quote:
                return None
            try:
                locator = self._locator(row, by_version[row["document_version_id"]])
            except KnowledgeError:
                return None
            result.append(
                {
                    **locator,
                    "evidence_id": item.id,
                    "quote": item.quote,
                    "evidence_start_offset": item.start_offset,
                    "evidence_end_offset": item.end_offset,
                    "evidence_status": item.evidence_status,
                }
            )
        return result

    def _enrich(self, hits, project_id, resolved, rows, warnings):
        by_version = {item.version_id: item for item in resolved.items}
        exercise_ids = tuple(
            exercise_id for item in resolved.items for exercise_id in item.exercise_ids
        )
        for hit in hits:
            hit["topics"], hit["exercises"], hit["prerequisites"] = [], [], []
            exercises = list(
                self.session.scalars(
                    select(Exercise)
                    .join(
                        ExerciseSegment,
                        and_(
                            ExerciseSegment.project_id == Exercise.project_id,
                            ExerciseSegment.exercise_id == Exercise.id,
                        ),
                    )
                    .where(
                        Exercise.project_id == project_id,
                        Exercise.id.in_(exercise_ids),
                        ExerciseSegment.segment_id == hit["segment_id"],
                    )
                    .order_by(Exercise.id)
                )
            )
            for exercise in exercises:
                members = list(
                    self.session.scalars(
                        select(ExerciseSegment.segment_id).where(
                            ExerciseSegment.project_id == project_id,
                            ExerciseSegment.exercise_id == exercise.id,
                        )
                    )
                )
                permitted = [segment_id for segment_id in members if segment_id in rows]
                hit["exercises"].append(
                    {
                        "id": exercise.id,
                        "label": exercise.label,
                        "source_type": hit["source_type"],
                        "document_version_id": exercise.document_version_id,
                        "segment_ids": permitted,
                        "issues": exercise.issues,
                        "partial": len(permitted) != len(members),
                        "verification_status": "extracted",
                    }
                )
            subject_ids = [exercise.id for exercise in exercises]
            links = self.session.scalars(
                select(SourceLink)
                .where(
                    SourceLink.project_id == project_id,
                    SourceLink.review_status == "accepted",
                    or_(
                        SourceLink.segment_id == hit["segment_id"],
                        SourceLink.exercise_id.in_(subject_ids),
                    ),
                )
                .order_by(SourceLink.id)
            )
            for link in links:
                evidence = self._checked_link_evidence(
                    link.id, project_id, "source", rows, by_version
                )
                if evidence is None:
                    continue
                topic = self.session.scalar(
                    select(Topic).where(Topic.project_id == project_id, Topic.id == link.topic_id)
                )
                if topic is not None:
                    hit["topics"].append(
                        {
                            "id": topic.id,
                            "name": topic.name,
                            "relation_type": link.relation_type,
                            "source_link_id": link.id,
                            "review_status": link.review_status,
                            "evidence": evidence,
                        }
                    )
            topic_ids = [topic["id"] for topic in hit["topics"]]
            relations = self.session.scalars(
                select(TopicRelation)
                .where(
                    TopicRelation.project_id == project_id,
                    TopicRelation.review_status == "accepted",
                    TopicRelation.relation_type == "IS_PREREQUISITE_OF",
                    TopicRelation.target_topic_id.in_(topic_ids),
                )
                .order_by(TopicRelation.id)
            )
            for relation in relations:
                evidence = self._checked_link_evidence(
                    relation.id, project_id, "topic", rows, by_version
                )
                if evidence is None:
                    continue
                source = self.session.get(Topic, relation.source_topic_id)
                target = self.session.get(Topic, relation.target_topic_id)
                hit["prerequisites"].append(
                    {
                        "id": relation.id,
                        "source_topic_id": relation.source_topic_id,
                        "target_topic_id": relation.target_topic_id,
                        "source_topic": {"id": source.id, "name": source.name},
                        "target_topic": {"id": target.id, "name": target.name},
                        "relation_type": relation.relation_type,
                        "review_status": relation.review_status,
                        "evidence": evidence,
                    }
                )

    def context(
        self,
        project_id,
        actor_id,
        scope_id,
        scope_revision,
        query,
        filters: RetrievalFilters = RetrievalFilters(),
        k=10,
        mode="lexical",
    ) -> dict:
        output = self.search(
            project_id, actor_id, scope_id, scope_revision, query, filters, k, mode
        )
        output["citation_constraints"] = {
            "scope_id": output["scope_id"],
            "scope_revision": output["scope_revision"],
            "filters": asdict(filters),
        }
        exercises, exams, topics, prerequisites = {}, {}, {}, {}
        for hit in output["hits"]:
            for exercise in hit["exercises"]:
                target = exams if exercise["source_type"] == "past_exam" else exercises
                target[exercise["id"]] = exercise
            for topic in hit["topics"]:
                topics[topic["id"]] = topic
            for relation in hit["prerequisites"]:
                prerequisites[relation["id"]] = relation
        output["tutor_context"] = {
            "passages": output["hits"],
            "exercises": list(exercises.values()),
            "exam_exercises": list(exams.values()),
            "topics": list(topics.values()),
            "prerequisites": list(prerequisites.values()),
        }
        return output
