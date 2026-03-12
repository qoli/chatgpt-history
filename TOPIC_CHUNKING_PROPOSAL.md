# Topic / Chunk Improvement Proposal

## Goal

Improve topic grouping quality by increasing the semantic purity of each chunk before embedding and clustering.

The core idea is:

`conversation/session -> structured doc -> embedding -> topic grouping -> topic abstraction -> knowledge report`

This proposal is meant to refine the current project-report pipeline rather than replace it entirely.

## Problem Statement

Raw chat sessions often contain mixed intents and noisy terms in the same conversation:

- implementation details
- side questions
- tool chatter
- repeated wording
- temporary detours

If raw or weakly-normalized text is embedded directly, one session may look semantically impure and become harder to group reliably with adjacent sessions.

## Why Structured Docs Help

### Topic Concentration

A raw conversation may mention:

- KV cache
- embeddings
- tmux
- agent behavior

But the actual dominant topic may be:

- `KV cache debugging`

Turning the session into a structured doc concentrates the semantic center before embedding.

### Lexical Normalization

Chats use inconsistent wording. A structured doc can normalize:

- `cache`
- `kv cache`
- `cache miss`

into a more stable concept such as:

- `KV cache miss`

This improves embedding consistency across sessions that discuss the same issue with different phrasing.

### Noise Removal

A structured doc can drop low-signal content:

- conversational filler
- repeated rephrasings
- off-topic branches
- execution chatter with little conceptual value

That reduces embedding noise and makes clustering more stable.

## Context Window View

This design does not require 1M context for single-session rewriting.

Typical session length is usually within the range a normal long-context model can handle. The larger context window becomes useful later when doing cross-session abstraction or project-level synthesis.

Practical interpretation:

- per-session structuring does not need ultra-long context
- cross-session topic abstraction may benefit from larger context

## Proposed Pipeline

### Step 1. Session to Structured Doc

Convert each conversation into a compact structured document.

Recommended fields:

- `title`
- `summary`
- `keywords`
- `decisions`
- `open_questions`
- `dominant_topic`
- `secondary_topics`

Recommended principle:

- `summary` should describe the main topic, not all side trails
- `keywords` should be normalized concepts, not surface words
- `dominant_topic` should force the model to state the center of gravity explicitly
- `secondary_topics` should preserve useful side themes without polluting the main summary

Example shape:

```json
{
  "title": "KV cache debugging in local agent runtime",
  "summary": "The session focused on diagnosing KV cache misses in the local runtime, isolating likely causes in prompt packing and session reuse logic.",
  "keywords": ["KV cache miss", "prompt packing", "session reuse", "local agent runtime"],
  "decisions": ["Use structured prompt boundaries for cache reuse validation"],
  "open_questions": ["Whether cache invalidation is triggered by tool-call formatting"],
  "dominant_topic": "KV cache debugging",
  "secondary_topics": ["embedding quality", "agent runtime instrumentation"]
}
```

### Step 2. Embedding

Embed the structured document rather than the raw conversation.

Recommended embedding text:

- `title`
- `dominant_topic`
- `summary`
- `keywords`
- `decisions`

This is close to the current implementation, but `dominant_topic` and stricter keyword normalization should improve topic purity further.

### Step 3. Similarity Matrix

Build pairwise similarity with cosine similarity over session embeddings.

This stage is useful even if the final grouping method stays simple, because it gives:

- threshold inspection
- cluster debugging
- outlier detection
- a basis for later graph-style grouping

### Step 4. Topic Grouping

Candidate grouping methods:

- threshold grouping
- hierarchical clustering
- k-means

Recommendation for this repo:

- keep threshold-based grouping as the initial baseline
- add similarity inspection artifacts
- evaluate hierarchical clustering next

Reason:

- k-means requires choosing `k` in advance
- threshold grouping is simple and debuggable
- hierarchical clustering is easier to inspect for evolving topic trees

### Step 5. Topic Abstraction

After grouping, summarize each topic group with an LLM.

Expected outputs per topic:

