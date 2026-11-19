"""Persisted, revisioned source permissions for retrieval, independent of models."""

from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import delete, select

from app.infrastructure.models import (
    AnalysisRun,
    Document,
    DocumentVersion,
    Module,
    ModuleDocument,
    RetrievalScope,
    RetrievalScopeItem,
)
from app.modules.knowledge.service import KnowledgeError, KnowledgeService, record

from .contracts import ResolvedScope, RetrievalFilters, ScopedVersion


class ScopeService:
    def __init__(self, knowledge: KnowledgeService):
        self.knowledge, self.session = knowledge, knowledge.session

    def create_module(self, project_id, actor_id, title):
        self.knowledge._project(project_id, actor_id, lock=True)
        module = Module(project_id=project_id, title=title.strip())
        self.session.add(module)
        self.session.commit()
        return record(module)

    def list_modules(self, project_id, actor_id):
        self.knowledge._project(project_id, actor_id)
        return [
            record(module)
            for module in self.session.scalars(
                select(Module)
                .where(Module.project_id == project_id)
                .order_by(Module.title, Module.id)
            )
        ]

    def assign_document(self, project_id, actor_id, module_id, document_id):
        self.knowledge._project(project_id, actor_id, lock=True)
        self.knowledge._resource(Module, module_id, project_id)
        self.knowledge._resource(Document, document_id, project_id)
        assignment = self.session.get(ModuleDocument, (project_id, module_id, document_id))
        if assignment is None:
            assignment = ModuleDocument(
                project_id=project_id, module_id=module_id, document_id=document_id
            )
            self.session.add(assignment)
            self.session.commit()
        return record(assignment)

    def create(self, project_id, actor_id, name):
        self.knowledge._project(project_id, actor_id, lock=True)
        scope = RetrievalScope(project_id=project_id, name=name.strip())
        self.session.add(scope)
        self.session.commit()
        return self._view(scope)

    def _items(self, scope):
        return list(
            self.session.scalars(
                select(RetrievalScopeItem)
                .where(
                    RetrievalScopeItem.project_id == scope.project_id,
                    RetrievalScopeItem.scope_id == scope.id,
                )
                .order_by(RetrievalScopeItem.document_version_id)
            )
        )

    def _view(self, scope):
        return {
            **record(scope),
            "sources": [
                {
                    "document_version_id": item.document_version_id,
                    "analysis_run_id": item.analysis_run_id,
                }
                for item in self._items(scope)
            ],
        }

    def get(self, project_id, actor_id, scope_id):
        self.knowledge._project(project_id, actor_id)
        return self._view(self.knowledge._resource(RetrievalScope, scope_id, project_id))

    def replace(
        self,
        project_id,
        actor_id,
        scope_id,
        expected_revision,
        document_version_ids,
        confirmed=False,
    ):
        self.knowledge._project(project_id, actor_id, lock=True)
        scope = self.knowledge._resource(RetrievalScope, scope_id, project_id)
        if scope.revision != expected_revision:
            raise KnowledgeError(
                409, "scope_revision_conflict", "Source selection changed; reload its revision."
            )
        old = {item.document_version_id: item.analysis_run_id for item in self._items(scope)}
        requested = set(document_version_ids)
        if len(requested) > 50:
            raise KnowledgeError(422, "scope_too_large", "Select at most 50 source versions.")
        additions = requested - old.keys()
        runs = {}
        for version_id in sorted(requested, key=str):
            version = self.session.scalar(
                select(DocumentVersion).where(
                    DocumentVersion.project_id == project_id,
                    DocumentVersion.id == version_id,
                )
            )
            if version is None:
                raise KnowledgeError(
                    409,
                    "source_unavailable",
                    "A requested source is not available in this project.",
                )
            self.knowledge._file(version)
            if version_id in old:
                runs[version_id] = old[version_id]
            else:
                run = self.session.scalar(
                    select(AnalysisRun)
                    .where(
                        AnalysisRun.project_id == project_id,
                        AnalysisRun.document_version_id == version_id,
                    )
                    .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
                )
                if run is None:
                    raise KnowledgeError(
                        409,
                        "source_unavailable",
                        "Analyze each requested source before activation.",
                    )
                runs[version_id] = run.id
        if additions and not confirmed:
            raise KnowledgeError(
                409,
                "source_confirmation_required",
                "Explicit confirmation is required to activate additional source versions.",
            )
        if requested == old.keys():
            return self._view(scope)
        self.session.execute(
            delete(RetrievalScopeItem).where(RetrievalScopeItem.scope_id == scope_id)
        )
        for version_id, run_id in runs.items():
            self.session.add(
                RetrievalScopeItem(
                    project_id=project_id,
                    scope_id=scope_id,
                    document_version_id=version_id,
                    analysis_run_id=run_id,
                )
            )
        scope.revision += 1
        self.session.commit()
        return self._view(scope)

    def _instruction_documents(self, project_id, instruction):
        match = re.fullmatch(
            r"\s*(?:(?:verwende|benutze|nutze)\s+)?(?:nur|ausschließlich)\s+(.+?)\s*",
            instruction,
            re.IGNORECASE,
        )
        if not match:
            raise KnowledgeError(
                422,
                "unsupported_source_instruction",
                "Use an exact “nur <document title>” instruction or structured source IDs.",
            )
        title = match.group(1).strip().strip('"„“').strip()
        documents = [
            document.id
            for document in self.session.scalars(
                select(Document).where(Document.project_id == project_id)
            )
            if document.title.casefold() == title.casefold()
        ]
        if len(documents) != 1:
            raise KnowledgeError(
                409,
                "source_conflict",
                "The requested title is unavailable or ambiguous; select an explicit source ID.",
            )
        return set(documents)

    def resolve(self, project_id, actor_id, scope_id, scope_revision, filters=RetrievalFilters()):
        # Selection updates use the same project lock; no deactivation can race
        # a retrieval/embedding call in the current request transaction.
        self.knowledge._project(project_id, actor_id, lock=True)
        scope = self.knowledge._resource(RetrievalScope, scope_id, project_id)
        if scope.revision != scope_revision:
            raise KnowledgeError(
                409, "scope_revision_conflict", "Source selection changed; reload before retrieval."
            )
        selected = self._items(scope)
        versions = {
            item.document_version_id: self.knowledge._resource(
                DocumentVersion, item.document_version_id, project_id
            )
            for item in selected
        }
        active_documents = {version.document_id for version in versions.values()}
        requested_documents = set(filters.document_ids)
        if filters.source_instruction:
            title_documents = self._instruction_documents(project_id, filters.source_instruction)
            if requested_documents and not title_documents <= requested_documents:
                raise KnowledgeError(
                    409,
                    "source_conflict",
                    "The source instruction conflicts with the explicit document filter.",
                )
            requested_documents = title_documents
        if (
            not requested_documents <= active_documents
            or not set(filters.document_version_ids) <= versions.keys()
        ):
            raise KnowledgeError(
                409, "source_conflict", "A requested source is not activated in this selection."
            )
        if requested_documents and any(
            versions[version_id].document_id not in requested_documents
            for version_id in filters.document_version_ids
        ):
            raise KnowledgeError(
                409,
                "source_conflict",
                "The explicit version filter conflicts with the requested document selection.",
            )
        module_documents = None
        if filters.module_id is not None:
            self.knowledge._resource(Module, filters.module_id, project_id)
            module_documents = set(
                self.session.scalars(
                    select(ModuleDocument.document_id).where(
                        ModuleDocument.project_id == project_id,
                        ModuleDocument.module_id == filters.module_id,
                    )
                )
            )
        result = []
        for item in selected:
            version = versions[item.document_version_id]
            document = self.knowledge._resource(Document, version.document_id, project_id)
            if requested_documents and document.id not in requested_documents:
                continue
            if filters.document_version_ids and version.id not in filters.document_version_ids:
                continue
            if module_documents is not None and document.id not in module_documents:
                continue
            if filters.source_types and document.source_type not in filters.source_types:
                continue
            self.knowledge._file(version)
            run = self.knowledge._resource(AnalysisRun, item.analysis_run_id, project_id)
            if run.document_version_id != version.id:
                raise KnowledgeError(
                    409, "source_unavailable", "Pinned analysis does not match this source version."
                )
            try:
                segment_ids = tuple(UUID(str(value)) for value in run.result["segments"])
                exercise_ids = tuple(UUID(str(value)) for value in run.result["exercises"])
                pages = tuple(run.result["pages"])
                if len(pages) != version.page_count:
                    raise ValueError("page count")
            except (ValueError, KeyError, TypeError) as exc:
                raise KnowledgeError(
                    409, "source_unavailable", "The pinned extraction is not readable."
                ) from exc
            result.append(
                ScopedVersion(
                    version.id,
                    document.id,
                    document.title,
                    document.source_type,
                    version.sha256,
                    version.page_count,
                    run.id,
                    segment_ids,
                    exercise_ids,
                    pages,
                    tuple(run.issues),
                )
            )
        return ResolvedScope(scope.id, scope.revision, tuple(result))
