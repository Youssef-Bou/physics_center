"""Paid-call authorization and attempt budgets, independent of scientific scoring."""

import asyncio
import os

from app.modules.tutor.contracts import ProviderError


class EvaluationSafetyError(ValueError):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def is_ci():
    return os.environ.get("CI", "").strip().lower() not in {"", "0", "false", "no"}


def preflight(dataset, config, cases, provider=None):
    if not cases:
        raise EvaluationSafetyError("no_cases", "Select at least one known case.")
    known = {case.id for case in dataset.cases}
    if set(config.case_ids) - known or len(config.case_ids) != len(set(config.case_ids)):
        raise EvaluationSafetyError("invalid_case_selection", "Case IDs must be known and unique.")
    if config.provider == "mock":
        if provider is not None and getattr(provider, "is_external", False):
            raise EvaluationSafetyError(
                "provider_mismatch", "Mock configuration cannot execute an external provider."
            )
        return
    if is_ci():
        raise EvaluationSafetyError(
            "real_calls_forbidden_in_ci", "Real model evaluations are disabled in CI."
        )
    if not config.allow_paid or os.environ.get("PHYSICS_LLM_ENABLE_REAL") != "1":
        raise EvaluationSafetyError(
            "real_calls_not_authorized",
            "Real evaluation requires --allow-paid and PHYSICS_LLM_ENABLE_REAL=1.",
        )
    if config.max_calls is None or not 1 <= config.max_calls <= 10:
        raise EvaluationSafetyError(
            "call_budget_required", "Explicitly set a real-call budget between 1 and 10."
        )
    if len(cases) > config.max_calls:
        raise EvaluationSafetyError(
            "call_budget_insufficient", "Select no more cases than the explicit call budget."
        )
    selected_sources = {source_id for case in cases for source_id in case.source_ids}
    sources = [source for source in dataset.sources if source.id in selected_sources]
    if any(not source.external_use_allowed for source in sources):
        raise EvaluationSafetyError(
            "source_not_authorized", "A selected source is not authorized for external processing."
        )
    if not config.allow_unvalidated and (
        any(case.validation.status != "manually_validated" for case in cases)
        or any(source.physical_review.status != "manually_validated" for source in sources)
    ):
        raise EvaluationSafetyError(
            "unvalidated_references",
            "References are not independently validated; exploratory real runs require --allow-unvalidated and remain ineligible as a gold benchmark.",
        )


class BudgetedProvider:
    """Count attempts before dispatch, including failures. Never automatically retry."""

    def __init__(self, provider, limit):
        if not isinstance(limit, int) or limit < 1:
            raise EvaluationSafetyError("invalid_budget", "Call limit must be a positive integer.")
        self.provider, self.limit, self.attempted = provider, limit, 0
        self.name, self.is_mock, self.is_external = (
            provider.name,
            provider.is_mock,
            provider.is_external,
        )
        self._lock = asyncio.Lock()

    async def generate(self, request):
        async with self._lock:
            if self.attempted >= self.limit:
                raise ProviderError("budget_exhausted", "The experiment call budget is exhausted.")
            self.attempted += 1
        return await self.provider.generate(request)
