"""Local evaluation CLI. Real requests require independent explicit safety opt-ins."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from app.modules.evaluation.contracts import ExperimentConfig
from app.modules.evaluation.dataset import load_dataset, validate_import_manifest
from app.modules.evaluation.reporting import (
    apply_ratings,
    compare_reports,
    export_report,
    load_report,
)
from app.modules.evaluation.runner import run_experiment, run_prompt_comparison
from app.modules.evaluation.safety import EvaluationSafetyError
from app.modules.tutor.contracts import ProviderError


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="physics-eval", description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="List candidate cases and validation status.")
    listing.add_argument("--dataset", type=Path)
    listing.add_argument("--json", action="store_true", dest="as_json")
    for command in ("run", "compare-prompts"):
        run = commands.add_parser(
            command,
            help="Run one experiment."
            if command == "run"
            else "Compare v1/v2 on identical DEEP cases and source contexts.",
        )
        run.add_argument("--dataset", type=Path)
        run.add_argument("--method", choices=("isolated", "end_to_end"), default="isolated")
        run.add_argument("--provider", choices=("mock", "openai_responses"), default="mock")
        run.add_argument("--model")
        run.add_argument(
            "--reasoning-effort",
            choices=("none", "minimal", "low", "medium", "high", "xhigh", "max"),
        )
        run.add_argument(
            "--explanation-depth",
            choices=("STANDARD", "DETAILED", "RIGOROUS", "AUTO"),
            default="AUTO" if command == "compare-prompts" else None,
        )
        if command == "run":
            run.add_argument("--prompt-version", choices=("physics-tutor-v1", "physics-tutor-v2"))
        run.add_argument("--temperature", type=float, default=0.2)
        run.add_argument("--timeout-seconds", type=float, default=30)
        run.add_argument("--max-output-tokens", type=int, default=1500)
        run.add_argument("--context-token-budget", type=int, default=6000)
        run.add_argument("--k", type=int, default=5)
        run.add_argument("--limit", type=int, default=24)
        run.add_argument("--case-id", action="append", default=[], dest="case_ids")
        run.add_argument("--allow-paid", action="store_true")
        run.add_argument("--max-calls", type=int)
        run.add_argument("--allow-unvalidated", action="store_true")
        run.add_argument("--storage-root", type=Path)
        run.add_argument("--output", type=Path)
    compare = commands.add_parser(
        "compare", help="Compare reports without asserting scientific gains."
    )
    compare.add_argument("left", type=Path)
    compare.add_argument("right", type=Path)
    compare.add_argument("--output", type=Path)
    export = commands.add_parser("export", help="Copy a validated report to a new JSON path.")
    export.add_argument("report", type=Path)
    export.add_argument("--output", type=Path, required=True)
    ratings = commands.add_parser(
        "apply-ratings", help="Attach explicit, answer-bound manual/model reviews."
    )
    ratings.add_argument("report", type=Path)
    ratings.add_argument("ratings", type=Path)
    ratings.add_argument("--output", type=Path, required=True)
    manifest = commands.add_parser(
        "validate-import", help="Check local PDF rights manifest and hashes without external calls."
    )
    manifest.add_argument("manifest", type=Path)
    return result


def _print(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str, allow_nan=False))


def _dispatch(args):
    if args.command == "list":
        dataset = load_dataset(args.dataset)
        if args.as_json:
            _print(
                {
                    "dataset": {"id": dataset.id, "version": dataset.version},
                    "cases": [
                        {
                            "id": case.id,
                            "category": case.category.value,
                            "mode": case.mode.value,
                            "topic": case.topic,
                            "reference_status": case.validation.status,
                        }
                        for case in dataset.cases
                    ],
                    "scientific_quality_established": False,
                }
            )
        else:
            print(f"{dataset.id} {dataset.version}: {len(dataset.cases)} candidate cases")
            for case in dataset.cases:
                print(
                    f"{case.id}\t{case.category.value}\t{case.mode.value}\t{case.validation.status}"
                )
        return 0
    if args.command in {"run", "compare-prompts"}:
        dataset = load_dataset(args.dataset)
        config = ExperimentConfig(
            method=args.method,
            provider=args.provider,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            temperature=args.temperature,
            timeout_seconds=args.timeout_seconds,
            max_output_tokens=args.max_output_tokens,
            context_token_budget=args.context_token_budget,
            k=args.k,
            case_ids=args.case_ids,
            limit=args.limit,
            max_calls=args.max_calls,
            allow_paid=args.allow_paid,
            allow_unvalidated=args.allow_unvalidated,
            explanation_depth=args.explanation_depth,
            prompt_version=getattr(args, "prompt_version", None),
        )
        runner = run_experiment if args.command == "run" else run_prompt_comparison
        report = asyncio.run(runner(dataset, config, storage_root=args.storage_root))
        if args.command == "run":
            summaries = report["summary"]
            completed = all(result["status"] == "completed" for result in report["results"])
        else:
            summaries = {name: arm["summary"] for name, arm in report["arms"].items()}
            completed = all(
                result["status"] == "completed"
                for arm in report["arms"].values()
                for result in arm["results"]
            )
            completed = completed and all(
                pair["controlled_comparison_eligible"]
                for pair in report["comparison"]["paired_cases"]
            )

        output = args.output or Path(".local/evaluations") / (report["run_id"] + ".json")
        export_report(report, output)
        _print(
            {
                "run_id": report["run_id"],
                "output": str(output),
                "method": report["method"],
                "call_budget": report["call_budget"],
                "summary": summaries,
            }
        )
        return 0 if completed else 1
    if args.command == "compare":
        comparison = compare_reports(load_report(args.left), load_report(args.right))
        if args.output is not None:
            # A comparison is not an experiment report. Preserve its own schema.
            export_report(comparison, args.output)
        _print(comparison)
        return 0
    if args.command == "export":
        path = export_report(load_report(args.report), args.output)
        _print({"output": str(path)})
        return 0
    if args.command == "apply-ratings":
        if args.ratings.stat().st_size > 1_000_000:
            raise ValueError("The review input is too large.")
        reviews = json.loads(args.ratings.read_text())
        report = apply_ratings(load_report(args.report), reviews)
        path = export_report(report, args.output)
        _print({"output": str(path), "summary": report["summary"]})
        return 0
    if args.command == "validate-import":
        _print({"sources": validate_import_manifest(args.manifest), "external_calls": 0})
        return 0
    return 2


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        return _dispatch(args)
    except EvaluationSafetyError as exc:
        print(f"Evaluation refused [{exc.code}]: {exc.message}", file=sys.stderr)
    except ProviderError as exc:
        print(f"Provider initialization failed [{exc.code}].", file=sys.stderr)
    except (OSError, ValueError, ValidationError, KeyError, TypeError):
        # Never print raw exception contents: user-provided files/URLs may contain secrets.
        print(
            "Invalid evaluation configuration, input file, or output destination.", file=sys.stderr
        )
    except Exception:
        print(
            "The local evaluation could not complete; inspect the saved safe stage status.",
            file=sys.stderr,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
