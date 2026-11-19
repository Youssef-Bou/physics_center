"""Orchestration and validation, independent from HTTP, persistence, and provider SDKs."""

import math
from dataclasses import replace

from .analysis import CatalogueAnalyzer
from .contracts import (
    AnalysisResult,
    Analyzer,
    EvidenceDraft,
    LinkDraft,
    TopicInput,
    TopicRelationDraft,
)
from .extraction import PdfExtractor, identify_exercises, segment_pages


class AnalysisPipeline:
    version = "source-analysis-v1"

    def __init__(self, analyzer: Analyzer | None = None, extractor: PdfExtractor | None = None):
        self.analyzer = analyzer or CatalogueAnalyzer()
        self.extractor = extractor or PdfExtractor()

    def run(
        self, pdf_bytes: bytes, topics: tuple[TopicInput, ...], source_type: str
    ) -> AnalysisResult:
        pages = self.extractor.extract(pdf_bytes)
        segments = segment_pages(pages)
        exercises = identify_exercises(segments, source_type)
        suggestions = self.analyzer.analyze(segments, exercises, topics, source_type)
        by_key = {s.key: s for s in segments}
        topic_ids = {topic.id for topic in topics}
        exercise_by_key = {exercise.key: exercise for exercise in exercises}

        def checked_evidence(
            items: tuple[EvidenceDraft, ...],
            allowed_keys: set[str] | None = None,
        ) -> tuple[tuple[EvidenceDraft, ...], tuple[str, ...]]:
            valid: list[EvidenceDraft] = []
            issues: list[str] = []
            for evidence in items:
                segment = by_key.get(evidence.segment_key)
                if segment is None:
                    raise ValueError("Analyzer referenced an unknown segment.")
                if allowed_keys is not None and evidence.segment_key not in allowed_keys:
                    issues.append("unrelated_evidence_removed")
                    continue
                start = evidence.start_offset - segment.start_offset
                end = evidence.end_offset - segment.start_offset
                if not (0 <= start < end <= len(segment.text)) or (
                    segment.text[start:end] != evidence.quote or not evidence.quote.strip()
                ):
                    issues.append("invalid_evidence_removed")
                    continue
                valid.append(evidence)
                issues.extend(segment.issues)
            if not valid:
                issues.append("missing_evidence")
            return tuple(dict.fromkeys(valid)), tuple(dict.fromkeys(issues))

        def checked_score(score: float | None, kind: str) -> str:
            if score is not None and (not math.isfinite(score) or not 0 <= score <= 1):
                raise ValueError("Confidence indicator must be finite and between zero and one.")
            if kind not in {"none", "heuristic_uncalibrated"}:
                raise ValueError("No empirically calibrated confidence model is configured.")
            if score is not None and kind != "heuristic_uncalibrated":
                raise ValueError("A score must be explicitly marked as an uncalibrated indicator.")
            return "none" if score is None else kind

        def checked_basis(basis: str) -> None:
            if basis not in {"lexical_match", "semantic_similarity", "explicit_statement"}:
                raise ValueError("Unknown or privileged automatic analysis basis.")

        checked_links: list[LinkDraft] = []
        for link in suggestions.links:
            if link.topic_id not in topic_ids:
                raise ValueError("Analyzer referenced an unknown topic.")
            if link.subject_kind == "segment":
                if link.subject_key not in by_key:
                    raise ValueError("Analyzer referenced an unknown subject segment.")
                allowed = {"EXPLAINS", "RELATED_TO"}
                evidence_keys = {link.subject_key}
            elif link.subject_kind == "exercise":
                if link.subject_key not in exercise_by_key:
                    raise ValueError("Analyzer referenced an unknown exercise.")
                allowed = {"APPLIES", "EXAMINES", "RELATED_TO"}
                evidence_keys = set(exercise_by_key[link.subject_key].segment_keys)
            else:
                raise ValueError("Unknown source-link subject kind.")
            if link.relation_type not in allowed:
                raise ValueError("Invalid relationship type for source-link endpoints.")
            if not link.reason.strip():
                raise ValueError("Relationship proposals need an explicit reason.")
            kind = checked_score(link.score, link.confidence_kind)
            checked_basis(link.basis)
            evidence, issues = checked_evidence(link.evidence, evidence_keys)
            checked_links.append(
                replace(
                    link,
                    evidence=evidence,
                    confidence_kind=kind,
                    issues=tuple(dict.fromkeys((*link.issues, *issues))),
                )
            )

        checked_relations: list[TopicRelationDraft] = []
        for relation in suggestions.topic_relations:
            if (
                relation.source_topic_id not in topic_ids
                or relation.target_topic_id not in topic_ids
            ):
                raise ValueError("Topic relation references an unknown topic.")
            if relation.source_topic_id == relation.target_topic_id:
                raise ValueError("Self-relations are not supported.")
            if relation.relation_type not in {"IS_PREREQUISITE_OF", "RELATED_TO"}:
                raise ValueError("Invalid relationship type for topic endpoints.")
            if (
                relation.relation_type == "IS_PREREQUISITE_OF"
                and relation.basis != "explicit_statement"
            ):
                raise ValueError("Similarity is not evidence of a scientific prerequisite.")
            if not relation.reason.strip():
                raise ValueError("Topic relationship proposals need an explicit reason.")
            kind = checked_score(relation.score, relation.confidence_kind)
            checked_basis(relation.basis)
            evidence, issues = checked_evidence(relation.evidence)
            checked_relations.append(
                replace(
                    relation,
                    evidence=evidence,
                    confidence_kind=kind,
                    issues=tuple(dict.fromkeys((*relation.issues, *issues))),
                )
            )

        issues = tuple(
            dict.fromkeys(
                (*suggestions.issues, *(issue for page in pages for issue in page.issues))
            )
        )
        return AnalysisResult(
            pages,
            segments,
            exercises,
            tuple(checked_links),
            tuple(checked_relations),
            self.extractor.version,
            self.analyzer.version,
            issues,
        )
