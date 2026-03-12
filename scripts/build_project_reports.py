#!/usr/bin/env python3
"""Build one local LLM-generated report per ChatGPT project."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import textwrap
import time
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DIR = PROJECT_DIR / "browser_control" / "output" / "chatgpt_markdown"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "browser_control" / "output" / "project_reports"

EMBEDDING_BASE_URL = "http://ronnie-mac-studio.local:1234/v1"
EMBEDDING_MODEL = "text-embedding-qwen3-0.6b-text-embedding"
LLM_BASE_URL = "http://ronnie-mac-studio.local:1234/v1"
LLM_MODEL = "qwen3.5-122b-a10b-text-mlx"
LLM_API_KEY = os.environ.get("CHATGPT_HISTORY_LLM_API_KEY", "")

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n\n?(.*)\Z", re.DOTALL)
FIELD_RE = re.compile(r"^([A-Za-z0-9_]+):\s*(.+?)\s*$")
UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|]+')
DISALLOWED_FILENAME_CHAR_RE = re.compile(r"[^0-9A-Za-z_\-\u3400-\u4dbf\u4e00-\u9fff]+")
UNDERSCORE_RUN_RE = re.compile(r"_+")
REQUIRED_REPORT_HEADERS = [
    "## Project Overview",
    "## Core Themes",
    "## Key Decisions",
    "## Repeated Patterns",
    "## Open Questions",
]


class PipelineError(RuntimeError):
    """Raised when the report pipeline fails."""


@dataclass
class ConversationRecord:
    project: str
    title: str
    conversation_id: str
    create_time: str
    update_time: str
    source_url: str
    body: str
    source_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build one report per ChatGPT project.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR), help="Directory containing exported markdown.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for generated reports.")
    parser.add_argument(
        "--project",
        action="append",
        default=[],
        help="Only process projects whose names contain this substring. Can be repeated.",
    )
    parser.add_argument(
        "--limit-conversations",
        type=int,
        default=None,
        help="Only process the first N conversations per matched project after sorting by update time descending.",
    )
    parser.add_argument(
        "--cluster-threshold",
        type=float,
        default=0.72,
        help="Cosine similarity threshold used for greedy per-project clustering.",
    )
    parser.add_argument(
        "--summary-max-chars",
        type=int,
        default=8000,
        help="Maximum conversation body characters sent to the conversation summarizer.",
    )
    parser.add_argument("--force", action="store_true", help="Rebuild summaries and reports even if cache exists.")
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.0,
        help="Optional delay after each model API request.",
    )
    return parser.parse_args()


def sanitize_filename(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = UNSAFE_FILENAME_RE.sub("_", normalized)

    pieces: List[str] = []
    for char in normalized:
        if unicodedata.combining(char):
            continue
        if DISALLOWED_FILENAME_CHAR_RE.fullmatch(char):
            pieces.append("_")
            continue
        pieces.append(char)

    cleaned = "".join(pieces).strip().strip(".")
    cleaned = UNDERSCORE_RUN_RE.sub("_", cleaned)
    cleaned = cleaned.strip("_")
    return cleaned or "untitled"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    ensure_parent(path)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_frontmatter(markdown: str) -> tuple[Dict[str, Any], str]:
    match = FRONTMATTER_RE.match(markdown)
    if not match:
        raise PipelineError("Markdown file is missing frontmatter block.")
    frontmatter_text = match.group(1)
    body = match.group(2)

    metadata: Dict[str, Any] = {}
    for line in frontmatter_text.splitlines():
        field_match = FIELD_RE.match(line)
        if not field_match:
            continue
        key, raw_value = field_match.groups()
        try:
            metadata[key] = json.loads(raw_value)
        except json.JSONDecodeError:
            metadata[key] = raw_value
    return metadata, body


def load_conversation(path: Path) -> ConversationRecord:
    metadata, body = parse_frontmatter(read_text(path))
    return ConversationRecord(
        project=str(metadata.get("project") or path.parent.name),
        title=str(metadata.get("title") or path.stem),
        conversation_id=str(metadata.get("conversation_id") or ""),
        create_time=str(metadata.get("create_time") or ""),
        update_time=str(metadata.get("update_time") or ""),
        source_url=str(metadata.get("source_url") or ""),
        body=body.strip(),
        source_path=path,
    )


def sorted_project_conversations(input_dir: Path, patterns: Sequence[str], limit: Optional[int]) -> Dict[str, List[ConversationRecord]]:
    if not input_dir.exists():
        raise PipelineError(f"Input directory does not exist: {input_dir}")

    lowered = [pattern.casefold() for pattern in patterns]
    projects: Dict[str, List[ConversationRecord]] = {}
    for path in sorted(input_dir.glob("*/*.md")):
        record = load_conversation(path)
        if lowered and not any(pattern in record.project.casefold() for pattern in lowered):
            continue
        projects.setdefault(record.project, []).append(record)

    if not projects:
        raise PipelineError("No matching markdown conversations found.")

    for project_name, records in projects.items():
        records.sort(key=lambda item: item.update_time or "", reverse=True)
        if limit is not None:
            projects[project_name] = records[: max(limit, 0)]
    return dict(sorted(projects.items(), key=lambda item: item[0].casefold()))


def truncate_for_summary(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    head = text[: max_chars // 2]
    tail = text[-max_chars // 2 :]
    return f"{head}\n\n[... truncated ...]\n\n{tail}"


def request_json(url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout: int = 600) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise PipelineError(f"HTTP {exc.code} from {url}: {detail[:1200]}") from exc
    except urllib.error.URLError as exc:
        raise PipelineError(f"Failed to reach {url}: {exc}") from exc


def build_json_schema(schema: str, name: str) -> Dict[str, Any]:
    payload = json.loads(schema)
    if not isinstance(payload, dict):
        raise PipelineError("Schema definition must decode into a JSON object.")
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "schema": {
                "type": "object",
                "properties": {key: _schema_value_to_spec(value) for key, value in payload.items()},
                "required": list(payload.keys()),
                "additionalProperties": False,
            },
        },
    }


def _schema_value_to_spec(value: Any) -> Dict[str, Any]:
    if isinstance(value, str):
        return {"type": "string"}
    if isinstance(value, list):
        item_example = value[0] if value else ""
        return {"type": "array", "items": _schema_value_to_spec(item_example)}
    if isinstance(value, dict):
        return {
            "type": "object",
            "properties": {key: _schema_value_to_spec(child) for key, child in value.items()},
            "required": list(value.keys()),
            "additionalProperties": False,
        }
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    return {"type": "string"}


def extract_json_block(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"\A```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\Z", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise PipelineError(f"Model did not return JSON:\n{cleaned[:1200]}")
    json_text = cleaned[start : end + 1]
    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise PipelineError(f"Could not decode model JSON response: {exc}\n{json_text[:1200]}") from exc
    if not isinstance(payload, dict):
        raise PipelineError("Model returned non-object JSON payload.")
    return payload


class LocalModelClient:
    def __init__(self, embedding_base_url: str, embedding_model: str, llm_base_url: str, llm_model: str, llm_api_key: str, sleep_seconds: float) -> None:
        self.embedding_base_url = embedding_base_url.rstrip("/")
        self.embedding_model = embedding_model
        self.llm_base_url = llm_base_url.rstrip("/")
        self.llm_model = llm_model
        self.llm_api_key = llm_api_key
        self.sleep_seconds = max(sleep_seconds, 0.0)

    def _sleep(self) -> None:
        if self.sleep_seconds:
            time.sleep(self.sleep_seconds)

    @staticmethod
    def _message_text(message: Dict[str, Any]) -> str:
        content = str(message.get("content") or "").strip()
        if content:
            return content
        reasoning = str(message.get("reasoning_content") or "").strip()
        if reasoning:
            return reasoning
        return ""

    @staticmethod
    def _looks_like_placeholder(value: Any) -> bool:
        placeholder_values = {
            "...",
            "string",
            "short label",
            "2-4 sentence summary",
            "1-3 paragraph cluster summary",
        }
        if isinstance(value, str):
            return value.strip().casefold() in placeholder_values
        if isinstance(value, list):
            return any(LocalModelClient._looks_like_placeholder(item) for item in value)
        if isinstance(value, dict):
            return any(LocalModelClient._looks_like_placeholder(item) for item in value.values())
        return False

    def summarize_conversation(self, record: ConversationRecord, max_chars: int) -> Dict[str, Any]:
        schema = """{
  "summary": "2-4 sentence summary",
  "key_points": ["string"],
  "decisions": ["string"],
  "open_questions": ["string"],
  "keywords": ["string"],
  "category_guess": "short label"
}"""
        field_rules = """Required keys:
