from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated

import typer

from .git import git_identity, sync_space
from .local import attach_space, load_profile, resolve_space, update_profile, validate_space
from .registry import join_group, load_registry, register_agent, register_group, register_user
from .space import initialize_space
from .text import email_local_part, slugify
from .threads import append_to_thread, create_thread, inbox_threads, iter_threads, thread_path


app = typer.Typer(no_args_is_help=True, help="CoAgentSpace append-only thread CLI.")
agent_app = typer.Typer(no_args_is_help=True, help="Manage agent identities.")
group_app = typer.Typer(no_args_is_help=True, help="Manage groups.")
app.add_typer(agent_app, name="agent")
app.add_typer(group_app, name="group")


def fail(message: str) -> None:
    raise typer.BadParameter(message)


def read_body(message: str | None, body_file: Path | None) -> str:
    if message and body_file:
        fail("Use either --message or --body-file, not both.")
    if body_file:
        return body_file.read_text(encoding="utf-8")
    return message or ""


def default_agent(required: bool = True) -> str | None:
    agent = load_profile().default_agent_id
    if required and not agent:
        fail("No agent provided and no default_agent_id in local profile. Use --agent or `cas profile --agent <id>`.")
    return agent


def print_threads(items) -> None:
    if not items:
        typer.echo("No threads found.")
        return
    for frontmatter, _ in items:
        typer.echo(
            f"{frontmatter.thread_id}  {frontmatter.to_type}:{frontmatter.to}  "
            f"{frontmatter.created_at}  {frontmatter.title}"
        )


def echo_sync(space: Path, message: str) -> None:
    for line in sync_space(space, message):
        typer.echo(line)


@app.command("init")
def init_command(
    space_path: Annotated[Path, typer.Argument(help="Path to the independent CAS space repo.")],
    user_id: Annotated[str | None, typer.Option("--user-id", help="User id to register.")] = None,
    user_name: Annotated[str | None, typer.Option("--user-name", help="User display name.")] = None,
    user_email: Annotated[str | None, typer.Option("--user-email", help="User email.")] = None,
    agent: Annotated[str | None, typer.Option("--agent", help="Optional initial agent id.")] = None,
) -> None:
    """Create an independent CoAgentSpace repo."""
    space = space_path.expanduser().resolve()
    initialize_space(space)

    git_name, git_email = git_identity(space)
    name = user_name or git_name
    email = user_email or git_email
    resolved_user_id = user_id or slugify(name or email_local_part(email) or "user")

    register_user(space, resolved_user_id, name, email)
    if agent:
        register_agent(space, agent, resolved_user_id)

    update_profile(
        default_user_id=resolved_user_id,
        default_agent_id=agent,
        name=name,
        email=email,
    )
    typer.echo(f"Initialized CoAgentSpace at {space}")
    typer.echo(f"Registered user: {resolved_user_id}")
    if agent:
        typer.echo(f"Registered default agent: {agent}")
    echo_sync(space, "cas init")


@app.command()
def attach(
    space_path: Annotated[Path, typer.Argument(help="Path to an initialized CAS space.")]
) -> None:
    """Attach the current project repo to a CAS space."""
    space = validate_space(space_path.expanduser().resolve())
    project = attach_space(space, Path.cwd())
    typer.echo(f"Attached {project} -> {space}")


@app.command()
def profile(
    user: Annotated[str | None, typer.Option("--user", help="Set default user id.")] = None,
    agent: Annotated[str | None, typer.Option("--agent", help="Set default agent id.")] = None,
    name: Annotated[str | None, typer.Option("--name", help="Set display name.")] = None,
    email: Annotated[str | None, typer.Option("--email", help="Set email.")] = None,
) -> None:
    """Show or update local operation defaults."""
    updated = update_profile(default_user_id=user, default_agent_id=agent, name=name, email=email)
    typer.echo(f"default_user_id: {updated.default_user_id or ''}")
    typer.echo(f"default_agent_id: {updated.default_agent_id or ''}")
    typer.echo(f"name: {updated.name or ''}")
    typer.echo(f"email: {updated.email or ''}")


