# A/B Turn Chunking Proposal

## Goal

Use simple turn-pair chunks for embedding and topic discovery without relying on sliding windows.

Core idea:

`session -> A/B turn chunks -> embedding -> similarity grouping -> topic synthesis`

This design is intentionally minimal and optimized for engineering stability.

## Core Claim

If the target is:

- topic discovery
- concept extraction
- clustering similar discussions

then sliding window chunking is usually unnecessary.

For this use case, the natural chunk unit is one User turn plus one Assistant turn.

## Chunk Definition

Each chunk is a single User to Assistant pair:

```text
User: ...
Assistant: ...
```

Example:

```text
User: Why does KV cache improve inference speed?
Assistant: KV cache avoids recomputing attention key/value states for prior tokens.
```

That full pair is one chunk.

## Chunking Algorithm

Given a session:

```text
U1
A1
U2
A2
U3
A3
```

Chunk as:

- `chunk_1 = U1 + A1`
- `chunk_2 = U2 + A2`
- `chunk_3 = U3 + A3`

Recommended rule:

- the default chunk is `(user_message, assistant_message)`

## Handling Irregular Turns

Real conversations may contain incomplete or uneven sequences such as:

```text
User
User
Assistant
```

Recommended repair rule:

- merge consecutive User messages until the next Assistant appears
- pair the merged User text with that next Assistant

Examples:

```text
U1
U2
A1
```

becomes:

- `chunk_1 = (U1 + U2) + A1`

If a final User message has no Assistant response:

- either drop it from embedding
- or store it as an incomplete chunk with `assistant = ""`

For this repo, dropping incomplete tail turns is the safer default for v1.

## What to Embed

Do not embed only the Assistant reply.

Recommended embedding text:

- User message
- Assistant reply

Reason:

- the question contains intent
- the answer contains resolution
- the pair together captures the full micro-topic

Example embedding text:

```text
Question:
Why does KV cache improve inference speed?

Answer:
KV cache avoids recomputing attention key/value states for prior tokens.
```

## Recommended Metadata

Each chunk should preserve enough information to trace back to the original session:

```json
{
  "session_id": "string",
  "turn_id": 3,
  "user": "...",
  "assistant": "...",
  "embedding": []
}
```

Recommended additional fields:

- `project`
- `conversation_id`
- `chunk_id`
- `create_time`
- `update_time`
- `source_path`
- `is_incomplete`

This enables:

- topic -> chunk -> session traceability
- cluster debugging
- report backreferences

## Why Sliding Window Is Not Required

Sliding windows are more useful when the goal is:

- retrieval over long documents
- preserving multi-paragraph continuity
- RAG recall optimization

This proposal targets:

- topic discovery
- concept clustering
- micro-topic mapping

In that setting, one Q/A pair is often already semantically complete.

Example:

```text
Q: What is KV cache?
A: KV cache stores prior attention key/value tensors.
```

That is already a valid micro-topic unit.

## Cross-Turn Topic Continuity

Some topics span multiple turns:

```text
U1: What is KV cache?
A1: ...
U2: Why does cache miss happen?
A2: ...
U3: Why does LM Studio fail to hit cache?
A3: ...
```

This produces three chunks:

- KV cache explanation
- cache miss
- LM Studio cache behavior

Even without sliding windows, these chunks should often cluster together naturally because their embeddings remain semantically adjacent.

This is the key practical argument for keeping the method simple.

## Normalization Trick

Before embedding, wrap the pair into a stable template:

```text
Question:
...

Answer:
...
```

This helps because:

- structure is consistent across chunks
- intent and response roles stay explicit
- embedding inputs become easier to compare

## Full Pipeline

Recommended pipeline:

1. parse session messages
2. build turn-pair chunks
3. normalize each chunk into `Question / Answer` text
4. generate embeddings
5. compute similarity
6. cluster related chunks
7. run LLM topic synthesis over each cluster