- summary: 2-4 concrete sentences based on the transcript
- key_points: short bullet-like strings
- decisions: actual decisions or proposed directions from the transcript
- open_questions: unresolved questions from the transcript
- keywords: high-signal topic words
- category_guess: short theme label

Critical rule:
- Fill every value with transcript-specific content.
- Never copy placeholder words such as "...", "string", "short label", or field descriptions."""
        prompt = f"""You are building a structured project-history digest from ChatGPT conversations.

Read the conversation transcript and return one JSON object only.

Rules:
- Preserve the original language of the source where appropriate.
- Be concrete and compress aggressively.
- Focus on engineering direction, design choices, product framing, repeated concepts, and unresolved questions.
- Do not mention that you are an AI.
- Do not wrap the JSON in markdown fences.
- Keep arrays short and high-signal.

{field_rules}

Project: {record.project}
Conversation title: {record.title}
Conversation create_time: {record.create_time}
Conversation update_time: {record.update_time}

Conversation transcript:
{truncate_for_summary(record.body, max_chars)}
"""
        summary = self._chat_json(prompt, max_tokens=1400, schema=schema)
        summary["conversation_id"] = record.conversation_id
        summary["title"] = record.title
        summary["project"] = record.project
        summary["create_time"] = record.create_time
        summary["update_time"] = record.update_time
        summary["source_path"] = str(record.source_path.relative_to(PROJECT_DIR))
        summary["source_url"] = record.source_url
        return summary

    def summarize_cluster(self, project_name: str, members: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        schema = """{
  "label": "short theme label",
  "summary": "1-3 paragraph cluster summary",
  "key_points": ["string"],
  "decisions": ["string"],
  "open_questions": ["string"],
  "representative_titles": ["string"]
}"""
        field_rules = """Required keys:
