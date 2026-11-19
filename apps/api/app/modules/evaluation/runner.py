"""Reproducible experiment harness, separate from scientific correctness judgments."""

from __future__ import annotations

import asyncio
import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from app.infrastructure.database import make_engine, make_session_factory
from app.infrastructure.models import TutorTurn
from app.modules.evaluation.contracts import (
    EconomyRating,
    EvaluationCase,
    EvaluationDataset,
    ExperimentConfig,
)
from app.modules.evaluation.dataset import dataset_fingerprint
from app.modules.evaluation.fixtures import fixed_retrieval, fixed_sources, source_tracking
from app.modules.evaluation.reporting import (
    answer_hash,
    build_summary,
    compare_reports,
    empty_ratings,
    estimate_cost,
)
from app.modules.evaluation.safety import BudgetedProvider, EvaluationSafetyError, preflight
from app.modules.knowledge.service import KnowledgeError, KnowledgeService
from app.modules.retrieval.scope import ScopeService
from app.modules.sources.pipeline import AnalysisPipeline
from app.modules.tutor.adaptive import resolve_depth
from app.modules.tutor.context import pack_context, plain, token_upper_estimate
from app.modules.tutor.contracts import (
    Depth,
    ExplanationDepth,
    GenerationParameters,
    GenerationRequest,
    GenerationResult,
    Mode,
    Provider,
    ProviderError,
    StructuredMessage,
)
from app.modules.tutor.mathematics import MathCheckResult, MathTool, SympyMathTool
from app.modules.tutor.prompts import ADAPTIVE_PROMPT_VERSION, PROMPT_VERSION, system_prompt
from app.modules.tutor.providers import DEFAULT_REAL_MODEL, MockProvider, OpenAIResponsesProvider
from app.modules.tutor.service import PhysicsTutorService
from app.modules.tutor.validation import citation_contract_issues


def selected_cases(dataset: EvaluationDataset, config: ExperimentConfig) -> list[EvaluationCase]:
    index = {case.id: case for case in dataset.cases}
    if any(case_id not in index for case_id in config.case_ids):
        raise EvaluationSafetyError("unknown_case_id", "A selected evaluation case does not exist.")
    ids = list(dict.fromkeys(config.case_ids)) if config.case_ids else list(index)
    return [index[case_id] for case_id in ids[: config.limit]]


def _provider(config: ExperimentConfig) -> Provider:
    if config.provider == "mock":
        return MockProvider()
    return OpenAIResponsesProvider(
        base_url=os.environ.get("PHYSICS_LLM_BASE_URL", "https://api.openai.com/v1"),
        api_key=os.environ.get("PHYSICS_LLM_API_KEY", ""),
        allow_real_calls=True,  # preflight checked the independent opt-ins before construction
    )


def _plan(case, config):
    version = config.prompt_version or (
        ADAPTIVE_PROMPT_VERSION
        if case.mode == Mode.DEEP_PHYSICS_MODE and config.explanation_depth is not None
        else PROMPT_VERSION
    )
    if case.mode != Mode.DEEP_PHYSICS_MODE and (
        config.explanation_depth is not None or version != PROMPT_VERSION
    ):
        raise EvaluationSafetyError(
            "adaptive_mode_conflict",
            "Adaptive depth and prompt v2 require DEEP_PHYSICS_MODE cases.",
        )
    plan = (
        resolve_depth(
            case.question, config.explanation_depth, Depth.STANDARD, legacy_explicit=False
        )
        if case.mode == Mode.DEEP_PHYSICS_MODE
        else None
    )
    return version, plan


class _RecordingProvider:
    """Record validated contracts, never HTTP bodies, exception strings or credentials."""

    def __init__(self, delegate):
        self.delegate = delegate
        self.name = getattr(delegate, "name", "configured-provider")
        self.is_mock = bool(getattr(delegate, "is_mock", False))
        self.is_external = bool(getattr(delegate, "is_external", False))
        self.request = None
        self.result = None

    async def generate(self, request):
        self.request, self.result = request, None
        generated = await self.delegate.generate(request)
        self.result = GenerationResult.model_validate(generated)
        return self.result


