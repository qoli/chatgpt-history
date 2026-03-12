#!/usr/bin/env python3
"""Export ChatGPT project conversations to Markdown via playwright-cli + Arc CDP."""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import time
import urllib.parse
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
DEFAULT_CONFIG = PROJECT_DIR / "browser_control" / "config" / "playwright-arc-cdp-local-9222.json"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "browser_control" / "output" / "chatgpt_exports"
DEFAULT_SESSION = "chatgpt_export"
CHATGPT_URL = "https://chatgpt.com/"
PAGE_LIMIT = 100

UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|]+')
DISALLOWED_FILENAME_CHAR_RE = re.compile(r"[^0-9A-Za-z_\-\u3400-\u4dbf\u4e00-\u9fff]+")
UNDERSCORE_RUN_RE = re.compile(r"_+")
CITE_MARKER_RE = re.compile(r"\uE200cite(?:\uE202turn\d+(?:search|view)\d+)+\uE201", re.IGNORECASE)
PLAIN_CITE_RE = re.compile(r"cite(?:turn\d+(?:search|view)\d+)+", re.IGNORECASE)


@dataclass
class AuthState:
    access_token: str
    account_id: Optional[str]
    device_id: str
    cookie: str
    user_id: Optional[str]
    email: Optional[str]


@dataclass
class ProjectEntry:
    id: str
    title: str
    preview_items: List[Dict[str, Any]]


@dataclass
class ConversationEntry:
    id: str
    title: str
    create_time: str
    update_time: str
    is_archived: bool
    project_id: str
    project_title: str


class ExportError(RuntimeError):
    """Raised when the export flow cannot continue."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export ChatGPT project conversations to Markdown using playwright-cli + Arc CDP."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="playwright-cli config file that points to Arc CDP.",
    )
    parser.add_argument(
        "--session",
        default=DEFAULT_SESSION,
        help="Named playwright-cli session to use.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where Markdown files and manifests will be written.",
    )
    parser.add_argument(
        "--project",
        action="append",
        default=[],
        help="Only export project names containing this string. Can be repeated.",
    )
    parser.add_argument(
        "--limit-projects",
        type=int,
        default=None,
        help="Only export the first N matched projects after sorting by title.",
    )
    parser.add_argument(
        "--limit-conversations",
        type=int,
        default=None,
        help="Only export the first N conversations per project after sorting by update time descending.",
    )
    parser.add_argument(
        "--list-projects",
        action="store_true",
        help="List matched projects and exit without exporting.",
    )
    parser.add_argument(
        "--save-json",
        action="store_true",
        help="Also save raw conversation JSON next to each Markdown file.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.15,
        help="Delay between backend API calls.",
    )
    return parser.parse_args()


def ensure_playwright_session(config_path: Path, session_name: str) -> None:
    if run_playwright_eval(session_name, "() => location.href", expect_json=False, allow_failure=True) is not None:
        return

    command = [
        "playwright-cli",
        f"-s={session_name}",
        "open",
        "--config",
        str(config_path),
        "--persistent",
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise ExportError(
            "Failed to open playwright-cli session.\n"
            f"stdout:\n{completed.stdout}\n\nstderr:\n{completed.stderr}"
        )

    current_url = run_playwright_eval(session_name, "() => location.href", expect_json=False)
    if not isinstance(current_url, str) or "chatgpt.com" not in current_url:
        goto = subprocess.run(
            ["playwright-cli", f"-s={session_name}", "goto", CHATGPT_URL],
            capture_output=True,
            text=True,
        )
        if goto.returncode != 0:
            raise ExportError(
                "Failed to navigate playwright-cli session to ChatGPT.\n"
                f"stdout:\n{goto.stdout}\n\nstderr:\n{goto.stderr}"
            )


def run_playwright_eval(
    session_name: str,
    js_func: str,
    *,
    expect_json: bool,
    allow_failure: bool = False,
) -> Any:
    command = ["playwright-cli", f"-s={session_name}", "eval", js_func]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        if allow_failure:
            return None
        raise ExportError(
            "playwright-cli eval failed.\n"
            f"stdout:\n{completed.stdout}\n\nstderr:\n{completed.stderr}"
        )

    payload = extract_playwright_result(completed.stdout)
    if payload is None:
        if allow_failure:
            return None
        raise ExportError(f"Could not parse playwright-cli output:\n{completed.stdout}")

    if not expect_json:
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return payload

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ExportError(f"Could not decode playwright result as JSON: {exc}\nPayload:\n{payload}") from exc


def extract_playwright_result(stdout: str) -> Optional[str]:
    lines = stdout.splitlines()
    collecting = False
    collected: List[str] = []
    for line in lines:
        if line.startswith("### Result"):
            collecting = True
            continue
        if collecting and line.startswith("### "):
            break
        if collecting:
            collected.append(line)
    result = "\n".join(collected).strip()
    return result or None


def bootstrap_auth(session_name: str) -> AuthState:
    js = """