- label: short theme label
- summary: 1-3 paragraph cluster summary grounded in the member conversations
- key_points: short high-signal strings
- decisions: actual decisions or directions across the cluster
- open_questions: unresolved issues across the cluster
- representative_titles: existing conversation titles from the cluster

Critical rule:
- Fill every value with cluster-specific content.
- Never copy placeholder words such as "...", "string", "short label", or field descriptions."""
        member_lines = []
        for item in members:
            member_lines.append(
                json.dumps(
                    {
                        "title": item.get("title"),
                        "summary": item.get("summary"),
                        "key_points": item.get("key_points", []),
                        "decisions": item.get("decisions", []),
                        "open_questions": item.get("open_questions", []),
                        "keywords": item.get("keywords", []),
                    },
                    ensure_ascii=False,
                )
            )
        prompt = f"""You are grouping related conversations from one project into a single theme cluster.

Return one JSON object only.

{field_rules}

Project: {project_name}
Conversation summaries:
{chr(10).join(member_lines)}
"""
        return self._chat_json(prompt, max_tokens=1400, schema=schema)

    def build_project_report(
        self,
        project_name: str,
        conversations: Sequence[ConversationRecord],
        cluster_payloads: Sequence[Dict[str, Any]],
    ) -> str:
        project_context = {
            "project": project_name,
            "conversation_count": len(conversations),
            "time_range": {
                "start": min((item.create_time for item in conversations if item.create_time), default=""),
                "end": max((item.update_time for item in conversations if item.update_time), default=""),
            },
            "clusters": [
                {
                    "cluster_index": item["cluster_index"],
                    "member_count": item["member_count"],
                    "label": item["label"],
                    "summary": item["summary"],
                    "key_points": item["key_points"],
                    "decisions": item["decisions"],
                    "open_questions": item["open_questions"],
                    "representative_titles": item["representative_titles"],
                }
                for item in cluster_payloads
            ],
        }
        prompt = f"""Write a Markdown project report from structured conversation clusters.

