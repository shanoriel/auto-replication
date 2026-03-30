from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RuntimeRegistration(BaseModel):
    runtime_id: str | None = None
    machine_id: str
    name: str
    status: str = "idle"
    summary: str | None = None
    host: str | None = None
    base_url: str | None = None
    labels: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)


class RuntimeHeartbeat(BaseModel):
    status: str
    summary: str | None = None
    labels: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)


class AgentRegistration(BaseModel):
    agent_id: str | None = None
    runtime_id: str | None = None
    machine_id: str | None = None
    name: str
    kind: str = "local"
    host: str | None = None
    role: str | None = None
    transport: str = "http"
    status: str = "idle"
    summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentHeartbeat(BaseModel):
    status: str
    summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskCreate(BaseModel):
    title: str
    created_by: str
    status: str = "created"
    summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskUpdate(BaseModel):
    status: str | None = None
    summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DispatchCreate(BaseModel):
    task_id: str
    kind: str
    from_agent_id: str
    to_agent_id: str
    parent_dispatch_id: str | None = None
    status: str = "pending"
    payload: dict[str, Any] = Field(default_factory=dict)


class DispatchUpdate(BaseModel):
    status: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None
    accepted: bool | None = None
    resolved: bool | None = None


class SessionCreate(BaseModel):
    agent_id: str
    runtime_id: str | None = None
    task_id: str | None = None
    dispatch_id: str | None = None
    title: str
    role: str | None = None
    workspace_path: str | None = None
    codex_home: str | None = None
    status: str = "created"
    summary: str | None = None
    machine_id: str | None = None
    preset_id: str | None = None
    model: str | None = None
    initial_prompt: str | None = None


class SessionUpdate(BaseModel):
    status: str | None = None
    summary: str | None = None
    codex_thread_id: str | None = None


class SessionClaim(BaseModel):
    runner_id: str
    status: str = "launching"
    summary: str | None = None


class SessionEventCreate(BaseModel):
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class MessageCreate(BaseModel):
    content: str
    sender: str = "operator"
    direction: str = "outbound"
    status: str = "queued"


class MessageAck(BaseModel):
    status: str = "delivered"
