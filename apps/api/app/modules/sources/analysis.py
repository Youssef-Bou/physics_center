"""Small local catalogue matcher; semantic/LLM adapters implement the same port."""

import re

from .contracts import (
    AnalysisSuggestions,
    EvidenceDraft,
    ExerciseDraft,
    LinkDraft,
    SegmentDraft,
    TopicInput,
)


class CatalogueAnalyzer:
    version = "catalogue-alias-v1"

    def analyze(
        self,
        segments: tuple[SegmentDraft, ...],
        exercises: tuple[ExerciseDraft, ...],
        topics: tuple[TopicInput, ...],
        source_type: str,
    ) -> AnalysisSuggestions:
        links: list[LinkDraft] = []
        exercise_for_segment = {
            key: exercise for exercise in exercises for key in exercise.segment_keys
        }
        for segment in segments:
            exercise = exercise_for_segment.get(segment.key)
            if exercise:
                subject_kind = "exercise"
                subject_key = exercise.key
                relation = "EXAMINES" if source_type == "past_exam" else "APPLIES"
            else:
                subject_kind = "segment"
                subject_key = segment.key
                relation = (
                    "EXPLAINS"
                    if source_type in {"lecture_notes", "textbook", "paper"}
                    else "RELATED_TO"
                )
            for topic in topics:
                # Escaped, exact bounded strings; no fuzzy prerequisite inference.
                aliases = tuple(dict.fromkeys((topic.name, *topic.aliases)))
                evidence: list[EvidenceDraft] = []
                for alias in aliases:
                    if not alias.strip():
                        continue
                    for match in re.finditer(
                        r"(?<!\w)" + re.escape(alias) + r"(?!\w)", segment.text, re.I
                    ):
                        evidence.append(
                            EvidenceDraft(
                                segment.key,
                                segment.start_offset + match.start(),
                                segment.start_offset + match.end(),
                                match.group(),
                            )
                        )
                if not evidence:
                    continue
                links.append(
                    LinkDraft(
                        subject_kind,
                        subject_key,
                        topic.id,
                        relation,
                        "Exact catalogue name/alias occurs in the extracted source; "
                        "the scientific relationship requires human review.",
                        tuple(dict.fromkeys(evidence)),
                        score=None,
                        confidence_kind="none",
                        issues=tuple(
                            dict.fromkeys((*segment.issues, "lexical_match_requires_review"))
                        ),
                        basis="lexical_match",
                    )
                )
        # A task may span multiple sections/pages. Merge its topic proposal while
        # retaining every actual occurrence as separate evidence.
        merged: dict[tuple[str, str, object, str], LinkDraft] = {}
        for link in links:
            key = (link.subject_kind, link.subject_key, link.topic_id, link.relation_type)
            previous = merged.get(key)
            if previous:
                link = LinkDraft(
                    link.subject_kind,
                    link.subject_key,
                    link.topic_id,
                    link.relation_type,
                    link.reason,
                    tuple(dict.fromkeys((*previous.evidence, *link.evidence))),
                    link.score,
                    link.confidence_kind,
                    tuple(dict.fromkeys((*previous.issues, *link.issues))),
                    link.basis,
                )
            merged[key] = link
        return AnalysisSuggestions(tuple(merged.values()))
