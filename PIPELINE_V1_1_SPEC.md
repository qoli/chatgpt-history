# Pipeline v1.1 Spec

## Status

This document defines the next iteration of the local project-history pipeline.

It extends the current session-level report pipeline with a second embedding path based on A/B turn chunks.

The design decisions already agreed for v1.1 are:

- build `session-level` and `chunk-level` indexes separately
- keep final topic synthesis centered on `session clusters`
- attach `chunk clusters` back to `session clusters` as evidence

## Goal

Improve topic quality and report quality by combining:

- high-level session abstraction
- fine-grained turn-pair topic mining

without collapsing both granularities into one clustering space.

## Core Design

Two parallel semantic layers exist in the same project pipeline:

### Layer 1. Session Layer

Purpose:

- capture the dominant topic of each conversation
- support project-level topic grouping
- drive final report generation

Unit:

- one structured document per conversation

Output:

- session summaries
- session embeddings
- session clusters

### Layer 2. Chunk Layer

Purpose:

- capture micro-topics inside conversations
- expose repeated concepts that are hidden by session-level averaging
- provide evidence for session clusters

Unit:

- one A/B turn pair per chunk

Output:

- chunk records
- chunk embeddings
- chunk clusters

## Final Report Principle

The final report is generated from `session clusters`, not directly from `chunk clusters`.

`chunk clusters` are used as:

- evidence
- recurring concept indicators
- subtopic signals
- supporting detail for synthesis

This keeps the report readable as a project document rather than turning it into a list of fragmented Q/A pairs.

## Full Pipeline

```text
conversations
  -> structured session docs
  -> session embeddings
  -> session clustering

conversations
  -> A/B turn chunks
  -> chunk embeddings
  -> chunk clustering

chunk clusters
  -> attach to session clusters

session clusters + attached chunk evidence
  -> final topic synthesis
  -> project report
```

## Input

Primary input remains:

- `browser_control/output/chatgpt_markdown/`

One Markdown file still represents one exported conversation.

## Session Layer Spec

### Session Structured Doc

Each conversation should first become a structured summary record.

Recommended schema:

```json
{
  "conversation_id": "string",
  "project": "string",
  "title": "string",
  "summary": "string",
  "key_points": ["string"],
  "decisions": ["string"],
  "open_questions": ["string"],
  "dominant_topic": "string",
  "secondary_topics": ["string"],
  "normalized_keywords": ["string"],
  "category_guess": "string",
  "create_time": "string",
  "update_time": "string",
  "source_path": "string",
  "source_url": "string"
}
```

### Session Embedding Text

Recommended composition:

- `title`
- `dominant_topic`
- `summary`
- `normalized_keywords`
- `decisions`

This embedding is intended to represent the semantic center of the conversation.

### Session Clustering

Clustering should remain per-project for v1.1.

Recommended default:

- greedy threshold clustering as the baseline

Evaluation option:

- hierarchical clustering as the next experiment

## Chunk Layer Spec

### Chunk Definition

One chunk is one User to Assistant turn pair.

Canonical structure:

```text
Question:
<user message>

Answer:
<assistant message>
```

### Chunking Rules

Default case:

- pair one User turn with the following Assistant turn

Repair case:

- merge consecutive User turns until the next Assistant appears

Incomplete tail:

- drop trailing incomplete chunks for v1.1 by default

### Chunk Schema

```json
{
  "project": "string",
  "conversation_id": "string",
  "chunk_id": "string",
  "turn_id": 3,
  "user": "string",
  "assistant": "string",
  "normalized_text": "string",
  "is_incomplete": false,
  "create_time": "string",
  "update_time": "string",
  "source_path": "string"
}
```

### Chunk Embedding Text

Use:

```text
Question:
...

Answer:
...
```

Do not embed only the Assistant text.

### Chunk Clustering

Chunk clustering should also remain per-project for v1.1.

Reason:

- current system is project-centric
- debugging is easier
- cross-project concept unification can be deferred

## Index Separation

Session and chunk indexes must remain separate.

### Session Index

Purpose:

