#!/usr/bin/env python3
"""Run the end-to-end ChatGPT refresh pipeline."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import List, Sequence


PROJECT_DIR = Path(__file__).resolve().parent.parent
SYNC_MARKDOWN_SCRIPT = PROJECT_DIR / "browser_control" / "scripts" / "sync_chatgpt_projects_to_pdf_and_gdrive.py"
BUILD_REPORTS_SCRIPT = PROJECT_DIR / "scripts" / "build_project_reports.py"
SYNC_PDFS_SCRIPT = PROJECT_DIR / "scripts" / "sync_project_report_pdfs.py"


def sanitize_project_fragment(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    pieces: List[str] = []
    for char in normalized:
        if unicodedata.combining(char):
            continue
        if char.isalnum() or char in {"_", "-", "\u3400", "\u4dbf", "\u4e00", "\u9fff"}:
            pieces.append(char)
        elif char.isspace() or char in {"/", "\\", ":", "*", "?", "\"", "<", ">", "|"}:
            pieces.append("_")
        else:
            pieces.append(char)
    cleaned = "".join(pieces).strip().strip(".")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "untitled"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Pull latest ChatGPT conversations, rebuild project reports, "
            "then convert reports to PDF and sync them to Google Drive."
        )
    )
    parser.add_argument(
        "--project",
        action="append",
        default=[],
        help="Only process project names containing this substring. Can be repeated.",
    )
    parser.add_argument(
        "--limit-projects",
        type=int,
        default=None,
        help="Limit the number of matched projects during ChatGPT sync.",
    )
    parser.add_argument(
        "--limit-conversations",
        type=int,
        default=None,
        help="Limit the number of conversations per project during sync and report build.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Optional playwright-cli config path for ChatGPT sync.",
    )
    parser.add_argument(
        "--session",
        default=None,
        help="Optional playwright-cli session name for ChatGPT sync.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.15,
        help="Delay between ChatGPT backend API calls.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.05,
        help="Delay after each local model API request during report build.",
    )
    parser.add_argument(
        "--save-json",
        action="store_true",
        help="Save raw conversation JSON during ChatGPT sync.",
    )
    parser.add_argument(
        "--force-all",
        action="store_true",
        help="Force refresh conversations, rebuild report artifacts, and regenerate PDFs.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Force re-fetch of ChatGPT conversations even when update_time is unchanged.",
    )
    parser.add_argument(
        "--force-report-rebuild",
        action="store_true",
        help="Force rebuild of cached report artifacts.",
    )
    parser.add_argument(
        "--force-pdf-rebuild",
        action="store_true",
        help="Force regeneration of PDFs even if project_report.md is unchanged.",
    )
    parser.add_argument(
        "--fallback-report-only",
        action="store_true",
        help="Use the deterministic project report synthesis path instead of LLM project knowledge synthesis.",
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Skip pulling the latest ChatGPT conversations.",
    )
    parser.add_argument(
        "--skip-report-build",
        action="store_true",
        help="Skip rebuilding project reports.",
    )
    parser.add_argument(
        "--skip-drive-sync",
        action="store_true",
        help="Generate PDFs locally but do not run rclone sync.",
    )
    parser.add_argument(
        "--dry-run-drive-sync",
        action="store_true",
        help="Run rclone sync with --dry-run.",
    )
    parser.add_argument(
        "--md-to-pdf-bin",
        default=None,
        help="Optional md-to-pdf binary path for PDF generation.",
    )
    parser.add_argument(
        "--rclone-bin",
        default=None,
        help="Optional rclone binary path for Google Drive sync.",
    )
    return parser.parse_args()


def extend_projects(command: List[str], projects: Sequence[str]) -> None:
    for project in projects:
        command.extend(["--project", project])


def pdf_project_filters(projects: Sequence[str]) -> List[str]:
    filters: List[str] = []
    seen = set()
    for project in projects:
        for candidate in (project, sanitize_project_fragment(project)):
            if candidate and candidate not in seen:
                filters.append(candidate)
                seen.add(candidate)
    return filters


def run_stage(name: str, command: Sequence[str]) -> None:
    print(f"[stage] {name}", file=sys.stderr)
    print("  " + " ".join(command), file=sys.stderr)
    started_at = time.time()
    completed = subprocess.run(command, cwd=str(PROJECT_DIR))
    elapsed = time.time() - started_at
    if completed.returncode != 0:
        raise RuntimeError(f"{name} failed with exit code {completed.returncode}")
    print(f"[done] {name} ({elapsed:.1f}s)", file=sys.stderr)


def build_sync_markdown_command(args: argparse.Namespace) -> List[str]:
    command = [sys.executable, str(SYNC_MARKDOWN_SCRIPT)]
    extend_projects(command, args.project)
    if args.limit_projects is not None:
        command.extend(["--limit-projects", str(args.limit_projects)])
    if args.limit_conversations is not None:
        command.extend(["--limit-conversations", str(args.limit_conversations)])
    if args.config:
        command.extend(["--config", args.config])
    if args.session:
        command.extend(["--session", args.session])
    command.extend(["--delay-seconds", str(args.delay_seconds)])
    if args.save_json:
        command.append("--save-json")
    if args.force_all or args.force_refresh:
        command.append("--force-refresh")
    return command


def build_report_command(args: argparse.Namespace) -> List[str]:
    command = [sys.executable, str(BUILD_REPORTS_SCRIPT)]
    extend_projects(command, args.project)
    if args.limit_conversations is not None:
        command.extend(["--limit-conversations", str(args.limit_conversations)])
    command.extend(["--sleep-seconds", str(args.sleep_seconds)])
    if args.fallback_report_only:
        command.append("--fallback-report-only")
    if args.force_all or args.force_report_rebuild:
        command.append("--force")
    return command


def build_pdf_command(args: argparse.Namespace) -> List[str]:
    command = [sys.executable, str(SYNC_PDFS_SCRIPT)]
    extend_projects(command, pdf_project_filters(args.project))
    if args.force_all or args.force_pdf_rebuild:
        command.append("--force")
    if args.skip_drive_sync:
        command.append("--skip-sync")
    if args.dry_run_drive_sync:
        command.append("--dry-run-sync")
    if args.md_to_pdf_bin:
        command.extend(["--md-to-pdf-bin", args.md_to_pdf_bin])
    if args.rclone_bin:
        command.extend(["--rclone-bin", args.rclone_bin])
    return command


def main() -> int:
    args = parse_args()
    try:
        if not args.skip_fetch:
            run_stage("pull-latest-chatgpt", build_sync_markdown_command(args))
        if not args.skip_report_build:
            run_stage("rebuild-project-reports", build_report_command(args))
        run_stage("pdf-and-google-drive-sync", build_pdf_command(args))
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "projects": args.project,
                "steps": {
                    "fetch": not args.skip_fetch,
                    "report_build": not args.skip_report_build,
                    "pdf_sync": True,
                },
                "fallback_report_only": bool(args.fallback_report_only),
                "skip_drive_sync": bool(args.skip_drive_sync),
                "dry_run_drive_sync": bool(args.dry_run_drive_sync),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