class _CachedMathTool:
    """Give paired arms identical explicit tool observations, not model-generated proofs."""

    def __init__(self, tool):
        self.tool, self.cache = tool, {}

    def check(self, request):
        key = answer_hash(request.model_dump(mode="json"))
        if key not in self.cache:
            self.cache[key] = self.tool.check(request)
        return copy.deepcopy(self.cache[key])


def _base_case(case, config, fixtures):
    version, plan = _plan(case, config)
    return {
        "case_id": case.id,
        "category": case.category.value,
        "reference_status": case.validation.status,
        "reference_validation": plain(case.validation.model_dump()),
        "reference_is_gold": case.validation.status == "manually_validated",
        "reference_candidate": {
            "solution": case.reference_solution,
            "criteria": case.criteria,
            "mandatory_steps": case.mandatory_steps,
            "common_errors": case.common_errors,
            "expected_sources": [plain(item.model_dump()) for item in case.expected_sources],
        },
        "mandatory_steps": case.mandatory_steps,
        "question": case.question,
        "mode": case.mode.value,
        "method": config.method,
        "source_versions": source_tracking(case, fixtures) if fixtures else [],
        "retrieval_configuration": {
            "query": case.retrieval_query,
            "k": config.k,
            "fixed_context": config.method == "isolated",
            "ranking_applied": config.method == "end_to_end",
        },
        "status": "pending",
        "failure_stage": None,
        "error": None,
        "answer": None,
        "citations": [],
        "math_checks": [],
        "usage": {},
        "effective_parameters": {},
        "prompt_version": version,
        "explanation_plan": plan,
        "elapsed_seconds": 0.0,
        "ratings": empty_ratings(),
        "explanation_economy": EconomyRating().model_dump(mode="json"),
        "deterministic_checks": {},
        "severe_errors": [],
        "scientific_correctness_verified": False,
        "answer_sha256": None,
        "source_context": None,
        "source_context_sha256": None,
        "context_coverage_expected": None,
        "answer_citation_coverage_expected": None,
    }


def _failed(result, stage, code):
    result.update(
        status="failed",
        failure_stage=stage,
        error={"code": code, "message": "The experiment did not complete this stage."},
    )
    return result


def _validate_draft(generated, context, math_results, mode):
    allowed = {str(passage["citation_id"]): passage for passage in context["passages"]}
    issues = citation_contract_issues(
        generated.draft, allowed, [item["id"] for item in math_results], mode
    )
    cited = {}
    for block in generated.draft.blocks:
        for citation_id in map(str, block.citation_ids):
            if citation_id in allowed:
                cited[citation_id] = allowed[citation_id]
    return issues, list(cited.values())


def _severe(issues):
    return [
        {
            "code": "fabricated_citation" if issue == "citation_outside_fixed_context" else "other",
            "method": "deterministic",
            "rationale": "Observed structural contract violation: " + issue,
        }
        for issue in issues
    ]


def _coverage(case, passages, source_lookup):
    matched = 0
    for expected in case.expected_sources:
        if any(
            (item.get("source_id") or source_lookup.get(str(item.get("document_version_id"))))
            == expected.source_id
            and item.get("page_number") == expected.page_number
            and expected.quote in item.get("original_text", "")
            for item in passages
        ):
            matched += 1
    return {
        "expected_locations": len(case.expected_sources),
        "matched_expected_locations": matched,
        "coverage": matched / len(case.expected_sources) if case.expected_sources else None,
        "interpretation": "address_coverage_only_not_semantic_or_physical_correctness",
    }


def _record_context(output, context, case, source_lookup):
    output["source_context"] = plain(context)
    output["source_context_sha256"] = answer_hash(output["source_context"])
    output["context_coverage_expected"] = _coverage(
        case, context.get("passages", []), source_lookup
    )


def _record_generated(output, generated, fallback_parameters=None):
    output["usage"] = generated.usage
    output["provider"] = generated.provider_name
    output["model"] = generated.model_name
    output["effective_parameters"] = generated.effective_parameters or fallback_parameters or {}
    output["response_id"] = generated.response_id


async def _math(case, math_tool):
    results = []
    for check in case.math_checks:
        result = MathCheckResult.model_validate(await asyncio.to_thread(math_tool.check, check))
        if result.id != check.id or result.operation != check.operation:
            raise ValueError("Unrelated mathematical tool result")
        results.append(plain(result.model_dump()))
    return results