## Expected Output Shape

Example chunk record:

```json
{
  "project": "eisonAI",
  "conversation_id": "abc123",
  "chunk_id": "abc123-turn-03",
  "turn_id": 3,
  "user": "Why does KV cache improve inference speed?",
  "assistant": "KV cache avoids recomputing attention key/value states for prior tokens.",
  "normalized_text": "Question:\nWhy does KV cache improve inference speed?\n\nAnswer:\nKV cache avoids recomputing attention key/value states for prior tokens.",
  "is_incomplete": false
}
```

## Benefits

### Simple and Stable

- easy to implement
- easy to debug
- easy to explain

### Fine-Grained Topic Discovery

- one session can produce multiple micro-topics
- concept drift inside a long conversation becomes visible
- clusters can form around precise technical questions

### Better Than Session-Level Embedding for Mixed Conversations

If one conversation covers several subjects, session-level embedding may blur them together.

Turn-pair chunking avoids that by separating:

- cache questions
- embedding questions
- agent questions

into different embedding units.

## Tradeoffs

### Loses Some Long-Range Context

A single A/B pair may miss:

- earlier assumptions
- prior definitions
- later refinements

This is the main limitation.

### Can Over-Split One Coherent Topic

A longer topic may become many small chunks.

This is acceptable if the downstream clustering step is strong enough to re-group them.

### Requires Careful Irregular-Turn Repair

Chat exports do not always alternate perfectly.

The chunker must handle:

- consecutive user turns
- consecutive assistant turns
- incomplete tails

## Fit With the Current Repo

This proposal fits the existing project well if the goal shifts from:

- project report generation from full conversations

toward:

- finer topic discovery across many turns

What maps cleanly to the current codebase:

- existing conversation parsing
- existing embedding endpoint
- existing cosine similarity logic
- existing cluster summarization pattern

What would need to change:

- parse conversation bodies into message-level turns
- introduce a new chunk data model
- embed chunks instead of, or in addition to, session summaries
- cluster chunks per project
- synthesize topics from chunk clusters rather than only session clusters

## Recommended Use Cases

This design is a strong fit for:

- topic discovery inside mixed conversations
- concept extraction
- building an explorable knowledge map
- identifying repeated technical questions across sessions

This design is a weaker fit for:

- polished session-level project reports
- preserving decision chronology
- summarizing a project's strategic direction from long conversations alone

## Best Positioning

This proposal should be treated as:

- a chunk-level topic discovery pipeline

not necessarily as:

- a full replacement for session-level structured summaries

In practice, the strongest architecture may be hybrid:

- session-level structured docs for project reports
- A/B turn chunks for fine-grained topic mining

## Feasibility Assessment

### Highly Feasible

- build a turn-pair chunker
- normalize chunks into `Question / Answer`
- embed all chunks
- cluster chunks per project
- generate topic summaries from chunk clusters

### Moderate Complexity

- robustly parse message boundaries from exported Markdown
- connect chunk clusters back to session-level reports
- deduplicate near-identical assistant answers across related turns

### Main Engineering Risk

The biggest risk is not the chunking itself. It is whether the exported Markdown format preserves message boundaries cleanly enough for reliable turn extraction.

If message boundary parsing is weak, the whole approach becomes fragile.

## Recommended Decision

Adopt this as a separate analysis mode, not as the only pipeline.

Recommended architecture:

- keep the current session-level structured-doc pipeline for project reports
- add A/B turn chunking as a second path for topic discovery and concept mining

This gives:

- stable project summaries at the session level
- higher-resolution topic signals at the chunk level

## Open Questions

1. Does the exported Markdown preserve explicit User / Assistant boundaries consistently enough?
2. Should incomplete final User turns be dropped or stored?
3. Should chunk clustering happen per project only, or across all projects when doing concept discovery?
4. Should session-level and chunk-level clusters eventually be merged into one report, or remain separate artifacts?
