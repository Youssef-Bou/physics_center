"""Deterministic context packing. Whole source passages are never cut mid-formula."""

from __future__ import annotations

import json


def plain(value):
    return json.loads(json.dumps(value, default=str, ensure_ascii=False))


def token_upper_estimate(value) -> int:
    # Conservative byte-based budget, NOT an exact provider tokenizer. Exact
    # provider usage, when supplied, is reported separately.
    return len(json.dumps(plain(value), ensure_ascii=False, separators=(",", ":")).encode())


def _bundle(hits, warnings):
    ids = {str(hit["citation_id"]) for hit in hits}
    passages, exercises, exams, topics, prerequisites = [], {}, {}, {}, {}
    for hit in hits:
        passages.append(
            {
                key: hit[key]
                for key in (
                    "citation_id",
                    "segment_id",
                    "document_id",
                    "document_title",
                    "source_type",
                    "document_version_id",
                    "sha256",
                    "analysis_run_id",
                    "page_number",
                    "start_offset",
                    "end_offset",
                    "original_text",
                    "chapter",
                    "issues",
                    "extraction_uncertain",
                    "locator_verified",
                    "scientific_verification",
                )
                if key in hit
            }
        )
        for exercise in hit.get("exercises", []):
            if all(str(member) in ids for member in exercise["segment_ids"]):
                target = exams if exercise["source_type"] == "past_exam" else exercises
                target[str(exercise["id"])] = exercise
        for topic in hit.get("topics", []):
            evidence = [str(item["citation_id"]) for item in topic.get("evidence", [])]
            if evidence and set(evidence) <= ids:
                topics[str(topic["id"])] = {
                    key: topic[key]
                    for key in ("id", "name", "relation_type", "source_link_id", "review_status")
                }
                topics[str(topic["id"])]["evidence_citation_ids"] = evidence
        for relation in hit.get("prerequisites", []):
            evidence = [str(item["citation_id"]) for item in relation.get("evidence", [])]
            if evidence and set(evidence) <= ids:
                prerequisites[str(relation["id"])] = {
                    key: relation[key]
                    for key in (
                        "id",
                        "source_topic",
                        "target_topic",
                        "relation_type",
                        "review_status",
                    )
                }
                prerequisites[str(relation["id"])]["evidence_citation_ids"] = evidence
    return plain(
        {
            "passages": passages,
            "exercises": list(exercises.values()),
            "exam_exercises": list(exams.values()),
            "topics": list(topics.values()),
            "prerequisites": list(prerequisites.values()),
            "warnings": warnings,
        }
    )


def pack_context(retrieval: dict, budget: int):
    hits, omitted = [], 0
    # Unbounded diagnostic strings are not useful model context.
    warnings = retrieval.get("warnings", [])[:20]
    for hit in retrieval.get("hits", []):
        candidate = _bundle([*hits, hit], warnings)
        if token_upper_estimate(candidate) <= budget:
            hits.append(hit)
        else:
            omitted += 1
    context = _bundle(hits, warnings)
    # Even an empty bundle must fit; no silent over-budget payload.
    if token_upper_estimate(context) > budget:
        context = _bundle([], [])
        hits = []
    return context, {
        "limit": budget,
        "estimated_tokens": token_upper_estimate(context),
        "estimator": "utf8_bytes_conservative_proxy",
        "exact_token_count": False,
        "included_passages": len(hits),
        "omitted_passages": omitted,
    }