@agent_app.command("add")
def agent_add(
    agent_id: Annotated[str, typer.Argument(help="Stable agent/persona id.")],
    user: Annotated[str | None, typer.Option("--user", help="Owner user id.")] = None,
    label: Annotated[str | None, typer.Option("--label", help="Display label.")] = None,
    space_option: Annotated[str | None, typer.Option("--space", help="CAS space path.")] = None,
) -> None:
    """Register an agent identity."""
    space = resolve_space(Path.cwd(), space_option)
    owner = user or load_profile().default_user_id
    register_agent(space, agent_id, owner, label)
    typer.echo(f"Registered agent `{agent_id}` in {space}")
    echo_sync(space, f"cas agent add {agent_id}")


@group_app.command("add")
def group_add(
    group_id: Annotated[str, typer.Argument(help="Group id.")],
    space_option: Annotated[str | None, typer.Option("--space", help="CAS space path.")] = None,
) -> None:
    """Register a group."""
    space = resolve_space(Path.cwd(), space_option)
    register_group(space, group_id)
    typer.echo(f"Registered group `{group_id}` in {space}")
    echo_sync(space, f"cas group add {group_id}")


@group_app.command("join")
def group_join(
    group_id: Annotated[str, typer.Argument(help="Group id.")],
    agent_id: Annotated[str, typer.Argument(help="Agent id.")],
    space_option: Annotated[str | None, typer.Option("--space", help="CAS space path.")] = None,
) -> None:
    """Add an agent to a group."""
    space = resolve_space(Path.cwd(), space_option)
    join_group(space, group_id, agent_id)
    typer.echo(f"Added `{agent_id}` to group `{group_id}`")
    echo_sync(space, f"cas group join {group_id} {agent_id}")


@app.command()
def send(
    title: Annotated[str, typer.Option("--title", help="Thread title.")],
    to_agent: Annotated[str | None, typer.Option("--to-agent", help="Send to one agent.")] = None,
    to_group: Annotated[str | None, typer.Option("--to-group", help="Send to one group.")] = None,
    from_agent: Annotated[str | None, typer.Option("--from", help="Sender agent id.")] = None,
    message: Annotated[str | None, typer.Option("--message", help="Markdown message body.")] = None,
    body_file: Annotated[Path | None, typer.Option("--body-file", help="Read Markdown body from file.")] = None,
    space_option: Annotated[str | None, typer.Option("--space", help="CAS space path.")] = None,
) -> None:
    """Create a new append-only thread."""
    if bool(to_agent) == bool(to_group):
        fail("Use exactly one of --to-agent or --to-group.")
    space = resolve_space(Path.cwd(), space_option)
    sender = from_agent or default_agent(required=True)
    thread_id = create_thread(
        space=space,
        from_agent=sender,
        to_type="agent" if to_agent else "group",
        to=to_agent or to_group or "",
        title=title,
        body=read_body(message, body_file),
    )
    typer.echo(f"Created {thread_id}")
    echo_sync(space, f"cas send {thread_id}")


@app.command("list")
def list_threads(
    limit: Annotated[int, typer.Option("--limit", "-n", help="Maximum threads to show.")] = 20,
    space_option: Annotated[str | None, typer.Option("--space", help="CAS space path.")] = None,
) -> None:
    """List recent threads."""
    space = resolve_space(Path.cwd(), space_option)
    items = iter_threads(space)[-limit:]
    print_threads(items)


@app.command()
def inbox(
    agent: Annotated[str | None, typer.Option("--agent", help="Agent id. Defaults to local profile.")] = None,
    space_option: Annotated[str | None, typer.Option("--space", help="CAS space path.")] = None,
) -> None:
    """Show threads addressed to an agent or its groups."""
    space = resolve_space(Path.cwd(), space_option)
    resolved_agent = agent or default_agent(required=True)
    print_threads(inbox_threads(space, resolved_agent))


@app.command()
def read(
    thread_id: Annotated[str, typer.Argument(help="Thread id, e.g. THREAD-0001.")],
    space_option: Annotated[str | None, typer.Option("--space", help="CAS space path.")] = None,
) -> None:
    """Print a full thread."""
    space = resolve_space(Path.cwd(), space_option)
    typer.echo(thread_path(space, thread_id).read_text(encoding="utf-8"))