async () => {
  const session = await (await fetch('/api/auth/session?unstable_client=true')).json();
  return {
    accessToken: session?.accessToken || null,
    accountId: session?.account?.id || null,
    userId: session?.user?.id || null,
    email: session?.user?.email || null,
    deviceId: document.cookie.match(/oai-did=([^;]+)/)?.[1] || null,
    cookie: document.cookie || ''
  };
}
"""
    data = run_playwright_eval(session_name, js, expect_json=True)
    if not isinstance(data, dict):
        raise ExportError("Unexpected auth bootstrap response from playwright-cli.")

    access_token = data.get("accessToken")
    device_id = data.get("deviceId")
    if not access_token or not device_id:
        raise ExportError("Could not obtain ChatGPT access token or device id from the active Arc session.")

    return AuthState(
        access_token=access_token,
        account_id=data.get("accountId"),
        device_id=device_id,
        cookie=data.get("cookie") or "",
        user_id=data.get("userId"),
        email=data.get("email"),
    )


class ChatGPTBackendClient:
    def __init__(self, session_name: str, auth: AuthState, delay_seconds: float) -> None:
        self.session_name = session_name
        self.auth = auth
        self.delay_seconds = max(delay_seconds, 0.0)

    def _request_json(self, path: str) -> Any:
        js = f"""
