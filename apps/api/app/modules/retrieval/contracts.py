"""Provider-neutral retrieval contracts. Scores are ranking signals, not probabilities."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class RetrievalFilters:
    document_ids: tuple[UUID, ...] = ()
    document_version_ids: tuple[UUID, ...] = ()
    source_types: tuple[str, ...] = ()
    module_id: UUID | None = None
    page_start: int | None = None
    page_end: int | None = None
    exercise_label: str | None = None
    chapter: str | None = None
    source_instruction: str | None = None


@dataclass(frozen=True)
class ScopedVersion:
    version_id: UUID
    document_id: UUID
    document_title: str
    source_type: str
    sha256: str
    page_count: int
    analysis_run_id: UUID
    segment_ids: tuple[UUID, ...]
    exercise_ids: tuple[UUID, ...]
    pages: tuple[dict, ...]
    issues: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedScope:
    scope_id: UUID
    revision: int
    items: tuple[ScopedVersion, ...]


class EmbeddingProvider(Protocol):
    """Optional local implementation; external processing is deliberately disabled.

    Providers must declare model_id and is_local=True. They receive only the query
    and allowed source passages, never an unfiltered corpus.
    """

    model_id: str
    is_local: bool

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...
