"""Controlled evaluation-harness checks, without real or paid model requests.

The manifest is a candidate test corpus, not independently validated physics gold.
Passing these tests proves harness behavior and source provenance, not LLM quality.
"""

import asyncio
import copy
import hashlib
import json
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from pypdf import PdfReader

from app.modules.evaluation import cli, runner
from app.modules.evaluation.contracts import (
    Category,
    Criterion,
    EvaluationDataset,
    ExperimentConfig,
    Rating,
)
from app.modules.evaluation.dataset import (
    dataset_fingerprint,
    load_dataset,
    validate_import_manifest,
)
from app.modules.evaluation.fixtures import fixed_sources
from app.modules.evaluation.reporting import (
    PRICING,
    REPORT_SCHEMA,
    answer_hash,
    apply_ratings,
    compare_reports,
    empty_ratings,
    estimate_cost,
    export_report,
    load_report,
)
from app.modules.evaluation.safety import (
    BudgetedProvider,
    EvaluationSafetyError,
    preflight,
)
from app.modules.tutor.contracts import AnswerBlock, GenerationResult, LLMDraft, ProviderError
from app.modules.tutor.mathematics import MathCheckResult

SOURCE_CASES = ["SOURCE_DREHIMPULS", "SOURCE_GAUSS_CLOSED"]


@pytest.fixture
def dataset():
    return load_dataset()


def selected(dataset, ids=SOURCE_CASES):
    by_id = {case.id: case for case in dataset.cases}
    return [by_id[case_id] for case_id in ids]


def authorized_config(**changes):
    values = {
        "provider": "openai_responses",
        "case_ids": [SOURCE_CASES[0]],
        "limit": 1,
        "allow_paid": True,
        "allow_unvalidated": True,
        "max_calls": 1,
    }
    values.update(changes)
    return ExperimentConfig(**values)


