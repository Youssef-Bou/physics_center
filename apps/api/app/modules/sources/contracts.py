"""Provider-neutral immutable contracts for document analysis.

Offsets always address the *unchanged extracted page text*, use Python Unicode
code-point indices, and form a half-open interval [start_offset, end_offset).
Physical page numbers are one-based. Scores are uncalibrated ranking indicators.
"""

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID


@dataclass(frozen=True)
class TopicInput:
    id: UUID
    name: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str
    kind: Literal["text", "scan", "unreadable"] = "text"
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class SegmentDraft:
    key: str
    page_number: int
    start_offset: int
    end_offset: int
    text: str
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExerciseDraft:
    key: str
    label: str
    segment_keys: tuple[str, ...]
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceDraft:
    segment_key: str
    start_offset: int
    end_offset: int
    quote: str


@dataclass(frozen=True)
class LinkDraft:
    subject_kind: Literal["segment", "exercise"]
    subject_key: str
    topic_id: UUID
    relation_type: str
    reason: str
    evidence: tuple[EvidenceDraft, ...] = ()
    score: float | None = None
    confidence_kind: str = "heuristic_uncalibrated"
    issues: tuple[str, ...] = ()
    basis: str = "lexical_match"


@dataclass(frozen=True)
class TopicRelationDraft:
    source_topic_id: UUID
    target_topic_id: UUID
    relation_type: str
    reason: str
    evidence: tuple[EvidenceDraft, ...] = ()
    score: float | None = None
    confidence_kind: str = "heuristic_uncalibrated"
    issues: tuple[str, ...] = ()
    basis: str = "explicit_statement"


@dataclass(frozen=True)
class AnalysisSuggestions:
    links: tuple[LinkDraft, ...] = ()
    topic_relations: tuple[TopicRelationDraft, ...] = ()
    issues: tuple[str, ...] = ()


class Analyzer(Protocol):
    version: str

    def analyze(
        self,
        segments: tuple[SegmentDraft, ...],
        exercises: tuple[ExerciseDraft, ...],
        topics: tuple[TopicInput, ...],
        source_type: str,
    ) -> AnalysisSuggestions: ...


@dataclass(frozen=True)
class AnalysisResult:
    pages: tuple[ExtractedPage, ...]
    segments: tuple[SegmentDraft, ...]
    exercises: tuple[ExerciseDraft, ...]
    links: tuple[LinkDraft, ...]
    topic_relations: tuple[TopicRelationDraft, ...]
    extraction_version: str
    analyzer_version: str
    issues: tuple[str, ...] = ()
