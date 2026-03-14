# Documentation Overview

## Purpose

This file is the entry point for the documentation in this repo.

The repo now contains three kinds of documents:

- current-state specs
- supporting proposals
- execution / iteration notes

If you are returning to the project after a break, start here.

## Recommended Reading Order

### 1. Current System

Read this first if you want to understand what the repo is doing now:

- `SPEC.md`

It describes:

- the current structured analysis pipeline
- input and output layout
- model endpoints
- the implemented session-first and chunk-evidence design
- the final report structure and operating commands

### 2. Active Roadmap

Read this next if you want to know what is done and what is still unresolved:

- `TODO.md`

It tracks:

- completed pipeline milestones
- clustering and report-design decisions still open
- validation status
- future directions

### 3. Supporting Proposal

This document explains the rationale behind one design choice that is still useful to keep separate:

- `AB_TURN_CHUNKING_PROPOSAL.md`

Use it like this:

- `AB_TURN_CHUNKING_PROPOSAL.md`
  Read for the turn-pair chunk strategy used for fine-grained concept mining.

## How The Documentation Maps to the Code

Primary implementation:

- `scripts/build_project_reports.py`

The code now supports:

- session-level summaries
- per-project session clustering
- A/B turn chunk extraction
- per-project chunk clustering
- chunk-to-session attachment
- structured project knowledge output
- timeline output
- deterministic report rendering
- report-only rebuild mode

## Current Output Artifacts

The report pipeline writes per-project artifacts under:

- `browser_control/output/project_reports/<project_name>/`

Important files:

- `conversation_summaries.jsonl`
  Session-level structured records.

- `session_clusters.json`
  Topic records derived primarily from session-level understanding.

- `ab_chunks.jsonl`
  Turn-pair chunk records.

- `chunk_clusters.json`
  Chunk-level evidence groupings.

- `chunk_to_session_cluster_links.json`
  Attachment map from chunk clusters back to session clusters.

- `project_knowledge.json`
  Project-level structured synthesis used to build the final report.

- `timeline.json`
  Event timeline derived from structured knowledge and topic records.

- `project_report.md`
  Final report rendered from structured intermediate artifacts.

- `index.md`
  Report index across projects.

## Recommended Commands

### Rebuild Everything in Stable Mode

Use this when you want the latest documents for all projects without relying on the final LLM Markdown-writing step:

```bash
cd <repo-root>
python3 scripts/build_project_reports.py --fallback-report-only --sleep-seconds 0.05
```

### Rebuild Only Final Reports

Use this when summaries, clusters, and structured knowledge already exist:

```bash
cd <repo-root>
python3 scripts/build_project_reports.py --report-only
```

### Force Full Regeneration

Use this when you want to ignore cached session summaries:

```bash
cd <repo-root>
python3 scripts/build_project_reports.py --force --fallback-report-only --sleep-seconds 0.05
```

### Force Full Regeneration From a Clean Output Directory

Use this when you want a complete clean rebuild:

```bash
cd <repo-root>
rm -rf browser_control/output/project_reports
python3 scripts/build_project_reports.py --force --fallback-report-only --sleep-seconds 0.05
```

## Current Documentation Roles

To avoid confusion, treat the files as follows:

- `SPEC.md`
  Main current system spec. This should match the implemented pipeline.

- `TODO.md`
  Active work tracker. This is the practical next-step document.

- `AB_TURN_CHUNKING_PROPOSAL.md`
  Design rationale for A/B turn chunking.

- `DOCUMENTATION_OVERVIEW.md`
  Navigation layer for all of the above.

## Suggested Next Documentation Cleanup

The docs are now in better shape, but one cleanup decision is still open.

The next useful cleanup would be:

- decide whether `AB_TURN_CHUNKING_PROPOSAL.md` should remain separate or also be folded into `SPEC.md`
- optionally add a short `README.md` for repo entry