def safe_environment(monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("PHYSICS_LLM_ENABLE_REAL", "1")


def candidate_report(dataset, *, method="isolated"):
    green = next(case for case in dataset.cases if case.id == "GREEN_DIRICHLET")
    return {
        "schema_version": REPORT_SCHEMA,
        "run_id": "synthetic-review-run",
        "method": method,
        "dataset": {
            "id": dataset.id,
            "version": dataset.version,
            "sha256": dataset_fingerprint(dataset),
        },
        "config": {"model": "mock-v1", "temperature": 0.2},
        "model": "mock-v1",
        "results": [
            {
                "case_id": green.id,
                "question": green.question,
                "status": "completed",
                "answer": {"blocks": [{"kind": "derivation", "text": "Kernel formula only."}]},
                "reference_status": "unvalidated",
                "reference_candidate": {"mandatory_steps": green.mandatory_steps},
                "ratings": empty_ratings(),
                "severe_errors": [],
                "source_context_sha256": "a" * 64,
                "model": "mock-v1",
            }
        ],
    }


def review_input(report, ratings, **extra):
    result = report["results"][0]
    return {
        "run_id": report["run_id"],
        "reviews": [
            {
                "case_id": result["case_id"],
                "answer_sha256": answer_hash(result["answer"]),
                "ratings": ratings,
                **extra,
            }
        ],
    }


def test_manifest_has_all_categories_without_implicit_expert_gold(dataset):
    assert len(dataset.cases) >= 24
    assert {case.category for case in dataset.cases} == set(Category)
    assert all(case.validation.status == "unvalidated" for case in dataset.cases)
    assert all(source.physical_review.status == "unvalidated" for source in dataset.sources)
    assert all(source.rights_status == "synthetic" for source in dataset.sources)
    sources = {source.id: source for source in dataset.sources}
    for case in dataset.cases:
        assert case.mandatory_steps and case.common_errors and case.prerequisites
        for expected in case.expected_sources:
            assert expected.source_id in case.source_ids
            assert expected.quote in sources[expected.source_id].pages[expected.page_number - 1]


def test_adaptive_patch_preserves_baseline_cases_and_original_source_pages(dataset):
    path = (
        Path(__file__).resolve().parents[1] / "app/modules/evaluation/data/physics_adaptive_v1.json"
    )
    adaptive = load_dataset(path)
    assert adaptive.version == "1.1.1"
    assert len(adaptive.cases) == 29
    assert adaptive.cases[: len(dataset.cases)] == dataset.cases
    sources = {source.id: source for source in adaptive.sources}
    for original in dataset.sources:
        assert sources[original.id].pages[: len(original.pages)] == original.pages
    assert all(case.validation.status == "unvalidated" for case in adaptive.cases)
    assert all(source.physical_review.status == "unvalidated" for source in adaptive.sources)


def test_manifest_fingerprint_is_deterministic_and_tracks_content(dataset, tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(dataset.model_dump(mode="json"), sort_keys=True))
    assert dataset_fingerprint(load_dataset(path)) == dataset_fingerprint(dataset)
    modified = dataset.model_dump(mode="json")
    modified["cases"][0]["question"] += " Explicit changed fixture question."
    assert dataset_fingerprint(EvaluationDataset.model_validate(modified)) != dataset_fingerprint(
        dataset
    )


def test_manifest_rejects_a_fabricated_expected_quote(dataset):
    modified = dataset.model_dump(mode="json")
    case = next(case for case in modified["cases"] if case["expected_sources"])
    case["expected_sources"][0]["quote"] = "THIS_TEXT_IS_NOT_IN_THE_ORIGINAL"
    with pytest.raises(ValidationError):
        EvaluationDataset.model_validate(modified)


def test_green_reference_requires_more_than_the_final_kernel(dataset):
    green = next(case for case in dataset.cases if case.id == "GREEN_DIRICHLET")
    requirements = " ".join(green.mandatory_steps)
    for term in (
        "Operator",
        "Dirichlet",
        "Homogene",
        "Stetigkeit",
        "Sprung",
        "delta",
        "Integraldarstellung",
        "Eindeutigkeit",
        "Dimensionen",
    ):
        assert term.casefold() in requirements.casefold()
    assert "C²-Lösung" in green.reference_solution
    assert "ohne Ränder" in requirements
    assert any("Kernformel" in error for error in green.common_errors)
    assert green.validation.status == "unvalidated"


@pytest.mark.parametrize(
    ("changes", "environment", "code"),
    [
        ({"allow_paid": False}, {}, "real_calls_not_authorized"),
        ({}, {"PHYSICS_LLM_ENABLE_REAL": "0"}, "real_calls_not_authorized"),
        ({}, {"CI": "true"}, "real_calls_forbidden_in_ci"),
        ({"max_calls": None}, {}, "call_budget_required"),
        ({"max_calls": 11}, {}, "call_budget_required"),
        ({"allow_unvalidated": False}, {}, "unvalidated_references"),
    ],
)
def test_real_preflight_requires_each_independent_opt_in(
    dataset, monkeypatch, changes, environment, code
):
    safe_environment(monkeypatch)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(EvaluationSafetyError) as failure:
        preflight(dataset, authorized_config(**changes), selected(dataset)[:1])
    assert failure.value.code == code


def test_real_preflight_enforces_case_budget_and_source_permission(dataset, monkeypatch):
    safe_environment(monkeypatch)
    with pytest.raises(EvaluationSafetyError) as failure:
        preflight(dataset, authorized_config(), selected(dataset))
    assert failure.value.code == "call_budget_insufficient"
    denied = dataset.model_copy(deep=True)
    bound_id = selected(denied)[0].source_ids[0]
    next(source for source in denied.sources if source.id == bound_id).external_use_allowed = False
    with pytest.raises(EvaluationSafetyError) as failure:
        preflight(denied, authorized_config(), selected(denied)[:1])
    assert failure.value.code == "source_not_authorized"


def test_authorized_preflight_itself_makes_no_provider_call(dataset, monkeypatch):
    safe_environment(monkeypatch)
    provider = CountingProvider()
    provider.is_external = True
    preflight(dataset, authorized_config(), selected(dataset)[:1], provider)
    assert provider.calls == 0
    with pytest.raises(EvaluationSafetyError) as failure:
        preflight(dataset, ExperimentConfig(), selected(dataset)[:1], provider)
    assert failure.value.code == "provider_mismatch"


class CountingProvider:
    name = "deterministic-evaluation-double"
    is_mock = True
    is_external = False

    def __init__(self, error=None):
        self.calls = 0
        self.error = error

    async def generate(self, request):
        self.calls += 1
        await asyncio.sleep(0)
        if self.error:
            raise self.error
        return "deterministic test result"


def test_budget_counts_failed_attempts_without_retry():
    provider = CountingProvider(ProviderError("timeout", "controlled timeout"))
    wrapped = BudgetedProvider(provider, 1)

    async def exercise():
        with pytest.raises(ProviderError) as timeout:
            await wrapped.generate(None)
        assert timeout.value.code == "timeout"
        with pytest.raises(ProviderError) as exhausted:
            await wrapped.generate(None)
        assert exhausted.value.code == "budget_exhausted"

    asyncio.run(exercise())
    assert wrapped.attempted == provider.calls == 1


def test_parallel_calls_cannot_exceed_the_attempt_budget():
    provider = CountingProvider()
    wrapped = BudgetedProvider(provider, 2)

    async def exercise():
        return await asyncio.gather(
            *(wrapped.generate(None) for _ in range(7)), return_exceptions=True
        )

    results = asyncio.run(exercise())
    assert wrapped.attempted == provider.calls == 2
    assert (
        sum(
            isinstance(result, ProviderError) and result.code == "budget_exhausted"
            for result in results
        )
        == 5
    )


def test_six_ratings_start_unreviewed_and_have_bounded_scores():
    ratings = empty_ratings()
    assert {rating["criterion"] for rating in ratings} == {
        criterion.value for criterion in Criterion
    }
    assert all(rating["score"] is None and rating["method"] == "not_reviewed" for rating in ratings)
    for score in (-1, 5):
        with pytest.raises(ValidationError):
            Rating(criterion=Criterion.MATHEMATICS, score=score, method="deterministic")


@pytest.mark.parametrize("mismatch", ["run", "answer"])
def test_reviews_are_bound_to_exact_experiment_and_answer(dataset, mismatch):
    report = candidate_report(dataset)
    reviews = review_input(report, [])
    if mismatch == "run":
        reviews["run_id"] = "another-run"
    else:
        reviews["reviews"][0]["answer_sha256"] = "b" * 64
    with pytest.raises(ValueError):
        apply_ratings(report, reviews)


def test_high_green_completeness_requires_each_mandatory_step(dataset):
    report = candidate_report(dataset)
    rating = {
        "criterion": "derivation_completeness",
        "score": 4,
        "method": "manual",
        "reviewer": "synthetic-reviewer",
        "rationale": "Controlled review fixture, not a scientific endorsement.",
    }
    with pytest.raises(ValueError):
        apply_ratings(report, review_input(report, [rating], mandatory_steps_checked={}))
    steps = report["results"][0]["reference_candidate"]["mandatory_steps"]
    incomplete_coverage = {step: True for step in steps}
    incomplete_coverage[steps[-1]] = False
    with pytest.raises(ValueError):
        apply_ratings(
            report, review_input(report, [rating], mandatory_steps_checked=incomplete_coverage)
        )
    stepwise_report = copy.deepcopy(report)
    stepwise_report["results"][0]["answer"] = {
        "blocks": [
            {"kind": "derivation", "text": "Synthetic stepwise fixture:\n" + "\n".join(steps)}
        ]
    }
    checked = apply_ratings(
        stepwise_report,
        review_input(
            stepwise_report, [rating], mandatory_steps_checked={step: True for step in steps}
        ),
    )
    assert any(
        item["criterion"] == "derivation_completeness" and item["score"] == 4
        for item in checked["results"][0]["ratings"]
    )
    assert checked["summary"]["scientific_quality_established"] is False
    assert all(item["score"] is None for item in report["results"][0]["ratings"])


def test_human_and_model_ratings_are_preserved_as_distinct_observations(dataset):
    report = candidate_report(dataset)
    ratings = [
        {
            "criterion": "mathematical_correctness",
            "score": 2,
            "method": "manual",
            "reviewer": "human-fixture",
            "rationale": "Known review input.",
        },
        {
            "criterion": "mathematical_correctness",
            "score": 4,
            "method": "model_judgment",
            "reviewer": "judge-fixture-v1",
            "rationale": "Unvalidated model judgment.",
        },
    ]
    reviewed = apply_ratings(report, review_input(report, ratings))
    observations = [
        item
        for item in reviewed["results"][0]["ratings"]
        if item["criterion"] == "mathematical_correctness"
    ]
    assert {(item["method"], item["reviewer"], item["score"]) for item in observations} == {
        ("manual", "human-fixture", 2),
        ("model_judgment", "judge-fixture-v1", 4),
    }
    assert reviewed["summary"]["scientific_quality_established"] is False


def test_comparison_separates_methods_and_never_infers_quality(dataset):
    isolated = candidate_report(dataset)
    end_to_end = candidate_report(dataset, method="end_to_end")
    comparison = compare_reports(isolated, end_to_end)
    assert comparison["same_dataset"] is True
    assert comparison["methods_differ"] is True
    assert comparison["warning"]
    assert comparison["paired_cases"][0]["controlled_comparison_eligible"] is False
    assert comparison["paired_cases"][0]["scientific_improvement_established"] is False
    missing_context = copy.deepcopy(isolated)
    del missing_context["results"][0]["source_context_sha256"]
    assert (
        compare_reports(isolated, missing_context)["paired_cases"][0]["same_source_context"]
        is False
    )


def test_reports_round_trip_and_refuse_overwrite(dataset, tmp_path):
    report = candidate_report(dataset)
    destination = tmp_path / "reports" / "run.json"
    export_report(report, destination)
    assert load_report(destination) == report
    with pytest.raises(ValueError):
        export_report({**report, "run_id": "overwrite"}, destination)
    assert load_report(destination)["run_id"] == report["run_id"]


def test_cost_estimates_require_observed_usage_and_dated_known_prices():
    assert (
        estimate_cost("mock-v1", {"input_tokens": 100, "output_tokens": 100})["estimated_usd"]
        is None
    )
    assert estimate_cost(PRICING["model"], {})["estimated_usd"] is None
    assert (
        estimate_cost(PRICING["model"], {"input_tokens": -1, "output_tokens": 2})["estimated_usd"]
        is None
    )
    estimate = estimate_cost(
        PRICING["model"],
        {
            "input_tokens": 1_000_000,
            "output_tokens": 100_000,
            "cached_input_tokens": 100_000,
            "cache_write_tokens": 10_000,
        },
    )
    rates = PRICING["per_million"]
    expected = (
        890_000 * rates["uncached_input"]
        + 100_000 * rates["cached_input"]
        + 10_000 * rates["cache_write"]
        + 100_000 * rates["output"]
    ) / 1_000_000
    assert estimate["estimated_usd"] == pytest.approx(expected)
    assert estimate["pricing_snapshot"]["as_of"]
    assert estimate["is_invoice"] is False


def test_local_source_import_checks_hash_and_never_implies_external_permission(
    pdf_factory, tmp_path, capsys
):
    source = tmp_path / "original.pdf"
    source.write_bytes(pdf_factory("Synthetic local source."))
    record = {
        "source_id": "local-fixture",
        "title": "Controlled local PDF",
        "path": source.name,
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "license_note": "Synthetic fixture authored for testing.",
    }
    manifest = tmp_path / "import.json"
    manifest.write_text(json.dumps([record]))
    imported = validate_import_manifest(manifest)
    assert imported[0]["external_use_allowed"] is False
    assert imported[0]["physical_review"] == "unvalidated"
    assert cli.main(["validate-import", str(manifest)]) == 0
    cli_result = json.loads(capsys.readouterr().out)
    assert cli_result["external_calls"] == 0
    assert cli_result["sources"][0]["external_use_allowed"] is False
    source.write_bytes(source.read_bytes() + b"\nchanged")
    with pytest.raises(ValueError):
        validate_import_manifest(manifest)


def test_isolated_mock_run_keeps_candidate_references_and_ratings_unscored(dataset):
    config = ExperimentConfig(case_ids=SOURCE_CASES, limit=2, context_token_budget=16000)
    report = asyncio.run(runner.run_experiment(dataset, config))
    assert report["method"] == "isolated"
    assert len(report["results"]) == 2
    assert report["call_budget"]["attempted"] == 2
    assert report["summary"]["scientific_quality_established"] is False
    for result in report["results"]:
        assert result["status"] == "completed", result.get("error")
        assert result["reference_status"] == "unvalidated"
        assert result["reference_is_gold"] is False
        assert all(rating["score"] is None for rating in result["ratings"])
        assert result["cost_estimate"]["estimated_usd"] is None


def test_end_to_end_runs_use_actual_selected_backend_sources(dataset, database_url, tmp_path):
    config = ExperimentConfig(
        method="end_to_end", case_ids=SOURCE_CASES, limit=2, context_token_budget=16000
    )
    report = asyncio.run(
        runner.run_experiment(dataset, config, database_url=database_url, storage_root=tmp_path)
    )
    assert report["method"] == "end_to_end"
    assert len(report["results"]) == 2
    originals = fixed_sources(dataset)
    for result in report["results"]:
        assert result["status"] == "completed", result.get("error")
        assert result["conversation_id"] and result["turn_id"]
        source_by_version = {
            item["document_version_id"]: item["source_id"] for item in result["source_versions"]
        }
        assert all(
            item["locator_origin"] == "postgresql_retrieval" for item in result["source_versions"]
        )
        assert result["citations"]
        for citation in result["citations"]:
            fixture = originals[source_by_version[citation["document_version_id"]]]
            original = (
                PdfReader(BytesIO(fixture.pdf_bytes))
                .pages[citation["page_number"] - 1]
                .extract_text()
            )
            assert (
                original[citation["start_offset"] : citation["end_offset"]]
                == citation["original_text"]
            )
        assert all(rating["score"] is None for rating in result["ratings"])


class BadCitationProvider:
    name = "bad-citation-evaluation-double"
    is_mock = True
    is_external = False

    async def generate(self, request):
        return GenerationResult(
            draft=LLMDraft(
                blocks=[
                    AnswerBlock(
                        kind="source_content",
                        text="Deliberately unsupported fixture.",
                        citation_ids=[uuid4()],
                    )
                ]
            ),
            provider_name=self.name,
            model_name=request.model,
        )


@pytest.mark.parametrize("method", ["isolated", "end_to_end"])
def test_bad_citation_is_attributed_to_validation_not_scored_as_quality(
    dataset, database_url, tmp_path, method
):
    config = ExperimentConfig(
        method=method, case_ids=[SOURCE_CASES[0]], limit=1, context_token_budget=16000
    )
    report = asyncio.run(
        runner.run_experiment(
            dataset,
            config,
            provider=BadCitationProvider(),
            database_url=database_url,
            storage_root=tmp_path,
        )
    )
    result = report["results"][0]
    assert result["status"] == "failed"
    assert result["failure_stage"] == "citation_validation"
    assert result["severe_errors"]
    assert all(rating["score"] is None for rating in result["ratings"])


def test_provider_exception_details_never_enter_a_report(dataset):
    provider = CountingProvider(RuntimeError("SECRET_SENTINEL_PROVIDER_EXCEPTION_BODY"))
    config = ExperimentConfig(case_ids=[SOURCE_CASES[0]], limit=1, context_token_budget=16000)
    report = asyncio.run(runner.run_experiment(dataset, config, provider=provider))
    result = report["results"][0]
    assert result["status"] == "failed"
    assert result["failure_stage"] == "generation"
    assert "SECRET_SENTINEL_PROVIDER_EXCEPTION_BODY" not in json.dumps(report)
    assert report["call_budget"]["attempted"] == provider.calls == 1


def test_no_retrieval_hits_is_attributed_before_any_model_call(dataset, database_url, tmp_path):
    modified = dataset.model_dump(mode="json")
    case = next(case for case in modified["cases"] if case["id"] == SOURCE_CASES[0])
    case["retrieval_query"] = "UNFINDABLE_SYNTHETIC_RETRIEVAL_QUERY"
    modified = EvaluationDataset.model_validate(modified)
    provider = CountingProvider()
    config = ExperimentConfig(
        method="end_to_end", case_ids=[SOURCE_CASES[0]], limit=1, context_token_budget=16000
    )
    report = asyncio.run(
        runner.run_experiment(
            modified, config, provider=provider, database_url=database_url, storage_root=tmp_path
        )
    )
    result = report["results"][0]
    assert result["status"] == "failed"
    assert result["failure_stage"] == "retrieval"
    assert result["error"]["code"] == "retrieval_has_no_evidence"
    assert result["answer"]["generation_invoked"] is False
    assert report["call_budget"]["attempted"] == provider.calls == 0


def test_critical_errors_and_explanation_economy_require_attributed_review(dataset):
    report = candidate_report(dataset)
    imported = review_input(
        report,
        [],
        severe_errors=[
            {
                "code": "wrong_sign",
                "method": "model_judgment",
                "reviewer": "judge-fixture-v1",
                "rationale": "Synthetic independent model observation, not a proven physical defect.",
            }
        ],
        explanation_economy={
            "score": 2,
            "method": "manual",
            "reviewer": "human-fixture",
            "rationale": "Explicit content review rather than word-count scoring.",
        },
    )
    reviewed = apply_ratings(report, imported)
    assert reviewed["results"][0]["severe_errors"][0]["method"] == "model_judgment"
    assert reviewed["results"][0]["explanation_economy"]["score"] == 2
    assert reviewed["summary"]["severe_error_counts"]["wrong_sign"] == 1
    assert reviewed["summary"]["scientific_quality_established"] is False
    del imported["reviews"][0]["severe_errors"][0]["reviewer"]
    with pytest.raises(ValidationError):
        apply_ratings(report, imported)


def test_mock_cli_run_export_comparison_and_rating_import_are_local(
    dataset, monkeypatch, tmp_path, capsys
):
    def no_database(*args, **kwargs):
        raise AssertionError("The isolated mock CLI must not connect to a database")

    monkeypatch.setattr(runner, "make_engine", no_database)
    output = tmp_path / "run.json"
    assert (
        cli.main(
            [
                "run",
                "--case-id",
                SOURCE_CASES[0],
                "--limit",
                "1",
                "--context-token-budget",
                "16000",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["method"] == "isolated"
    assert summary["summary"]["scientific_quality_established"] is False
    report = load_report(output)
    assert report["call_budget"]["attempted"] == 1
    assert all(rating["score"] is None for rating in report["results"][0]["ratings"])
    copied = tmp_path / "copy.json"
    assert cli.main(["export", str(output), "--output", str(copied)]) == 0
    capsys.readouterr()
    assert load_report(copied) == report
    assert cli.main(["compare", str(output), str(copied)]) == 0
    comparison = json.loads(capsys.readouterr().out)
    assert comparison["same_dataset"] is True
    assert comparison["paired_cases"][0]["scientific_improvement_established"] is False
    reviews_file = tmp_path / "reviews.json"
    reviews_file.write_text(
        json.dumps(
            review_input(
                report,
                [
                    {
                        "criterion": "uncertainty_transparency",
                        "score": 2,
                        "method": "manual",
                        "reviewer": "human-fixture",
                        "rationale": "Controlled CLI review-import fixture.",
                    }
                ],
            )
        )
    )
    reviewed_file = tmp_path / "reviewed.json"
    assert (
        cli.main(["apply-ratings", str(output), str(reviews_file), "--output", str(reviewed_file)])
        == 0
    )
    capsys.readouterr()
    assert any(
        rating["method"] == "manual"
        for rating in load_report(reviewed_file)["results"][0]["ratings"]
    )
    assert all(rating["score"] is None for rating in load_report(output)["results"][0]["ratings"])


def test_cli_lists_candidates_and_refuses_real_execution_before_provider_creation(
    dataset, monkeypatch, capsys, tmp_path
):
    assert cli.main(["list", "--json"]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert len(listing["cases"]) >= 24
    assert listing["scientific_quality_established"] is False
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("PHYSICS_LLM_ENABLE_REAL", raising=False)
    calls = []

    def forbidden(config):
        calls.append(config)
        raise AssertionError("Provider creation must follow safety preflight")

    monkeypatch.setattr(runner, "_provider", forbidden)
    output = tmp_path / "must-not-exist.json"
    assert (
        cli.main(
            [
                "run",
                "--provider",
                "openai_responses",
                "--case-id",
                SOURCE_CASES[0],
                "--limit",
                "1",
                "--output",
                str(output),
            ]
        )
        == 2
    )
    assert calls == []
    assert not output.exists()
    assert "real_calls_not_authorized" in capsys.readouterr().err


class UncheckedMathDouble:
    def __init__(self):
        self.calls = []

    def check(self, request):
        self.calls.append(request)
        return MathCheckResult(
            id=request.id,
            operation=request.operation,
            status="not_checked",
            details="Comparison fixture deliberately skips mathematical computation.",
            method="deterministic-unchecked-test-double",
        )


@pytest.mark.parametrize("method", ["isolated", "end_to_end"])
def test_prompt_comparison_reuses_source_context_and_math_without_inventing_quality(
    dataset, database_url, tmp_path, method
):
    tool = UncheckedMathDouble()
    config = ExperimentConfig(
        method=method,
        case_ids=["GREEN_DIRICHLET", "CON_GAUSS_FLUX"],
        limit=2,
        max_calls=4,
        context_token_budget=16000,
        explanation_depth="AUTO",
    )
    report = asyncio.run(
        runner.run_prompt_comparison(
            dataset, config, math_tool=tool, database_url=database_url, storage_root=tmp_path
        )
    )
    assert report["schema_version"] == "physics-evaluation-prompt-comparison.v1"
    assert report["prompt_versions"] == ["physics-tutor-v1", "physics-tutor-v2"]
    assert report["call_budget"] == {"limit": 4, "attempted": 4}
    assert report["scientific_improvement_established"] is False
    assert len(tool.calls) == 1
    by_arm = {
        name: {result["case_id"]: result for result in arm["results"]}
        for name, arm in report["arms"].items()
    }
    for case_id in config.case_ids:
        before, after = by_arm["v1"][case_id], by_arm["v2"][case_id]
        assert before["status"] == after["status"] == "completed"
        assert before["question"] == after["question"]
        assert before["source_context_sha256"] == after["source_context_sha256"]
        assert before["source_context"] == after["source_context"]
        assert before["prompt_version"] != after["prompt_version"]
        assert before["math_checks"] == after["math_checks"]
        assert all(rating["score"] is None for rating in before["ratings"] + after["ratings"])
        assert after["explanation_economy"]["score"] is None
    assert by_arm["v2"]["GREEN_DIRICHLET"]["explanation_plan"]["effective"] == "RIGOROUS"
    for pair in report["comparison"]["paired_cases"]:
        assert pair["same_question"] is True
        assert pair["same_source_context"] is True
        assert pair["same_model_parameters"] is True
        assert pair["controlled_comparison_eligible"] is True
        assert pair["scientific_improvement_established"] is False


def test_paired_real_budget_counts_both_arms_before_provider_creation(dataset, monkeypatch):
    safe_environment(monkeypatch)
    constructed = []

    def forbidden(config):
        constructed.append(config)
        raise AssertionError("Preflight must reject an insufficient pair budget first")

    monkeypatch.setattr(runner, "_provider", forbidden)
    config = authorized_config(case_ids=["GREEN_DIRICHLET"], max_calls=1)
    with pytest.raises(EvaluationSafetyError) as failure:
        asyncio.run(runner.run_prompt_comparison(dataset, config))
    assert failure.value.code == "call_budget_insufficient"
    assert constructed == []


def test_prompt_comparison_refuses_non_deep_cases(dataset):
    config = ExperimentConfig(case_ids=[SOURCE_CASES[0]], limit=1)
    with pytest.raises(EvaluationSafetyError) as failure:
        asyncio.run(runner.run_prompt_comparison(dataset, config))
    assert failure.value.code == "comparison_mode_conflict"
