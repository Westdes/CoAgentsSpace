from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import RegistryState
from .timeutils import utc_now


def registry_log_path(space: Path) -> Path:
    return space / ".coagentspace" / "users.yaml"


def append_registry_event(space: Path, event: dict[str, Any]) -> None:
    path = registry_log_path(space)
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {"created_at": utc_now(), **event}
    with path.open("a", encoding="utf-8") as handle:
        handle.write("---\n")
        yaml.safe_dump(event, handle, sort_keys=False)


def load_registry(space: Path) -> RegistryState:
    path = registry_log_path(space)
    state = RegistryState()
    if not path.exists():
        return state

    for event in yaml.safe_load_all(path.read_text(encoding="utf-8")):
        if not event:
            continue
        event_type = event.get("event_type")
        if event_type == "user_registered":
            state.users[event["user_id"]] = event
        elif event_type == "agent_registered":
            state.agents[event["agent_id"]] = event
        elif event_type == "group_registered":
            group_id = event["group_id"]
            state.groups.setdefault(group_id, {"group_id": group_id, "members": []})
            state.groups[group_id].update(event)
            state.groups[group_id].setdefault("members", [])
        elif event_type == "group_member_added":
            group_id = event["group_id"]
            agent_id = event["agent_id"]
            group = state.groups.setdefault(group_id, {"group_id": group_id, "members": []})
            if agent_id not in group["members"]:
                group["members"].append(agent_id)
    return state


def register_user(space: Path, user_id: str, name: str | None, email: str | None) -> None:
    if user_id in load_registry(space).users:
        return
    append_registry_event(
        space,
        {
            "event_type": "user_registered",
            "user_id": user_id,
            "name": name,
            "email": email,
        },
    )


def register_agent(space: Path, agent_id: str, owner_user_id: str | None, label: str | None = None) -> None:
    state = load_registry(space)
    if agent_id in state.agents:
        return
    append_registry_event(
        space,
        {
            "event_type": "agent_registered",
            "agent_id": agent_id,
            "owner_user_id": owner_user_id,
            "label": label or agent_id,
        },
    )


def register_group(space: Path, group_id: str) -> None:
    if group_id in load_registry(space).groups:
        return
    append_registry_event(
        space,
        {
            "event_type": "group_registered",
            "group_id": group_id,
        },
    )


def join_group(space: Path, group_id: str, agent_id: str) -> None:
    state = load_registry(space)
    if agent_id not in state.agents:
        raise RuntimeError(f"Unknown agent `{agent_id}`. Run `cas agent add {agent_id}` first.")
    if group_id not in state.groups:
        raise RuntimeError(f"Unknown group `{group_id}`. Run `cas group add {group_id}` first.")
    if agent_id in state.groups[group_id].get("members", []):
        return
    append_registry_event(
        space,
        {
            "event_type": "group_member_added",
            "group_id": group_id,
            "agent_id": agent_id,
        },
    )


def groups_for_agent(space: Path, agent_id: str) -> list[str]:
    state = load_registry(space)
    return sorted(
        group_id
        for group_id, group in state.groups.items()
        if agent_id in group.get("members", [])
    )
