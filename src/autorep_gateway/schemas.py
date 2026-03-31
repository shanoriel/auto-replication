from __future__ import annotations

from typing import Any
from typing import Literal

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
    created_by: Literal["human"] = "human"
    entry_agent_id: str
    participant_agent_ids: list[str] = Field(default_factory=list)
    objective: str
    initial_input: str | None = None
    status: str = "created"
    summary: str | None = None
    stage_plan: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskUpdate(BaseModel):
    status: str | None = None
    summary: str | None = None
    entry_agent_id: str | None = None
    participant_agent_ids: list[str] | None = None
    objective: str | None = None
    stage_plan: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DispatchCreate(BaseModel):
    task_id: str
    kind: str
    from_agent_id: str
    to_agent_id: str
    parent_dispatch_id: str | None = None
    status: str = "pending"
    payload: dict[str, Any] = Field(default_factory=dict)
    reply: dict[str, Any] | None = None


class DispatchUpdate(BaseModel):
    status: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    reply: dict[str, Any] | None = None
    session_id: str | None = None
    accepted: bool | None = None
    resolved: bool | None = None


class SessionCreate(BaseModel):
    agent_id: str
    runtime_id: str | None = None
    task_id: str | None = None
    dispatch_id: str | None = None
    title: str
    session_key: str | None = None
    role: str | None = None
    workspace_path: str | None = None
    codex_home: str | None = None
    status: str = "created"
    lifecycle_status: str | None = None
    summary: str | None = None
    machine_id: str | None = None
    preset_id: str | None = None
    model: str | None = None
    backend_kind: str = "codex"
    backend_session_id: str | None = None
    initial_prompt: str | None = None
    initial_input: str | None = None


class SessionUpdate(BaseModel):
    status: str | None = None
    lifecycle_status: str | None = None
    summary: str | None = None
    codex_thread_id: str | None = None
    backend_session_id: str | None = None


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


class SessionInputCreate(BaseModel):
    content: str
    kind: str = "message"
    sender: str = "operator"
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionInputUpdate(BaseModel):
    status: str
    error_text: str | None = None


class RuntimeInboxUpdate(BaseModel):
    status: str
