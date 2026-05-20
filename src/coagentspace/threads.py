from __future__ import annotations

import os
import re
import secrets
from pathlib import Path

import yaml

from .models import ThreadFrontmatter
from .registry import groups_for_agent
from .timeutils import utc_now


THREAD_RE = re.compile(r"^THREAD-(\d{4,})\.md$")


def threads_dir(space: Path) -> Path:
    return space / "threads"


def next_thread_id(space: Path) -> str:
    highest = 0
    for path in threads_dir(space).glob("THREAD-*.md"):
        match = THREAD_RE.match(path.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"THREAD-{highest + 1:04d}"


def thread_path(space: Path, thread_id: str) -> Path:
    path = threads_dir(space) / f"{thread_id}.md"
    if not path.exists():
        raise RuntimeError(f"Thread `{thread_id}` was not found in {threads_dir(space)}.")
    return path


def split_frontmatter(content: str) -> tuple[dict, str]:
    if not content.startswith("---\n"):
        raise RuntimeError("Thread file is missing YAML frontmatter.")
    _, rest = content.split("---\n", 1)
    raw_frontmatter, body = rest.split("\n---\n", 1)
    data = yaml.safe_load(raw_frontmatter) or {}
    return data, body


def read_thread_frontmatter(path: Path) -> ThreadFrontmatter:
    data, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    return ThreadFrontmatter.model_validate(data)


def iter_threads(space: Path) -> list[tuple[ThreadFrontmatter, Path]]:
    items: list[tuple[ThreadFrontmatter, Path]] = []
    for path in sorted(threads_dir(space).glob("THREAD-*.md")):
        try:
            items.append((read_thread_frontmatter(path), path))
        except Exception:
            continue
    return items


def create_thread(
    *,
    space: Path,
    from_agent: str,
    to_type: str,
    to: str,
    title: str,
    body: str,
) -> str:
    threads_dir(space).mkdir(parents=True, exist_ok=True)

    while True:
        thread_id = next_thread_id(space)
        path = threads_dir(space) / f"{thread_id}.md"
        frontmatter = ThreadFrontmatter(
            thread_id=thread_id,
            from_agent=from_agent,
            to_type=to_type,
            to=to,
            title=title,
            created_at=utc_now(),
        )
        content = render_thread(frontmatter, body)
        try:
            with path.open("x", encoding="utf-8") as handle:
                handle.write(content)
            return thread_id
        except FileExistsError:
            continue


def render_thread(frontmatter: ThreadFrontmatter, body: str) -> str:
    data = frontmatter.model_dump(by_alias=True)
    yaml_text = yaml.safe_dump(data, sort_keys=False).strip()
    normalized_body = body.rstrip() + "\n" if body else "\n"
    return f"---\n{yaml_text}\n---\n{normalized_body}"


def resolve_session_id(agent: str, explicit_session_id: str | None) -> str:
    if explicit_session_id:
        return explicit_session_id
    env_session = os.environ.get("CAS_SESSION_ID")
    if env_session:
        return env_session
    return f"{agent}-{secrets.token_hex(4)}"


def append_to_thread(
    *,
    space: Path,
    thread_id: str,
    agent: str,
    message: str,
    session_id: str | None = None,
) -> str:
    path = thread_path(space, thread_id)
    resolved_session = resolve_session_id(agent, session_id)
    entry = (
        "\n---\n\n"
        f"## {utc_now()}\n\n"
        f"agent: {agent}\n"
        f"session: {resolved_session}\n\n"
        f"{message.rstrip()}\n"
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(entry)
    return resolved_session


def inbox_threads(space: Path, agent: str) -> list[tuple[ThreadFrontmatter, Path]]:
    group_ids = set(groups_for_agent(space, agent))
    visible: list[tuple[ThreadFrontmatter, Path]] = []
    for frontmatter, path in iter_threads(space):
        if frontmatter.to_type == "agent" and frontmatter.to == agent:
            visible.append((frontmatter, path))
        elif frontmatter.to_type == "group" and frontmatter.to in group_ids:
            visible.append((frontmatter, path))
    return visible
