"""Thin project-scoped routes for analysis and manual review."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.api.dependencies import Actor, Service
from app.api.schemas import (
    CorrectionRequest,
    EvidenceAppendRequest,
    ProjectCreate,
    ReviewRequest,
    ReviewStatus,
    SourceType,
    TopicCreate,
    TopicRelationCreate,
)

MAX_UPLOAD_BYTES = 16 * 1024 * 1024
router = APIRouter(prefix="/api/v1/projects")


@router.post("", status_code=201)
def create_project(body: ProjectCreate, actor: Actor, service: Service):
    return service.create_project(actor, body.title)


@router.post("/{project_id}/topics", status_code=201)
def create_topic(project_id: UUID, body: TopicCreate, actor: Actor, service: Service):
    return service.create_topic(project_id, actor, body.name, body.aliases)


@router.get("/{project_id}/topics")
def list_topics(project_id: UUID, actor: Actor, service: Service):
    return service.list_topics(project_id, actor)


@router.post("/{project_id}/documents", status_code=201)
async def upload_document(
    project_id: UUID,
    actor: Actor,
    service: Service,
    title: Annotated[str, Form(min_length=1, max_length=300)],
    source_type: Annotated[SourceType, Form()],
    file: Annotated[UploadFile, File()],
):
    if not title.strip():
        raise HTTPException(status_code=422, detail="A document title is required.")
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=415, detail="Only application/pdf is supported.")
    try:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await file.close()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="PDF exceeds the 16 MiB upload limit.")
    return service.upload(project_id, actor, title.strip(), source_type.value, content)


@router.post("/{project_id}/document-versions/{version_id}/analyses")
def analyze_version(project_id: UUID, version_id: UUID, actor: Actor, service: Service):
    return service.analyze(project_id, actor, version_id)


@router.get("/{project_id}/document-versions/{version_id}/segments")
def list_segments(project_id: UUID, version_id: UUID, actor: Actor, service: Service):
    return service.list_segments(project_id, actor, version_id)


@router.get("/{project_id}/document-versions/{version_id}/exercises")
def list_exercises(project_id: UUID, version_id: UUID, actor: Actor, service: Service):
    return service.list_exercises(project_id, actor, version_id)


@router.get("/{project_id}/document-versions/{version_id}/file")
def download_document(project_id: UUID, version_id: UUID, actor: Actor, service: Service):
    path = service.document_file(project_id, actor, version_id)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"{version_id}.pdf",
        content_disposition_type="attachment",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
    )


@router.get("/{project_id}/links")
def list_links(
    project_id: UUID,
    actor: Actor,
    service: Service,
    status: ReviewStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return service.list_links(project_id, actor, status.value if status else None, limit, offset)


@router.get("/{project_id}/links/{link_id}")
def get_link(project_id: UUID, link_id: UUID, actor: Actor, service: Service):
    return service.get_link(project_id, actor, link_id, kind="source")


@router.post("/{project_id}/links/{link_id}/review")
def review_link(
    project_id: UUID, link_id: UUID, body: ReviewRequest, actor: Actor, service: Service
):
    return service.review(
        project_id,
        actor,
        link_id,
        kind="source",
        decision=body.decision.value,
        expected_revision=body.expected_revision,
        reason=body.reason,
        evidence_checked=body.evidence_checked,
    )


@router.post("/{project_id}/links/{link_id}/correction")
def correct_link(
    project_id: UUID, link_id: UUID, body: CorrectionRequest, actor: Actor, service: Service
):
    return service.correct(
        project_id, actor, link_id, kind="source", **body.model_dump(exclude_none=True)
    )


@router.post("/{project_id}/links/{link_id}/evidence")
def append_link_evidence(
    project_id: UUID, link_id: UUID, body: EvidenceAppendRequest, actor: Actor, service: Service
):
    return service.add_evidence(project_id, actor, link_id, kind="source", **body.model_dump())


@router.get("/{project_id}/topic-relations")
def list_relations(
    project_id: UUID,
    actor: Actor,
    service: Service,
    status: ReviewStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return service.list_relations(
        project_id, actor, status.value if status else None, limit, offset
    )


@router.post("/{project_id}/topic-relations", status_code=201)
def create_relation(project_id: UUID, body: TopicRelationCreate, actor: Actor, service: Service):
    return service.create_relation(project_id, actor, **body.model_dump())


@router.get("/{project_id}/topic-relations/{link_id}")
def get_relation(project_id: UUID, link_id: UUID, actor: Actor, service: Service):
    return service.get_link(project_id, actor, link_id, kind="topic")


@router.post("/{project_id}/topic-relations/{link_id}/review")
def review_relation(
    project_id: UUID, link_id: UUID, body: ReviewRequest, actor: Actor, service: Service
):
    return service.review(
        project_id,
        actor,
        link_id,
        kind="topic",
        decision=body.decision.value,
        expected_revision=body.expected_revision,
        reason=body.reason,
        evidence_checked=body.evidence_checked,
    )


@router.post("/{project_id}/topic-relations/{link_id}/correction")
def correct_relation(
    project_id: UUID, link_id: UUID, body: CorrectionRequest, actor: Actor, service: Service
):
    return service.correct(
        project_id, actor, link_id, kind="topic", **body.model_dump(exclude_none=True)
    )


@router.post("/{project_id}/topic-relations/{link_id}/evidence")
def append_relation_evidence(
    project_id: UUID, link_id: UUID, body: EvidenceAppendRequest, actor: Actor, service: Service
):
    return service.add_evidence(project_id, actor, link_id, kind="topic", **body.model_dump())
