"""HTTP contracts for explicit source selection, retrieval and locator verification."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import Field, StringConstraints, model_validator

from app.api.dependencies import Actor, Service
from app.api.schemas import InputModel, Name, SourceType
from app.modules.retrieval.contracts import RetrievalFilters
from app.modules.retrieval.scope import ScopeService
from app.modules.retrieval.service import RetrievalService

router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["retrieval"])

QueryText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
LocatorLabel = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
]
SourceInstruction = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]


class ModuleCreate(InputModel):
    title: Name


class ScopeCreate(InputModel):
    name: Name


class ScopeReplace(InputModel):
    expected_revision: int = Field(ge=1)
    document_version_ids: list[UUID] = Field(default_factory=list, max_length=50)
    confirmed: bool = False


class FiltersInput(InputModel):
    document_ids: list[UUID] = Field(default_factory=list, max_length=50)
    document_version_ids: list[UUID] = Field(default_factory=list, max_length=50)
    source_types: list[SourceType] = Field(default_factory=list, max_length=8)
    module_id: UUID | None = None
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    exercise_label: LocatorLabel | None = None
    chapter: LocatorLabel | None = None
    source_instruction: SourceInstruction | None = None

    @model_validator(mode="after")
    def ordered_pages(self):
        if self.page_start is not None and self.page_end is not None:
            if self.page_end < self.page_start:
                raise ValueError("page_end must be greater than or equal to page_start")
        return self

    def to_domain(self) -> RetrievalFilters:
        return RetrievalFilters(
            document_ids=tuple(self.document_ids),
            document_version_ids=tuple(self.document_version_ids),
            source_types=tuple(source_type.value for source_type in self.source_types),
            module_id=self.module_id,
            page_start=self.page_start,
            page_end=self.page_end,
            exercise_label=self.exercise_label,
            chapter=self.chapter,
            source_instruction=self.source_instruction,
        )


class SearchRequest(InputModel):
    scope_id: UUID
    scope_revision: int = Field(ge=1)
    query: QueryText
    k: int = Field(default=10, ge=1, le=50)
    mode: Literal["lexical", "semantic", "hybrid"] = "lexical"
    filters: FiltersInput = Field(default_factory=FiltersInput)

    def arguments(self) -> dict:
        return {
            "scope_id": self.scope_id,
            "scope_revision": self.scope_revision,
            "query": self.query,
            "filters": self.filters.to_domain(),
            "k": self.k,
            "mode": self.mode,
        }


class CitationVerificationRequest(InputModel):
    scope_id: UUID
    scope_revision: int = Field(ge=1)
    segment_id: UUID
    filters: FiltersInput = Field(default_factory=FiltersInput)


@router.post("/modules", status_code=201)
def create_module(project_id: UUID, body: ModuleCreate, actor: Actor, service: Service):
    return ScopeService(service).create_module(project_id, actor, body.title)


@router.get("/modules")
def list_modules(project_id: UUID, actor: Actor, service: Service):
    return ScopeService(service).list_modules(project_id, actor)


@router.put("/modules/{module_id}/documents/{document_id}")
def assign_document(
    project_id: UUID, module_id: UUID, document_id: UUID, actor: Actor, service: Service
):
    return ScopeService(service).assign_document(project_id, actor, module_id, document_id)


@router.post("/retrieval/scopes", status_code=201)
def create_scope(project_id: UUID, body: ScopeCreate, actor: Actor, service: Service):
    return ScopeService(service).create(project_id, actor, body.name)


@router.get("/retrieval/scopes/{scope_id}")
def get_scope(project_id: UUID, scope_id: UUID, actor: Actor, service: Service):
    return ScopeService(service).get(project_id, actor, scope_id)


@router.put("/retrieval/scopes/{scope_id}/sources")
def replace_scope(
    project_id: UUID, scope_id: UUID, body: ScopeReplace, actor: Actor, service: Service
):
    return ScopeService(service).replace(project_id, actor, scope_id, **body.model_dump())


@router.post("/retrieval/search")
def search(project_id: UUID, body: SearchRequest, request: Request, actor: Actor, service: Service):
    retrieval = RetrievalService(service, request.app.state.embedding_provider)
    return retrieval.search(project_id, actor, **body.arguments())


@router.post("/retrieval/context")
def tutor_context(
    project_id: UUID, body: SearchRequest, request: Request, actor: Actor, service: Service
):
    retrieval = RetrievalService(service, request.app.state.embedding_provider)
    return retrieval.context(project_id, actor, **body.arguments())


@router.get("/retrieval/scopes/{scope_id}/citations/{segment_id}")
def verify_citation(
    project_id: UUID,
    scope_id: UUID,
    segment_id: UUID,
    actor: Actor,
    service: Service,
    scope_revision: Annotated[int, Query(ge=1)],
):
    return RetrievalService(service).citation(
        project_id, actor, scope_id, scope_revision, segment_id
    )


@router.post("/retrieval/citations/verify")
def verify_filtered_citation(
    project_id: UUID, body: CitationVerificationRequest, actor: Actor, service: Service
):
    return RetrievalService(service).citation(
        project_id,
        actor,
        body.scope_id,
        body.scope_revision,
        body.segment_id,
        filters=body.filters.to_domain(),
    )
