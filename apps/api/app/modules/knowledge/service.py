"""Transactional knowledge use cases. HTTP and model providers are adapters."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import (
    AnalysisRun,
    Document,
    DocumentSegment,
    DocumentVersion,
    Exercise,
    ExerciseSegment,
    LinkEvidence,
    Project,
    ReviewDecision,
    SourceLink,
    Topic,
    TopicRelation,
)
from app.modules.sources.contracts import TopicInput
from app.modules.sources.extraction import PdfExtractionError, PdfExtractor, explicit_chapter_label
from app.modules.sources.pipeline import AnalysisPipeline


class KnowledgeError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code, self.code, self.message = status_code, code, message
        super().__init__(message)


def fingerprint(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def record(row) -> dict:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


class KnowledgeService:
    def __init__(self, session: Session, storage_root: Path, pipeline: AnalysisPipeline):
        self.session, self.storage_root, self.pipeline = session, Path(storage_root), pipeline

    def _project(self, project_id: UUID, actor_id: str, *, lock: bool = False) -> Project:
        statement = select(Project).where(Project.id == project_id, Project.owner_id == actor_id)
        if lock:
            statement = statement.with_for_update()
        project = self.session.scalar(statement)
        if project is None:
            raise KnowledgeError(404, "not_found", "Project or resource not available.")
        return project

    def _resource(self, cls, resource_id: UUID, project_id: UUID):
        obj = self.session.scalar(
            select(cls).where(cls.id == resource_id, cls.project_id == project_id)
        )
        if obj is None:
            raise KnowledgeError(404, "not_found", "Project or resource not available.")
        return obj

    def create_project(self, actor_id: str, title: str) -> dict:
        project = Project(owner_id=actor_id, title=title.strip())
        self.session.add(project)
        self.session.commit()
        return record(project)

    def create_topic(self, project_id, actor_id, name, aliases) -> dict:
        self._project(project_id, actor_id, lock=True)
        name = name.strip()
        if self.session.scalar(
            select(Topic).where(Topic.project_id == project_id, Topic.name == name)
        ):
            raise KnowledgeError(409, "topic_exists", "Topic name already exists in this project.")
        topic = Topic(
            project_id=project_id,
            name=name,
            aliases=list(dict.fromkeys(a.strip() for a in aliases if a.strip())),
        )
        self.session.add(topic)
        self.session.commit()
        return record(topic)

    def list_topics(self, project_id, actor_id) -> list[dict]:
        self._project(project_id, actor_id)
        return [
            record(t)
            for t in self.session.scalars(
                select(Topic).where(Topic.project_id == project_id).order_by(Topic.name, Topic.id)
            )
        ]

    def upload(self, project_id, actor_id, title, source_type, content: bytes) -> dict:
        self._project(project_id, actor_id, lock=True)
        if len(content) > 16 * 1024 * 1024:
            raise KnowledgeError(413, "file_too_large", "PDF exceeds the 16 MiB limit.")
        try:
            pages = PdfExtractor().extract(content)
        except PdfExtractionError as exc:
            raise KnowledgeError(422, "invalid_pdf", str(exc)) from exc
        digest = hashlib.sha256(content).hexdigest()
        document = self.session.scalar(
            select(Document)
            .where(
                Document.project_id == project_id,
                Document.title == title.strip(),
                Document.source_type == source_type,
            )
            .order_by(Document.id)
        )
        if document is None:
            document = Document(project_id=project_id, title=title.strip(), source_type=source_type)
            self.session.add(document)
            self.session.flush()
        existing = self.session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.sha256 == digest,
            )
        )
        if existing:
            return {
                "document_id": document.id,
                "version_id": existing.id,
                "sha256": digest,
                "page_count": existing.page_count,
                "reused": True,
            }
        key = f"{project_id}/{digest}.pdf"
        target = self.storage_root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        # Bytes are committed before metadata: failures may leave a harmless orphan,
        # but the DB can never publish a version whose file was only half written.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
                temporary = handle.name
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
        version = DocumentVersion(
            project_id=project_id,
            document_id=document.id,
            sha256=digest,
            storage_key=key,
            page_count=len(pages),
        )
        self.session.add(version)
        self.session.commit()
        return {
            "document_id": document.id,
            "version_id": version.id,
            "sha256": digest,
            "page_count": len(pages),
            "reused": False,
        }

    def _file(self, version: DocumentVersion) -> Path:
        root = self.storage_root.resolve()
        path = (root / version.storage_key).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise KnowledgeError(409, "file_unavailable", "Stored original is not available.")
        if hashlib.sha256(path.read_bytes()).hexdigest() != version.sha256:
            raise KnowledgeError(
                409, "hash_mismatch", "Stored original failed its integrity check."
            )
        return path

    def document_file(self, project_id, actor_id, version_id) -> Path:
        self._project(project_id, actor_id)
        return self._file(self._resource(DocumentVersion, version_id, project_id))

    def analyze(self, project_id, actor_id, version_id) -> dict:
        # Serializes mutations in this small synchronous prototype. No background
        # task can overwrite a manual decision between the read and the commit.
        self._project(project_id, actor_id, lock=True)
        version = self._resource(DocumentVersion, version_id, project_id)
        document = self._resource(Document, version.document_id, project_id)
        topics = tuple(
            TopicInput(t.id, t.name, tuple(t.aliases))
            for t in self.session.scalars(
                select(Topic).where(Topic.project_id == project_id).order_by(Topic.id)
            )
        )
        data = self._file(version).read_bytes()
        configuration = {
            "pipeline": self.pipeline.version,
            "source_type": document.source_type,
            "topics": [{"id": str(t.id), "name": t.name, "aliases": t.aliases} for t in topics],
            "analyzer_configuration": getattr(self.pipeline.analyzer, "configuration", {}),
            "extractor_configuration": {
                "max_pages": getattr(self.pipeline.extractor, "max_pages", None),
                "max_page_chars": getattr(self.pipeline.extractor, "max_page_chars", None),
            },
        }
        config_hash = fingerprint(configuration)
        identity = fingerprint(
            [
                version.sha256,
                self.pipeline.extractor.version,
                self.pipeline.analyzer.version,
                config_hash,
            ]
        )
        existing = self.session.scalar(
            select(AnalysisRun).where(
                AnalysisRun.document_version_id == version_id, AnalysisRun.identity_key == identity
            )
        )
        if existing:
            return self._run_view(existing, reused=True)
        try:
            result = self.pipeline.run(data, topics, document.source_type)
        except ValueError as exc:
            raise KnowledgeError(422, "invalid_analysis", str(exc)) from exc
        if len(result.pages) != version.page_count:
            raise KnowledgeError(
                422, "page_mismatch", "Extraction does not match the stored PDF page count."
            )
        run = AnalysisRun(
            project_id=project_id,
            document_version_id=version_id,
            identity_key=identity,
            extractor_version=result.extraction_version,
            analyzer_version=result.analyzer_version,
            configuration_hash=config_hash,
            issues=list(result.issues),
            result={},
        )
        self.session.add(run)
        self.session.flush()
        segments, exercises = {}, {}
        for draft in result.segments:
            segment_identity = fingerprint([draft.key, list(draft.issues)])
            segment = self.session.scalar(
                select(DocumentSegment).where(
                    DocumentSegment.document_version_id == version_id,
                    DocumentSegment.fingerprint == segment_identity,
                )
            )
            if segment is None:
                segment = DocumentSegment(
                    project_id=project_id,
                    document_version_id=version_id,
                    analysis_run_id=run.id,
                    fingerprint=segment_identity,
                    page_number=draft.page_number,
                    start_offset=draft.start_offset,
                    end_offset=draft.end_offset,
                    text=draft.text,
                    issues=list(draft.issues),
                    chapter_label=explicit_chapter_label(draft.text)
                    if document.source_type in {"lecture_notes", "textbook", "paper"}
                    else None,
                )
                self.session.add(segment)
                self.session.flush()
            segments[draft.key] = segment
        for draft in result.exercises:
            exercise_identity = fingerprint(
                [draft.key, [str(segments[key].id) for key in draft.segment_keys]]
            )
            exercise = self.session.scalar(
                select(Exercise).where(
                    Exercise.document_version_id == version_id,
                    Exercise.fingerprint == exercise_identity,
                )
            )
            if exercise is None:
                exercise = Exercise(
                    project_id=project_id,
                    document_version_id=version_id,
                    analysis_run_id=run.id,
                    fingerprint=exercise_identity,
                    label=draft.label,
                    issues=list(draft.issues),
                )
                self.session.add(exercise)
                self.session.flush()
                for key in draft.segment_keys:
                    self.session.add(
                        ExerciseSegment(
                            project_id=project_id,
                            exercise_id=exercise.id,
                            segment_id=segments[key].id,
                            document_version_id=version_id,
                        )
                    )
                self.session.flush()
            exercises[draft.key] = exercise
        links, relations = [], []
        for draft in result.links:
            subject = (
                segments[draft.subject_key]
                if draft.subject_kind == "segment"
                else exercises[draft.subject_key]
            )
            identity = fingerprint(
                ["source", str(subject.id), str(draft.topic_id), draft.relation_type]
            )
            obj = self.session.scalar(
                select(SourceLink).where(
                    SourceLink.project_id == project_id, SourceLink.identity_key == identity
                )
            )
            is_new = obj is None
            if is_new:
                obj = SourceLink(
                    project_id=project_id,
                    analysis_run_id=run.id,
                    segment_id=subject.id if draft.subject_kind == "segment" else None,
                    exercise_id=subject.id if draft.subject_kind == "exercise" else None,
                    topic_id=draft.topic_id,
                    relation_type=draft.relation_type,
                    identity_key=identity,
                    reason=draft.reason,
                    basis=draft.basis,
                    score=draft.score,
                    confidence_kind="none" if draft.score is None else "heuristic_uncalibrated",
                    issues=list(draft.issues),
                )
                self.session.add(obj)
                self.session.flush()
            if obj.review_status == "proposed":
                added = self._store_evidence(obj, "source", draft.evidence, segments, run_id=run.id)
                if added and not is_new:
                    obj.revision += 1
                self._refresh_evidence_issues(obj, "source")
            links.append(str(obj.id))
        for draft in result.topic_relations:
            obj = self._new_relation(
                project_id,
                draft.source_topic_id,
                draft.target_topic_id,
                draft.relation_type,
                draft.reason,
                draft.basis,
                run.id,
                draft.score,
                list(draft.issues),
            )
            is_new = obj.id is None
            if is_new:
                self.session.add(obj)
                self.session.flush()
            if obj.review_status == "proposed":
                added = self._store_evidence(obj, "topic", draft.evidence, segments, run_id=run.id)
                if added and not is_new:
                    obj.revision += 1
                self._refresh_evidence_issues(obj, "topic")
            relations.append(str(obj.id))
        run.result = {
            "segments": [str(s.id) for s in segments.values()],
            "exercises": [str(e.id) for e in exercises.values()],
            "links": links,
            "topic_relations": relations,
            "pages": [asdict(p) for p in result.pages],
        }
        self.session.commit()
        return self._run_view(run, reused=False)

    def _run_view(self, run, reused):
        return {
            "run_id": run.id,
            "reused": reused,
            "extraction_version": run.extractor_version,
            "analyzer_version": run.analyzer_version,
            "issues": run.issues,
            **run.result,
        }

    def _store_evidence(self, obj, kind, evidence, segments, run_id=None):
        added = 0
        for draft in evidence:
            segment = segments[draft.segment_key]
            added += self._add_evidence(
                obj,
                kind,
                segment,
                draft.start_offset,
                draft.end_offset,
                draft.quote,
                run_id=run_id,
            )
        return added

    def _add_evidence(self, obj, kind, segment, start, end, quote, run_id=None, actor_id=None):
        if kind == "source":
            valid_subject = (
                segment.id == obj.segment_id
                if obj.segment_id
                else self.session.scalar(
                    select(ExerciseSegment.segment_id).where(
                        ExerciseSegment.project_id == obj.project_id,
                        ExerciseSegment.exercise_id == obj.exercise_id,
                        ExerciseSegment.segment_id == segment.id,
                    )
                )
                is not None
            )
            if not valid_subject:
                raise KnowledgeError(
                    422,
                    "invalid_evidence",
                    "Evidence must belong to the linked segment or exercise.",
                )
        start_in_segment, end_in_segment = start - segment.start_offset, end - segment.start_offset
        if (
            not (0 <= start_in_segment < end_in_segment <= len(segment.text))
            or segment.text[start_in_segment:end_in_segment] != quote
            or not quote.strip()
        ):
            raise KnowledgeError(
                422, "invalid_evidence", "Evidence does not match the preserved source span."
            )
        identity = fingerprint([str(obj.id), str(segment.id), start, end, quote])
        existing = self.session.scalar(
            select(LinkEvidence).where(
                LinkEvidence.project_id == obj.project_id, LinkEvidence.identity_key == identity
            )
        )
        if existing:
            return 0
        self.session.add(
            LinkEvidence(
                project_id=obj.project_id,
                source_link_id=obj.id if kind == "source" else None,
                topic_relation_id=obj.id if kind != "source" else None,
                segment_id=segment.id,
                start_offset=start,
                end_offset=end,
                quote=quote,
                identity_key=identity,
                evidence_status="uncertain" if segment.issues else "extracted",
                analysis_run_id=run_id,
                created_by=actor_id,
            )
        )
        self.session.flush()
        return 1

    def _refresh_evidence_issues(self, obj, kind):
        if self._evidence(obj, kind):
            obj.issues = [issue for issue in obj.issues if issue != "missing_evidence"]

    def add_evidence(self, project_id, actor_id, link_id, kind, expected_revision, evidence):
        self._project(project_id, actor_id, lock=True)
        obj = self._edge(project_id, link_id, kind)
        self._revision(obj, expected_revision)
        if obj.review_status != "proposed":
            raise KnowledgeError(
                409,
                "already_reviewed",
                "Only unreviewed proposals can receive additional evidence.",
            )
        added = 0
        for item in evidence:
            segment = self._resource(DocumentSegment, UUID(str(item["segment_id"])), project_id)
            added += self._add_evidence(
                obj,
                kind,
                segment,
                item["start_offset"],
                item["end_offset"],
                item["quote"],
                actor_id=actor_id,
            )
        if added:
            obj.revision += 1
        self._refresh_evidence_issues(obj, kind)
        self.session.commit()
        return self._edge_view(obj, kind)

    def list_segments(self, project_id, actor_id, version_id):
        self._project(project_id, actor_id)
        self._resource(DocumentVersion, version_id, project_id)
        return [
            record(s)
            for s in self.session.scalars(
                select(DocumentSegment)
                .where(
                    DocumentSegment.project_id == project_id,
                    DocumentSegment.document_version_id == version_id,
                )
                .order_by(
                    DocumentSegment.page_number, DocumentSegment.start_offset, DocumentSegment.id
                )
            )
        ]

    def list_exercises(self, project_id, actor_id, version_id):
        self._project(project_id, actor_id)
        self._resource(DocumentVersion, version_id, project_id)
        result = []
        for exercise in self.session.scalars(
            select(Exercise)
            .where(Exercise.project_id == project_id, Exercise.document_version_id == version_id)
            .order_by(Exercise.created_at, Exercise.id)
        ):
            ids = self.session.scalars(
                select(ExerciseSegment.segment_id).where(ExerciseSegment.exercise_id == exercise.id)
            ).all()
            result.append({**record(exercise), "segment_ids": ids})
        return result

    def _list_edges(self, cls, project_id, actor_id, status, limit, offset):
        self._project(project_id, actor_id)
        statement = select(cls).where(cls.project_id == project_id)
        if status:
            statement = statement.where(cls.review_status == status)
        return [
            self._edge_view(obj, "source" if cls is SourceLink else "topic")
            for obj in self.session.scalars(
                statement.order_by(cls.created_at, cls.id).limit(limit).offset(offset)
            )
        ]

    def list_links(self, project_id, actor_id, status=None, limit=100, offset=0):
        return self._list_edges(SourceLink, project_id, actor_id, status, limit, offset)

    def list_relations(self, project_id, actor_id, status=None, limit=100, offset=0):
        return self._list_edges(TopicRelation, project_id, actor_id, status, limit, offset)

    def _edge(self, project_id, link_id, kind):
        return self._resource(
            SourceLink if kind == "source" else TopicRelation, link_id, project_id
        )

    def _evidence(self, obj, kind):
        column = LinkEvidence.source_link_id if kind == "source" else LinkEvidence.topic_relation_id
        return list(
            self.session.scalars(
                select(LinkEvidence)
                .where(LinkEvidence.project_id == obj.project_id, column == obj.id)
                .order_by(LinkEvidence.created_at, LinkEvidence.id)
            )
        )

    def _edge_view(self, obj, kind):
        evidence = []
        for item in self._evidence(obj, kind):
            segment = self._resource(DocumentSegment, item.segment_id, obj.project_id)
            version = self._resource(DocumentVersion, segment.document_version_id, obj.project_id)
            document = self._resource(Document, version.document_id, obj.project_id)
            evidence.append(
                {
                    **record(item),
                    "document_id": version.document_id,
                    "document_title": document.title,
                    "document_version_id": version.id,
                    "sha256": version.sha256,
                    "page_number": segment.page_number,
                    "segment_text": segment.text,
                }
            )
        column = (
            ReviewDecision.source_link_id if kind == "source" else ReviewDecision.topic_relation_id
        )
        history = [
            record(d)
            for d in self.session.scalars(
                select(ReviewDecision)
                .where(ReviewDecision.project_id == obj.project_id, column == obj.id)
                .order_by(ReviewDecision.revision)
            )
        ]
        run = self.session.get(AnalysisRun, obj.analysis_run_id) if obj.analysis_run_id else None
        return {
            **record(obj),
            "kind": kind,
            "evidence": evidence,
            "review_decisions": history,
            "analyzer_version": run.analyzer_version if run else "manual",
            "extraction_version": run.extractor_version if run else None,
            "needs_review": obj.review_status == "proposed",
        }

    def get_link(self, project_id, actor_id, link_id, kind="source"):
        self._project(project_id, actor_id)
        return self._edge_view(self._edge(project_id, link_id, kind), kind)

    def _revision(self, obj, expected):
        if obj.revision != expected:
            raise KnowledgeError(
                409, "revision_conflict", "Review state changed; reload before deciding."
            )

    def _decision(self, obj, actor_id, kind, decision, reason, evidence_checked=False):
        obj.revision += 1
        self.session.add(
            ReviewDecision(
                project_id=obj.project_id,
                source_link_id=obj.id if kind == "source" else None,
                topic_relation_id=obj.id if kind != "source" else None,
                actor_id=actor_id,
                decision=decision,
                reason=reason,
                revision=obj.revision,
                evidence_checked=evidence_checked,
            )
        )

    def review(
        self,
        project_id,
        actor_id,
        link_id,
        kind,
        decision,
        expected_revision,
        reason,
        evidence_checked=False,
    ):
        self._project(project_id, actor_id, lock=True)
        obj = self._edge(project_id, link_id, kind)
        self._revision(obj, expected_revision)
        if decision == "accept":
            evidence = self._evidence(obj, kind)
            if not evidence or not evidence_checked:
                raise KnowledgeError(
                    422,
                    "evidence_required",
                    "Inspect the original evidence and explicitly confirm it before acceptance.",
                )
            for item in evidence:
                segment = self._resource(DocumentSegment, item.segment_id, project_id)
                version = self._resource(DocumentVersion, segment.document_version_id, project_id)
                self._file(version)
                start, end = (
                    item.start_offset - segment.start_offset,
                    item.end_offset - segment.start_offset,
                )
                if (
                    not (0 <= start < end <= len(segment.text))
                    or segment.text[start:end] != item.quote
                ):
                    raise KnowledgeError(
                        422, "invalid_evidence", "Evidence span cannot be verified."
                    )
                item.evidence_status = "manually_checked"
            obj.review_status = "accepted"
        elif decision == "reject":
            obj.review_status = "rejected"
        else:
            raise KnowledgeError(422, "invalid_decision", "Choose accept or reject.")
        self._decision(obj, actor_id, kind, decision, reason, evidence_checked)
        self.session.commit()
        return self._edge_view(obj, kind)

    def _new_relation(
        self,
        project_id,
        source_id,
        target_id,
        relation_type,
        reason,
        basis="manual",
        run_id=None,
        score=None,
        issues=None,
    ):
        self._resource(Topic, source_id, project_id)
        self._resource(Topic, target_id, project_id)
        if source_id == target_id or relation_type not in {"IS_PREREQUISITE_OF", "RELATED_TO"}:
            raise KnowledgeError(
                422,
                "invalid_relation",
                "Choose distinct topics and a supported topic relationship.",
            )
        if relation_type == "RELATED_TO":
            source_id, target_id = sorted((source_id, target_id), key=str)
        identity = fingerprint(["topic", str(source_id), str(target_id), relation_type])
        existing = self.session.scalar(
            select(TopicRelation).where(
                TopicRelation.project_id == project_id, TopicRelation.identity_key == identity
            )
        )
        return existing or TopicRelation(
            project_id=project_id,
            source_topic_id=source_id,
            target_topic_id=target_id,
            relation_type=relation_type,
            reason=reason,
            basis=basis,
            analysis_run_id=run_id,
            score=score,
            confidence_kind="none" if score is None else "heuristic_uncalibrated",
            issues=issues or [],
            identity_key=identity,
        )

    def create_relation(
        self,
        project_id,
        actor_id,
        source_topic_id,
        target_topic_id,
        relation_type,
        reason,
        evidence,
        expected_revision=None,
    ):
        self._project(project_id, actor_id, lock=True)
        obj = self._new_relation(
            project_id,
            source_topic_id,
            target_topic_id,
            relation_type,
            reason,
            issues=[] if evidence else ["missing_evidence"],
        )
        if obj.id is not None:
            if evidence:
                if expected_revision is None:
                    raise KnowledgeError(
                        409,
                        "revision_required",
                        "Provide the current proposal revision to add evidence.",
                    )
                return self.add_evidence(
                    project_id, actor_id, obj.id, "topic", expected_revision, evidence
                )
            return self._edge_view(obj, "topic")
        self.session.add(obj)
        self.session.flush()
        for item in evidence:
            segment = self._resource(DocumentSegment, UUID(str(item["segment_id"])), project_id)
            self._add_evidence(
                obj,
                "topic",
                segment,
                item["start_offset"],
                item["end_offset"],
                item["quote"],
                actor_id=actor_id,
            )
        self.session.commit()
        return self._edge_view(obj, "topic")

    def correct(
        self,
        project_id,
        actor_id,
        link_id,
        kind,
        expected_revision,
        topic_id=None,
        relation_type=None,
        source_topic_id=None,
        target_topic_id=None,
        reason="",
    ):
        self._project(project_id, actor_id, lock=True)
        obj = self._edge(project_id, link_id, kind)
        self._revision(obj, expected_revision)
        if kind == "source":
            target = topic_id or obj.topic_id
            relation = relation_type or obj.relation_type
            self._resource(Topic, target, project_id)
            allowed = (
                {"EXPLAINS", "RELATED_TO"}
                if obj.segment_id
                else {"APPLIES", "EXAMINES", "RELATED_TO"}
            )
            if relation not in allowed:
                raise KnowledgeError(
                    422, "invalid_relation", "Invalid relationship for these endpoints."
                )
            identity = fingerprint(
                ["source", str(obj.segment_id or obj.exercise_id), str(target), relation]
            )
            replacement = self.session.scalar(
                select(SourceLink).where(
                    SourceLink.project_id == project_id, SourceLink.identity_key == identity
                )
            )
            if replacement is None:
                replacement = SourceLink(
                    project_id=project_id,
                    segment_id=obj.segment_id,
                    exercise_id=obj.exercise_id,
                    topic_id=target,
                    relation_type=relation,
                    reason=reason,
                    basis="manual",
                    identity_key=identity,
                    confidence_kind="none",
                    issues=[],
                    corrected_from_id=obj.id,
                )
        else:
            replacement = self._new_relation(
                project_id,
                source_topic_id or obj.source_topic_id,
                target_topic_id or obj.target_topic_id,
                relation_type or obj.relation_type,
                reason,
            )
        if replacement.id == obj.id:
            raise KnowledgeError(
                422, "unchanged_link", "Correction must change an endpoint or relationship type."
            )
        if replacement.id is not None:
            raise KnowledgeError(
                409, "link_exists", "The replacement already exists; review that proposal directly."
            )
        replacement.corrected_from_id = obj.id
        self.session.add(replacement)
        self.session.flush()
        for item in self._evidence(obj, kind):
            segment = self._resource(DocumentSegment, item.segment_id, project_id)
            self._add_evidence(
                replacement,
                kind,
                segment,
                item.start_offset,
                item.end_offset,
                item.quote,
                actor_id=actor_id,
            )
        self._refresh_evidence_issues(replacement, kind)
        obj.review_status = "rejected"
        self._decision(obj, actor_id, kind, "correct", reason)
        self.session.commit()
        return {
            "original": self._edge_view(obj, kind),
            "replacement": self._edge_view(replacement, kind),
        }
