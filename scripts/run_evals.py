"""Run the eval harness over the dataset and print/emit a report.

uv run python scripts/run_evals.py
uv run python scripts/run_evals.py --only minimo
uv run python scripts/run_evals.py --json report.json --fail-under 0.7
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from arras_ai.analyzer import _build_client
from arras_ai.config import load_settings
from arras_ai.evals.dataset import load_casos
from arras_ai.evals.report import render_human, to_json
from arras_ai.evals.runner import metricas_cabecera, run_evals


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the arras-ai eval harness.")
    parser.add_argument("--json", type=Path, default=None, help="Write the JSON report here.")
    parser.add_argument("--only", default=None, help="Run only the case with this id.")
    parser.add_argument(
        "--fail-under",
        type=float,
        default=None,
        help="Exit non-zero if any headline metric is below this (0-1).",
    )
    args = parser.parse_args()

    settings = load_settings()
    casos = load_casos()
    if args.only:
        casos = [c for c in casos if c.id == args.only]
        if not casos:
            print(f"No case with id {args.only!r}", file=sys.stderr)
            return 2

    client = _build_client(settings.anthropic_api_key)
    report = run_evals(
        casos,
        analyzer_client=client,
        judge_client=client,
        analyzer_model=settings.model,
        judge_model=settings.judge_model,
    )

    render_human(report)
    if args.json:
        args.json.write_text(to_json(report), encoding="utf-8")
        print(f"\nJSON report written to {args.json}")

    if args.fail_under is not None:
        head = metricas_cabecera(report)
        bajos = {k: v for k, v in head.items() if v < args.fail_under}
        if bajos:
            print(f"\nFAIL: below --fail-under={args.fail_under}: {bajos}", file=sys.stderr)
            return 1
        print(f"\nPASS: all headline metrics >= {args.fail_under}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
