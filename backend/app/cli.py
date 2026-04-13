from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .services.common import load_json_file
from .services.pipeline import analyze_bundle
from .services.thematic import extract_excerpts
from .services.usability import bootstrap_task_template


def cmd_analyze(args: argparse.Namespace) -> None:
    config = {}
    if args.config:
        config = load_json_file(args.config)
    result = analyze_bundle(
        survey_path=args.survey,
        usability_path=args.usability,
        config=config,
        task_outcomes_path=args.task_outcomes,
        theme_assignments_path=args.theme_assignments,
    )
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"Wrote analysis to {output_path}")


def cmd_bootstrap_theme_template(args: argparse.Namespace) -> None:
    rows = extract_excerpts(args.usability)
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "excerpt_id",
        "excel_row",
        "participant_name",
        "tool",
        "task",
        "prompt_id",
        "source_column",
        "text",
        "theme_id",
        "reviewer_notes",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote theme template to {output_path}")


def cmd_bootstrap_task_template(args: argparse.Namespace) -> None:
    rows = bootstrap_task_template(args.usability)
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["participant_name", "tool", "task", "subtask", "status"]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote task template to {output_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Email encryption study analysis pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser("analyze", help="Run the full analysis pipeline")
    analyze_parser.add_argument("--survey", required=True)
    analyze_parser.add_argument("--usability", required=True)
    analyze_parser.add_argument("--task-outcomes")
    analyze_parser.add_argument("--theme-assignments")
    analyze_parser.add_argument("--config")
    analyze_parser.add_argument("--out", required=True)
    analyze_parser.set_defaults(func=cmd_analyze)

    theme_parser = subparsers.add_parser("bootstrap-theme-template", help="Create a theme assignment template")
    theme_parser.add_argument("--usability", required=True)
    theme_parser.add_argument("--out", required=True)
    theme_parser.set_defaults(func=cmd_bootstrap_theme_template)

    task_parser = subparsers.add_parser("bootstrap-task-template", help="Create a task outcomes template")
    task_parser.add_argument("--usability", required=True)
    task_parser.add_argument("--out", required=True)
    task_parser.set_defaults(func=cmd_bootstrap_task_template)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
