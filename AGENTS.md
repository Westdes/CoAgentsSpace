# CoAgentSpace Agent Notes

This repository contains the source for CoAgentSpace, a Python CLI installed as `cas`.

## Hard Rules

- Coverage must stay above 90% for every change. `uv run pytest` enforces this with `--cov-fail-under=90`.
- Run `uv run pytest` before publishing or handing off changes.
- After every source or behavior change, also test the installed `cas` CLI against the live playground CAS repo at `/Users/edward/Documents/casPlayGround`.
- Playground tests must exercise the changed behavior through `cas`, not only through unit tests.
- If the playground test mutates CAS data, confirm the change auto-commits and pushes to `git@github.com:Westdes/casPlayGround.git`.
- CoAgentSpace must not write `.coagentspace/`, `threads/`, or other CAS files into a user's working project repo.
- CAS data belongs in an independent CAS Git repo selected by `cas init`, `cas attach`, `--space`, or `CAS_SPACE`.
- `cas init <space_path>` must target an existing Git repo root. If it is not already CAS-enabled, the worktree must be clean.
- Every command that mutates the CAS space must commit and push immediately when a remote exists.
- Mutating commands must pull/rebase before writing when a remote branch is available.
- Read-only commands such as `cas inbox`, `cas list`, and `cas read` must not create commits.
- Thread files are append-only after creation. Never rewrite, truncate, delete, move, or edit existing thread content.
- Thread frontmatter is immutable after creation.
- Corrections and progress updates must be appended as new Markdown entries.
- Do not reintroduce task, claim, completion, owner, status, or file-move workflow without an explicit product decision.
- Do not persist session IDs in local config. Session IDs may appear only in thread body audit entries.
- Sends and appends must include visible `agent:` and `session:` audit metadata in the thread body.
- Keep `README.md`, `AGENTS.md`, tests, and actual CLI behavior in sync.

## Current Product Shape

- CoAgentSpace stores collaboration data in an independent CAS Git repo, not in the user's project repo.
- `cas init <space_path>` requires an existing Git repo root.
- If the CAS repo is not already CAS-enabled, its working tree must be clean before initialization.
- `cas attach <space_path>` maps the current project repo to the CAS space in local config.
- Mutating CAS-space commands auto-sync by committing and pushing to the CAS remote.
- v1.0 adds `cas version`, `cas status`, `cas doctor`, `cas session`, and `cas search`.
- New thread IDs use `THREAD-YYYYMMDDTHHMMSSZ-<8hex>`; old `THREAD-0001` style files remain readable and appendable.
- Threads live under `threads/THREAD-YYYYMMDDTHHMMSSZ-<8hex>.md` in the CAS space.
- Thread frontmatter is immutable after creation.
- Thread body content is append-only.
- Registry data is stored as an append-only YAML event stream in `.coagentspace/users.yaml`.
- No task, claim, completion, status, or file-move workflow exists in the MVP.

## Local Config

Runtime user config is outside this repo:

```text
~/.config/coagentspace/profile.yaml
~/.config/coagentspace/projects.yaml
```

Tests set `CAS_CONFIG_DIR` so they do not touch real user config.

## Development Commands

Use `uv`:

```bash
uv run cas --help
uv run pytest
uv build
```

Coverage is a hard rule. The test command is configured in `pyproject.toml` to fail below 90% total package coverage.

After code changes, run a playground smoke test with the pipx-installed `cas`, for example:

```bash
cas inbox --agent codex
cas append THREAD-0003 --agent codex --session-id codex-playground-smoke --message "Playground smoke test for <change>."
```

If the smoke test appends data, verify `/Users/edward/Documents/casPlayGround` is clean and tracking `origin/main` afterward.

## Packaging

The install command documented in `README.md` is:

```bash
pipx install git+https://github.com/Westdes/CoAgentsSpace.git
```

For the v1.0 release, use:

```bash
pipx install git+https://github.com/Westdes/CoAgentsSpace.git@v1.0.2
```

The console entry point is:

```toml
[project.scripts]
cas = "coagentspace.cli:app"
```

## Source Map

- `src/coagentspace/cli.py` defines Typer commands.
- `src/coagentspace/local.py` resolves local profile, project mappings, and CAS space location.
- `src/coagentspace/space.py` validates and initializes CAS spaces.
- `src/coagentspace/threads.py` creates, reads, lists, filters, and appends thread files.
- `src/coagentspace/registry.py` appends and derives users, agents, groups, and group membership.
- `src/coagentspace/templates.py` contains files generated into CAS spaces.
- `tests/test_cli.py` covers the CLI and the important workflow guarantees.

## Invariants

- Do not write CoAgentSpace files into a user's project repo.
- Do not rewrite existing thread files.
- Do not edit thread frontmatter after creation.
- Do not persist session IDs in local config.
- Keep `README.md`, this file, and CLI behavior in sync.
- Run `uv run pytest` before publishing changes.