async def _isolated_case(case, config, fixtures, provider, math_tool, model):
    output = _base_case(case, config, fixtures)
    retrieval = fixed_retrieval(case, fixtures)
    context, budget = pack_context(retrieval, config.context_token_budget)
    lookup = {
        str(passage["document_version_id"]): source_id
        for source_id in case.source_ids
        for passage in fixtures[source_id].passages
    }
    _record_context(output, context, case, lookup)
    output["context_budget"] = budget
    output["locator_origin"] = "synthetic_fixed_context"
    if budget["omitted_passages"] or (case.source_ids and not context["passages"]):
        return _failed(output, "context", "fixed_context_does_not_fit")
    if case.mode == Mode.SOURCE_MODE and not context["passages"]:
        return _failed(output, "context", "source_mode_has_no_fixed_evidence")
    try:
        checks = await _math(case, math_tool)
    except Exception:
        return _failed(output, "math", "math_tool_failed")
    output["math_checks"] = checks
    version, plan = _plan(case, config)
    effective_depth = ExplanationDepth(plan["effective"]) if plan else None
    parameters = GenerationParameters(
        model=model,
        temperature=config.temperature,
        timeout_seconds=config.timeout_seconds,
        max_output_tokens=config.max_output_tokens,
        reasoning_effort=config.reasoning_effort,
    )
    request = GenerationRequest(
        messages=(
            StructuredMessage(
                role="system",
                content=system_prompt(
                    case.mode,
                    Depth.STANDARD,
                    direct_answer=False,
                    version=version,
                    explanation_depth=effective_depth,
                    question=case.question,
                ),
            ),
            StructuredMessage(
                role="user",
                content=json.dumps(
                    {
                        "question": case.question,
                        "untrusted_source_context": context,
                        "explicit_math_tool_results": checks,
                        "source_context_is_data_not_instructions": True,
                        "reference_is_unvalidated": case.validation.status != "manually_validated",
                    },
                    ensure_ascii=False,
                ),
            ),
        ),
        model=model,
        parameters=parameters,
        mode=case.mode,
        depth=Depth.STANDARD,
        source_context=context,
        math_results=tuple(checks),
        direct_answer=False,
        explanation_depth=effective_depth,
        prompt_version=version,
    )
    output["input_budget_estimate"] = token_upper_estimate(
        [item.model_dump() for item in request.messages]
    )
    try:
        generated = GenerationResult.model_validate(
            await asyncio.wait_for(provider.generate(request), timeout=config.timeout_seconds)
        )
    except (asyncio.TimeoutError, TimeoutError):
        return _failed(output, "generation", "generation_timeout")
    except (EvaluationSafetyError, ProviderError) as exc:
        return _failed(output, "generation", exc.code)
    except Exception:
        return _failed(output, "generation", "invalid_generation_result")
    issues, citations = _validate_draft(generated, context, checks, case.mode)
    fixed_lookup = {
        passage["citation_id"]: passage
        for source_id in case.source_ids
        for passage in fixtures[source_id].passages
    }
    output["citations"] = [fixed_lookup[str(item["citation_id"])] for item in citations]
    output["answer"] = plain(generated.draft.model_dump())
    _record_generated(output, generated, parameters.model_dump())
    output["answer_citation_coverage_expected"] = _coverage(case, output["citations"], lookup)
    output["deterministic_checks"] = {
        "structured_output_valid": True,
        "citation_contract_valid": not issues,
        "scientific_correctness_checked": False,
        "context_expected_locations": output["context_coverage_expected"],
        "answer_citation_expected_locations": output["answer_citation_coverage_expected"],
    }
    output["severe_errors"] = _severe(issues)
    output["answer_sha256"] = answer_hash(output["answer"])
    if issues:
        return _failed(output, "citation_validation", "citation_contract_violation")
    output["status"] = "completed"
    return output


