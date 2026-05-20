from __future__ import annotations

from pathlib import Path

from .files import write_text_if_missing
from .git import git_toplevel, is_git_repo, is_worktree_clean
from .templates import AGENT_SKILL_TEMPLATE, AGENTS, APPEND_TEMPLATE, CLAUDE, CONFIG, THREAD_TEMPLATE


def init_space_dirs(space: Path) -> None:
    space.mkdir(parents=True, exist_ok=True)
    (space / ".coagentspace" / "skills").mkdir(parents=True, exist_ok=True)
    (space / ".coagentspace" / "templates").mkdir(parents=True, exist_ok=True)
    (space / "threads").mkdir(parents=True, exist_ok=True)


def init_space_files(space: Path) -> None:
    write_text_if_missing(space / ".coagentspace" / "config.yaml", CONFIG)
    write_text_if_missing(space / ".coagentspace" / "users.yaml", "")
    write_text_if_missing(space / ".coagentspace" / "templates" / "thread.md", THREAD_TEMPLATE)
    write_text_if_missing(space / ".coagentspace" / "templates" / "append.md", APPEND_TEMPLATE)
    write_text_if_missing(space / ".coagentspace" / "skills" / "agent.md", AGENT_SKILL_TEMPLATE)
    write_text_if_missing(space / "AGENTS.md", AGENTS)
    write_text_if_missing(space / "CLAUDE.md", CLAUDE)


def validate_init_target(space: Path) -> None:
    if not space.exists() or not space.is_dir():
        raise RuntimeError(f"{space} does not exist. Create or clone a Git repo first, then run `cas init`.")
    if not is_git_repo(space):
        raise RuntimeError(f"{space} is not a Git repo. Run `git init` there first or use a cloned repo.")
    root = git_toplevel(space)
    if root != space.resolve():
        raise RuntimeError(f"{space} is inside Git repo {root}. Run `cas init` at the Git repo root.")
    already_cas = (space / ".coagentspace" / "config.yaml").exists()
    if not already_cas and not is_worktree_clean(space):
        raise RuntimeError(
            f"{space} has uncommitted files. Commit/stash them first, or use an already CAS-enabled repo."
        )


def initialize_space(space: Path) -> None:
    validate_init_target(space)
    init_space_dirs(space)
    init_space_files(space)
