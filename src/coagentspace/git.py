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


def git_error(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stderr or result.stdout or "git command failed").strip()


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


def require_clean_worktree(path: Path) -> None:
    result = run_git(["status", "--porcelain"], cwd=path, check=False)
    if result.returncode != 0:
        raise RuntimeError(git_error(result))
    if result.stdout.strip():
        raise RuntimeError(
            "CAS space has uncommitted changes. Run `cas sync`, inspect the CAS repo, "
            "or resolve the dirty worktree before mutating it."
        )


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
    return git_output(["branch", "--show-current"], cwd)


def upstream_branch(cwd: Path) -> str | None:
    return git_output(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd)


def remote_branch_exists(cwd: Path, remote: str, branch: str) -> bool:
    result = run_git(["ls-remote", "--exit-code", "--heads", remote, branch], cwd=cwd, check=False)
    return result.returncode == 0


def remote_url(cwd: Path, remote: str = "origin") -> str | None:
    return git_output(["remote", "get-url", remote], cwd)


def latest_commit(cwd: Path) -> str | None:
    return git_output(["rev-parse", "--short", "HEAD"], cwd)


def pull_rebase_before_write(cwd: Path) -> list[str]:
    """Ensure the CAS repo is clean and up to date before an append-only write."""
    output: list[str] = []
    require_clean_worktree(cwd)
    if not has_remote(cwd):
        output.append("No Git remote configured; skipped pre-write pull.")
        return output

    branch = current_branch(cwd)
    if not branch:
        output.append("No current branch yet; skipped pre-write pull.")
        return output

    upstream = upstream_branch(cwd)
    remote_has_branch = remote_branch_exists(cwd, "origin", branch)
    if upstream:
        result = run_git(["pull", "--rebase"], cwd=cwd, check=False)
    elif remote_has_branch:
        result = run_git(["pull", "--rebase", "origin", branch], cwd=cwd, check=False)
    else:
        output.append("Remote branch not found yet; skipped pre-write pull.")
        return output

    if result.returncode != 0:
        raise RuntimeError(
            "Could not pull/rebase the CAS space before writing. Resolve the Git issue, "
            f"then retry. Details: {git_error(result)}"
        )
    output.append("Pulled latest CAS changes.")
    require_clean_worktree(cwd)
    return output


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
    if not branch:
        raise RuntimeError("Cannot sync detached HEAD CAS space.")

    upstream = upstream_branch(cwd)
    if upstream and remote_branch_exists(cwd, "origin", branch):
        run_git(["pull", "--rebase"], cwd=cwd)
        run_git(["push"], cwd=cwd)
    else:
        run_git(["push", "-u", "origin", branch], cwd=cwd)
    output.append("Synced CAS space.")
    return output
