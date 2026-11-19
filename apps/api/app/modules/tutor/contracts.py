"""Provider-neutral, validated inputs and structured tutor generation outputs."""

from enum import StrEnum
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Mode(StrEnum):
    SOURCE_MODE = "SOURCE_MODE"
    DEEP_PHYSICS_MODE = "DEEP_PHYSICS_MODE"
    EXAM_MODE = "EXAM_MODE"
    SOCRATIC_MODE = "SOCRATIC_MODE"


class Depth(StrEnum):
    CONCISE = "concise"
    STANDARD = "standard"
    DEEP = "deep"


class ExplanationDepth(StrEnum):
    STANDARD = "STANDARD"
    DETAILED = "DETAILED"
    RIGOROUS = "RIGOROUS"
    AUTO = "AUTO"


class AnswerBlock(StrictModel):
    kind: Literal["source_content", "derivation", "model_knowledge", "unverified_assumption"]
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=12000)]
    citation_ids: list[UUID] = Field(default_factory=list, max_length=30)
    math_check_ids: list[str] = Field(default_factory=list, max_length=30)


class LLMDraft(StrictModel):
    blocks: list[AnswerBlock] = Field(min_length=1, max_length=20)
    uncertainties: list[ShortText] = Field(default_factory=list, max_length=20)
    math_claims: list[ShortText] = Field(default_factory=list, max_length=20)


class GenerationParameters(StrictModel):
    temperature: float = Field(default=0.2, ge=0, le=2, allow_inf_nan=False)
    max_output_tokens: int = Field(default=1024, ge=128, le=4096)
    timeout_seconds: float = Field(default=30, ge=1, le=120, allow_inf_nan=False)
    model: str = Field(default="mock-v1", min_length=1, max_length=255)
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"] | None = (
        None
    )


class StructuredMessage(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=250000)


class GenerationRequest(StrictModel):
    messages: tuple[StructuredMessage, ...] = Field(min_length=1, max_length=100)
    model: str = Field(default="mock-v1", min_length=1, max_length=255)
    parameters: GenerationParameters = Field(default_factory=GenerationParameters)
    mode: Mode
    depth: Depth = Depth.STANDARD
    source_context: dict[str, Any] = Field(default_factory=dict)
    math_results: tuple[dict[str, Any], ...] = ()
    direct_answer: bool = False
    explanation_depth: ExplanationDepth | None = None
    prompt_version: str = "physics-tutor-v1"


class GenerationResult(StrictModel):
    draft: LLMDraft
    provider_name: str = Field(min_length=1, max_length=255)
    model_name: str = Field(min_length=1, max_length=255)
    usage: dict[str, int] = Field(default_factory=dict)
    effective_parameters: dict[str, Any] = Field(default_factory=dict)
    response_id: str | None = Field(default=None, max_length=255)


class ProviderError(Exception):
    """Safe failure details, without service bodies, keys, prompts or source text."""

    def __init__(
        self,
        code: Literal[
            "timeout",
            "unavailable",
            "invalid_response",
            "rate_limit",
            "disabled",
            "invalid_configuration",
            "budget_exhausted",
        ],
        message: str,
        retry_after_seconds: float | None = None,
    ):
        self.code = code
        self.message = message
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message)


class Provider(Protocol):
    name: str
    is_mock: bool
    is_external: bool

    async def generate(self, request: GenerationRequest) -> GenerationResult: ...
