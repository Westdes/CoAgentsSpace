# CoAgentSpace

CoAgentSpace is a minimal CLI for append-only Markdown threads shared through an independent Git repo.

It is meant for humans and coding agents that need durable context across sessions without adding files to the project repo they are working on.

## Install

From GitHub:

```bash
pipx install git+https://github.com/Westdes/CoAgentsSpace.git@v1.0.2
cas --help
```

For local development in this repo:

```bash
uv run cas --help
uv run pytest
```

## Mental Model

CoAgentSpace uses two repos:

- your normal project repo, for example `~/src/linux`
- a separate CAS space repo, for example `~/cas-spaces/linux-kernel`

CAS files live only in the CAS space. Your project repo does not get `.coagentspace/` or thread files.

## Quickstart

Create or clone a Git repo to use as the CAS space. The path you pass to `cas init` must be the Git repo root. If the repo is not already CAS-enabled, its working tree must be clean.

```bash
mkdir -p ~/cas-spaces/linux-kernel
cd ~/cas-spaces/linux-kernel
git init
```

Initialize it:

```bash
cas init ~/cas-spaces/linux-kernel --user-id westdes --agent codex
```

Attach a project repo to that CAS space:

```bash
cd ~/src/linux
cas attach ~/cas-spaces/linux-kernel
```

Register another agent and a group:

```bash
cas agent add claude
cas group add research
cas group join research codex
cas group join research claude
```

Create threads:

```bash
cas send --to-agent claude --title "Continue scheduler notes" --message "I stopped at fair.c."
cas send --to-group research --title "Review this idea" --message "Can someone check this design?"
```

At the start of every agent session:

```bash
cas status
cas session
cas inbox
```

Read and append:

```bash
cas read THREAD-20260520T130000Z-a13f9c82
cas append THREAD-20260520T130000Z-a13f9c82 --message "I picked this up and continued from the previous note."
```

Sync the CAS space:

```bash
cas sync
```

Mutating CAS commands also sync automatically. When the CAS space has a Git remote, commands such as `cas init`, `cas agent add`, `cas group add`, `cas group join`, `cas send`, and `cas append` commit the CAS-space change and push it immediately. Read-only commands such as `cas inbox`, `cas list`, and `cas read` do not create commits.

## Identity

`agent_id` is a stable worker or persona, not a single chat session.

Good IDs:

- `codex`
- `claude`
- `human`
- `reviewer`
- `codex-tests`

Multiple Codex sessions can use `agent_id=codex`. Each send and append records a session id for audit. Session ids are never stored in local config; they come from `--session-id`, `CAS_SESSION_ID`, or an ephemeral id generated for that command.

Check the session id CAS would use:

```bash
cas session
cas session --agent codex --session-id codex-explicit-session
```

## Thread Format

Threads live under `threads/` in the CAS space.

```markdown
---
thread_id: THREAD-20260520T130000Z-a13f9c82
from: codex
to_type: agent
to: claude
title: "Continue scheduler notes"
created_at: "2026-05-20T13:00:00Z"
---
## 2026-05-20T13:00:00Z | created

agent: codex
session: codex-a13f9c82

I stopped here. Continue from this note next session.
```

Append entries look like this:

```markdown
---

## 2026-05-20T13:20:00Z

agent: codex
session: codex-a13f9c82

I picked this up in a new session.
```

## Hard History Rule

Thread files are append-only.

- Do not rewrite existing thread content.
- Do not edit thread frontmatter after creation.
- Do not move or delete thread files.
- Add corrections as new appended notes.

The CLI follows this rule for thread files. Registry files use an append-only YAML event log.

## Commands

```bash
cas init <space_path>
cas attach <space_path>
cas profile
cas version
cas status
cas doctor
cas session
cas agent add <agent_id>
cas group add <group_id>
cas group join <group_id> <agent_id>
cas send --to-agent <agent_id> --title "..." --message "..."
cas send --to-group <group_id> --title "..." --message "..."
cas inbox
cas list --to-agent <agent_id>
cas search <query>
cas read THREAD-20260520T130000Z-a13f9c82
cas append THREAD-20260520T130000Z-a13f9c82 --message "..."
cas comment THREAD-20260520T130000Z-a13f9c82 --message "..."
cas sync
cas guide
```

## Sync Behavior

CoAgentSpace is Git-native by default. Every command that changes the CAS space first verifies the CAS repo is clean, pulls/rebases from the remote when possible, commits the change, and pushes to the configured remote when one exists. If the CAS space has no remote, the command still creates a local Git commit and reports that pull/push was skipped.

`cas sync` remains available for manual recovery or for pushing changes made outside the CLI.

## Discovery

Use `cas status` and `cas doctor` to verify which CAS space and identity are active.

Use filters when a space gets busy:

```bash
cas list --to-agent codex
cas list --to-group research
cas list --from claude
cas search "scheduler"
```

CoAgentSpace does not track unread state in v1.0. Agents should start with `cas inbox`, then read or search relevant threads.

## How The CLI Works

`pyproject.toml` declares this console script:

```toml
[project.scripts]
cas = "coagentspace.cli:app"
```

When a user installs the package with `pipx`, Python creates a `cas` executable that calls the Typer app in `coagentspace.cli`.
