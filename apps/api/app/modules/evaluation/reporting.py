"""Experiment tracking without invented scientific scores or cost observations."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from .contracts import Criterion, EconomyRating, Rating, SevereError

REPORT_SCHEMA = "physics-evaluation.v1"
PRICING = {
    "model": "gpt-6.1-sol",
    "currency": "USD",
    "as_of": "2026-11-16",
    "source": "https://developers.openai.com/api/docs/models/gpt-6.1-sol",
    "per_million": {
        "uncached_input": 2.0,
        "cached_input": 0.10,
        "cache_write": 2.50,
        "output": 10.0,
    },
}


def empty_ratings():
    return [Rating(criterion=criterion).model_dump(mode="json") for criterion in Criterion]


def answer_hash(answer):
    return hashlib.sha256(
        json.dumps(
            answer, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")
        ).encode()
    ).hexdigest()


def answer_content_hash(answer):
    """Compare actual answer content, excluding per-run IDs and server metadata."""
    if isinstance(answer, dict) and isinstance(answer.get("blocks"), list):
        content = {
            "blocks": [
                {key: block.get(key) for key in ("kind", "text", "citation_ids", "math_check_ids")}
                for block in answer["blocks"]
            ],
            "uncertainties": answer.get(
                "uncertainties", answer.get("quality", {}).get("uncertainties", [])
            ),
            "math_claims": answer.get("math_claims", []),
        }
        return answer_hash(content)
    return answer_hash(answer)


def estimate_cost(model, usage):
    output = {
        "estimated_usd": None,
        "pricing_snapshot": PRICING,
        "reason": None,
        "is_invoice": False,
    }
    if model != PRICING["model"]:
        return {**output, "reason": "no_verified_price_for_model"}
    if not isinstance(usage, dict) or any(
        not isinstance(usage.get(key), int) or isinstance(usage[key], bool) or usage[key] < 0
        for key in ("input_tokens", "output_tokens")
    ):
        return {**output, "reason": "actual_token_usage_unavailable"}
    cached, writes = usage.get("cached_input_tokens", 0), usage.get("cache_write_tokens", 0)
    if (
        not all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in (cached, writes)
        )
        or cached + writes > usage["input_tokens"]
    ):
        return {**output, "reason": "unsupported_usage_breakdown"}
    rates = PRICING["per_million"]
    cost = (
        (usage["input_tokens"] - cached - writes) * rates["uncached_input"]
        + cached * rates["cached_input"]
        + writes * rates["cache_write"]
        + usage["output_tokens"] * rates["output"]
    ) / 1_000_000
    return {
        **output,
        "estimated_usd": round(cost, 10),
        "reason": "standard_text_tokens_at_dated_public_rates",
        "limitations": "Reasoning tokens are already part of output_tokens. Excludes taxes, tools, special service tiers and unreported usage; not a bill.",
    }


def build_summary(results):
    references = Counter(result.get("reference_status", "unvalidated") for result in results)
    failures = Counter(
        result.get("failure_stage", "none")
        for result in results
        if result.get("status") != "completed"
    )
    methods = Counter(
        rating.get("method", "not_reviewed")
        for result in results
        for rating in result.get("ratings", [])
    )
    severe = Counter(
        (error.get("code", "other") if isinstance(error, dict) else str(error))
        for result in results
        for error in result.get("severe_errors", [])
    )
    return {
        "cases": len(results),
        "completed_cases": sum(result.get("status") == "completed" for result in results),
        "reference_status_counts": dict(references),
        "failure_stage_counts": dict(failures),
        "rating_method_counts": dict(methods),
        "severe_error_counts": dict(severe),
        "scientific_quality_established": False,
        "interpretation": "Completion and deterministic checks measure the harness. Unvalidated references and model judgments are not independent scientific quality evidence.",
    }


def export_report(report, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError("Refusing to overwrite an existing report; choose a new output path.")
    with path.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        handle.write("\n")
    return path


def load_report(path):
    path = Path(path)
    if path.stat().st_size > 25 * 1024 * 1024:
        raise ValueError("Report exceeds the local size limit.")
    report = json.loads(path.read_text())
    if report.get("schema_version") != REPORT_SCHEMA or not isinstance(report.get("results"), list):
        raise ValueError("Unsupported experiment report format.")
    return report


def compare_reports(left, right):
    identity = ("id", "version", "sha256")
    left_dataset, right_dataset = left.get("dataset", {}), right.get("dataset", {})
    comparable = all(
        left_dataset.get(key) is not None and left_dataset.get(key) == right_dataset.get(key)
        for key in identity
    )
    methods_differ = left.get("method") != right.get("method")
    by_left = {result["case_id"]: result for result in left["results"]}
    by_right = {result["case_id"]: result for result in right["results"]}
    pairs = []
    for case_id in sorted(by_left.keys() & by_right.keys()):
        a, b = by_left[case_id], by_right[case_id]
        context_a, context_b = a.get("source_context_sha256"), b.get("source_context_sha256")
        same_context = bool(context_a and context_b and context_a == context_b)
        keys = (
            "model",
            "reasoning_effort",
            "temperature",
            "timeout_seconds",
            "max_output_tokens",
            "context_token_budget",
            "k",
            "explanation_depth",
        )
        same_parameters = all(
            left.get("config", {}).get(key) == right.get("config", {}).get(key) for key in keys
        )
        same_model = (a.get("model") or left.get("model")) == (b.get("model") or right.get("model"))
        pairs.append(
            {
                "case_id": case_id,
                "left_status": a.get("status"),
                "right_status": b.get("status"),
                "left_failure_stage": a.get("failure_stage"),
                "right_failure_stage": b.get("failure_stage"),
                "answer_changed": answer_content_hash(a.get("answer"))
                != answer_content_hash(b.get("answer")),
                "reference_status": a.get("reference_status", "unvalidated"),
                "ratings_left": a.get("ratings", []),
                "ratings_right": b.get("ratings", []),
                "scientific_improvement_established": False,
                "same_question": a.get("question") == b.get("question"),
                "same_source_context": same_context,
                "same_model_parameters": same_parameters and same_model,
                "controlled_comparison_eligible": comparable
                and not methods_differ
                and same_context
                and same_parameters
                and same_model
                and a.get("question") == b.get("question"),
                "explanation_economy_left": a.get(
                    "explanation_economy", EconomyRating().model_dump()
                ),
                "explanation_economy_right": b.get(
                    "explanation_economy", EconomyRating().model_dump()
                ),
            }
        )
    return {
        "schema_version": "physics-evaluation-comparison.v1",
        "same_dataset": comparable,
        "methods_differ": methods_differ,
        "left_method": left.get("method"),
        "right_method": right.get("method"),
        "warning": "Isolated and end-to-end outcomes are distinct experiments; no scientific improvement is inferred from answer differences or mock runs.",
        "paired_cases": pairs,
        "only_left": sorted(by_left.keys() - by_right.keys()),
        "only_right": sorted(by_right.keys() - by_left.keys()),
    }


def apply_ratings(report, reviews):
    """Attach explicit manual/model judgments to exact answers; never auto-grade prose."""
    report = json.loads(json.dumps(report))
    by_id = {result["case_id"]: result for result in report["results"]}
    if reviews.get("run_id") != report.get("run_id"):
        raise ValueError("Ratings refer to another experiment.")
    for review in reviews.get("reviews", []):
        result = by_id.get(review["case_id"])
        if result is None or review.get("answer_sha256") != answer_hash(result.get("answer")):
            raise ValueError("Ratings must match the exact case answer hash.")
        ratings = [Rating.model_validate(value) for value in review["ratings"]]
        rating_keys = [(rating.criterion, rating.method, rating.reviewer) for rating in ratings]
        if len(set(rating_keys)) != len(ratings):
            raise ValueError("Each criterion/method/reviewer judgment must be unique.")
        coverage = review.get("mandatory_steps_checked", {})
        for rating in ratings:
            if (
                rating.criterion == Criterion.STEPS
                and rating.score is not None
                and rating.score >= 3
            ):
                expected = result.get("mandatory_steps") or result.get(
                    "reference_candidate", {}
                ).get("mandatory_steps", [])
                if not expected or not all(coverage.get(step) is True for step in expected):
                    raise ValueError(
                        "High completeness requires an explicit check of every mandatory mathematical step."
                    )
        # Preserve human, symbolic and model judgments as distinct observations.
        current = {
            (entry["criterion"], entry.get("method", "not_reviewed"), entry.get("reviewer")): entry
            for entry in result.get("ratings", empty_ratings())
        }
        for rating in ratings:
            for key in list(current):
                if key[0] == rating.criterion.value and key[1] == "not_reviewed":
                    del current[key]
            current[(rating.criterion.value, rating.method, rating.reviewer)] = rating.model_dump(
                mode="json"
            )
        result["ratings"] = list(current.values())
        if "severe_errors" in review:
            additions = [
                SevereError.model_validate(value).model_dump(mode="json")
                for value in review["severe_errors"]
            ]
            result["severe_errors"] = [*result.get("severe_errors", []), *additions]
        if "explanation_economy" in review:
            result["explanation_economy"] = EconomyRating.model_validate(
                review["explanation_economy"]
            ).model_dump(mode="json")
        result["mandatory_steps_checked"] = coverage
        result["rating_source"] = "explicit_import_not_automatic_proof"
    report["summary"] = build_summary(report["results"])
    return report