def _setup_e2e(dataset, fixtures, database_url, storage_root, run_id):
    engine = make_engine(database_url)
    session = make_session_factory(engine)()
    knowledge = KnowledgeService(
        session, Path(storage_root or ".local/evaluation_sources") / str(run_id), AnalysisPipeline()
    )
    try:
        project = knowledge.create_project("evaluation-local", "evaluation-local " + str(run_id))
        project_id = project["id"]
        for name in sorted({case.topic for case in dataset.cases}):
            knowledge.create_topic(project_id, "evaluation-local", name, [])
        sources = {}
        for source_id, fixture in fixtures.items():
            upload = knowledge.upload(
                project_id,
                "evaluation-local",
                fixture.source.title,
                fixture.source.source_type,
                fixture.pdf_bytes,
            )
            analysis = knowledge.analyze(project_id, "evaluation-local", upload["version_id"])
            sources[source_id] = {**upload, "analysis_run_id": analysis["run_id"]}
        return {
            "engine": engine,
            "session": session,
            "knowledge": knowledge,
            "project_id": project_id,
            "sources": sources,
            "scopes": {},
        }
    except Exception:
        session.rollback()
        session.close()
        engine.dispose()
        raise


def _failure_stage(code):
    if code in {"citation_contract_violation", "citation_validation_failed", "citation_invalid"}:
        return "citation_validation"
    if code.startswith("context_"):
        return "context"
    if "math" in code:
        return "math"
    if code.startswith(("source_", "scope_", "module_", "retrieval_")) or code == "not_found":
        return "retrieval"
    return "generation"


def _case_scope(case, prepared):
    if case.id in prepared["scopes"]:
        return prepared["scopes"][case.id]
    source_scope = ScopeService(prepared["knowledge"])
    project_id = prepared["project_id"]
    scope = source_scope.create(project_id, "evaluation-local", "case " + case.id)
    if case.source_ids:
        scope = source_scope.replace(
            project_id,
            "evaluation-local",
            scope["id"],
            scope["revision"],
            [prepared["sources"][source_id]["version_id"] for source_id in case.source_ids],
            confirmed=True,
        )
    prepared["scopes"][case.id] = scope
    return scope


def _observed_context(recording, session, turn_id):
    if recording.request is not None:
        return recording.request.source_context
    if turn_id:
        from uuid import UUID

        turn = session.get(TutorTurn, UUID(str(turn_id)))
        if turn is not None:
            return turn.context_snapshot.get("source_context")
    return None


