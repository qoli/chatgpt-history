# Repository Guidelines

## Project Structure & Module Organization
Core automation lives in [`scripts/`](./scripts). The main pipeline is `build_project_reports.py`, PDF export is `sync_project_report_pdfs.py`, and the top-level orchestrator is `run_chatgpt_refresh_pipeline.py`. Browser-driven ChatGPT export code lives in [`browser_control/scripts/`](./browser_control/scripts), especially `export_chatgpt_projects_markdown.py` and `sync_chatgpt_projects_to_pdf_and_gdrive.py`. Specs and planning notes are in [`SPEC.md`](./SPEC.md), [`TODO.md`](./TODO.md), and [`DOCUMENTATION_OVERVIEW.md`](./DOCUMENTATION_OVERVIEW.md). Generated artifacts are written under [`browser_control/output/`](./browser_control/output): `chatgpt_markdown/`, `project_reports/`, and `chatgpt_pdf/`.

## Build, Test, and Development Commands
- `python3 scripts/run_chatgpt_refresh_pipeline.py --force-all`: full refresh of markdown sync, report rebuild, PDF generation, and Google Drive sync.
- `python3 scripts/build_project_reports.py --fallback-report-only --sleep-seconds 0.05`: rebuild reports without the final project-level LLM synthesis step.
- `python3 scripts/build_project_reports.py --project 'eisonAI' --report-only`: re-render a single report from existing structured artifacts.
- `python3 scripts/sync_project_report_pdfs.py --project eisonAI --dry-run-sync`: test PDF export and Drive sync for one project.
- `python3 -m py_compile scripts/*.py browser_control/scripts/*.py`: quick syntax validation before commit.

## Coding Style & Naming Conventions
Use Python 3, 4-space indentation, type hints, and standard-library-first solutions. Prefer `Path` for filesystem work and keep helper functions small and composable. Preserve stable artifact names and sanitized project folder names such as `Telegram_AI_Workspace/`. Avoid ad hoc text patches in synthesis code; prefer embeddings, LLM classification, or other generalizable methods.

## Testing Guidelines
There is no dedicated automated test suite yet. Validate syntax with `py_compile`, then run one targeted pipeline command against a small project such as `--project 'eisonAI'` or `--project 'Nano Tower'`. When schemas change, inspect the JSON artifacts under `browser_control/output/project_reports/<project>/` and confirm the expected fields are present.

## Commit & Pull Request Guidelines
Recent history follows emoji-prefixed Conventional Commits, for example `✨ feat(scripts): ...`, `♻️ refactor(build_project_reports): ...`, and `📝 docs(readme): ...`. Keep scopes narrow and mention the pipeline stage touched. PRs should include purpose, commands run, impacted output paths, and any report-quality change worth reviewing.

## Security & Configuration Tips
This repo depends on local tools and services: `playwright-cli`, `md-to-pdf`, `rclone`, and the local LLM endpoints configured in `build_project_reports.py`. Do not commit secrets, tokens, or browser session state. Treat files under `browser_control/output/` as reproducible build artifacts unless a task explicitly requires updating checked-in outputs.
