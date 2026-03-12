# ChatGPT History Summarization Spec

## Status

Prototype implemented. The local pipeline script exists and has been validated end-to-end on a minimal `B-Roll 方程式` run with one conversation, on a multi-conversation `Nano Tower` run with three conversations, and on a medium `Magic Vision` run with nine conversations. Conversation summaries, embeddings, per-project clustering, and final Markdown report generation are all wired up. Remaining work is focused on report quality, runtime tuning, and broader validation on larger projects.

## Goal

Build a local pipeline that reads exported ChatGPT project conversations from Markdown, summarizes them with local models, groups related conversations semantically, and produces one report per project.

## Inputs

- Source directory: `browser_control/output/chatgpt_markdown/`
- Unit of input: one Markdown file per conversation
- Metadata expected in each file:
  - `title`
  - `conversation_id`
  - `project`
  - `create_time`
  - `update_time`
  - conversation body

## Local Model Endpoints

### Embedding API

- Base URL: `http://ronnie-mac-studio.local:1234/v1`
- Model: `text-embedding-qwen3-0.6b-text-embedding`

### LLM API

- Base URL: `http://ronnie-mac-studio.local:1234/v1`
- Model: `qwen3.5-122b-a10b-text-mlx`

## Output

One report per project.

Recommended output layout:

```text
browser_control/output/project_reports/
  index.md
  <project_name>/
    project_report.md
    conversation_summaries.jsonl
    clusters.json
```

## Pipeline

### 1. Parse Markdown Conversations

For each Markdown file:

- parse frontmatter
- extract conversation title and project name
- extract conversation body
- preserve source path for traceability

Structured output:

- one normalized in-memory record per conversation

### 2. Conversation-Level Summarization

Each conversation should be summarized independently before any project-level report generation.

Current implementation note:

- `scripts/build_project_reports.py` now uses LM Studio `response_format=json_schema` for structured outputs.
- The client falls back to `reasoning_content` when LM Studio leaves `message.content` empty.
- Default `--summary-max-chars` has been reduced to `8000` to keep the local 122B model practical.
- Final report generation now includes post-processing cleanup for LM Studio reasoning-heavy outputs.
- If the LLM still fails to produce a complete report, the pipeline falls back to a deterministic report assembled from cluster summaries.

Recommended summary schema:

```json
{
  "conversation_id": "string",
  "title": "string",
  "project": "string",
  "summary": "string",
  "key_points": ["string"],
  "decisions": ["string"],
  "open_questions": ["string"],
  "keywords": ["string"],
  "category_guess": "string"
}
```

Why this exists:

- reduces token load for later stages
- makes semantic grouping more stable
- separates extraction from final writing

### 3. Embedding and Semantic Grouping

Embeddings should be built from compressed semantic text, not raw full conversations.

Recommended embedding text composition:

- title
- summary
- keywords
- decisions

Grouping should happen inside each project only.

Target outcome:

- identify topic clusters
- merge branch-like or duplicate conversations
- reduce repetition in the final report

### 4. Cluster Summaries

For each project cluster, generate:

- cluster label
- cluster summary
- representative conversations
- repeated viewpoints
- unresolved questions

### 5. Project Report Generation

Generate one Markdown report per project using the cluster summaries as the main input.

Recommended report structure:

```md
# <Project Name> Report

## Project Overview
## Core Themes
## Key Decisions
## Repeated Patterns
## Open Questions
## Conversation Index
```

## Report Intent

The report should be a project document, not a raw transcript compression.

Primary emphasis:

- engineering direction
- design decisions
- recurring concepts
- unresolved issues

Secondary emphasis:

- product framing
- naming and messaging

## Non-Goals

- no PDF generation
- no Google Drive sync
- no cross-project clustering in the first version
- no attempt to preserve every sentence from the original chats

## Open Decisions

These are intentionally still unresolved:

1. Whether to persist intermediate summaries as JSONL only, or also write Markdown per conversation.
2. Which clustering strategy to use in v1:
   - threshold-based nearest-neighbor grouping
   - hierarchical clustering
   - simple centroid merge
3. How long each `project_report.md` should be.
4. Whether branch conversations should be explicitly marked in the final report.

## Current Validation Snapshot

- End-to-end prototype script: `scripts/build_project_reports.py`
- Validated projects:
  - `B-Roll 方程式` (1 conversation)
  - `Nano Tower` (3 conversations)
  - `Magic Vision` (9 conversations)
- Validation scope:
  - summary JSON generated successfully
  - cluster summaries generated successfully
  - `project_report.md` and `index.md` written successfully
  - multi-conversation clustering behaves plausibly, though threshold tuning is still open
  - final report cleanup successfully strips LM Studio reasoning text from generated reports
- Known remaining risks:
  - larger projects may still be slow with the current local 122B model
  - prompt tuning is still needed for higher consistency across diverse conversation styles

## Suggested v1 Implementation Order

1. Markdown parser
2. Conversation summary generator
3. Embedding builder
4. Per-project clustering
5. Project report writer
6. Index report writer

## Migration Note

This work has been moved out of `macOSAgentBot` into a dedicated workspace because the task has shifted from browser export/sync into standalone ChatGPT history analysis.