async () => {{
  const session = await (await fetch('/api/auth/session?unstable_client=true')).json();
  const deviceId = document.cookie.match(/oai-did=([^;]+)/)?.[1] || null;
  const accountId = session?.account?.id || null;
  const headers = {{
    Authorization: `Bearer ${{session.accessToken}}`,
    'oai-device-id': deviceId,
    Accept: 'application/json'
  }};
  if (accountId) headers['ChatGPT-Account-Id'] = accountId;
  const response = await fetch({json.dumps(path)}, {{ headers }});
  const text = await response.text();
  let data = null;
  try {{
    data = JSON.parse(text);
  }} catch (_error) {{
    data = null;
  }}
  const result = {{
    ok: response.ok,
    status: response.status,
    data,
  }};
  if (!response.ok || data === null) {{
    result.text = text.slice(0, 4000);
  }}
  const jsonText = JSON.stringify(result);
  const bytes = new TextEncoder().encode(jsonText);
  let binary = '';
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {{
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }}
  return btoa(binary);
}}
"""
        payload = run_playwright_eval(self.session_name, js, expect_json=False)
        if not isinstance(payload, str):
            raise ExportError(f"Unexpected playwright backend response type for {path}.")
        try:
            decoded_payload = base64.b64decode(payload).decode("utf-8")
        except Exception as exc:
            raise ExportError(f"Could not base64-decode backend wrapper payload for {path}: {exc}") from exc
        try:
            payload_data = json.loads(decoded_payload)
        except json.JSONDecodeError as exc:
            raise ExportError(f"Could not decode backend wrapper payload for {path}: {exc}") from exc
        if not isinstance(payload_data, dict):
            raise ExportError(f"Unexpected playwright backend response for {path}.")
        if not payload_data.get("ok"):
            snippet = str(payload_data.get("text") or "")[:500]
            raise ExportError(
                f"ChatGPT backend request failed for {path} ({payload_data.get('status')}): {snippet}"
            )
        data = payload_data.get("data")
        if data is None:
            raise ExportError(
                f"Backend returned non-JSON payload for {path}: {str(payload_data.get('text') or '')[:500]}"
            )

        if self.delay_seconds:
            time.sleep(self.delay_seconds)

        return data

    def list_projects(self) -> List[ProjectEntry]:
        projects_by_id: Dict[str, ProjectEntry] = {}
        cursor = ""

        while True:
            path = "/backend-api/gizmos/snorlax/sidebar?conversations_per_gizmo=0&owned_only=true"
            if cursor:
                path += f"&cursor={urllib.parse.quote(cursor, safe='')}"

            data = self._request_json(path)
            items = data.get("items") if isinstance(data, dict) else None
            if not isinstance(items, list):
                raise ExportError("Unexpected project sidebar payload.")

            for item in items:
                if not isinstance(item, dict):
                    continue
                raw_gizmo = ((item.get("gizmo") or {}).get("gizmo")) or item.get("gizmo") or item
                display = raw_gizmo.get("display") if isinstance(raw_gizmo, dict) else None
                project_id = raw_gizmo.get("id") if isinstance(raw_gizmo, dict) else None
                title = ""
                if isinstance(display, dict):
                    title = display.get("name") or ""
                if not title and isinstance(raw_gizmo, dict):
                    title = raw_gizmo.get("name") or ""
                if not project_id or not title:
                    continue
                projects_by_id[project_id] = ProjectEntry(
                    id=project_id,
                    title=title,
                    preview_items=[],
                )

            next_cursor = data.get("cursor") if isinstance(data, dict) else None
            if not isinstance(next_cursor, str) or not next_cursor:
                break
            cursor = next_cursor

        projects = list(projects_by_id.values())
        projects.sort(key=lambda item: item.title.casefold())
        return projects

    def list_project_conversations(self, project: ProjectEntry) -> List[ConversationEntry]:
        entries: List[ConversationEntry] = []
        seen_ids: set[str] = set()
        cursor = "0"
        fetched = False

        while cursor:
            try:
                path = f"/backend-api/gizmos/{project.id}/conversations?cursor={urllib.parse.quote(cursor, safe='')}"
                data = self._request_json(path)
            except ExportError:
                if not fetched and project.preview_items:
                    for item in project.preview_items:
                        entry = self._conversation_entry_from_item(item, project)
                        if entry and entry.id not in seen_ids:
                            entries.append(entry)
                            seen_ids.add(entry.id)
                    return self._sort_conversations(entries)
                raise

            fetched = True
            items = data.get("items") if isinstance(data, dict) else None
            if isinstance(items, list):
                for item in items:
                    entry = self._conversation_entry_from_item(item, project)
                    if entry and entry.id not in seen_ids:
                        entries.append(entry)
                        seen_ids.add(entry.id)
            cursor_value = data.get("cursor") if isinstance(data, dict) else None
            cursor = cursor_value if isinstance(cursor_value, str) and cursor_value else ""

        return self._sort_conversations(entries)

    def get_conversation(self, conversation_id: str) -> Dict[str, Any]:
        data = self._request_json(f"/backend-api/conversation/{conversation_id}")
        if not isinstance(data, dict):
            raise ExportError(f"Unexpected conversation payload for {conversation_id}.")
        data["__fetched_at"] = datetime.now(timezone.utc).isoformat()
        return data

    @staticmethod
    def _conversation_entry_from_item(item: Dict[str, Any], project: ProjectEntry) -> Optional[ConversationEntry]:
        conversation_id = item.get("id")
        if not conversation_id:
            return None
        return ConversationEntry(
            id=conversation_id,
            title=item.get("title") or "Untitled Conversation",
            create_time=item.get("create_time") or "",
            update_time=item.get("update_time") or item.get("create_time") or "",
            is_archived=bool(item.get("is_archived")),
            project_id=project.id,
            project_title=project.title,
        )

    @staticmethod
    def _sort_conversations(entries: List[ConversationEntry]) -> List[ConversationEntry]:
        return sorted(entries, key=lambda item: item.update_time or "", reverse=True)


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


def short_conversation_suffix(conversation_id: str) -> str:
    if "-" in conversation_id:
        return conversation_id.split("-")[-1]
    return conversation_id[-8:] or "conv"


def normalize_epoch_seconds(value: Any) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, (int, float)):
        value_float = float(value)
        if value_float > 1e12:
            return int(value_float / 1000)
        return int(value_float)
    if isinstance(value, str):
        try:
            if value.endswith("Z"):
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            else:
                parsed = datetime.fromisoformat(value)
        except ValueError:
            return 0
        return int(parsed.timestamp())
    return 0


def clean_message_content(text: str) -> str:
    without_markers = CITE_MARKER_RE.sub("", text)
    return PLAIN_CITE_RE.sub("", without_markers).strip()


def get_reference_info(reference: Dict[str, Any]) -> Dict[str, str]:
    item = None
    items = reference.get("items")
    if isinstance(items, list) and items:
        item = items[0]

    url = ""
    title = ""
    label = ""
    if isinstance(item, dict):
        url = item.get("url") or ""
        title = item.get("title") or ""
        label = item.get("attribution") or ""

    safe_urls = reference.get("safe_urls")
    if not url and isinstance(safe_urls, list) and safe_urls:
        url = safe_urls[0] or ""

    alt = reference.get("alt")
    if not label and isinstance(alt, str):
        match = re.search(r"\[([^\]]+)\]\([^)]+\)", alt)
        if match:
            label = match.group(1)

    if not label:
        label = title or url

    return {"url": url, "title": title, "label": label}


def process_content_references(text: str, content_references: Sequence[Dict[str, Any]]) -> tuple[str, List[Dict[str, Any]]]:
    references = [ref for ref in content_references if isinstance(ref, dict) and isinstance(ref.get("matched_text"), str) and ref.get("matched_text")]
    if not references:
        return text, []

    footnotes: List[Dict[str, Any]] = []
    footnote_index_by_key: Dict[str, int] = {}
    citation_refs = sorted(
        [ref for ref in references if ref.get("type") == "grouped_webpages"],
        key=lambda ref: ref.get("start_idx") if isinstance(ref.get("start_idx"), int) else sys.maxsize,
    )

    for ref in citation_refs:
        info = get_reference_info(ref)
        if not info["url"]:
            continue
        key = f"{info['url']}|{info['title']}"
        if key in footnote_index_by_key:
            continue
        index = len(footnotes) + 1
        footnote_index_by_key[key] = index
        footnotes.append(
            {
                "index": index,
                "url": info["url"],
                "title": info["title"],
                "label": info["label"],
            }
        )

    def replacement_sort_key(ref: Dict[str, Any]) -> tuple[int, int]:
        start_idx = ref.get("start_idx")
        if isinstance(start_idx, int):
            return (0, -start_idx)
        matched = ref.get("matched_text") or ""
        return (1, -len(matched))

    output = text
    for ref in sorted(references, key=replacement_sort_key):
        matched_text = ref.get("matched_text")
        if not matched_text or ref.get("type") == "sources_footnote":
            continue

        replacement = ""
        if ref.get("type") == "grouped_webpages":
            info = get_reference_info(ref)
            if info["url"]:
                key = f"{info['url']}|{info['title']}"
                index = footnote_index_by_key.get(key)
                replacement = f"([{info['label']}][{index}])" if index else (ref.get("alt") or "")
            else:
                replacement = ref.get("alt") or ""
        else:
            replacement = ref.get("alt") or ""

        start_idx = ref.get("start_idx")
        end_idx = ref.get("end_idx")
        if isinstance(start_idx, int) and isinstance(end_idx, int):
            if output[start_idx:end_idx] == matched_text:
                output = output[:start_idx] + replacement + output[end_idx:]
                continue
        output = output.replace(matched_text, replacement)

    return output, footnotes


def extract_text_parts(parts: Sequence[Any]) -> str:
    lines: List[str] = []
    for part in parts:
        if isinstance(part, str):
            lines.append(part)
        elif isinstance(part, dict):
            text = part.get("text")
            if isinstance(text, str):
                lines.append(text)
    return "\n".join([line for line in lines if line])


def extract_conversation_messages(conversation: Dict[str, Any]) -> List[Dict[str, Any]]:
    mapping = conversation.get("mapping")
    if not isinstance(mapping, dict) or not mapping:
        return []

    mapping_keys = list(mapping.keys())
    root_id = "client-created-root" if "client-created-root" in mapping else next(
        (node_id for node_id in mapping_keys if not isinstance(mapping.get(node_id), dict) or not mapping[node_id].get("parent")),
        mapping_keys[0],
    )

    visited: set[str] = set()
    messages: List[Dict[str, Any]] = []

    def traverse(node_id: str) -> None:
        if not node_id or node_id in visited:
            return
        visited.add(node_id)
        node = mapping.get(node_id)
        if not isinstance(node, dict):
            return

        message = node.get("message")
        if isinstance(message, dict):
            author = ((message.get("author") or {}).get("role")) if isinstance(message.get("author"), dict) else None
            metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
            is_hidden = bool(metadata.get("is_visually_hidden_from_conversation")) or bool(
                metadata.get("is_contextual_answers_system_message")
            )
            if author and author != "system" and not is_hidden:
                content = message.get("content") if isinstance(message.get("content"), dict) else {}
                parts = content.get("parts")
                if content.get("content_type") == "text" and isinstance(parts, list):
                    raw_text = extract_text_parts(parts)
                    content_references = metadata.get("content_references")
                    processed_text = raw_text
                    footnotes: List[Dict[str, Any]] = []
                    if isinstance(content_references, list) and content_references:
                        processed_text, footnotes = process_content_references(raw_text, content_references)
                    cleaned = clean_message_content(processed_text)
                    if cleaned:
                        messages.append(
                            {
                                "role": author,
                                "content": cleaned,
                                "create_time": message.get("create_time"),
                                "footnotes": footnotes,
                            }
                        )

        children = node.get("children")
        if isinstance(children, list):
            for child_id in children:
                if isinstance(child_id, str):
                    traverse(child_id)

    traverse(root_id)
    return messages


def iso_or_empty(value: Any) -> str:
    if isinstance(value, str):
        return value
    epoch = normalize_epoch_seconds(value)
    if not epoch:
        return ""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def conversation_markdown(conversation: Dict[str, Any], project_title: str) -> str:
    title = conversation.get("title") or "Untitled Conversation"
    conversation_id = conversation.get("conversation_id") or conversation.get("id") or ""
    create_time = iso_or_empty(conversation.get("create_time"))
    update_time = iso_or_empty(conversation.get("update_time"))
    fetched_at = iso_or_empty(conversation.get("__fetched_at"))
    messages = extract_conversation_messages(conversation)

    lines = [
        "---",
        f"title: {json.dumps(title, ensure_ascii=False)}",
        f"conversation_id: {json.dumps(conversation_id)}",
        f"project: {json.dumps(project_title, ensure_ascii=False)}",
        f"create_time: {json.dumps(create_time)}",
        f"update_time: {json.dumps(update_time)}",
        f"exported_at: {json.dumps(fetched_at)}",
        f"source_url: {json.dumps(f'https://chatgpt.com/c/{conversation_id}' if conversation_id else CHATGPT_URL)}",
        "---",
        "",
        f"# {title}",
        "",
        f"Project: `{project_title}`",
        "",
    ]

    if not messages:
        lines.extend(
            [
                "_No visible user or assistant text messages were found in the exported conversation._",
                "",
            ]
        )
        return "\n".join(lines)

    for index, message in enumerate(messages, start=1):
        role = str(message.get("role") or "assistant").capitalize()
        lines.append(f"## {index}. {role}")
        lines.append("")
        lines.append(str(message.get("content") or ""))
        footnotes = message.get("footnotes")
        if isinstance(footnotes, list) and footnotes:
            lines.append("")
            for note in sorted(footnotes, key=lambda item: item.get("index", 0)):
                url = note.get("url")
                if not url:
                    continue
                title_part = f' "{note.get("title")}"' if note.get("title") else ""
                lines.append(f'[{note.get("index")}]: {url}{title_part}')
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_filename(conversation_title: str, conversation_id: str, suffix: str) -> str:
    stem = sanitize_filename(conversation_title)
    short_id = short_conversation_suffix(conversation_id)
    return f"{stem}_{short_id}.{suffix}"


def filter_projects(projects: Sequence[ProjectEntry], patterns: Sequence[str]) -> List[ProjectEntry]:
    if not patterns:
        return list(projects)
    lowered = [pattern.casefold() for pattern in patterns]
    return [
        project
        for project in projects
        if any(pattern in project.title.casefold() for pattern in lowered)
    ]


def export_projects(args: argparse.Namespace) -> int:
    config_path = Path(args.config).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    ensure_playwright_session(config_path, args.session)
    auth = bootstrap_auth(args.session)
    client = ChatGPTBackendClient(args.session, auth, args.delay_seconds)

    projects = filter_projects(client.list_projects(), args.project)
    if args.limit_projects is not None:
        projects = projects[: max(args.limit_projects, 0)]

    if not projects:
        print("No matching ChatGPT projects found.", file=sys.stderr)
        return 1

    if args.list_projects:
        for project in projects:
            print(project.title)
        return 0

    export_stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    run_dir = output_dir / export_stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest: Dict[str, Any] = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "session": args.session,
        "config": str(config_path),
        "projects": [],
    }

    print(f"Export directory: {run_dir}")
    for project in projects:
        print(f"Project: {project.title}", file=sys.stderr)
        conversations = client.list_project_conversations(project)
        if args.limit_conversations is not None:
            conversations = conversations[: max(args.limit_conversations, 0)]

        project_dir = run_dir / sanitize_filename(project.title)
        project_dir.mkdir(parents=True, exist_ok=True)

        project_manifest = {
            "project_id": project.id,
            "project_title": project.title,
            "conversation_count": len(conversations),
            "conversations": [],
        }

        for conversation in conversations:
            print(f"  - {conversation.title}", file=sys.stderr)
            data = client.get_conversation(conversation.id)
            markdown = conversation_markdown(data, project.title)
            markdown_path = project_dir / build_filename(conversation.title, conversation.id, "md")
            write_text(markdown_path, markdown)

            if args.save_json:
                json_path = project_dir / build_filename(conversation.title, conversation.id, "json")
                write_json(json_path, data)

            project_manifest["conversations"].append(
                {
                    "id": conversation.id,
                    "title": conversation.title,
                    "create_time": conversation.create_time,
                    "update_time": conversation.update_time,
                    "is_archived": conversation.is_archived,
                    "markdown_path": str(markdown_path.relative_to(run_dir)),
                }
            )

        manifest["projects"].append(project_manifest)

    write_json(run_dir / "manifest.json", manifest)
    print(f"Finished. Wrote manifest: {run_dir / 'manifest.json'}")
    return 0


def main() -> int:
    args = parse_args()
    try:
        return export_projects(args)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except ExportError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