- support report generation
- support project-level topic abstraction
- preserve high-level conversation structure

Suggested artifact:

- `conversation_summaries.jsonl`

### Chunk Index

Purpose:

- support topic mining
- support repeated-concept discovery
- support evidence lookup

Suggested artifact:

- `ab_chunks.jsonl`

These two indexes must not be mixed into one clustering input by default.

## Chunk-to-Session Attachment

Chunk clusters should be attached back to session clusters after both clustering stages are complete.

### Attachment Goal

For each chunk cluster, determine which session cluster it best supports.

### Recommended Signals

Use two signals together:

#### 1. Source-Session Vote

Count which session cluster owns the sessions that produced the chunks in the chunk cluster.

This should be the primary signal.

#### 2. Centroid Similarity

Compare:

- chunk cluster centroid
- session cluster centroid

This should be the secondary signal for tie-breaking or validation.

### Attachment Rule

Recommended first-pass rule:

1. assign each conversation to exactly one session cluster
2. for each chunk cluster, count the originating session clusters of its chunks
3. choose the winning session cluster by majority vote
4. if the vote is weak or tied, use centroid similarity to break ties
5. record attachment confidence

### Attachment Output

Suggested schema:

```json
{
  "chunk_cluster_id": "string",
  "session_cluster_id": "string",
  "source_vote": {
    "session_cluster_1": 5,
    "session_cluster_2": 2
  },
  "centroid_similarity": 0.81,
  "confidence": "high"
}
```

## Topic Synthesis

Final synthesis should be driven by the session cluster.

For each session cluster, the synthesis stage should consume:

- session cluster label
- session cluster summary
- key decisions
- open questions
- representative conversations
- attached chunk clusters

The chunk evidence should enrich the report with:

- recurring concepts
- repeated technical questions
- supporting subtopics
- sharper terminology

## Report Structure

Recommended report shape remains:

```md
# <Project Name> Report

## Project Overview
## Core Themes
## Key Decisions
## Repeated Patterns
## Open Questions
## Conversation Index
```

Possible v1.1 enhancement:

- each Core Theme section may include a short `Evidence Concepts` block derived from attached chunk clusters

Example:

```md
### Theme: KV Cache Debugging

Theme summary...

Evidence Concepts:
- cache miss
- LM Studio cache behavior
- prompt packing
```

## Output Layout

Recommended output layout:

```text
browser_control/output/project_reports/
  index.md
  <project_name>/
    project_report.md
    conversation_summaries.jsonl
    session_clusters.json
    ab_chunks.jsonl
    chunk_clusters.json
    chunk_to_session_cluster_links.json
```

## Debug Artifacts

To make tuning practical, write explicit debug outputs.

Recommended additions:

- `session_similarities.json`
- `chunk_similarities.json`

Useful contents:

- nearest neighbors
- pairs above threshold
- cluster membership
- attachment confidence

## Scope for v1.1

Included:

- stronger session structured docs
- A/B turn chunk extraction
- separate session and chunk indexes
- per-project chunk clustering
- chunk-to-session attachment
- report synthesis with chunk evidence

Not included:

- cross-project chunk clustering
- graph-native topic modeling
- soft multi-label session ownership
- full knowledge graph generation

## Recommended Implementation Order

1. strengthen session summary schema
2. add turn parser and A/B chunk extraction
3. write `ab_chunks.jsonl`
4. add chunk embedding and chunk clustering
5. add chunk-to-session attachment output
6. update report synthesis to consume attached chunk evidence
7. add similarity debug artifacts

## Success Criteria

v1.1 is successful if:

- session clusters remain readable and stable
- chunk clusters reveal useful recurring micro-topics
- chunk evidence sharpens final reports instead of adding noise
- topic drift inside long conversations becomes more visible
- report quality improves without losing project-level coherence

## Open Questions

1. How reliable are User / Assistant boundaries in the exported Markdown format?
2. Should chunk evidence appear only in debug artifacts, or also visibly in final reports?
3. What confidence threshold should prevent a weak chunk cluster from attaching to any session cluster?
4. At what project size should graph-based topic modeling become necessary?