Requirements:
- Output Markdown only.
- Prefer Traditional Chinese when the source material is mostly Chinese.
- The report must read like a project document, not like chat compression.
- Emphasize engineering direction, design decisions, repeated patterns, and unresolved questions.
- Mention representative conversation titles where useful.
- Keep the report concise and complete.
- Target roughly 400-700 words before the conversation index.

Required sections:
1. # {project_name} Report
2. ## Project Overview
3. ## Core Themes
4. ## Key Decisions
5. ## Repeated Patterns
6. ## Open Questions
- Do not include a Conversation Index section.

Structured project context:
{json.dumps(project_context, ensure_ascii=False, indent=2)}
"""
        report_body = extract_report_markdown(self._chat_text(prompt, max_tokens=2200), project_name)
        if not report_has_required_sections(report_body):
            retry_prompt = f"""Rewrite the project report as a shorter but complete Markdown document.

Requirements:
- Output Markdown only.
- Include all required sections exactly once.
- Keep every section concise.
- Do not include a Conversation Index section.

Required sections:
1. # {project_name} Report
2. ## Project Overview
3. ## Core Themes
4. ## Key Decisions
5. ## Repeated Patterns
6. ## Open Questions

Structured project context:
{json.dumps(project_context, ensure_ascii=False, indent=2)}
"""
            report_body = extract_report_markdown(self._chat_text(retry_prompt, max_tokens=2600), project_name)
        if not report_has_required_sections(report_body):
            report_body = build_fallback_project_report(project_name, conversations, cluster_payloads)
        return report_body.rstrip() + "\n\n" + build_conversation_index_section(conversations)

    def embedding_vectors(self, texts: Sequence[str]) -> List[List[float]]:
        payload = {"model": self.embedding_model, "input": list(texts)}
        data = request_json(f"{self.embedding_base_url}/embeddings", payload, headers={})
        rows = data.get("data")
        if not isinstance(rows, list):
            raise PipelineError("Embedding API returned unexpected payload.")
        vectors: List[List[float]] = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("embedding"), list):
                raise PipelineError("Embedding row is malformed.")
            vectors.append([float(value) for value in row["embedding"]])
        self._sleep()
        return vectors

    def _chat_text(self, prompt: str, max_tokens: int) -> str:
        return self._chat_text_payload(prompt, max_tokens=max_tokens, extra_payload=None)

    def _chat_text_payload(self, prompt: str, max_tokens: int, extra_payload: Optional[Dict[str, Any]]) -> str:
        payload = {
            "model": self.llm_model,
            "messages": [
                {"role": "system", "content": "Return exactly the requested content. Be concise and concrete."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        if extra_payload:
            payload.update(extra_payload)
        headers: Dict[str, str] = {}
        if self.llm_api_key:
            headers["Authorization"] = f"Bearer {self.llm_api_key}"
        data = request_json(
            f"{self.llm_base_url}/chat/completions",
            payload,
            headers=headers,
        )
        self._sleep()
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise PipelineError(f"LLM API returned unexpected payload: {json.dumps(data)[:1200]}") from exc
        text = self._message_text(message)
        if text:
            return text
        raise PipelineError(f"LLM API returned empty message payload: {json.dumps(data)[:1200]}")

    def _chat_json(self, prompt: str, max_tokens: int, schema: str) -> Dict[str, Any]:
        schema_payload = build_json_schema(schema, name="structured_output")
        schema_prompt = (
            f"{prompt}\n\nStrict output rule: return one valid JSON object only. "
            "Fill all fields with source-grounded content. "
            "Do not echo placeholder words or field descriptions."
        )
        first_pass = self._chat_text_payload(schema_prompt, max_tokens=max_tokens, extra_payload={"response_format": schema_payload})
        try:
            payload = extract_json_block(first_pass)
            if not self._looks_like_placeholder(payload):
                return payload
        except PipelineError:
            payload = None

        primary_prompt = (
            f"{prompt}\n\nStrict output rule: return JSON only. "
            "Do not include analysis, bullets, markdown fences, or commentary. "
            "The first character must be { and the last character must be }. "
            "Do not echo placeholder words from any schema or instructions."
        )
        first_pass = self._chat_text(primary_prompt, max_tokens=max_tokens)
        try:
            payload = extract_json_block(first_pass)
            if not self._looks_like_placeholder(payload):
                return payload
        except PipelineError:
            payload = None
        repair_prompt = f"""Convert the following draft into one valid JSON object with real content.

