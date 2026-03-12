#!/usr/bin/env python3
"""Incrementally sync ChatGPT project conversations to Markdown."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from export_chatgpt_projects_markdown import (
    DEFAULT_CONFIG,
    DEFAULT_SESSION,
    ChatGPTBackendClient,
    ProjectEntry,
    bootstrap_auth,
    build_filename,
    conversation_markdown,
    ensure_playwright_session,
    filter_projects,
    sanitize_filename,
)


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
DEFAULT_MARKDOWN_DIR = PROJECT_DIR / "browser_control" / "output" / "chatgpt_markdown"
DEFAULT_STATE_PATH = DEFAULT_MARKDOWN_DIR / "sync_state.json"


class SyncError(RuntimeError):
    """Raised when the sync pipeline fails."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync ChatGPT project conversations to Markdown."
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
        "--markdown-dir",
        default=str(DEFAULT_MARKDOWN_DIR),
        help="Stable Markdown mirror directory.",
    )
    parser.add_argument(
        "--state-path",
        default=str(DEFAULT_STATE_PATH),
        help="State file used for incremental sync.",
    )
    parser.add_argument(
        "--project",
        action="append",
        default=[],
        help="Only sync project names containing this string. Can be repeated.",
    )
    parser.add_argument(
        "--limit-projects",
        type=int,
        default=None,
        help="Only sync the first N matched projects after sorting by title.",
    )
    parser.add_argument(
        "--limit-conversations",
        type=int,
        default=None,
        help="Only sync the first N conversations per project after sorting by update time descending.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.15,
        help="Delay between ChatGPT backend API calls.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Re-fetch and rewrite all matched conversations even if update_time is unchanged.",
    )
    parser.add_argument(
        "--save-json",
        action="store_true",
        help="Also save raw conversation JSON next to each Markdown file.",
    )
    return parser.parse_args()


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {
            "version": 1,
            "last_synced_at": None,
            "conversations": {},
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SyncError(f"Failed to read sync state {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SyncError(f"Unexpected sync state format in {path}.")
    data.setdefault("version", 1)
    data.setdefault("last_synced_at", None)
    data.setdefault("conversations", {})
    if not isinstance(data["conversations"], dict):
        raise SyncError(f"Unexpected conversations state format in {path}.")
    return data


def save_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def canonical_markdown_relative_path(project_title: str, conversation_title: str, conversation_id: str) -> Path:
    project_dir = sanitize_filename(project_title)
    filename = build_filename(conversation_title, conversation_id, "md")
    return Path(project_dir) / filename


def canonical_json_relative_path(project_title: str, conversation_title: str, conversation_id: str) -> Path:
    project_dir = sanitize_filename(project_title)
    filename = build_filename(conversation_title, conversation_id, "json")
    return Path(project_dir) / filename


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str) -> None:
    ensure_parent(path)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def select_projects(client: ChatGPTBackendClient, args: argparse.Namespace) -> List[ProjectEntry]:
    projects = filter_projects(client.list_projects(), args.project)
    if args.limit_projects is not None:
        projects = projects[: max(args.limit_projects, 0)]
    return projects


def conversation_needs_refresh(
    args: argparse.Namespace,
    state_entry: Optional[Dict[str, Any]],
    markdown_path: Path,
    conversation_update_time: str,
) -> bool:
    if args.force_refresh:
        return True
    if not markdown_path.exists():
        return True
    if not isinstance(state_entry, dict):
        return True
    return state_entry.get("update_time") != conversation_update_time


def sync_pipeline(args: argparse.Namespace) -> int:
    config_path = Path(args.config).resolve()
    markdown_dir = Path(args.markdown_dir).resolve()
    state_path = Path(args.state_path).resolve()

    markdown_dir.mkdir(parents=True, exist_ok=True)

    ensure_playwright_session(config_path, args.session)
    auth = bootstrap_auth(args.session)
    client = ChatGPTBackendClient(args.session, auth, args.delay_seconds)

    projects = select_projects(client, args)
    if not projects:
        raise SyncError("No matching ChatGPT projects found.")

    state = load_state(state_path)
    conversations_state: Dict[str, Any] = state["conversations"]

    refreshed_count = 0
    skipped_count = 0

    for project in projects:
        print(f"Project: {project.title}", file=sys.stderr)
        conversations = client.list_project_conversations(project)
        if args.limit_conversations is not None:
            conversations = conversations[: max(args.limit_conversations, 0)]

        for conversation in conversations:
            existing = conversations_state.get(conversation.id)
            markdown_rel = canonical_markdown_relative_path(project.title, conversation.title, conversation.id)
            markdown_path = markdown_dir / markdown_rel
            json_rel = canonical_json_relative_path(project.title, conversation.title, conversation.id)
            json_path = markdown_dir / json_rel

            if isinstance(existing, dict):
                previous_rel = existing.get("markdown_path")
                if isinstance(previous_rel, str):
                    previous_path = markdown_dir / previous_rel
                    if previous_path.exists() and previous_path != markdown_path:
                        ensure_parent(markdown_path)
                        shutil.move(str(previous_path), str(markdown_path))
                previous_json_rel = existing.get("json_path")
                if isinstance(previous_json_rel, str) and args.save_json:
                    previous_json_path = markdown_dir / previous_json_rel
                    if previous_json_path.exists() and previous_json_path != json_path:
                        ensure_parent(json_path)
                        shutil.move(str(previous_json_path), str(json_path))

            needs_markdown = conversation_needs_refresh(args, existing, markdown_path, conversation.update_time)
            if needs_markdown:
                print(f"  refresh: {conversation.title}", file=sys.stderr)
                data = client.get_conversation(conversation.id)
                markdown = conversation_markdown(data, project.title)
                write_text(markdown_path, markdown)
                if args.save_json:
                    write_json(json_path, data)
                refreshed_count += 1
            else:
                print(f"  skip: {conversation.title}", file=sys.stderr)
                skipped_count += 1
                if args.save_json and not json_path.exists():
                    data = client.get_conversation(conversation.id)
                    write_json(json_path, data)

            conversations_state[conversation.id] = {
                "project_id": project.id,
                "project_title": project.title,
                "title": conversation.title,
                "create_time": conversation.create_time,
                "update_time": conversation.update_time,
                "is_archived": conversation.is_archived,
                "markdown_path": str(markdown_rel),
                "json_path": str(json_rel) if args.save_json else None,
                "last_synced_at": datetime.now(timezone.utc).isoformat(),
            }

    state["last_synced_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state_path, state)

    print(
        json.dumps(
            {
                "projects": len(projects),
                "markdown_refreshed": refreshed_count,
                "markdown_skipped": skipped_count,
                "markdown_dir": str(markdown_dir),
                "state_path": str(state_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> int:
    args = parse_args()
    try:
        return sync_pipeline(args)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except SyncError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