@app.command()
def append(
    thread_id: Annotated[str, typer.Argument(help="Thread id, e.g. THREAD-0001.")],
    agent: Annotated[str | None, typer.Option("--agent", help="Appending agent id.")] = None,
    session_id: Annotated[str | None, typer.Option("--session-id", help="Audit session id for this append.")] = None,
    message: Annotated[str | None, typer.Option("--message", help="Markdown message to append.")] = None,
    body_file: Annotated[Path | None, typer.Option("--body-file", help="Read Markdown body from file.")] = None,
    space_option: Annotated[str | None, typer.Option("--space", help="CAS space path.")] = None,
) -> None:
    """Append a Markdown entry to a thread."""
    space = resolve_space(Path.cwd(), space_option)
    resolved_agent = agent or default_agent(required=True)
    resolved_session = append_to_thread(
        space=space,
        thread_id=thread_id,
        agent=resolved_agent,
        session_id=session_id,
        message=read_body(message, body_file),
    )
    typer.echo(f"Appended to {thread_id} as {resolved_agent} session {resolved_session}")
    echo_sync(space, f"cas append {thread_id}")


@app.command()
def comment(
    thread_id: Annotated[str, typer.Argument(help="Thread id, e.g. THREAD-0001.")],
    agent: Annotated[str | None, typer.Option("--agent", help="Appending agent id.")] = None,
    session_id: Annotated[str | None, typer.Option("--session-id", help="Audit session id for this append.")] = None,
    message: Annotated[str | None, typer.Option("--message", help="Markdown message to append.")] = None,
    body_file: Annotated[Path | None, typer.Option("--body-file", help="Read Markdown body from file.")] = None,
    space_option: Annotated[str | None, typer.Option("--space", help="CAS space path.")] = None,
) -> None:
    """Alias for append."""
    append(thread_id, agent, session_id, message, body_file, space_option)


@app.command()
def sync(
    message: Annotated[str | None, typer.Option("--message", "-m", help="Commit message.")] = None,
    space_option: Annotated[str | None, typer.Option("--space", help="CAS space path.")] = None,
) -> None:
    """Commit and sync the independent CAS space repo."""
    space = resolve_space(Path.cwd(), space_option)
    echo_sync(space, message or "cas sync")


@app.command()
def guide(
    space_option: Annotated[str | None, typer.Option("--space", help="CAS space path.")] = None,
) -> None:
    """Print agent guidance from the attached CAS space."""
    space = resolve_space(Path.cwd(), space_option)
    guide_path = space / "AGENTS.md"
    typer.echo(guide_path.read_text(encoding="utf-8"))


@app.command()
def watch(
    agent: Annotated[str | None, typer.Option("--agent", help="Agent id. Defaults to local profile.")] = None,
    interval: Annotated[float, typer.Option("--interval", help="Polling interval in seconds.")] = 5.0,
    space_option: Annotated[str | None, typer.Option("--space", help="CAS space path.")] = None,
) -> None:
    """Poll inbox and print newly visible threads."""
    space = resolve_space(Path.cwd(), space_option)
    resolved_agent = agent or default_agent(required=True)
    seen: set[str] = set()
    typer.echo(f"Watching inbox for {resolved_agent}. Press Ctrl-C to stop.")
    while True:
        for frontmatter, _ in inbox_threads(space, resolved_agent):
            if frontmatter.thread_id not in seen:
                seen.add(frontmatter.thread_id)
                typer.echo(f"{frontmatter.thread_id}  {frontmatter.title}")
        time.sleep(interval)


@app.command()
def registry(
    space_option: Annotated[str | None, typer.Option("--space", help="CAS space path.")] = None,
) -> None:
    """Show derived users, agents, and groups."""
    space = resolve_space(Path.cwd(), space_option)
    state = load_registry(space)
    typer.echo("users:")
    for user_id in sorted(state.users):
        typer.echo(f"  {user_id}")
    typer.echo("agents:")
    for agent_id in sorted(state.agents):
        typer.echo(f"  {agent_id}")
    typer.echo("groups:")
    for group_id, group in sorted(state.groups.items()):
        members = ", ".join(group.get("members", []))
        typer.echo(f"  {group_id}: {members}")


if __name__ == "__main__":
    app()
