# ChatGPT History Analysis Spec

## Status

The current pipeline is no longer a flat project-summary prototype. The implemented flow in `scripts/build_project_reports.py` is now a structured, multi-layer analysis pipeline:

- session-level understanding is the primary topic layer
- A/B turn-pair chunks provide supporting evidence
- project reports are rendered from intermediate structured knowledge, not written directly as one opaque Markdown prompt

The remaining work is quality tuning, larger-project validation, and better evidence abstraction.

## Goal

Build a local pipeline that reads exported ChatGPT project conversations from Markdown and produces one structured, traceable technical retrospective per project.

The report should:

- discover recurring concepts and topics across conversations
- keep topic derivation anchored in whole-session understanding
- use turn-pair chunks as evidence, not as the main report driver
- separate concepts, architecture, decisions, patterns, and open questions
- remain traceable back to original conversations

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

Raw conversation files are read-only inputs. The pipeline does not modify them.

## Local Model Endpoints

### Embedding API

- Base URL: `CHATGPT_HISTORY_EMBEDDING_BASE_URL` or default `http://127.0.0.1:1234/v1`
- Model: `text-embedding-qwen3-0.6b-text-embedding`

### LLM API

- Base URL: `CHATGPT_HISTORY_LLM_BASE_URL` or default `http://127.0.0.1:1234/v1`
- Model: `qwen3.5-122b-a10b-text-mlx`

Implementation note:

- structured chat calls first try `response_format=json_schema`
- if LM Studio rejects schema output, the client falls back to plain JSON prompting instead of hard-failing

## Output Layout

Per-project outputs are written under:

```text
browser_control/output/project_reports/
  index.md
  <project_name>/
    project_report.md
    conversation_summaries.jsonl
    clusters.json
    session_clusters.json
    ab_chunks.jsonl
    chunk_clusters.json
    chunk_to_session_cluster_links.json
    project_knowledge.json
    timeline.json
```

Artifact roles:

- `conversation_summaries.jsonl`
  Session-level structured summaries.
- `clusters.json`
  Session cluster summaries before chunk evidence is attached.
- `session_clusters.json`
  Enriched session clusters used as the main topic layer for the report.
- `ab_chunks.jsonl`
  A/B turn-pair chunk records extracted from the original conversation markdown.
- `chunk_clusters.json`
  Chunk-level evidence groupings.
- `chunk_to_session_cluster_links.json`
  Attachment map from chunk clusters back to session clusters.
- `project_knowledge.json`
  Structured project synthesis used to render the final report.
- `timeline.json`
  Structured event timeline derived from project knowledge and topic records.
- `project_report.md`
  Final deterministic report rendered from structured intermediate artifacts.
- `index.md`
  Aggregate index rebuilt from report directories on disk.

## Core Design

### Session Layer

The session layer is the main topic-discovery layer.

- one conversation becomes one structured session summary
- session summaries are embedded and clustered per project
- cluster summaries become the primary topic records
- final synthesis is session-first

This is where dominant topics and recurring project-level themes should come from.

### Chunk Layer

The chunk layer is an evidence layer.

- each chunk is one `User -> Assistant` turn pair
- chunks are embedded separately from sessions
- chunk clusters discover finer recurring concepts and question patterns
- chunk clusters are attached back to session clusters as supporting evidence

This layer should improve topic purity and recall without replacing session-level understanding.

### Synthesis Rule

The report is generated from structured knowledge assembled across layers:

- session clusters define the main topics
- chunk clusters provide evidence concepts and recurring subtopics
- project knowledge organizes the final report sections
- timeline entries capture evolution and turning points

## Pipeline

### 1. Parse Markdown Conversations

For each Markdown file:

- parse frontmatter and metadata
- extract conversation content
- preserve relative source path for traceability
- keep conversation order and timestamps

Output:

- one normalized in-memory conversation record per file

### 2. Session-Level Summarization

Each conversation is summarized independently before project-level synthesis.

Current summary schema includes structured fields such as:

- `summary`
- `key_points`
- `decisions`
- `open_questions`
- `keywords`
- `category_guess`

Why this stage exists:

- reduces token load for later stages
- normalizes terminology before embedding
- gives the pipeline a stable semantic representation per conversation

### 3. Session Embedding and Per-Project Clustering

Embeddings are built from compressed semantic text rather than raw conversation bodies.

Session clustering happens per project only.

Current outcome:

- related sessions are grouped into topic clusters
- cluster summaries produce labels, concepts, architecture ideas, decisions, patterns, and open questions

### 4. Topic-Level Session Synthesis

Each session cluster is summarized into a structured topic record.

These topic records are stored in `clusters.json` and then enriched into `session_clusters.json`.

This is the main source for:

- report topics
- topic-level concept separation
- project-level synthesis

### 5. A/B Turn-Pair Chunk Extraction

Each conversation is also parsed into turn-pair chunks:

- `User + Assistant`
- incomplete runs like `User, User, Assistant` are repaired by pairing the last pending user turn with the next assistant turn

Chunk text is normalized into a stable embedding format:

```text
Question:
...

Answer:
...
```

### 6. Chunk Embedding and Evidence Grouping

Chunks are embedded independently from sessions and clustered per project.

Current role of chunk clusters:

