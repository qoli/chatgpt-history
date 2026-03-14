# Repository Guidelines

## Project Structure & Module Organization
Core pipeline code lives in [`scripts/`](./scripts), especially `build_project_reports.py` for session/chunk analysis and `sync_project_report_pdfs.py` for PDF export and Drive sync. Browser-side export helpers live in [`browser_control/scripts/`](./browser_control/scripts). Reference docs and design notes are in [`browser_control/docs/`](./browser_control/docs), [`SPEC.md`](./SPEC.md), and [`TODO.md`](./TODO.md). Generated artifacts are written under [`browser_control/output/`](./browser_control/output): `chatgpt_markdown/`, `project_reports/`, and `chatgpt_pdf/`.

## Build, Test, and Development Commands
- `python3 scripts/build_project_reports.py --fallback-report-only --sleep-seconds 0.05`: rebuild structured reports for all projects.
- `python3 scripts/build_project_reports.py --project 'eisonAI' --report-only`: re-render one report from existing structured artifacts.
- `python3 scripts/sync_project_report_pdfs.py`: convert all `project_report.md` files to PDF and sync `chatgpt_pdf/` to `gdrive:chatgpt_pdf`.
- `python3 -m py_compile scripts/build_project_reports.py scripts/sync_project_report_pdfs.py`: quick syntax validation before commit.

## Coding Style & Naming Conventions
Use Python 3 with 4-space indentation and standard library-first implementations where practical. Prefer `Path` over raw strings for filesystem code. Keep filenames and artifact names stable and ASCII-safe; generated project folders use sanitized names such as `Telegram_AI_Workspace/`. Add small, purposeful functions instead of inline control flow when extending the pipeline.

## Testing Guidelines
There is no dedicated test suite yet. Validate changes with `python3 -m py_compile ...` and one targeted runtime check against a small project, for example `--project 'Nano Tower'` or `--project 'eisonAI'`. When output schemas change, inspect the corresponding JSON artifacts in `browser_control/output/project_reports/<project>/`.

## Commit & Pull Request Guidelines
Recent history uses emoji-prefixed Conventional Commit style, for example `✨ feat(scripts): ...`, `♻️ refactor(build_project_reports): ...`, and `📝 docs(spec): ...`. Keep scopes specific to the area touched. PRs should include: purpose, commands run, affected output paths, and before/after notes for report quality if generated artifacts changed.

## Security & Configuration Tips
Local model endpoints are hardcoded in `build_project_reports.py`; do not commit secrets. `rclone` remote `gdrive:` must already be configured locally. Generated output under `browser_control/output/` is reproducible; avoid editing it manually unless you are intentionally updating checked-in artifacts.