Requirements:
- Return JSON only.
- Do not add explanation.
- Follow this schema exactly:
{schema}
- Replace placeholder words with concrete, source-grounded content.
- Do not use values like "...", "string", "short label", or repeat field descriptions.

Draft text:
{first_pass}
"""
        second_pass = self._chat_text(repair_prompt, max_tokens=max_tokens)
        repaired = extract_json_block(second_pass)
        if self._looks_like_placeholder(repaired):
            raise PipelineError(f"Model returned placeholder JSON instead of real content: {json.dumps(repaired, ensure_ascii=False)[:1200]}")
        return repaired


def load_jsonl_cache(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    cache: Dict[str, Dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if isinstance(record, dict) and isinstance(record.get("conversation_id"), str):
            cache[record["conversation_id"]] = record
    return cache


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    ensure_parent(path)
    content = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    path.write_text(content + ("\n" if content else ""), encoding="utf-8")


def build_conversation_index_section(conversations: Sequence[ConversationRecord]) -> str:
    lines = [
        "## Conversation Index",
        "| Title | Update Time | Source Path |",
        "| :--- | :--- | :--- |",
    ]
    for item in conversations:
        lines.append(f"| {item.title} | {item.update_time or ''} | `{item.source_path.relative_to(PROJECT_DIR)}` |")
    return "\n".join(lines).rstrip() + "\n"


def report_has_required_sections(markdown: str) -> bool:
    return all(header in markdown for header in REQUIRED_REPORT_HEADERS)


def unique_preserving_order(items: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        value = item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def extract_report_markdown(text: str, project_name: str) -> str:
    cleaned = text.strip()
    start_marker = f"# {project_name} Report"
    start_index = cleaned.rfind(start_marker)
    if start_index != -1:
        cleaned = cleaned[start_index:]
    index_marker = "\n## Conversation Index"
    index_pos = cleaned.find(index_marker)
    if index_pos != -1:
        cleaned = cleaned[:index_pos]
    cleaned = textwrap.dedent(cleaned).strip()
    cleaned = re.sub(r"(?m)^ {4}", "", cleaned)
    meta_markers = [
        "Word Count Check",
        "Final Review",
        "Self-Correction",
        "Revised Draft Plan",
        "Let's assemble",
        "Let's write",
    ]
    lines = cleaned.splitlines()
    kept: List[str] = []
    for line in lines:
        if any(marker in line for marker in meta_markers):
            break
        kept.append(line)
    return "\n".join(kept).strip()


def build_fallback_project_report(
    project_name: str,
    conversations: Sequence[ConversationRecord],
    cluster_payloads: Sequence[Dict[str, Any]],
) -> str:
    start_time = min((item.create_time for item in conversations if item.create_time), default="")
    end_time = max((item.update_time for item in conversations if item.update_time), default="")
    theme_lines = []
    for cluster in cluster_payloads:
        summary = str(cluster.get("summary") or "").strip().replace("\n", " ")
        theme_lines.append(f"- **{cluster.get('label') or 'Theme'}**: {summary}")

    decisions = unique_preserving_order(
        str(item)
        for cluster in cluster_payloads
        for item in (cluster.get("decisions") or [])
    )[:6]
    patterns = unique_preserving_order(
        str(item)
        for cluster in cluster_payloads
        for item in (cluster.get("key_points") or [])
    )[:6]
    questions = unique_preserving_order(
        str(item)
        for cluster in cluster_payloads
        for item in (cluster.get("open_questions") or [])
    )[:6]
    if not questions:
        questions = ["仍需進一步驗證各主題的具體實作細節與優先順序。"]
    decision_lines = [f"- {item}" for item in decisions] or ["- 尚未抽取到明確決策。"]
    pattern_lines = [f"- {item}" for item in patterns] or ["- 尚未抽取到明確重複模式。"]
    question_lines = [f"- {item}" for item in questions]

    lines = [
        f"# {project_name} Report",
        "",
        "## Project Overview",
        f"{project_name} 目前整理了 {len(conversations)} 篇對話，時間範圍約為 {start_time or 'unknown'} 到 {end_time or 'unknown'}。"
        f" 現階段報告以 cluster summaries 為基礎，重點整理項目定位、主要主題、已形成的決策，以及仍待確認的問題。",
        "",
        "## Core Themes",
        *theme_lines,
        "",
        "## Key Decisions",
        *decision_lines,
        "",
        "## Repeated Patterns",
        *pattern_lines,
        "",
        "## Open Questions",
        *question_lines,
    ]
    return "\n".join(lines).rstrip()


def embedding_text(summary: Dict[str, Any]) -> str:
    sections = [
        str(summary.get("title") or ""),
        str(summary.get("summary") or ""),
        "; ".join(str(item) for item in summary.get("keywords") or []),
        "; ".join(str(item) for item in summary.get("decisions") or []),
        "; ".join(str(item) for item in summary.get("open_questions") or []),
    ]
    return "\n".join(section for section in sections if section).strip()


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def mean_vector(vectors: Sequence[Sequence[float]]) -> List[float]:
    if not vectors:
        return []
    length = len(vectors[0])
    return [sum(vector[index] for vector in vectors) / len(vectors) for index in range(length)]


def cluster_summaries(summaries: Sequence[Dict[str, Any]], vectors: Sequence[Sequence[float]], threshold: float) -> List[Dict[str, Any]]:
    clusters: List[Dict[str, Any]] = []
    for index, summary in enumerate(summaries):
        vector = list(vectors[index])
        best_cluster: Optional[Dict[str, Any]] = None
        best_similarity = -1.0
        for cluster in clusters:
            similarity = cosine_similarity(vector, cluster["centroid"])
            if similarity > best_similarity:
                best_similarity = similarity
                best_cluster = cluster
        if best_cluster is not None and best_similarity >= threshold:
            best_cluster["member_indices"].append(index)
            best_cluster["centroid"] = mean_vector([vectors[i] for i in best_cluster["member_indices"]])
            best_cluster["max_similarity"] = max(best_cluster["max_similarity"], best_similarity)
        else:
            clusters.append(
                {
                    "member_indices": [index],
                    "centroid": vector,
                    "max_similarity": 1.0,
                }
            )
    clusters.sort(key=lambda item: (-len(item["member_indices"]), item["member_indices"][0]))
    return clusters


def build_index_markdown(project_reports: Sequence[Dict[str, Any]]) -> str:
    lines = ["# Project Reports", ""]
    for item in project_reports:
        report_path = Path(str(item["report_path"]))
        if report_path.is_absolute():
            try:
                link_path = report_path.relative_to(DEFAULT_OUTPUT_DIR)
            except ValueError:
                link_path = Path(report_path.name)
        else:
            if "project_reports" in report_path.parts:
                index = report_path.parts.index("project_reports")
                link_path = Path(*report_path.parts[index + 1 :])
            else:
                link_path = report_path
        lines.append(f"## {item['project']}")
        lines.append("")
        lines.append(f"- Conversations: {item['conversation_count']}")
        lines.append(f"- Clusters: {item['cluster_count']}")
        lines.append(f"- Report: [{report_path.name}]({link_path.as_posix()})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def collect_report_index(output_dir: Path) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for report_path in sorted(output_dir.glob("*/project_report.md")):
        project_dir = report_path.parent
        summaries_path = project_dir / "conversation_summaries.jsonl"
        clusters_path = project_dir / "clusters.json"
        conversation_count = 0
        if summaries_path.exists():
            conversation_count = len([line for line in summaries_path.read_text(encoding="utf-8").splitlines() if line.strip()])
        cluster_count = 0
        if clusters_path.exists():
            try:
                payload = json.loads(clusters_path.read_text(encoding="utf-8"))
                if isinstance(payload, list):
                    cluster_count = len(payload)
            except json.JSONDecodeError:
                cluster_count = 0
        project_title = project_dir.name
        if summaries_path.exists():
            first_line = next((line for line in summaries_path.read_text(encoding="utf-8").splitlines() if line.strip()), "")
            if first_line:
                try:
                    row = json.loads(first_line)
                    project_title = str(row.get("project") or project_title)
                except json.JSONDecodeError:
                    pass
        items.append(
            {
                "project": project_title,
                "conversation_count": conversation_count,
                "cluster_count": cluster_count,
                "report_path": report_path,
            }
        )
    items.sort(key=lambda item: str(item["project"]).casefold())
    return items


def run_pipeline(args: argparse.Namespace) -> int:
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    projects = sorted_project_conversations(input_dir, args.project, args.limit_conversations)

    client = LocalModelClient(
        embedding_base_url=EMBEDDING_BASE_URL,
        embedding_model=EMBEDDING_MODEL,
        llm_base_url=LLM_BASE_URL,
        llm_model=LLM_MODEL,
        llm_api_key=LLM_API_KEY,
        sleep_seconds=args.sleep_seconds,
    )

    for project_name, conversations in projects.items():
        print(f"Project: {project_name}", file=sys.stderr)
        project_dir = output_dir / sanitize_filename(project_name)
        summaries_path = project_dir / "conversation_summaries.jsonl"
        clusters_path = project_dir / "clusters.json"
        report_path = project_dir / "project_report.md"

        cached_summaries = {} if args.force else load_jsonl_cache(summaries_path)
        summaries: List[Dict[str, Any]] = []
        for record in conversations:
            cached = cached_summaries.get(record.conversation_id)
            if (
                isinstance(cached, dict)
                and cached.get("update_time") == record.update_time
                and cached.get("source_path") == str(record.source_path.relative_to(PROJECT_DIR))
            ):
                print(f"  summary-cache: {record.title}", file=sys.stderr)
                summaries.append(cached)
                continue
            print(f"  summarize: {record.title}", file=sys.stderr)
            summary = client.summarize_conversation(record, args.summary_max_chars)
            summaries.append(summary)
        write_jsonl(summaries_path, summaries)

        texts = [embedding_text(summary) for summary in summaries]
        vectors = client.embedding_vectors(texts)
        clusters = cluster_summaries(summaries, vectors, args.cluster_threshold)

        cluster_payloads: List[Dict[str, Any]] = []
        cluster_dump: List[Dict[str, Any]] = []
        for cluster_index, cluster in enumerate(clusters, start=1):
            member_summaries = [summaries[index] for index in cluster["member_indices"]]
            cluster_summary = client.summarize_cluster(project_name, member_summaries)
            cluster_payload = {
                "cluster_index": cluster_index,
                "member_count": len(member_summaries),
                "label": cluster_summary.get("label") or f"Cluster {cluster_index}",
                "summary": cluster_summary.get("summary") or "",
                "key_points": cluster_summary.get("key_points") or [],
                "decisions": cluster_summary.get("decisions") or [],
                "open_questions": cluster_summary.get("open_questions") or [],
                "representative_titles": cluster_summary.get("representative_titles") or [],
                "members": [
                    {
                        "conversation_id": item.get("conversation_id"),
                        "title": item.get("title"),
                        "update_time": item.get("update_time"),
                        "source_path": item.get("source_path"),
                    }
                    for item in member_summaries
                ],
            }
            cluster_payloads.append(cluster_payload)
            cluster_dump.append(cluster_payload)
        write_json(clusters_path, cluster_dump)

        report_markdown = client.build_project_report(project_name, conversations, cluster_payloads)
        report_markdown = extract_report_markdown(report_markdown, project_name).rstrip() + "\n\n" + build_conversation_index_section(conversations)
        write_text(report_path, report_markdown)

    index_path = output_dir / "index.md"
    report_index = collect_report_index(output_dir)
    write_text(index_path, build_index_markdown(report_index))

    print(
        json.dumps(
            {
                "projects": len(report_index),
                "output_dir": str(output_dir),
                "index_path": str(index_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> int:
    args = parse_args()
    try:
        return run_pipeline(args)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except PipelineError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
