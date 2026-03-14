# chatgpt-history

This repository turns exported ChatGPT project conversations into structured technical reports.

The pipeline is built around three stages:
- sync ChatGPT project conversations to local Markdown
- analyze conversations into structured project knowledge
- render Markdown reports, convert them to PDF, and sync them to Google Drive

## What You Get

The output is not a flat chat summary or a transcript dump.

This pipeline turns long, messy project conversations into a report that lets you quickly answer questions like:
- What is this project really trying to build?
- Which concepts kept recurring across multiple sessions?
- What architectural shape emerged over time?
- Which engineering decisions were actually made?
- What patterns kept showing up in implementation thinking?
- What remains unresolved?

Each report is organized into:
- concepts
- architectural ideas
- engineering decisions
- recurring patterns
- open questions
- a key timeline
- a topic map with source traceability

That means the output is useful both as a memory aid and as a technical retrospective. You can reopen a project months later and still recover:
- the core framing of the product
- the major design pivots
- the decision trail behind implementation choices
- the original conversations that support each theme

The reports are especially useful for projects that evolved through many scattered ChatGPT sessions, where the important ideas are otherwise buried across dozens of conversations.

Example from `eisonAI`:

```md
## Concepts
- **本地優先**
- **離線推理**
- **思考緩衝層**

## Engineering Decisions
- **推理執行環境從 native handler 移至 popup (WebGPU + WebLLM)**
- **模型資產打包在 extension bundle，禁止 Runtime 下載**

## Key Timeline
- **Decision**: 推理執行環境從 native handler 移至 popup (WebGPU + WebLLM)
  Topic: eisonAI 本地優先思考緩衝系統
```

Example from `Nano Tower`:

```md
## Project Overview
Nano Tower is a turn-based, episodic life simulator and AI exploration sandbox built on Godot 4.x.

## Architectural Ideas
- **Separation of creative LLM layer from rule-based simulation core**
- **Node=Element, Scene=Context mapping**

## Topic Map
### Generative Asset Pipeline
The cluster focuses on transforming natural language prompts into verifiable engineering constraints for asset generation.
```

Example from `Telegram AI Workspace`:

```md
## Concepts
- **AI Operating Environment**
- **Agent Orchestration**
- **Telegram Mini App Integration**

## Topic Map
### AI Operating Environment
The cluster focuses on establishing a Telegram-based AI Workspace that functions as an "AI Operating Environment" rather than a simple chatbot.
Sources: AI Operating Environment (`browser_control/output/chatgpt_markdown/Telegram_AI_Workspace/...`)
```

These examples show the intended shape of the output:
- high-level synthesis at the top
- concrete design and implementation signals in the middle
- traceability back to source conversations at the bottom

The result is closer to a project memory system than a chat export.

## Repository Layout

- [`scripts/`](./scripts): main pipeline scripts
- [`browser_control/scripts/`](./browser_control/scripts): browser-side ChatGPT export and sync helpers
- [`browser_control/output/`](./browser_control/output): generated markdown, reports, PDFs, and state files
- [`SPEC.md`](./SPEC.md): current pipeline specification
- [`TODO.md`](./TODO.md): active implementation backlog
- [`DOCUMENTATION_OVERVIEW.md`](./DOCUMENTATION_OVERVIEW.md): doc index

## Main Workflow

Run the end-to-end refresh pipeline:

```bash
cd /Volumes/Data/Github/chatgpt-history
python3 scripts/run_chatgpt_refresh_pipeline.py --force-all
```

This command:
1. pulls the latest ChatGPT conversations through `playwright-cli`
2. rebuilds `project_report.md` files from the current analysis pipeline
3. converts reports to PDF with `md-to-pdf`
4. syncs `browser_control/output/chatgpt_pdf/` to `gdrive:chatgpt_pdf`

## Example Output Files

You can inspect real generated reports here:
- [`browser_control/output/project_reports/eisonAI/project_report.md`](./browser_control/output/project_reports/eisonAI/project_report.md)
- [`browser_control/output/project_reports/Nano_Tower/project_report.md`](./browser_control/output/project_reports/Nano_Tower/project_report.md)
- [`browser_control/output/project_reports/Telegram_AI_Workspace/project_report.md`](./browser_control/output/project_reports/Telegram_AI_Workspace/project_report.md)

## Useful Commands

Rebuild reports only:

```bash
python3 scripts/build_project_reports.py --fallback-report-only --sleep-seconds 0.05
```

Re-render one report from existing artifacts:

```bash
python3 scripts/build_project_reports.py --project 'eisonAI' --report-only
```

Generate and sync PDFs only:

```bash
python3 scripts/sync_project_report_pdfs.py
```

## Requirements

The repo expects these tools or services to already exist locally:
- `playwright-cli` with a working ChatGPT browser session
- a reachable local embedding / LLM server for `build_project_reports.py`
- `md-to-pdf`
- `rclone` with `gdrive:` configured

## Output Artifacts

Per-project analysis artifacts are written to:

```text
browser_control/output/project_reports/<project>/
```

Typical files include:
- `conversation_summaries.jsonl`
- `session_clusters.json`
- `chunk_clusters.json`
- `project_knowledge.json`
- `timeline.json`
- `project_report.md`

Generated PDFs are written to:

```text
browser_control/output/chatgpt_pdf/<project>/project_report.pdf
```