- discover recurring micro-topics across sessions
- provide evidence concepts
- improve traceability from report themes back to concrete turns

Chunk clusters are not the primary report topics.

### 7. Chunk-to-Session Attachment

Chunk clusters are attached back to session clusters.

Current attachment design combines:

- source-session ownership
- centroid similarity

Result:

- `session_clusters.json` becomes the enriched topic layer with attached evidence
- report synthesis stays session-first while still using chunk-level support

### 8. Project-Level Knowledge Synthesis

The report is not generated directly from raw cluster text.

Instead, the pipeline builds `project_knowledge.json`, which separates:

- concepts
- architectural ideas
- engineering decisions
- recurring patterns
- open questions

This can be produced in two ways:

- full synthesis through the local LLM
- deterministic fallback synthesis when `--fallback-report-only` is used or when the LLM path fails

### 9. Timeline Generation

The pipeline builds `timeline.json` from project knowledge and topic records.

Timeline design:

- event-oriented, not transcript-oriented
- based primarily on session-level topics
- chunk evidence supports events but does not drive them

### 10. Deterministic Report Rendering

The final Markdown report is rendered from:

- `project_knowledge.json`
- `session_clusters.json`
- `timeline.json`
- original conversation metadata

This keeps the final report traceable and stable even when the final LLM Markdown-writing step is skipped.

## Final Report Structure

The current report renderer produces:

```md
# <Project Name> Report

## Project Overview
## Concepts
## Architectural Ideas
## Engineering Decisions
## Recurring Patterns
## Open Questions
## Key Timeline
## Topic Map
## Conversation Index
```

This is intended to read like a distilled technical retrospective, not a transcript summary.

## Traceability Rules

Traceability is a core requirement.

The pipeline preserves it by:

- keeping `conversation_id`, title, timestamps, and source path in intermediate records
- recording cluster members in session topic payloads
- attaching chunk evidence back to session clusters instead of flattening it away
- rendering `Topic Map` and `Conversation Index` sections in the final report

The existing conversation index is maintained. The pipeline rebuilds `index.md` from on-disk project outputs.

## Run Commands

### Stable Full Rebuild for All Projects

```bash
cd <repo-root>
python3 scripts/build_project_reports.py --fallback-report-only --sleep-seconds 0.05
```

### Rebuild Only Final Reports

```bash
cd <repo-root>
python3 scripts/build_project_reports.py --report-only
```

### Force Full Regeneration

```bash
cd <repo-root>
python3 scripts/build_project_reports.py --force --fallback-report-only --sleep-seconds 0.05
```

### Clean Rebuild

```bash
cd <repo-root>
rm -rf browser_control/output/project_reports
python3 scripts/build_project_reports.py --force --fallback-report-only --sleep-seconds 0.05
```

### Rebuild One Project

```bash
cd <repo-root>
python3 scripts/build_project_reports.py --project 'Nano Tower' --fallback-report-only --sleep-seconds 0.05
python3 scripts/build_project_reports.py --project 'Nano Tower' --report-only
```

## Constraints

- Do not modify raw conversation files.
- Keep the project-level `index.md`.
- Avoid relying on prompt structure alone for report organization.
- Prefer intermediate structured artifacts over direct Markdown generation.
- Keep clustering per project; cross-project clustering is not part of the current pipeline.

## Non-Goals

- no PDF generation
- no Google Drive sync
- no cross-project topic clustering in the current implementation
- no requirement to preserve every sentence from the original chats
- no transcript-style timeline

## Current Validation Snapshot

Validated implementation: `scripts/build_project_reports.py`

Validated projects:

- `B-Roll 方程式`
- `Nano Tower`
- `Magic Vision`
- `Telegram AI Workspace`

Validated capabilities:

- session-level conversation summaries
- per-project session embedding and clustering
- A/B turn-pair chunk extraction
- per-project chunk embedding and clustering
- chunk-to-session evidence attachment
- `project_knowledge.json` generation
- `timeline.json` generation
- deterministic `project_report.md` rendering
- `--report-only` report regeneration
- schema-output failures no longer hard-stop the pipeline

## Remaining Open Work

1. Upgrade chunk evidence from question excerpts to better chunk-cluster abstractions.
2. Tune clustering thresholds on larger and noisier projects.
3. Compress and deduplicate timeline events so only turning points remain.
4. Validate the new report structure on larger projects such as `HLN Machine`, `Syncnext`, `eisonAI`, and `observo`.
5. Normalize mixed Chinese/English wording in synthesized outputs where needed.
  - multi-conversation clustering behaves plausibly, though threshold tuning is still open
  - final report cleanup successfully strips LM Studio reasoning text from generated reports
  - deterministic fallback report path works when LLM report output is incomplete
- Known remaining risks:
  - larger projects may still be slow with the current local 122B model
  - prompt tuning is still needed for higher consistency across diverse conversation styles
  - fallback reports are structurally complete but may be more mechanical and mixed-language than LLM-authored reports

## Suggested v1 Implementation Order

1. Markdown parser
2. Conversation summary generator
3. Embedding builder
4. Per-project clustering
5. Project report writer
6. Index report writer

## Migration Note

This work has been moved out of `macOSAgentBot` into a dedicated workspace because the task has shifted from browser export/sync into standalone ChatGPT history analysis.
