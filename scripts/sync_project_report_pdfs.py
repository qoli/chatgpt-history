#!/usr/bin/env python3
"""Convert project reports to PDF and sync them to Google Drive."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_REPORTS_DIR = PROJECT_DIR / "browser_control" / "output" / "project_reports"
DEFAULT_PDF_DIR = PROJECT_DIR / "browser_control" / "output" / "chatgpt_pdf"
DEFAULT_STATE_PATH = PROJECT_DIR / "browser_control" / "output" / "chatgpt_pdf_state.json"
DEFAULT_SYNC_DEST = "gdrive:chatgpt_pdf"
STATE_VERSION = 1
PDF_CSS = """
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 12px;
  line-height: 1.55;
  color: #111827;
  padding: 18px 24px 24px;
}
h1, h2, h3 {
  color: #0f172a;
}
h1 {
  border-bottom: 2px solid #cbd5e1;
  padding-bottom: 10px;
}
h2 {
  border-bottom: 1px solid #e2e8f0;
  padding-bottom: 4px;
  margin-top: 28px;
}
code {
  background: #f1f5f9;
  padding: 0.1em 0.3em;
  border-radius: 4px;
}
pre code {
  display: block;
  padding: 10px 12px;
  overflow-x: auto;
}
table {
  border-collapse: collapse;
  width: 100%;
}
th, td {
  border: 1px solid #cbd5e1;
  padding: 6px 8px;
  text-align: left;
}
blockquote {
  border-left: 4px solid #cbd5e1;
  margin-left: 0;
  padding-left: 12px;
  color: #334155;
}
"""
PDF_OPTIONS = {
    "format": "A4",
    "margin": {
        "top": "14mm",
        "right": "12mm",
        "bottom": "14mm",
        "left": "12mm",
    },
    "printBackground": True,
}


class PdfSyncError(RuntimeError):
    """Raised when PDF generation or remote sync fails."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert project_report.md files to PDF and sync them to Google Drive."
    )
    parser.add_argument(
        "--reports-dir",
        default=str(DEFAULT_REPORTS_DIR),
        help="Directory containing per-project project_report.md files.",
    )
    parser.add_argument(
        "--pdf-dir",
        default=str(DEFAULT_PDF_DIR),
        help="Directory where generated PDFs will be written.",
    )
    parser.add_argument(
        "--state-path",
        default=str(DEFAULT_STATE_PATH),
        help="State file used to skip unchanged PDF conversions.",
    )
    parser.add_argument(
        "--sync-dest",
        default=DEFAULT_SYNC_DEST,
        help="rclone destination, for example gdrive:chatgpt_pdf",
    )
    parser.add_argument(
        "--project",
        action="append",
        default=[],
        help="Only process projects whose directory names contain this substring. Can be repeated.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate PDFs even if the source report appears unchanged.",
    )
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="Generate PDFs locally but do not run rclone sync.",
    )
    parser.add_argument(
        "--dry-run-sync",
        action="store_true",
        help="Run rclone sync with --dry-run.",
    )
    parser.add_argument(
        "--md-to-pdf-bin",
        default=shutil.which("md-to-pdf") or "md-to-pdf",
        help="Path to the md-to-pdf executable.",
    )
    parser.add_argument(
        "--rclone-bin",
        default=shutil.which("rclone") or "rclone",
        help="Path to the rclone executable.",
    )
    return parser.parse_args()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"version": STATE_VERSION, "md_to_pdf_version": "", "entries": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PdfSyncError(f"Unexpected state file format: {path}")
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        entries = {}
    return {
        "version": int(payload.get("version") or STATE_VERSION),
        "md_to_pdf_version": str(payload.get("md_to_pdf_version") or ""),
        "entries": entries,
    }


def save_state(path: Path, state: Dict[str, Any]) -> None:
    write_json(path, state)


def run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        detail = stderr or stdout or f"command exited with {result.returncode}"
        raise PdfSyncError(f"Command failed: {' '.join(command)}\n{detail}")
    return result


def md_to_pdf_version(binary: str) -> str:
    result = run_command([binary, "--version"])
    return result.stdout.strip()


def project_matches(name: str, filters: Sequence[str]) -> bool:
    if not filters:
        return True
    lowered = name.casefold()
    return any(fragment.casefold() in lowered for fragment in filters)


def collect_reports(reports_dir: Path, filters: Sequence[str]) -> List[Path]:
    report_paths = []
    for report_path in sorted(reports_dir.glob("*/project_report.md")):
        if project_matches(report_path.parent.name, filters):
            report_paths.append(report_path)
    if not report_paths:
        raise PdfSyncError("No matching project_report.md files found.")
    return report_paths


def destination_pdf_path(report_path: Path, reports_dir: Path, pdf_dir: Path) -> Path:
    relative = report_path.relative_to(reports_dir).with_suffix(".pdf")
    return pdf_dir / relative


def state_entry_key(report_path: Path, reports_dir: Path) -> str:
    return report_path.relative_to(reports_dir).as_posix()


