from __future__ import annotations

import subprocess
from pathlib import Path

import yaml
from typer.testing import CliRunner

from coagentspace.cli import app
from coagentspace.text import email_local_part, slugify


runner = CliRunner()


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
    assert [path.name for path in thread_files] == ["THREAD-0001.md", "THREAD-0002.md"]

    result = runner.invoke(
        app,
        ["inbox", "--agent", "claude"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert "THREAD-0001" in result.output
    assert "Direct" in result.output
    assert "THREAD-0002" in result.output
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

    thread = space / "threads" / "THREAD-0001.md"
    before = thread.read_text(encoding="utf-8")
    result = runner.invoke(
        app,
        ["append", "THREAD-0001", "--message", "continued here", "--session-id", "session-123"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output

    after = thread.read_text(encoding="utf-8")
    assert after.startswith(before)
    assert "session: session-123" in after
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

    result = runner.invoke(
        app,
        ["append", "THREAD-0001", "--message", "env session"],
        env={"CAS_CONFIG_DIR": str(config_dir), "CAS_SESSION_ID": "env-session"},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert "session: env-session" in (space / "threads" / "THREAD-0001.md").read_text()
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
    assert "cas send THREAD-0001" in log.stdout
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

    remote_thread = subprocess.run(
        ["git", f"--git-dir={bare}", "show", "main:threads/THREAD-0001.md"],
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

    result = runner.invoke(app, ["list"], env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "THREAD-0001" in result.output

    result = runner.invoke(app, ["read", "THREAD-0001"], env={"CAS_CONFIG_DIR": str(config_dir)}, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "body from file" in result.output

    result = runner.invoke(
        app,
        ["comment", "THREAD-0001", "--agent", "claude", "--message", "comment alias", "--session-id", "comment-session"],
        env={"CAS_CONFIG_DIR": str(config_dir)},
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    thread_text = (space / "threads" / "THREAD-0001.md").read_text(encoding="utf-8")
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


def test_text_helpers():
    assert slugify("West Des") == "west-des"
    assert slugify("!!!", fallback="fallback") == "fallback"
    assert email_local_part("tester@example.com") == "tester"
    assert email_local_part(None) is None
    assert email_local_part("not-an-email") is None
