from __future__ import annotations

import subprocess
import re
from pathlib import Path

import yaml
from typer.testing import CliRunner

from coagentspace import __version__
from coagentspace.cli import app
from coagentspace.text import email_local_part, slugify


runner = CliRunner()
CREATED_RE = re.compile(r"Created (THREAD-[A-Za-z0-9-]+)")
NEW_THREAD_RE = re.compile(r"^THREAD-\d{8}T\d{6}Z-[0-9a-f]{8}$")


def created_thread_id(output: str) -> str:
    match = CREATED_RE.search(output)
    assert match, output
    return match.group(1)


def thread_file(space: Path, thread_id: str) -> Path:
    return space / "threads" / f"{thread_id}.md"


def git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=path, check=True)
    return path


def init_space(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path]:
    config_dir = tmp_path / "config"
    space = git_repo(tmp_path / "space")
    project = git_repo(tmp_path / "project")

    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["init", str(space), "--user-id", "westdes", "--agent", "codex"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output

    monkeypatch.chdir(project)
    result = runner.invoke(
        app,
        ["attach", str(space)],
        env={"CAS_CONFIG_DIR": str(config_dir)},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    return space, project, config_dir


def registry_events(space: Path) -> list[dict]:
    return [
        event
        for event in yaml.safe_load_all((space / ".coagentspace" / "users.yaml").read_text())
        if event
    ]


def test_init_requires_clean_git_repo_and_registers_user_agent(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    space = git_repo(tmp_path / "space")

    subdir = space / "subdir"
    subdir.mkdir()
    result = runner.invoke(
        app,
        ["init", str(subdir), "--user-id", "westdes"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
    )
    assert result.exit_code != 0

    (space / "dirty.txt").write_text("untracked", encoding="utf-8")
    result = runner.invoke(
        app,
        ["init", str(space), "--user-id", "westdes", "--agent", "codex"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
    )
    assert result.exit_code != 0

    (space / "dirty.txt").unlink()
    result = runner.invoke(
        app,
        ["init", str(space), "--user-id", "westdes", "--agent", "codex"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert (space / ".coagentspace" / "config.yaml").exists()
    assert (space / "threads").is_dir()

    events = registry_events(space)
    assert [event["event_type"] for event in events] == ["user_registered", "agent_registered"]
    assert events[0]["user_id"] == "westdes"
    assert events[1]["agent_id"] == "codex"

    profile = yaml.safe_load((config_dir / "profile.yaml").read_text())
    assert profile["default_user_id"] == "westdes"
    assert profile["default_agent_id"] == "codex"


def test_attach_maps_project_without_writing_to_project_repo(tmp_path, monkeypatch):
    space, project, config_dir = init_space(tmp_path, monkeypatch)

    assert not (project / ".coagentspace").exists()
    projects = yaml.safe_load((config_dir / "projects.yaml").read_text())
    assert projects["projects"][str(project)]["space"] == str(space)


def test_send_and_inbox_show_direct_and_group_threads(tmp_path, monkeypatch):
    space, project, config_dir = init_space(tmp_path, monkeypatch)
    monkeypatch.chdir(project)

    for args in (
        ["agent", "add", "claude"],
        ["group", "add", "research"],
        ["group", "join", "research", "claude"],
        ["send", "--to-agent", "claude", "--title", "Direct", "--message", "hello claude"],
        ["send", "--to-group", "research", "--title", "Group", "--message", "hello group"],
    ):
        result = runner.invoke(app, args, env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
        assert result.exit_code == 0, result.output

    thread_files = sorted((space / "threads").glob("THREAD-*.md"))
    assert len(thread_files) == 2
    assert all(NEW_THREAD_RE.match(path.stem) for path in thread_files)

    result = runner.invoke(
        app,
        ["inbox", "--agent", "claude"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert "Direct" in result.output
    assert "Group" in result.output


def test_append_preserves_existing_thread_prefix_and_records_session(tmp_path, monkeypatch):
    space, project, config_dir = init_space(tmp_path, monkeypatch)
    monkeypatch.chdir(project)

    result = runner.invoke(
        app,
        ["send", "--to-agent", "codex", "--title", "Progress", "--message", "initial body"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    thread_id = created_thread_id(result.output)
    assert NEW_THREAD_RE.match(thread_id)

    thread = thread_file(space, thread_id)
    before = thread.read_text(encoding="utf-8")
    result = runner.invoke(
        app,
        ["append", thread_id, "--message", "continued here", "--session-id", "session-123"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output

    after = thread.read_text(encoding="utf-8")
    assert after.startswith(before)
    assert "session: session-123" in after
    assert "session:" in before
    assert "continued here" in after

    frontmatter_before = before.split("---\n", 2)[1]
    frontmatter_after = after.split("---\n", 2)[1]
    assert frontmatter_after == frontmatter_before


def test_session_id_from_env_is_not_persisted_to_local_profile(tmp_path, monkeypatch):
    space, project, config_dir = init_space(tmp_path, monkeypatch)
    monkeypatch.chdir(project)

    result = runner.invoke(
        app,
        ["send", "--to-agent", "codex", "--title", "Env Session", "--message", "body"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    thread_id = created_thread_id(result.output)

    result = runner.invoke(
        app,
        ["append", thread_id, "--message", "env session"],
        env={"CAS_CONFIG_DIR": str(config_dir), "CAS_SESSION_ID": "env-session"},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert "session: env-session" in thread_file(space, thread_id).read_text()
    assert "session" not in (config_dir / "profile.yaml").read_text()


def test_sync_commits_only_in_cas_space_without_remote(tmp_path, monkeypatch):
    space, project, config_dir = init_space(tmp_path, monkeypatch)
    monkeypatch.chdir(project)

    result = runner.invoke(
        app,
        ["send", "--to-agent", "codex", "--title", "Sync", "--message", "body"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["sync"], env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "No CAS changes to commit." in result.output
    assert "No Git remote configured" in result.output

    log = subprocess.run(["git", "log", "--oneline"], cwd=space, check=True, text=True, capture_output=True)
    assert "cas send THREAD-" in log.stdout
    assert "cas init" in log.stdout
    project_status = subprocess.run(["git", "status", "--short"], cwd=project, check=True, text=True, capture_output=True)
    assert project_status.stdout == ""


def test_mutating_commands_auto_push_to_remote(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=bare, check=True)

    space = tmp_path / "space"
    subprocess.run(["git", "clone", str(bare), str(space)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=space, check=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=space, check=True)

    project = git_repo(tmp_path / "project")
    monkeypatch.chdir(project)

    result = runner.invoke(
        app,
        ["init", str(space), "--user-id", "westdes", "--agent", "codex"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert "Synced CAS space." in result.output

    result = runner.invoke(
        app,
        ["attach", str(space)],
        env={"CAS_CONFIG_DIR": str(config_dir)},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(
        app,
        ["send", "--to-agent", "codex", "--title", "Remote", "--message", "pushed body"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert "Synced CAS space." in result.output

    thread_id = created_thread_id(result.output)
    remote_thread = subprocess.run(
        ["git", f"--git-dir={bare}", "show", f"main:threads/{thread_id}.md"],
        check=True,
        text=True,
        capture_output=True,
    )
    assert "pushed body" in remote_thread.stdout


def test_profile_body_file_read_list_comment_guide_and_registry(tmp_path, monkeypatch):
    space, project, config_dir = init_space(tmp_path, monkeypatch)
    monkeypatch.chdir(project)

    body_file = tmp_path / "body.md"
    body_file.write_text("body from file\n", encoding="utf-8")

    commands = [
        ["profile", "--user", "westdes", "--agent", "claude", "--name", "West Des", "--email", "w@example.com"],
        ["agent", "add", "claude", "--label", "Claude Code"],
        ["group", "add", "research"],
        ["group", "join", "research", "claude"],
        ["send", "--from", "codex", "--to-agent", "claude", "--title", "Body File", "--body-file", str(body_file)],
    ]
    for args in commands:
        result = runner.invoke(app, args, env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
        assert result.exit_code == 0, result.output
    thread_id = created_thread_id(result.output)

    result = runner.invoke(app, ["list"], env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert thread_id in result.output

    result = runner.invoke(app, ["read", thread_id], env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "body from file" in result.output

    result = runner.invoke(
        app,
        ["comment", thread_id, "--agent", "claude", "--message", "comment alias", "--session-id", "comment-session"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    thread_text = thread_file(space, thread_id).read_text(encoding="utf-8")
    assert "comment alias" in thread_text
    assert "session: comment-session" in thread_text

    result = runner.invoke(app, ["guide"], env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "CoAgentSpace Agent Guide" in result.output

    result = runner.invoke(app, ["registry"], env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "westdes" in result.output
    assert "claude" in result.output
    assert "research: claude" in result.output


def test_empty_views_and_cli_validation_errors(tmp_path, monkeypatch):
    space, project, config_dir = init_space(tmp_path, monkeypatch)
    monkeypatch.chdir(project)

    result = runner.invoke(app, ["list"], env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "No threads found." in result.output

    result = runner.invoke(
        app,
        ["send", "--to-agent", "codex", "--to-group", "research", "--title", "Bad", "--message", "bad"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
    )
    assert result.exit_code != 0
    assert "Use exactly one" in result.output

    body_file = tmp_path / "body.md"
    body_file.write_text("file body", encoding="utf-8")
    result = runner.invoke(
        app,
        ["send", "--to-agent", "codex", "--title", "Bad", "--message", "msg", "--body-file", str(body_file)],
        env={"CAS_CONFIG_DIR": str(config_dir)},
    )
    assert result.exit_code != 0
    assert "Use either --message or --body-file" in result.output
    assert "pre-write pull" not in result.output

    result = runner.invoke(app, ["group", "join", "missing", "codex"], env={"CAS_CONFIG_DIR": str(config_dir)})
    assert result.exit_code != 0
    assert "Unknown group" in str(result.exception)

    result = runner.invoke(app, ["group", "add", "research"], env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
    assert result.exit_code == 0
    result = runner.invoke(app, ["group", "join", "research", "missing"], env={"CAS_CONFIG_DIR": str(config_dir)})
    assert result.exit_code != 0
    assert "Unknown agent" in str(result.exception)


def test_space_resolution_modes_and_validation_errors(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    space = git_repo(tmp_path / "space")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["init", str(space), "--user-id", "westdes", "--agent", "codex"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output

    project = git_repo(tmp_path / "project")
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["list", "--space", str(space)], env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["list"], env={"CAS_CONFIG_DIR": str(config_dir), "CAS_SPACE": str(space)}, catch_exceptions=False)
    assert result.exit_code == 0, result.output

    monkeypatch.chdir(space)
    result = runner.invoke(app, ["list"], env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
    assert result.exit_code == 0, result.output

    other_project = git_repo(tmp_path / "other")
    monkeypatch.chdir(other_project)
    result = runner.invoke(app, ["list"], env={"CAS_CONFIG_DIR": str(config_dir)})
    assert result.exit_code != 0
    assert "No CoAgentSpace space found" in str(result.exception)

    fake_space = tmp_path / "fake-space"
    (fake_space / ".coagentspace").mkdir(parents=True)
    (fake_space / ".coagentspace" / "config.yaml").write_text("version: 1\n", encoding="utf-8")
    (fake_space / "threads").mkdir()
    result = runner.invoke(app, ["attach", str(fake_space)], env={"CAS_CONFIG_DIR": str(config_dir)})
    assert result.exit_code != 0
    assert "not a Git repo" in str(result.exception)


def test_thread_parser_skips_bad_files_and_reports_missing_thread(tmp_path, monkeypatch):
    space, project, config_dir = init_space(tmp_path, monkeypatch)
    monkeypatch.chdir(project)

    bad = space / "threads" / "THREAD-9999.md"
    bad.write_text("missing frontmatter", encoding="utf-8")

    result = runner.invoke(app, ["list"], env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "THREAD-9999" not in result.output

    result = runner.invoke(app, ["read", "THREAD-1234"], env={"CAS_CONFIG_DIR": str(config_dir)})
    assert result.exit_code != 0
    assert "was not found" in str(result.exception)


def test_v1_status_doctor_version_session_search_and_filters(tmp_path, monkeypatch):
    space, project, config_dir = init_space(tmp_path, monkeypatch)
    monkeypatch.chdir(project)

    commands = [
        ["agent", "add", "claude"],
        ["group", "add", "research"],
        ["group", "join", "research", "claude"],
        [
            "send",
            "--from",
            "codex",
            "--to-agent",
            "claude",
            "--title",
            "Alpha direct",
            "--message",
            "body has needle",
            "--session-id",
            "send-session",
        ],
        ["send", "--from", "claude", "--to-group", "research", "--title", "Beta group", "--message", "group body"],
    ]
    for args in commands:
        result = runner.invoke(app, args, env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
        assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["version"], env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
    assert result.exit_code == 0
    assert __version__ in result.output

    result = runner.invoke(
        app,
        ["session", "--agent", "codex", "--session-id", "explicit-session"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
        catch_exceptions=False,
    )
    assert result.output.strip() == "explicit-session"

    result = runner.invoke(app, ["status"], env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert f"space: {space}" in result.output
    assert "default_agent_id: codex" in result.output
    assert "dirty: no" in result.output

    result = runner.invoke(app, ["doctor"], env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "doctor: ok" in result.output

    result = runner.invoke(app, ["search", "needle"], env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "Alpha direct" in result.output
    assert "Beta group" not in result.output

    result = runner.invoke(app, ["list", "--to-agent", "claude"], env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
    assert "Alpha direct" in result.output
    assert "Beta group" not in result.output

    result = runner.invoke(app, ["list", "--to-group", "research"], env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
    assert "Beta group" in result.output
    assert "Alpha direct" not in result.output

    result = runner.invoke(app, ["list", "--from", "claude"], env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
    assert "Beta group" in result.output
    assert "Alpha direct" not in result.output

    alpha_thread = next(path.read_text() for path in (space / "threads").glob("THREAD-*.md") if "Alpha direct" in path.read_text())
    assert "session: send-session" in alpha_thread


def test_old_thread_ids_remain_readable_and_appendable(tmp_path, monkeypatch):
    space, project, config_dir = init_space(tmp_path, monkeypatch)
    monkeypatch.chdir(project)

    old_thread = space / "threads" / "THREAD-0001.md"
    old_thread.write_text(
        "---\n"
        "thread_id: THREAD-0001\n"
        "from: codex\n"
        "to_type: agent\n"
        "to: codex\n"
        "title: Old thread\n"
        "created_at: '2026-05-20T13:00:00Z'\n"
        "---\n"
        "old body\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "threads/THREAD-0001.md"], cwd=space, check=True)
    subprocess.run(["git", "commit", "-m", "add old thread"], cwd=space, check=True, capture_output=True)

    result = runner.invoke(app, ["read", "THREAD-0001"], env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "old body" in result.output

    result = runner.invoke(
        app,
        ["append", "THREAD-0001", "--message", "old append", "--session-id", "old-session"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert "session: old-session" in old_thread.read_text(encoding="utf-8")


def test_dirty_cas_repo_blocks_mutation_without_partial_write(tmp_path, monkeypatch):
    space, project, config_dir = init_space(tmp_path, monkeypatch)
    monkeypatch.chdir(project)
    (space / "dirty.txt").write_text("dirty", encoding="utf-8")

    result = runner.invoke(
        app,
        ["send", "--to-agent", "codex", "--title", "Should fail", "--message", "body"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
    )
    assert result.exit_code != 0
    assert "uncommitted changes" in str(result.exception)
    assert list((space / "threads").glob("THREAD-*.md")) == []


def test_doctor_reports_invalid_thread_files(tmp_path, monkeypatch):
    space, project, config_dir = init_space(tmp_path, monkeypatch)
    monkeypatch.chdir(project)
    (space / "threads" / "THREAD-bad.md").write_text("bad", encoding="utf-8")

    result = runner.invoke(app, ["doctor"], env={"CAS_CONFIG_DIR": str(config_dir)})
    assert result.exit_code != 0
    assert "invalid thread files" in result.output


def test_pre_write_pull_rebase_gets_remote_changes_before_send(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=bare, check=True)

    space1 = tmp_path / "space1"
    subprocess.run(["git", "clone", str(bare), str(space1)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=space1, check=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=space1, check=True)
    project1 = git_repo(tmp_path / "project1")
    monkeypatch.chdir(project1)

    result = runner.invoke(
        app,
        ["init", str(space1), "--user-id", "westdes", "--agent", "codex"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["attach", str(space1)], env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
    assert result.exit_code == 0, result.output

    space2 = tmp_path / "space2"
    subprocess.run(["git", "clone", str(bare), str(space2)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=space2, check=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=space2, check=True)
    result = runner.invoke(
        app,
        ["send", "--space", str(space2), "--to-agent", "codex", "--title", "Remote ahead", "--message", "ahead"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(
        app,
        ["send", "--to-agent", "codex", "--title", "After pull", "--message", "local"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert "Pulled latest CAS changes." in result.output

    remote_log = subprocess.run(
        ["git", f"--git-dir={bare}", "log", "--oneline", "--all"],
        check=True,
        text=True,
        capture_output=True,
    )
    assert "Remote ahead" in subprocess.run(
        ["git", f"--git-dir={bare}", "grep", "Remote ahead", "main"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    assert "cas send" in remote_log.stdout


def test_failed_pre_write_rebase_does_not_create_new_thread(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=bare, check=True)

    space1 = tmp_path / "space1"
    subprocess.run(["git", "clone", str(bare), str(space1)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=space1, check=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=space1, check=True)
    project1 = git_repo(tmp_path / "project1")
    monkeypatch.chdir(project1)

    result = runner.invoke(
        app,
        ["init", str(space1), "--user-id", "westdes", "--agent", "codex"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["attach", str(space1)], env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
    assert result.exit_code == 0, result.output

    conflict_path = Path("threads/THREAD-conflict.md")
    (space1 / conflict_path).write_text(
        "---\nthread_id: THREAD-conflict\nfrom: codex\nto_type: agent\nto: codex\ntitle: local\ncreated_at: '2026-05-20T13:00:00Z'\n---\nlocal\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", str(conflict_path)], cwd=space1, check=True)
    subprocess.run(["git", "commit", "-m", "local conflict"], cwd=space1, check=True, capture_output=True)

    space2 = tmp_path / "space2"
    subprocess.run(["git", "clone", str(bare), str(space2)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=space2, check=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=space2, check=True)
    (space2 / conflict_path.parent).mkdir(parents=True, exist_ok=True)
    (space2 / conflict_path).write_text(
        "---\nthread_id: THREAD-conflict\nfrom: claude\nto_type: agent\nto: codex\ntitle: remote\ncreated_at: '2026-05-20T13:00:00Z'\n---\nremote\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", str(conflict_path)], cwd=space2, check=True)
    subprocess.run(["git", "commit", "-m", "remote conflict"], cwd=space2, check=True, capture_output=True)
    subprocess.run(["git", "push"], cwd=space2, check=True, capture_output=True)

    result = runner.invoke(
        app,
        ["send", "--to-agent", "codex", "--title", "Should not write", "--message", "body"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
    )
    assert result.exit_code != 0
    assert "Could not pull/rebase" in str(result.exception)
    assert not any("Should not write" in path.read_text(encoding="utf-8", errors="ignore") for path in (space1 / "threads").glob("THREAD-*.md"))


def test_text_helpers():
    assert slugify("West Des") == "west-des"
    assert slugify("!!!", fallback="fallback") == "fallback"
    assert email_local_part("tester@example.com") == "tester"
    assert email_local_part(None) is None
    assert email_local_part("not-an-email") is None
