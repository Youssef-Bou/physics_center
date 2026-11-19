"""Strict experiment data and evidence labels. No implicit gold-standard status."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.tutor.contracts import ExplanationDepth, Mode
from app.modules.tutor.mathematics import MathCheckRequest


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Category(StrEnum):
    DERIVATION = "derivation"
    CONCEPT = "concept"
    EXAM = "exam"
    LIMITS = "limits"
    SOURCE = "source"
    SOCRATIC = "socratic"


class ValidationRecord(Strict):
    status: Literal["unvalidated", "manually_validated"] = "unvalidated"
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    notes: str = "Candidate reference; independent expert review required."

    @model_validator(mode="after")
    def independent_record(self):
        if self.status == "manually_validated" and (not self.reviewer or not self.reviewed_at):
            raise ValueError(
                "Validated references require an explicit reviewer and review timestamp."
            )
        return self


class SyntheticSource(Strict):
    id: str = Field(pattern=r"^[a-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=300)
    source_type: Literal[
        "lecture_notes",
        "textbook",
        "exercise_sheet",
        "worked_solution",
        "past_exam",
        "paper",
        "other",
    ]
    pages: list[str] = Field(min_length=1, max_length=10)
    rights_status: Literal["synthetic"] = "synthetic"
    external_use_allowed: bool = True
    physical_review: ValidationRecord = Field(default_factory=ValidationRecord)


class ExpectedSource(Strict):
    source_id: str
    page_number: int = Field(ge=1)
    quote: str = Field(min_length=1)


class EvaluationCase(Strict):
    id: str = Field(pattern=r"^[A-Z][A-Z0-9_-]+$")
    category: Category
    topic: str
    difficulty: Literal["foundational", "intermediate", "advanced"]
    mode: Mode
    question: str = Field(min_length=1, max_length=8000)
    prerequisites: list[str] = Field(min_length=1)
    reference_solution: str = Field(min_length=1)
    criteria: list[str] = Field(min_length=1)
    mandatory_steps: list[str] = Field(min_length=1)
    common_errors: list[str] = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    expected_sources: list[ExpectedSource] = Field(default_factory=list)
    validation: ValidationRecord = Field(default_factory=ValidationRecord)
    retrieval_query: str = Field(min_length=1, max_length=1000)
    math_checks: list[MathCheckRequest] = Field(default_factory=list, max_length=4)


class EvaluationDataset(Strict):
    id: str
    version: str
    description: str
    sources: list[SyntheticSource]
    cases: list[EvaluationCase] = Field(min_length=24)

    @model_validator(mode="after")
    def consistent(self):
        cases = [case.id for case in self.cases]
        sources = {source.id: source for source in self.sources}
        if len(cases) != len(set(cases)) or len(sources) != len(self.sources):
            raise ValueError("Case and source IDs must be unique.")
        if set(case.category for case in self.cases) != set(Category):
            raise ValueError("All six case categories must be represented.")
        for case in self.cases:
            if not set(case.source_ids) <= sources.keys():
                raise ValueError("Unknown source binding.")
            if len(case.source_ids) != len(set(case.source_ids)):
                raise ValueError("Source bindings must be unique.")
            if len({check.id for check in case.math_checks}) != len(case.math_checks):
                raise ValueError("Mathematical check IDs must be unique.")
            for expected in case.expected_sources:
                source = sources.get(expected.source_id)
                if source is None or expected.source_id not in case.source_ids:
                    raise ValueError("Expected evidence must be among the allowed sources.")
                if (
                    expected.page_number > len(source.pages)
                    or expected.quote not in source.pages[expected.page_number - 1]
                ):
                    raise ValueError(
                        "Expected source location is not present in the declared synthetic original."
                    )
        return self


class Criterion(StrEnum):
    MATHEMATICS = "mathematical_correctness"
    STEPS = "derivation_completeness"
    ASSUMPTIONS = "physical_assumptions"
    INTERPRETATION = "physical_interpretation"
    CITATIONS = "citation_accuracy"
    UNCERTAINTY = "uncertainty_transparency"


class Rating(Strict):
    criterion: Criterion
    score: int | None = Field(default=None, ge=0, le=4)
    method: Literal["not_reviewed", "deterministic", "symbolic", "model_judgment", "manual"] = (
        "not_reviewed"
    )
    rationale: str = ""
    reviewer: str | None = None

    @model_validator(mode="after")
    def honest_status(self):
        if self.method == "not_reviewed" and self.score is not None:
            raise ValueError("An unreviewed criterion cannot have a score.")
        if (
            self.method in {"manual", "model_judgment"}
            and self.score is not None
            and not self.reviewer
        ):
            raise ValueError("Scored human/model judgments require an identifiable reviewer/model.")
        return self


class SevereError(Strict):
    code: Literal[
        "wrong_sign",
        "invalid_boundary",
        "fabricated_citation",
        "unjustified_generalization",
        "other",
    ]
    method: Literal["deterministic", "symbolic", "model_judgment", "manual"]
    rationale: str = Field(min_length=1)
    reviewer: str | None = None

    @model_validator(mode="after")
    def attributed(self):
        if self.method in {"manual", "model_judgment"} and not self.reviewer:
            raise ValueError("Human/model critical-error judgments need an attributable reviewer.")
        return self


class EconomyRating(Strict):
    score: int | None = Field(default=None, ge=0, le=4)
    method: Literal["not_reviewed", "manual", "model_judgment"] = "not_reviewed"
    reviewer: str | None = None
    rationale: str = "Explanation economy requires content review, never answer-length scoring."

    @model_validator(mode="after")
    def attributed(self):
        if self.score is not None and (self.method == "not_reviewed" or not self.reviewer):
            raise ValueError("An explanation-economy score needs an explicit attributed judgment.")
        return self


class ExternalSourceManifest(Strict):
    """Prepared import boundary. Permission never follows from possessing a PDF."""

    source_id: str
    title: str
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    authorization: Literal["local_only", "external_allowed"] = "local_only"
    license_note: str = Field(min_length=1)


class ExperimentConfig(Strict):
    method: Literal["isolated", "end_to_end"] = "isolated"
    provider: Literal["mock", "openai_responses"] = "mock"
    model: str | None = Field(default=None, min_length=1, max_length=255)
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"] | None = (
        None
    )
    temperature: float = Field(default=0.2, ge=0, le=2, allow_inf_nan=False)
    timeout_seconds: float = Field(default=30, ge=1, le=120, allow_inf_nan=False)
    max_output_tokens: int = Field(default=1500, ge=128, le=4096)
    context_token_budget: int = Field(default=6000, ge=512, le=16000)
    k: int = Field(default=5, ge=1, le=10)
    case_ids: list[str] = Field(default_factory=list, max_length=100)
    limit: int = Field(default=24, ge=1, le=100)
    max_calls: int | None = Field(default=None, ge=1, le=100)
    allow_paid: bool = False
    allow_unvalidated: bool = False
    explanation_depth: ExplanationDepth | None = None
    prompt_version: Literal["physics-tutor-v1", "physics-tutor-v2"] | None = None
