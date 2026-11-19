"""Deterministic explanation planning, independent of generation cost or reasoning effort.

The rules are transparent heuristics, not calibrated difficulty estimates. They
only select presentation depth and a whitelist of relevant scientific aspects;
they neither infer facts nor grant access to sources or tools.
"""

import re
import unicodedata

from app.modules.tutor.contracts import Depth, ExplanationDepth

# Order also defines reproducible metadata and presentation order. Labels are
# trusted application text; no user-controlled text enters the system prompt.
ASPECT_LABELS = {
    "problem": "Problem und gesuchte Größen präzisieren",
    "definitions": "benötigte Begriffe und Größen definieren",
    "mathematical_assumptions": "mathematische Voraussetzungen und Definitionsbereiche nennen",
    "equations": "relevante Gleichungen mit Konventionen angeben",
    "derivation": "notwendige prüfbare Herleitungsschritte zeigen",
    "interpretation": "Ergebnis physikalisch interpretieren",
    "validity": "Gültigkeit, Grenzen und Näherungen erläutern",
    "consistency": "Einheiten, Rand- oder Grenzfälle auf Konsistenz prüfen",
    "connections": "begründete fachliche Zusammenhänge herstellen",
}

_PROOF = re.compile(
    r"\b(?:beweis\w*|nachweis\w*|prove|proof|demonstrate)\b|\bzeig\w*\s*,?\s+dass\b"
)
_DERIVATION = re.compile(r"\b(?:herleit\w*|derive|derivation)\b|\bleit\w*\b.{0,100}\bher\b")
_CALCULATION = re.compile(
    r"\b(?:berechn\w*|berechne\w*|bestimm\w*|rechn\w*|rechne\w*|integrier\w*|"
    r"differenzier\w*|calculate|compute|solve|evaluate|löse\w*|loese\w*)\b"
)
_BOUNDARY = re.compile(r"\b(?:randbeding\w*|boundary\s+conditions?)\b")
_ADVANCED_CONTEXT = re.compile(
    r"\b(?:green\w*|delta\w*|distribution\w*|definitionsbereich\w*|domain\w*|"
    r"variation\w*|funktionalanal\w*|sobolev\w*|gegenbeispiel\w*|counterexample\w*)\b|δ"
)
_COUNTEREXAMPLE = re.compile(r"\b(?:gegenbeispiel\w*|counterexample\w*)\b")
_CONNECTIONS = re.compile(
    r"\b(?:zusammenhang\w*|verbindung\w*|vergleich\w*|vergleiche\w*|unterschied\w*|"
    r"connection\w*|compare|relationship\w*)\b"
)
_FORMULA = re.compile(r"=|\\(?:frac|int|sum|partial|delta)\b|[∫∑∂]")


def _legacy_mapping(depth: Depth) -> ExplanationDepth:
    return ExplanationDepth.DETAILED if depth == Depth.DEEP else ExplanationDepth.STANDARD


def resolve_depth(
    question: str,
    requested: ExplanationDepth | None,
    legacy_depth: Depth = Depth.STANDARD,
    legacy_explicit: bool = False,
) -> dict:
    """Resolve a request without ever overriding an explicit non-AUTO setting.

    ``None`` preserves the old depth mapping. AUTO is opt-in and may only choose
    heuristically when the legacy depth was not explicitly supplied by the user.
    Returned strings are JSON metadata, never numeric confidence or probability.
    """
    if not isinstance(question, str):
        raise TypeError("A question string is required")
    requested = ExplanationDepth(requested) if requested is not None else None
    legacy_depth = Depth(legacy_depth)
    normalized = unicodedata.normalize("NFKC", question[:20000]).casefold()
    proof = bool(_PROOF.search(normalized))
    derivation = bool(_DERIVATION.search(normalized))
    calculation = bool(_CALCULATION.search(normalized))
    boundary = bool(_BOUNDARY.search(normalized))
    advanced = bool(_ADVANCED_CONTEXT.search(normalized))
    counterexample = bool(_COUNTEREXAMPLE.search(normalized))

    if requested is not None and requested != ExplanationDepth.AUTO:
        effective = requested
        selection_source = "explicit"
        reasons = ["explicit_explanation_depth"]
    elif legacy_explicit:
        effective = _legacy_mapping(legacy_depth)
        selection_source = "legacy_explicit"
        reasons = ["explicit_legacy_depth_preserved"]
    elif requested is None:
        effective = _legacy_mapping(legacy_depth)
        selection_source = "legacy_default"
        reasons = ["legacy_depth_mapping_preserved"]
    else:
        selection_source = "auto_heuristic"
        if proof or counterexample or ((derivation or boundary) and advanced):
            effective = ExplanationDepth.RIGOROUS
            reasons = []
            if proof:
                reasons.append("proof_requested")
            if counterexample:
                reasons.append("counterexample_requested")
            if derivation and advanced:
                reasons.append("derivation_with_advanced_constraints")
            if boundary and advanced:
                reasons.append("boundary_conditions_with_advanced_context")
        elif derivation or calculation:
            effective = ExplanationDepth.DETAILED
            reasons = ["calculation_or_derivation_requested"]
        else:
            effective = ExplanationDepth.STANDARD
            reasons = ["conceptual_or_unspecified_question"]

    aspects = {"problem", "definitions", "interpretation"}
    if proof or derivation or calculation or _FORMULA.search(normalized):
        aspects.update(
            {"mathematical_assumptions", "equations", "derivation", "validity", "consistency"}
        )
    if boundary or advanced or effective == ExplanationDepth.RIGOROUS:
        aspects.update({"mathematical_assumptions", "validity", "consistency"})
    if effective == ExplanationDepth.DETAILED:
        aspects.add("validity")
    if _CONNECTIONS.search(normalized):
        aspects.add("connections")
    return {
        "requested": requested.value if requested is not None else None,
        "effective": effective.value,
        "selection_source": selection_source,
        "reasons": reasons,
        "aspects": [name for name in ASPECT_LABELS if name in aspects],
        "heuristic_calibrated": False,
    }
