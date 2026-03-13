# TODO

## Current Focus

- Improve `chunk_clusters.json` evidence quality so session topics attach synthesized concepts instead of mostly user-question excerpts.
- Compress `timeline.json` into clearer turning points with less repeated evidence.
- Validate the new report structure on larger projects such as `HLN Machine`, `Syncnext`, `eisonAI`, and `observo`.
- Tune session and chunk clustering thresholds on noisier projects.
- Normalize mixed Chinese/English wording in project knowledge and final reports where needed.

## Implemented

- Done: Markdown parser for `browser_control/output/chatgpt_markdown/`.
- Done: session-level conversation summary schema and cache in `conversation_summaries.jsonl`.
- Done: session embeddings and per-project session clustering.
- Done: structured session topic records in `clusters.json` and enriched topic records in `session_clusters.json`.
- Done: A/B turn-pair chunk extraction into `ab_chunks.jsonl`.
- Done: chunk embeddings and per-project chunk clustering into `chunk_clusters.json`.
- Done: chunk-to-session attachment in `chunk_to_session_cluster_links.json`.
- Done: structured project synthesis in `project_knowledge.json`.
- Done: structured timeline generation in `timeline.json`.
- Done: deterministic `project_report.md` rendering from intermediate structured artifacts.
- Done: preserve and rebuild the project-level `index.md`.
- Done: `--fallback-report-only` mode for stable local rebuilds.
- Done: `--report-only` mode to rebuild final reports without rerunning analysis.
- Done: LM Studio schema fallback so `400` schema failures do not hard-stop the pipeline.

## Validation

- Done: validated on `B-Roll 方程式`.
- Done: validated on `Nano Tower`.
- Done: validated on `Magic Vision`.
- Done: validated on `Telegram AI Workspace`.
- Next: run the new structured report flow on larger projects and inspect report quality, not just artifact creation.
- Next: compare `--fallback-report-only` outputs with full LLM project knowledge synthesis on the same projects.

## Documentation

- Done: merged the newer session-first, chunk-evidence design into `SPEC.md`.
- Done: removed superseded design docs that have already been absorbed into the main spec.
- Next: decide whether `AB_TURN_CHUNKING_PROPOSAL.md` should remain as a separate rationale document or also be folded into `SPEC.md`.
- Next: consider adding a short `README.md` as a repo entry point.

## Future

- Add incremental caching for chunk embeddings and higher-level synthesis stages, not only conversation summaries.
- Add machine-readable manifest output across generated project reports.
- Add similarity/debug artifacts to make clustering threshold tuning easier.
- Evaluate hierarchical clustering or graph-based grouping only after current per-project reports stabilize.
- Consider cross-project analysis only after per-project retrospective quality is reliable.
