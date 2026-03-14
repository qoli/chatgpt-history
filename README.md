# chatgpt-history

## Idea

Modern software projects increasingly evolve through long conversations with AI systems.

Those conversations are often fragmented across dozens or hundreds of sessions. Important design insights, decisions, and conceptual shifts become buried in chat history.

This repository explores a different idea:

**Treat ChatGPT conversation history as a knowledge substrate.**

Instead of exporting transcripts, the system analyzes conversations and reconstructs:
- the conceptual landscape of the project
- architectural thinking that emerged over time
- engineering decisions that shaped the implementation
- recurring implementation patterns
- unresolved questions that remain open
- project evolution timelines

The result is not a chat archive.

It is a distilled project memory.

## Concept

Most chat archives are searchable, but they are not legible as project thinking.

This repository experiments with a pipeline that tries to turn scattered AI conversations into structured project knowledge:
- sync ChatGPT project conversations into a stable local corpus
- analyze them at both session level and turn-pair level
- cluster recurring themes across sessions
- synthesize project knowledge from those clusters
- render a report that behaves more like a technical retrospective than a chat summary

In that sense, the repository is investigating whether AI conversation history can serve as a durable memory layer for projects, especially when a project's reasoning is distributed across many asynchronous sessions.

## What The System Reconstructs

The pipeline is designed to rebuild a project's thinking history from dispersed conversations. For each project, it attempts to surface:
- core concepts that kept reappearing even when wording changed
- architectural ideas that gave shape to the system
- engineering decisions and their surrounding context
- recurring implementation patterns
- unresolved design or product questions
- a timeline of major topic and decision shifts

This makes it possible to return to a project months later and recover not only what was discussed, but how the project gradually formed.

## Evidence From Real Outputs

The examples below are not mockups. They are fragments from generated `project_report.md` files and are included here as evidence of the system's intended capability.

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

## Example Output Files

You can inspect real generated reports here:
- [`browser_control/output/project_reports/eisonAI/project_report.md`](./browser_control/output/project_reports/eisonAI/project_report.md)
- [`browser_control/output/project_reports/Nano_Tower/project_report.md`](./browser_control/output/project_reports/Nano_Tower/project_report.md)
- [`browser_control/output/project_reports/Telegram_AI_Workspace/project_report.md`](./browser_control/output/project_reports/Telegram_AI_Workspace/project_report.md)

## Main Workflow

The operational pipeline still matters, but it is downstream of the main idea.

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