- topic label
- topic summary
- representative sessions
- repeated decisions
- unresolved questions
- possible branch relations

This becomes the bridge between clustering and the final knowledge report.

### Step 6. Knowledge Report

Build the final report from topic abstractions rather than directly from raw sessions.

Result:

- more stable project reports
- less repetition
- clearer project-level themes

## Multi-Topic Reality

A key constraint is that one session may genuinely belong to more than one topic.

This is where traditional hard clustering starts to break down.

For larger projects, a more mature pattern is:

- session summary
- keyword / concept extraction
- concept graph or topic graph
- topic-level synthesis

Practical implication:

- short term: keep one primary topic per session for simplicity
- medium term: allow `secondary_topics`
- longer term: consider graph-based grouping instead of forcing every session into exactly one cluster

## Mapping to Current Pipeline

Current repo pipeline already has this backbone:

- conversation parsing
- per-conversation summary
- embedding
- per-project clustering
- cluster summary
- final report

What is already aligned:

- session-level preprocessing exists
- embedding uses compressed semantic text instead of raw transcript
- clustering is already per-project
- topic abstraction already exists in the form of cluster summaries

What this proposal adds:

- stronger session schema centered on `dominant_topic`
- better keyword normalization
- explicit handling of secondary topics
- similarity inspection as a first-class artifact
- a path from hard clustering toward topic graphs

## Recommended v1.1 Changes

These changes are realistic without rewriting the whole system.

### 1. Strengthen the Session Summary Schema

Add fields:

- `dominant_topic`
- `secondary_topics`
- `normalized_keywords`

Keep existing fields:

- `summary`
- `key_points`
- `decisions`
- `open_questions`

### 2. Change Embedding Input Composition

Use:

- `title`
- `dominant_topic`
- `summary`
- `normalized_keywords`
- `decisions`

Avoid feeding too much side-topic material into the embedding text.

### 3. Emit a Similarity Debug Artifact

For each project, write a file such as:

- `similarities.json`

Useful contents:

- session pairs above threshold
- nearest neighbors per session
- cluster assignment rationale

This will make threshold tuning much easier.

### 4. Preserve Branch Signal Explicitly

If the original title or metadata indicates a branch conversation, record it as metadata instead of letting it disappear into summary text.

Suggested fields:

- `is_branch`
- `parent_topic_hint`

### 5. Keep Topic Grouping Simple First

Do not jump straight to a concept graph for v1.1.

A realistic sequence is:

1. better structured docs
2. better embedding text
3. better threshold tuning
4. inspect failure cases
5. only then consider graph-based grouping

## Feasibility Assessment

### Highly Feasible Now

- strengthen the structured summary schema
- normalize keywords more aggressively
- update embedding text composition
- output similarity diagnostics
- mark branch conversations explicitly

These fit the current code structure well.

### Feasible With Moderate Work

- hierarchical clustering experiments
- soft assignment via primary plus secondary topic hints
- language normalization for mixed Chinese/English projects

These need evaluation logic and better debug outputs, but do not require a full redesign.

### Better Deferred

- full topic graph construction
- multi-label session assignment as the default grouping model
- cross-project knowledge graph

These are good directions, but they raise modeling and debugging complexity significantly.

## Recommended Decision

Adopt this proposal as a v1.1 refinement of the existing pipeline:

- keep `conversation -> summary -> embedding -> cluster -> report`
- improve the `summary` into a more topic-centered structured doc
- add explicit `dominant_topic` and normalized keywords
- treat branch and multi-topic behavior as metadata first, not as a full graph problem yet

This gives a meaningful quality gain without destabilizing the current prototype.

## Open Questions

1. Should `dominant_topic` be fully free-form, or chosen from a controlled vocabulary per project?
2. Should `secondary_topics` affect embedding, or only be stored for later graph analysis?
3. Should branch sessions remain merged into primary topic clusters, or appear as explicitly marked subtopics in reports?
4. At what project size should the pipeline switch from hard clustering to concept-graph assistance?
