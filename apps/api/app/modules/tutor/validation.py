"""Shared structural checks, kept separate from future semantic evidence review."""

from __future__ import annotations

import re
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from .contracts import LLMDraft, Mode


def citation_contract_issues(draft: LLMDraft, permitted_ids, math_check_ids, mode):
    permitted, checks = set(map(str, permitted_ids)), set(map(str, math_check_ids))
    issues = []
    for block in draft.blocks:
        ids = set(map(str, block.citation_ids))
        if block.kind == "source_content" and not ids:
            issues.append("source_block_without_citation")
        if not ids <= permitted:
            issues.append("citation_outside_fixed_context")
        if mode == Mode.SOURCE_MODE and block.kind == "model_knowledge":
            issues.append("model_knowledge_in_source_mode")
        if not set(block.math_check_ids) <= checks:
            issues.append("unknown_math_check_reference")
        if re.search(
            r"\b(?:Seite|pages?|S\.|Kapitel|chapters?|Abschnitt|sections?|Gleichung|equations?|Aufgabe|exercises?)\s*\(?\d+",
            block.text,
            re.IGNORECASE,
        ):
            issues.append("unstructured_numeric_locator")
    return list(dict.fromkeys(issues))


class SemanticSupportAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["not_checked", "supported", "unsupported", "inconclusive"] = "not_checked"
    method: Literal["not_checked", "rule", "model_judgment", "human_review"] = "not_checked"
    rationale: str = "Structural citation integrity does not establish semantic support."
    independent_scientific_proof: Literal[False] = False


class SemanticEvidenceChecker(Protocol):
    def check(self, claim: str, evidence: list[dict]) -> SemanticSupportAssessment: ...


class NotCheckedEvidenceChecker:
    """Explicit default; no hidden model call or invented semantic verdict."""

    def check(self, claim, evidence):
        return SemanticSupportAssessment()
