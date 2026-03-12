# TODO

## Immediate

- Review `SPEC.md` and confirm the desired report style.
- Decide whether intermediate conversation summaries should be stored as JSONL only or also as Markdown.
- Rename legacy scripts that still mention PDF / Google Drive if they will remain part of this repo.
- Decide whether fallback-generated reports should be kept as-is or marked explicitly in the output.

## Pipeline v1

- Done: build a Markdown conversation parser for `browser_control/output/chatgpt_markdown/`.
- Done: define the conversation summary JSON schema used by the pipeline.
- Done: implement conversation-level summarization with the local LLM endpoint.
- Done: implement embedding generation with the local embedding endpoint.
- Done: implement per-project semantic grouping.
- Done: implement project report generation for one `project_report.md` per project.
- Done: implement `index.md` generation across all project reports.
- Done: validate the pipeline on more than one conversation per project.
- Done: rebuild `index.md` from on-disk reports so partial reruns do not wipe prior entries.
- Next: tune prompts and report size for larger projects.

## Clustering And Report Design

- Choose the clustering strategy for v1.
- Decide how to treat branch conversations in clustering and reporting.
- Decide the desired report length range for small, medium, and large projects.
- Decide whether repeated ideas should be collapsed into one theme section or preserved as timeline notes.

## Validation

- Done: run the pipeline on a small project first using `B-Roll_方程式` with 1 conversation.
- Done: validate that summaries preserve concrete decisions and open questions on the minimal `B-Roll_方程式` run.
- Done: validate that clustering produces a usable cluster summary on the minimal `B-Roll_方程式` run.
- Done: validate that the final report is readable without opening the original conversation on the minimal `B-Roll_方程式` run.
- Done: validate a multi-conversation project using `Nano Tower` with 3 conversations.
- Done: verify that `Nano Tower` clustering remains plausible across multiple distinct topics.
- Done: validate a medium project using `Magic Vision` with 9 conversations.
- Done: add report post-processing cleanup for LM Studio reasoning-heavy outputs.
- Done: add deterministic fallback report generation when LLM report output is incomplete.
- Next: tune clustering threshold so conceptually adjacent conversations are merged when appropriate.
- Next: validate on a larger project such as `HLN Machine` or `observo`.
- Next: decide whether reports should be normalized to one language when cluster summaries mix Chinese and English.

## Future

- Add incremental caching for conversation summaries and embeddings.
- Add a way to re-run one project without rebuilding everything.
- Consider a machine-readable manifest for all generated reports.
- Consider cross-project analysis only after per-project reports are stable.
