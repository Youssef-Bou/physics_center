"""Project-scoped tutor contracts; retrieval, generation and review stay in services."""

from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import Field, StringConstraints

from app.api.dependencies import Actor, Service
from app.api.retrieval import FiltersInput
from app.api.schemas import InputModel
from app.modules.tutor.contracts import Depth, ExplanationDepth, Mode
from app.modules.tutor.mathematics import MathCheckRequest
from app.modules.tutor.service import PhysicsTutorService, TutorError

router = APIRouter(prefix="/api/v1/projects/{project_id}/tutor", tags=["tutor"])

Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]
HistoryText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]
RetrievalQuery = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
]
ModelName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class HistoryMessage(InputModel):
    role: Literal["user", "assistant"]
    content: HistoryText


class TutorAnswerRequest(InputModel):
    question: Question
    mode: Mode = Mode.SOURCE_MODE
    scope_id: UUID
    scope_revision: int = Field(ge=1)
    module_id: UUID | None = None
    conversation_id: UUID | None = None
    request_id: UUID = Field(default_factory=uuid4)
    depth: Depth = Depth.STANDARD
    explanation_depth: ExplanationDepth | None = None
    prompt_version: Literal["physics-tutor-v1", "physics-tutor-v2"] | None = None
    filters: FiltersInput = Field(default_factory=FiltersInput)
    retrieval_query: RetrievalQuery | None = None
    k: int = Field(default=5, ge=1, le=10)
    context_token_budget: int = Field(default=6000, ge=512, le=16000)
    max_output_tokens: int = Field(default=1500, ge=128, le=4096)
    temperature: float = Field(default=0.2, ge=0, le=2, allow_inf_nan=False)
    timeout_seconds: float = Field(default=30, ge=1, le=120, allow_inf_nan=False)
    model: ModelName | None = None
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"] | None = (
        None
    )
    history: list[HistoryMessage] = Field(default_factory=list, max_length=8)
    direct_answer: bool = False
    full_solution: bool = False
    math_checks: list[MathCheckRequest] = Field(default_factory=list, max_length=4)
    allow_external_processing: bool = False


def tutor_service(request: Request, knowledge) -> PhysicsTutorService:
    return PhysicsTutorService(
        knowledge,
        provider=request.app.state.tutor_provider,
        math_tool=request.app.state.math_tool,
        default_model=request.app.state.tutor_model,
    )


def safe_error(exc: TutorError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder(
            {
                "code": exc.code,
                "detail": exc.message,
                "conversation_id": getattr(exc, "conversation_id", None),
                "turn_id": getattr(exc, "turn_id", None),
            }
        ),
    )


@router.post("/answers")
async def answer(
    project_id: UUID, body: TutorAnswerRequest, request: Request, actor: Actor, service: Service
):
    try:
        payload = body.model_dump()
        payload["_legacy_depth_explicit"] = "depth" in body.model_fields_set
        return await tutor_service(request, service).ask(project_id, actor, payload)
    except TutorError as exc:
        return safe_error(exc)


@router.get("/conversations/{conversation_id}")
def conversation_history(
    project_id: UUID, conversation_id: UUID, request: Request, actor: Actor, service: Service
):
    try:
        return tutor_service(request, service).history(project_id, actor, conversation_id)
    except TutorError as exc:
        return safe_error(exc)