def should_regenerate(
    report_path: Path,
    destination_path: Path,
    state_entry: Dict[str, Any] | None,
    md_version: str,
    force: bool,
) -> bool:
    if force or not destination_path.exists():
        return True
    source_stat = report_path.stat()
    if destination_path.stat().st_mtime_ns < source_stat.st_mtime_ns:
        return True
    if not isinstance(state_entry, dict):
        return True
    if str(state_entry.get("md_to_pdf_version") or "") != md_version:
        return True
    return (
        int(state_entry.get("source_mtime_ns") or 0) != source_stat.st_mtime_ns
        or int(state_entry.get("source_size") or -1) != source_stat.st_size
    )


def convert_markdown_to_pdf(md_to_pdf_bin: str, report_path: Path, destination_path: Path) -> None:
    ensure_parent(destination_path)
    with tempfile.TemporaryDirectory(prefix="project-report-pdf-") as tmpdir:
        staging_dir = Path(tmpdir)
        staged_markdown = staging_dir / report_path.name
        staged_pdf = staged_markdown.with_suffix(".pdf")
        staged_markdown.write_text(report_path.read_text(encoding="utf-8"), encoding="utf-8")
        command = [
            md_to_pdf_bin,
            str(staged_markdown),
            "--basedir",
            str(PROJECT_DIR),
            "--document-title",
            report_path.parent.name,
            "--css",
            PDF_CSS,
            "--pdf-options",
            json.dumps(PDF_OPTIONS, ensure_ascii=False),
        ]
        run_command(command)
        if not staged_pdf.exists():
            raise PdfSyncError(f"md-to-pdf did not produce {staged_pdf}")
        shutil.move(str(staged_pdf), str(destination_path))


def join_rclone_path(base: str, child: str) -> str:
    base = base.rstrip("/")
    if not child:
        return base
    return f"{base}/{child}"


def sync_to_remote(
    rclone_bin: str,
    pdf_dir: Path,
    sync_dest: str,
    filters: Sequence[str],
    dry_run: bool,
) -> List[str]:
    synced_targets: List[str] = []
    if filters:
        project_dirs = sorted(path.name for path in pdf_dir.iterdir() if path.is_dir() and project_matches(path.name, filters))
        for project_name in project_dirs:
            local_path = pdf_dir / project_name
            remote_path = join_rclone_path(sync_dest, project_name)
            command = [rclone_bin, "sync", str(local_path), remote_path]
            if dry_run:
                command.append("--dry-run")
            run_command(command)
            synced_targets.append(remote_path)
        return synced_targets

    command = [rclone_bin, "sync", str(pdf_dir), sync_dest]
    if dry_run:
        command.append("--dry-run")
    run_command(command)
    synced_targets.append(sync_dest)
    return synced_targets


def sync_pipeline(args: argparse.Namespace) -> int:
    reports_dir = Path(args.reports_dir).resolve()
    pdf_dir = Path(args.pdf_dir).resolve()
    state_path = Path(args.state_path).resolve()

    if not reports_dir.exists():
        raise PdfSyncError(f"Reports directory does not exist: {reports_dir}")
    pdf_dir.mkdir(parents=True, exist_ok=True)

    reports = collect_reports(reports_dir, args.project)
    state = load_state(state_path)
    md_version = md_to_pdf_version(args.md_to_pdf_bin)
    entries = state.get("entries", {})
    if not isinstance(entries, dict):
        entries = {}

    generated = 0
    skipped = 0
    outputs: List[Path] = []

    for report_path in reports:
        destination_path = destination_pdf_path(report_path, reports_dir, pdf_dir)
        outputs.append(destination_path)
        key = state_entry_key(report_path, reports_dir)
        entry = entries.get(key) if isinstance(entries.get(key), dict) else None
        if should_regenerate(report_path, destination_path, entry, md_version, args.force):
            print(f"pdf: {report_path.parent.name}", file=sys.stderr)
            convert_markdown_to_pdf(args.md_to_pdf_bin, report_path, destination_path)
            generated += 1
        else:
            print(f"pdf-skip: {report_path.parent.name}", file=sys.stderr)
            skipped += 1

        source_stat = report_path.stat()
        entries[key] = {
            "source_path": key,
            "destination_path": str(destination_path.relative_to(pdf_dir)),
            "source_mtime_ns": source_stat.st_mtime_ns,
            "source_size": source_stat.st_size,
            "md_to_pdf_version": md_version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    state = {
        "version": STATE_VERSION,
        "md_to_pdf_version": md_version,
        "entries": entries,
        "last_run_at": datetime.now(timezone.utc).isoformat(),
    }
    save_state(state_path, state)

    synced_targets: List[str] = []
    if not args.skip_sync:
        synced_targets = sync_to_remote(
            rclone_bin=args.rclone_bin,
            pdf_dir=pdf_dir,
            sync_dest=args.sync_dest,
            filters=args.project,
            dry_run=args.dry_run_sync,
        )

    print(
        json.dumps(
            {
                "reports": len(reports),
                "pdf_generated": generated,
                "pdf_skipped": skipped,
                "pdf_dir": str(pdf_dir),
                "state_path": str(state_path),
                "sync_dest": None if args.skip_sync else args.sync_dest,
                "sync_targets": synced_targets,
                "dry_run_sync": bool(args.dry_run_sync),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> int:
    args = parse_args()
    try:
        return sync_pipeline(args)
    except PdfSyncError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
