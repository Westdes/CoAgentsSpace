from __future__ import annotations


CONFIG = """version: 1
protocol: simple-thread
history_rule: append-only
"""

AGENTS = """# CoAgentSpace Agent Guide

This repository is a CoAgentSpace space: an append-only Markdown thread log for agent collaboration.

At session start:

```bash
cas status
cas session
cas inbox
```

Read a thread:

```bash
cas read THREAD-20260520T130000Z-a13f9c82
```

Append progress, notes, corrections, or handoff context:

```bash
cas append THREAD-20260520T130000Z-a13f9c82 --message "I continued from here..."
```

Rules:
- Do not rewrite existing thread files.
- Do not edit frontmatter after a thread is created.
- Add corrections as new appended notes.
- Mutating commands auto-commit and push to the CAS Git remote when one exists.
- Session IDs are printed by `cas session` and recorded in every thread entry.
- Use natural language; threads are for durable shared context.
"""

CLAUDE = AGENTS.replace("CoAgentSpace Agent Guide", "CoAgentSpace Claude Guide")

THREAD_TEMPLATE = """---
thread_id: THREAD-20260520T130000Z-a13f9c82
from: codex
to_type: agent
to: claude
title: "Short title"
created_at: "2026-05-20T13:00:00Z"
---
## 2026-05-20T13:00:00Z | created

agent: codex
session: codex-a13f9c82

Write natural language Markdown here.
"""

APPEND_TEMPLATE = """---

## 2026-05-20T13:20:00Z

agent: codex
session: codex-a13f9c82

Write an append-only update here.
"""

AGENT_SKILL_TEMPLATE = """# Agent Skill

Use CoAgentSpace to read inbox threads, preserve context, and append progress.

Start with:

```bash
cas status
cas session
cas inbox
```
"""
