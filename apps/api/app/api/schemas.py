"""Strict input contracts; domain decisions belong to application services."""

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceType(StrEnum):
    TEXTBOOK = "textbook"
    LECTURE_NOTES = "lecture_notes"
    EXERCISE_SHEET = "exercise_sheet"
    WORKED_SOLUTION = "worked_solution"
    PAST_EXAM = "past_exam"
    PAPER = "paper"
    WEBSITE = "website"
    OTHER = "other"


class ReviewStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ReviewAction(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"


class RelationType(StrEnum):
    IS_PREREQUISITE_OF = "IS_PREREQUISITE_OF"
    EXPLAINS = "EXPLAINS"
    APPLIES = "APPLIES"
    EXAMINES = "EXAMINES"
    RELATED_TO = "RELATED_TO"


class TopicRelationType(StrEnum):
    IS_PREREQUISITE_OF = "IS_PREREQUISITE_OF"
    RELATED_TO = "RELATED_TO"


class ProjectCreate(InputModel):
    title: Name


class TopicCreate(InputModel):
    name: Name
    aliases: list[Name] = Field(default_factory=list, max_length=50)


class ReviewRequest(InputModel):
    decision: ReviewAction
    expected_revision: int = Field(ge=1)
    reason: Reason
    evidence_checked: bool = False


class CorrectionRequest(InputModel):
    expected_revision: int = Field(ge=1)
    reason: Reason
    topic_id: UUID | None = None
    relation_type: RelationType | None = None
    source_topic_id: UUID | None = None
    target_topic_id: UUID | None = None


class EvidenceInput(InputModel):
    segment_id: UUID
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=16000)


class TopicRelationCreate(InputModel):
    source_topic_id: UUID
    target_topic_id: UUID
    relation_type: TopicRelationType
    reason: Reason
    evidence: list[EvidenceInput] = Field(default_factory=list, max_length=50)
    expected_revision: int | None = Field(default=None, ge=1)


class EvidenceAppendRequest(InputModel):
    expected_revision: int = Field(ge=1)
    evidence: list[EvidenceInput] = Field(min_length=1, max_length=50)
