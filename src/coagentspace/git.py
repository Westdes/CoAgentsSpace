from __future__ import annotations

import subprocess
from pathlib import Path


def run_git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        text=True,
        capture_output=True,
    )


def git_output(args: list[str], cwd: Path) -> str | None:
    result = run_git(args, cwd, check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def ensure_git_repo(path: Path) -> None:
    if (path / ".git").exists():
        return
    run_git(["init"], cwd=path)


def is_git_repo(path: Path) -> bool:
    result = run_git(["rev-parse", "--is-inside-work-tree"], cwd=path, check=False)
    return result.returncode == 0 and result.stdout.strip() == "true"


def git_toplevel(path: Path) -> Path | None:
    root = git_output(["rev-parse", "--show-toplevel"], path)
    return Path(root).resolve() if root else None


def is_worktree_clean(path: Path) -> bool:
    result = run_git(["status", "--porcelain"], cwd=path, check=False)
    return result.returncode == 0 and not result.stdout.strip()


def git_identity(cwd: Path) -> tuple[str | None, str | None]:
    name = git_output(["config", "user.name"], cwd) or git_output(["config", "--global", "user.name"], cwd)
    email = git_output(["config", "user.email"], cwd) or git_output(["config", "--global", "user.email"], cwd)
    return name, email


def project_root(cwd: Path) -> Path:
    root = git_output(["rev-parse", "--show-toplevel"], cwd)
    if root:
        return Path(root).resolve()
    return cwd.resolve()


def has_remote(cwd: Path) -> bool:
    result = run_git(["remote"], cwd=cwd, check=False)
    return result.returncode == 0 and bool(result.stdout.strip())


def current_branch(cwd: Path) -> str | None:
    return git_output(["rev-parse", "--abbrev-ref", "HEAD"], cwd)


def upstream_branch(cwd: Path) -> str | None:
    return git_output(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd)


def remote_branch_exists(cwd: Path, remote: str, branch: str) -> bool:
    result = run_git(["ls-remote", "--exit-code", "--heads", remote, branch], cwd=cwd, check=False)
    return result.returncode == 0


def sync_space(cwd: Path, message: str) -> list[str]:
    """Commit local CAS changes and push them when a remote is configured."""
    output: list[str] = []
    run_git(["add", "-A"], cwd=cwd)
    diff = run_git(["diff", "--cached", "--quiet"], cwd=cwd, check=False)
    if diff.returncode != 0:
        run_git(["commit", "-m", message], cwd=cwd)
        output.append("Committed CAS changes.")
    else:
        output.append("No CAS changes to commit.")

    if not has_remote(cwd):
        output.append("No Git remote configured; skipped pull/push.")
        return output

    branch = current_branch(cwd)
    if not branch or branch == "HEAD":
        raise RuntimeError("Cannot sync detached HEAD CAS space.")

    upstream = upstream_branch(cwd)
    if upstream and remote_branch_exists(cwd, "origin", branch):
        run_git(["pull", "--rebase"], cwd=cwd)
        run_git(["push"], cwd=cwd)
    else:
        run_git(["push", "-u", "origin", branch], cwd=cwd)
    output.append("Synced CAS space.")
    return output