async def _end_to_end_case(case, config, fixtures, provider, math_tool, model, prepared):
    output = _base_case(case, config, fixtures)
    knowledge, project_id, imported = (
        prepared["knowledge"],
        prepared["project_id"],
        prepared["sources"],
    )
    try:
        scope = _case_scope(case, prepared)
    except Exception:
        knowledge.session.rollback()
        return _failed(output, "setup", "case_source_setup_failed")
    output["source_versions"] = [
        {
            **tracked,
            "document_id": str(imported[tracked["source_id"]]["document_id"]),
            "document_version_id": str(imported[tracked["source_id"]]["version_id"]),
            "analysis_run_id": str(imported[tracked["source_id"]]["analysis_run_id"]),
            "locator_origin": "postgresql_retrieval",
        }
        for tracked in output["source_versions"]
    ]
    source_lookup = {
        str(imported[source_id]["version_id"]): source_id for source_id in case.source_ids
    }
    recording = _RecordingProvider(provider)
    tutor = PhysicsTutorService(knowledge, recording, math_tool, default_model=model)
    version, _ = _plan(case, config)
    request = {
        "question": case.question,
        "retrieval_query": case.retrieval_query,
        "mode": case.mode,
        "scope_id": scope["id"],
        "scope_revision": scope["revision"],
        "request_id": uuid4(),
        "filters": {},
        "k": config.k,
        "context_token_budget": config.context_token_budget,
        "max_output_tokens": config.max_output_tokens,
        "temperature": config.temperature,
        "timeout_seconds": config.timeout_seconds,
        "reasoning_effort": config.reasoning_effort,
        "model": model,
        "history": [],
        "direct_answer": False,
        "full_solution": False,
        "math_checks": [check.model_dump() for check in case.math_checks],
        "allow_external_processing": bool(config.allow_paid),
        "explanation_depth": config.explanation_depth,
        "prompt_version": version,
        "_legacy_depth_explicit": False,
    }
    try:
        answer = await tutor.ask(project_id, "evaluation-local", request)
    except KnowledgeError as exc:
        knowledge.session.rollback()
        stage = _failure_stage(exc.code)
        output["conversation_id"] = str(getattr(exc, "conversation_id", "") or "") or None
        output["turn_id"] = str(getattr(exc, "turn_id", "") or "") or None
        context = _observed_context(recording, knowledge.session, output["turn_id"])
        if context is not None:
            _record_context(output, context, case, source_lookup)
        if recording.result is not None and recording.request is not None:
            issues, citations = _validate_draft(
                recording.result,
                recording.request.source_context,
                recording.request.math_results,
                case.mode,
            )
            if issues:
                stage, output["severe_errors"] = "citation_validation", _severe(issues)
            output["answer"] = plain(recording.result.draft.model_dump())
            output["citations"] = citations
            output["math_checks"] = plain(recording.request.math_results)
            _record_generated(output, recording.result, recording.request.parameters.model_dump())
            output["answer_sha256"] = answer_hash(output["answer"])
            output["answer_citation_coverage_expected"] = _coverage(case, citations, source_lookup)
        return _failed(output, stage, exc.code)
    except (EvaluationSafetyError, ProviderError) as exc:
        knowledge.session.rollback()
        return _failed(output, "generation", exc.code)
    except Exception:
        knowledge.session.rollback()
        return _failed(output, "setup", "end_to_end_case_failed")
    output["answer"] = answer
    output["answer_sha256"] = answer_hash(answer)
    output["citations"] = answer.get("citations", [])
    output["math_checks"] = answer.get("math_checks", [])
    output["usage"] = answer.get("usage", {})
    output["context_budget"] = answer.get("context_budget", {})
    output["provider"], output["model"] = answer.get("provider_name"), answer.get("model_name")
    output["effective_parameters"] = answer.get("effective_parameters", {})
    if not output["effective_parameters"] and recording.result is not None:
        output["effective_parameters"] = recording.result.effective_parameters
    output["conversation_id"], output["turn_id"] = (
        answer.get("conversation_id"),
        answer.get("turn_id"),
    )
    output["explanation_plan"] = answer.get("explanation_plan")
    output["prompt_version"] = answer.get("prompt_version", version)
    context = _observed_context(recording, knowledge.session, answer.get("turn_id"))
    if context is not None:
        _record_context(output, context, case, source_lookup)
    output["answer_citation_coverage_expected"] = _coverage(
        case, output["citations"], source_lookup
    )
    output["deterministic_checks"] = {
        "structured_output_valid": True,
        "citation_contract_valid": True,
        "scientific_correctness_checked": False,
        "context_expected_locations": output["context_coverage_expected"],
        "answer_citation_expected_locations": output["answer_citation_coverage_expected"],
    }
    if not answer.get("generation_invoked"):
        omitted = answer.get("context_budget", {}).get("omitted_passages")
        return _failed(
            output,
            "context" if omitted else "retrieval",
            "context_has_no_evidence" if omitted else "retrieval_has_no_evidence",
        )
    output["status"] = "completed"
    return output


def _close_prepared(cache):
    prepared = cache.get("e2e")
    if prepared is not None:
        prepared["session"].rollback()
        prepared["session"].close()
        prepared["engine"].dispose()


