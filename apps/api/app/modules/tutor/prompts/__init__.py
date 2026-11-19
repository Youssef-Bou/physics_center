"""Versioned scientific response rules, kept separate from source data."""

from importlib.resources import files

from app.modules.tutor.adaptive import ASPECT_LABELS, resolve_depth
from app.modules.tutor.contracts import Depth, ExplanationDepth, Mode

PROMPT_VERSION = "physics-tutor-v1"
ADAPTIVE_PROMPT_VERSION = "physics-tutor-v2"


def system_prompt(
    mode: Mode,
    depth: Depth,
    direct_answer: bool = False,
    *,
    version: str = PROMPT_VERSION,
    explanation_depth: ExplanationDepth | None = None,
    question: str = "",
) -> str:
    mode = Mode(mode)
    depth = Depth(depth)
    resource = files(__package__)
    if version == ADAPTIVE_PROMPT_VERSION:
        if mode != Mode.DEEP_PHYSICS_MODE:
            raise ValueError("The adaptive prompt version only supports DEEP_PHYSICS_MODE")
        plan = resolve_depth(question, explanation_depth, legacy_depth=depth)
        base = resource.joinpath("base_v2.md").read_text(encoding="utf-8")
        guidance = resource.joinpath("deep_physics_mode_v2.md").read_text(encoding="utf-8")
        depth_guidance = resource.joinpath(
            f"explanation_{plan['effective'].lower()}_v2.md"
        ).read_text(encoding="utf-8")
        aspects = "\n".join(f"- {ASPECT_LABELS[name]}" for name in plan["aspects"])
        return (
            f"Promptversion: {ADAPTIVE_PROMPT_VERSION}\n\n{base}\n\n{guidance}\n\n"
            f"Erklärungstiefe: {plan['effective']}\n{depth_guidance}\n\n"
            f"Situativ relevante Aspekte (keine Pflichtabschnitte):\n{aspects}"
        )
    if version != PROMPT_VERSION:
        raise ValueError("Unsupported tutor prompt version")
    base = resource.joinpath("base.md").read_text(encoding="utf-8")
    guidance = resource.joinpath(f"{mode.value.lower()}.md").read_text(encoding="utf-8")
    depth_text = {
        Depth.CONCISE: "Antworte knapp, aber ohne notwendige Voraussetzungen oder Belege wegzulassen.",
        Depth.STANDARD: "Erkläre die relevanten Schritte in angemessener fachlicher Tiefe.",
        Depth.DEEP: "Entwickle relevante Voraussetzungen und Zwischenschritte ausführlich und prüfbar.",
    }[depth]
    direct = (
        "Eine direkte vollständige Antwort wurde ausdrücklich angefordert; sie ist erlaubt."
        if direct_answer
        else "Im sokratischen Modus zunächst Hinweise und Fragen statt vollständiger Lösungen."
    )
    return f"Promptversion: {PROMPT_VERSION}\n\n{base}\n\n{guidance}\n\n{depth_text}\n{direct}"
