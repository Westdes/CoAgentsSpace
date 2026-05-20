from __future__ import annotations

import os
from pathlib import Path

from .files import atomic_write_yaml, read_yaml_file
from .git import git_toplevel, is_git_repo, project_root
from .models import LocalProfile, ProjectMapping, ProjectsConfig


def config_dir() -> Path:
    override = os.environ.get("CAS_CONFIG_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".config" / "coagentspace"


def profile_path() -> Path:
    return config_dir() / "profile.yaml"


def projects_path() -> Path:
    return config_dir() / "projects.yaml"


def load_profile() -> LocalProfile:
    return LocalProfile.model_validate(read_yaml_file(profile_path(), {}))


def save_profile(profile: LocalProfile) -> None:
    atomic_write_yaml(profile_path(), profile.model_dump(exclude_none=True))


def update_profile(
    *,
    default_user_id: str | None = None,
    default_agent_id: str | None = None,
    name: str | None = None,
    email: str | None = None,
) -> LocalProfile:
    profile = load_profile()
    if default_user_id is not None:
        profile.default_user_id = default_user_id
    if default_agent_id is not None:
        profile.default_agent_id = default_agent_id
    if name is not None:
        profile.name = name
    if email is not None:
        profile.email = email
    save_profile(profile)
    return profile


def load_projects() -> ProjectsConfig:
    return ProjectsConfig.model_validate(read_yaml_file(projects_path(), {"projects": {}}))


def save_projects(projects: ProjectsConfig) -> None:
    atomic_write_yaml(
        projects_path(),
        {
            "projects": {
                path: mapping.model_dump()
                for path, mapping in sorted(projects.projects.items())
            }
        },
    )


def attach_space(space: Path, cwd: Path) -> Path:
    root = project_root(cwd)
    projects = load_projects()
    projects.projects[str(root)] = ProjectMapping(space=str(space.expanduser().resolve()))
    save_projects(projects)
    return root


def find_space_upwards(cwd: Path) -> Path | None:
    for candidate in [cwd.resolve(), *cwd.resolve().parents]:
        if (candidate / ".coagentspace" / "config.yaml").exists() and (candidate / "threads").is_dir():
            return candidate
    return None


def resolve_space(cwd: Path, explicit_space: str | None = None) -> Path:
    if explicit_space:
        return validate_space(Path(explicit_space).expanduser().resolve())

    env_space = os.environ.get("CAS_SPACE")
    if env_space:
        return validate_space(Path(env_space).expanduser().resolve())

    current_space = find_space_upwards(cwd)
    if current_space:
        return current_space

    root = project_root(cwd)
    projects = load_projects()
    mapping = projects.projects.get(str(root))
    if mapping:
        return validate_space(Path(mapping.space).expanduser().resolve())

    raise RuntimeError(
        "No CoAgentSpace space found. Run `cas attach /path/to/space`, set CAS_SPACE, "
        "or run this command inside a CAS space."
    )


def validate_space(space: Path) -> Path:
    if not (space / ".coagentspace" / "config.yaml").exists():
        raise RuntimeError(f"{space} is not a CoAgentSpace space. Run `cas init {space}` first.")
    if not is_git_repo(space):
        raise RuntimeError(f"{space} is not a Git repo.")
    root = git_toplevel(space)
    if root != space.resolve():
        raise RuntimeError(f"{space} is inside Git repo {root}. Use the CAS space repo root.")
    return space