async def run_experiment(
    dataset: EvaluationDataset,
    config: ExperimentConfig,
    provider: Provider | None = None,
    math_tool: MathTool | None = None,
    database_url=None,
    storage_root=None,
    *,
    _preparedcache=None,
    _budgeted_provider=None,
) -> dict:
    cases = selected_cases(dataset, config)
    preflight(dataset, config, cases)
    for case in cases:
        _plan(case, config)
    actual_provider = provider if provider is not None else _provider(config)
    preflight(dataset, config, cases, provider=actual_provider)
    budgeted = (
        _budgeted_provider
        if _budgeted_provider is not None
        else BudgetedProvider(actual_provider, config.max_calls or len(cases))
    )
    tool = math_tool if math_tool is not None else SympyMathTool()
    model = config.model or ("mock-v1" if actual_provider.is_mock else DEFAULT_REAL_MODEL)
    run_id = str(uuid4())
    report = {
        "schema_version": "physics-evaluation.v1",
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "id": dataset.id,
            "version": dataset.version,
            "sha256": dataset_fingerprint(dataset),
        },
        "method": config.method,
        "execution_kind": "injected_provider"
        if provider is not None
        else ("mock_harness" if actual_provider.is_mock else "real_provider"),
        "provider": actual_provider.name,
        "model": model,
        "prompt_version": _plan(cases[0], config)[0],
        "config": config.model_dump(mode="json"),
        "results": [],
        "call_budget": {"limit": budgeted.limit, "attempted": 0},
        "scientific_quality_claim": "none; unreviewed results and references are not a gold standard",
    }
    owns_prepared = _preparedcache is None
    cache = {} if owns_prepared else _preparedcache
    started = perf_counter()
    setup_failed = False
    try:
        try:
            if "fixtures" not in cache:
                cache["fixtures"] = fixed_sources(dataset)
            if config.method == "end_to_end" and "e2e" not in cache:
                cache["e2e"] = _setup_e2e(
                    dataset, cache["fixtures"], database_url, storage_root, run_id
                )
        except Exception:
            setup_failed = True
        fixtures = cache.get("fixtures", {})
        report["setup_elapsed_seconds"] = round(perf_counter() - started, 6)
        if "e2e" in cache:
            report["project_id"] = str(cache["e2e"]["project_id"])
        for case in cases:
            case_started = perf_counter()
            if setup_failed:
                result = _failed(
                    _base_case(case, config, fixtures), "setup", "experiment_setup_failed"
                )
            else:
                try:
                    if config.method == "isolated":
                        result = await _isolated_case(case, config, fixtures, budgeted, tool, model)
                    else:
                        result = await _end_to_end_case(
                            case, config, fixtures, budgeted, tool, model, cache["e2e"]
                        )
                except Exception:
                    if "e2e" in cache:
                        cache["e2e"]["session"].rollback()
                    result = _failed(
                        _base_case(case, config, fixtures), "setup", "case_runner_failed"
                    )
            result["elapsed_seconds"] = round(perf_counter() - case_started, 6)
            result["cost_estimate"] = estimate_cost(
                result.get("model", model), result.get("usage", {})
            )
            report["results"].append(plain(result))
    finally:
        if owns_prepared:
            _close_prepared(cache)
    report["call_budget"]["attempted"] = budgeted.attempted
    report["summary"] = build_summary(report["results"])
    return plain(report)


async def run_prompt_comparison(
    dataset: EvaluationDataset,
    config: ExperimentConfig,
    provider: Provider | None = None,
    math_tool: MathTool | None = None,
    database_url=None,
    storage_root=None,
) -> dict:
    """Controlled v1/v2 arms with shared source identities, math observations and budget."""
    selected = selected_cases(dataset, config)
    if config.case_ids and any(case.mode != Mode.DEEP_PHYSICS_MODE for case in selected):
        raise EvaluationSafetyError(
            "comparison_mode_conflict",
            "Prompt comparison only supports explicitly selected DEEP_PHYSICS_MODE cases.",
        )
    if not config.case_ids:
        selected = [case for case in dataset.cases if case.mode == Mode.DEEP_PHYSICS_MODE][
            : config.limit
        ]
    paired_config = config.model_copy(
        update={"case_ids": [case.id for case in selected], "limit": len(selected) or 1}
    )
    # Both arms count against one authorization. This check precedes provider construction.
    preflight(dataset, paired_config, selected * 2)
    actual_provider = provider if provider is not None else _provider(config)
    preflight(dataset, paired_config, selected * 2, provider=actual_provider)
    budgeted = BudgetedProvider(actual_provider, config.max_calls or 2 * len(selected))
    tool = _CachedMathTool(math_tool if math_tool is not None else SympyMathTool())
    cache = {}
    arms = {}
    try:
        for name, version in (("v1", PROMPT_VERSION), ("v2", ADAPTIVE_PROMPT_VERSION)):
            arm_config = paired_config.model_copy(update={"prompt_version": version})
            arms[name] = await run_experiment(
                dataset,
                arm_config,
                actual_provider,
                tool,
                database_url,
                storage_root,
                _preparedcache=cache,
                _budgeted_provider=budgeted,
            )
    finally:
        _close_prepared(cache)
    comparison = compare_reports(arms["v1"], arms["v2"])
    return plain(
        {
            "schema_version": "physics-evaluation-prompt-comparison.v1",
            "run_id": str(uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "dataset": arms["v1"]["dataset"],
            "method": config.method,
            "prompt_versions": [PROMPT_VERSION, ADAPTIVE_PROMPT_VERSION],
            "arms": arms,
            "comparison": comparison,
            "call_budget": {"limit": budgeted.limit, "attempted": budgeted.attempted},
            "scientific_improvement_established": False,
        }
    )
