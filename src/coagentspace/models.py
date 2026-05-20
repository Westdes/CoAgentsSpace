from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ThreadFrontmatter(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    thread_id: str
    from_agent: str = Field(alias="from")
    to_type: Literal["agent", "group"]
    to: str
    title: str
    created_at: str


class LocalProfile(BaseModel):
    default_user_id: str | None = None
    default_agent_id: str | None = None
    name: str | None = None
    email: str | None = None


class ProjectMapping(BaseModel):
    space: str


class ProjectsConfig(BaseModel):
    projects: dict[str, ProjectMapping] = Field(default_factory=dict)


class RegistryState(BaseModel):
    users: dict[str, dict] = Field(default_factory=dict)
    agents: dict[str, dict] = Field(default_factory=dict)
    groups: dict[str, dict] = Field(default_factory=dict)
