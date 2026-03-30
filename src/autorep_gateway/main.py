from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .catalog import find_by_id
from .config import settings
from .schemas import (
    AgentHeartbeat,
    AgentRegistration,
    DispatchCreate,
    DispatchUpdate,
    MessageAck,
    MessageCreate,
    RuntimeHeartbeat,
    RuntimeRegistration,
    SessionClaim,
    SessionCreate,
    SessionEventCreate,
    SessionUpdate,
    TaskCreate,
    TaskUpdate,
)
from .service import catalog_snapshot, db, ensure_layout, health_snapshot


ensure_layout()

app = FastAPI(title=settings.app_name, version="0.2.0")
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")


@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", **health_snapshot()}


@app.get("/")
def index() -> FileResponse:
    index_path = settings.static_dir / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="UI not found")
    return FileResponse(index_path)


@app.get("/api/catalog")
def catalog() -> dict[str, object]:
    return catalog_snapshot()


@app.get("/api/runtimes")
def list_runtimes() -> list[dict[str, object]]:
    return db.list_runtimes()


@app.post("/api/runtimes/register")
def register_runtime(payload: RuntimeRegistration) -> dict[str, object]:
    return db.upsert_runtime(
        runtime_id=payload.runtime_id,
        machine_id=payload.machine_id,
        name=payload.name,
        status=payload.status,
        summary=payload.summary,
        host=payload.host,
        base_url=payload.base_url,
        labels=payload.labels,
        capabilities=payload.capabilities,
    )


@app.post("/api/runtimes/{runtime_id}/heartbeat")
def runtime_heartbeat(runtime_id: str, payload: RuntimeHeartbeat) -> dict[str, object]:
    runtime = db.update_runtime_heartbeat(
        runtime_id,
        status=payload.status,
        summary=payload.summary,
        labels=payload.labels,
        capabilities=payload.capabilities,
    )
    if runtime is None:
        raise HTTPException(status_code=404, detail="Runtime not found")
    return runtime


@app.get("/api/runtime/launch-queue")
def launch_queue(runtime_id: str) -> list[dict[str, object]]:
    return db.list_runtime_launch_queue(runtime_id)


@app.get("/api/runtime/dispatch-queue")
def dispatch_queue(runtime_id: str, status: str = "pending") -> list[dict[str, object]]:
    return db.list_dispatches_for_runtime(runtime_id, statuses=[status])


@app.get("/api/agents")
def list_agents() -> list[dict[str, object]]:
    return db.list_agents()


@app.post("/api/agents/register")
def register_agent(payload: AgentRegistration) -> dict[str, object]:
    if payload.runtime_id is not None and db.get_runtime(payload.runtime_id) is None:
        raise HTTPException(status_code=404, detail="Runtime not found")
    return db.upsert_agent(
        agent_id=payload.agent_id,
        runtime_id=payload.runtime_id,
        machine_id=payload.machine_id,
        name=payload.name,
        kind=payload.kind,
        host=payload.host,
        role=payload.role,
        transport=payload.transport,
        status=payload.status,
        summary=payload.summary,
        metadata=payload.metadata,
    )


@app.post("/api/agents/{agent_id}/heartbeat")
def heartbeat(agent_id: str, payload: AgentHeartbeat) -> dict[str, object]:
    agent = db.update_agent_heartbeat(
        agent_id,
        status=payload.status,
        summary=payload.summary,
        metadata=payload.metadata,
    )
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@app.get("/api/agents/{agent_id}/outbox")
def outbox(agent_id: str) -> list[dict[str, object]]:
    return db.list_agent_outbox(agent_id)


@app.get("/api/tasks")
def list_tasks() -> list[dict[str, object]]:
    return db.list_tasks()


@app.post("/api/tasks")
def create_task(payload: TaskCreate) -> dict[str, object]:
    if db.get_agent(payload.created_by) is None:
        raise HTTPException(status_code=404, detail="created_by agent not found")
    return db.create_task(
        title=payload.title,
        created_by=payload.created_by,
        status=payload.status,
        summary=payload.summary,
        metadata=payload.metadata,
    )


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, object]:
    task = db.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.patch("/api/tasks/{task_id}")
def patch_task(task_id: str, payload: TaskUpdate) -> dict[str, object]:
    task = db.update_task(
        task_id,
        status=payload.status,
        summary=payload.summary,
        metadata=payload.metadata,
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.get("/api/dispatches")
def list_dispatches(
    to_agent_id: str | None = None,
    task_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, object]]:
    return db.list_dispatches(to_agent_id=to_agent_id, task_id=task_id, status=status)


@app.post("/api/dispatches")
def create_dispatch(payload: DispatchCreate) -> dict[str, object]:
    if db.get_task(payload.task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if db.get_agent(payload.from_agent_id) is None:
        raise HTTPException(status_code=404, detail="from_agent not found")
    if db.get_agent(payload.to_agent_id) is None:
        raise HTTPException(status_code=404, detail="to_agent not found")
    if payload.parent_dispatch_id is not None and db.get_dispatch(payload.parent_dispatch_id) is None:
        raise HTTPException(status_code=404, detail="parent dispatch not found")
    return db.create_dispatch(
        task_id=payload.task_id,
        kind=payload.kind,
        status=payload.status,
        from_agent_id=payload.from_agent_id,
        to_agent_id=payload.to_agent_id,
        parent_dispatch_id=payload.parent_dispatch_id,
        payload=payload.payload,
    )


@app.get("/api/dispatches/{dispatch_id}")
def get_dispatch(dispatch_id: str) -> dict[str, object]:
    dispatch = db.get_dispatch(dispatch_id)
    if dispatch is None:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    return dispatch


@app.patch("/api/dispatches/{dispatch_id}")
def patch_dispatch(dispatch_id: str, payload: DispatchUpdate) -> dict[str, object]:
    dispatch = db.update_dispatch(
        dispatch_id,
        status=payload.status,
        payload=payload.payload,
        session_id=payload.session_id,
        accepted=payload.accepted,
        resolved=payload.resolved,
    )
    if dispatch is None:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    return dispatch


@app.get("/api/sessions")
def list_sessions() -> list[dict[str, object]]:
    return db.list_sessions()


@app.post("/api/sessions")
def create_session(payload: SessionCreate) -> dict[str, object]:
    agent = db.get_agent(payload.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    runtime = None
    if payload.runtime_id is not None:
        runtime = db.get_runtime(payload.runtime_id)
        if runtime is None:
            raise HTTPException(status_code=404, detail="Runtime not found")
    if payload.task_id is not None and db.get_task(payload.task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if payload.dispatch_id is not None and db.get_dispatch(payload.dispatch_id) is None:
        raise HTTPException(status_code=404, detail="Dispatch not found")

    catalog_data = catalog_snapshot()
    machine = find_by_id(catalog_data["machines"], payload.machine_id or agent.get("machine_id"))
    preset = find_by_id(catalog_data["presets"], payload.preset_id)
    model = find_by_id(catalog_data["models"], payload.model)

    resolved_workspace = payload.workspace_path or (machine.get("workspace_path") if machine else None)
    base_codex_home = payload.codex_home or (machine.get("codex_home") if machine else None)
    resolved_codex_home = f"{base_codex_home}/presets/{preset['id']}" if base_codex_home and preset else base_codex_home
    resolved_role = payload.role or agent.get("role")

    session = db.create_session(
        agent_id=payload.agent_id,
        runtime_id=payload.runtime_id,
        task_id=payload.task_id,
        dispatch_id=payload.dispatch_id,
        title=payload.title,
        role=resolved_role,
        status=payload.status,
        summary=payload.summary,
        workspace_path=resolved_workspace,
        codex_home=resolved_codex_home,
        machine_id=payload.machine_id or agent.get("machine_id"),
        preset_id=payload.preset_id,
        model=model["id"] if model else payload.model,
        initial_prompt=payload.initial_prompt,
    )
    db.add_event(
        session_id=session["id"],
        agent_id=payload.agent_id,
        event_type="session.created",
        payload={
            "runtime_id": runtime["id"] if runtime else payload.runtime_id,
            "task_id": payload.task_id,
            "dispatch_id": payload.dispatch_id,
            "title": payload.title,
            "role": resolved_role,
            "machine_id": payload.machine_id or agent.get("machine_id"),
            "preset_id": payload.preset_id,
            "model": model["id"] if model else payload.model,
        },
    )
    if payload.dispatch_id is not None:
        db.update_dispatch(
            payload.dispatch_id,
            status="accepted",
            session_id=session["id"],
            accepted=True,
        )
    return session


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, object]:
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str) -> dict[str, object]:
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    deleted = db.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True, "id": session_id}


@app.patch("/api/sessions/{session_id}")
def patch_session(session_id: str, payload: SessionUpdate) -> dict[str, object]:
    session = db.update_session(
        session_id,
        status=payload.status,
        summary=payload.summary,
        codex_thread_id=payload.codex_thread_id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.post("/api/sessions/{session_id}/claim")
def claim_session(session_id: str, payload: SessionClaim) -> dict[str, object]:
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    updated = db.update_session(
        session_id,
        status=payload.status,
        summary=payload.summary or f"Claimed by {payload.runner_id}",
        codex_thread_id=session.get("codex_thread_id"),
    )
    assert updated is not None
    db.add_event(
        session_id=session_id,
        agent_id=session["agent_id"],
        event_type="runtime.session.claimed",
        payload={"runner_id": payload.runner_id, "status": payload.status},
    )
    return updated


@app.get("/api/sessions/{session_id}/events")
def session_events(session_id: str, limit: int = 50) -> list[dict[str, object]]:
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return db.list_events(session_id=session_id, limit=limit)


@app.post("/api/sessions/{session_id}/events")
def create_event(session_id: str, payload: SessionEventCreate) -> dict[str, object]:
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return db.add_event(
        session_id=session_id,
        agent_id=session["agent_id"],
        event_type=payload.event_type,
        payload=payload.payload,
    )


@app.get("/api/sessions/{session_id}/messages")
def session_messages(
    session_id: str,
    limit: int = 50,
    status: str | None = None,
    direction: str | None = None,
) -> list[dict[str, object]]:
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return db.list_messages(session_id=session_id, limit=limit, status=status, direction=direction)


@app.post("/api/sessions/{session_id}/messages")
def create_message(session_id: str, payload: MessageCreate) -> dict[str, object]:
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return db.add_message(
        session_id=session_id,
        agent_id=session["agent_id"],
        sender=payload.sender,
        direction=payload.direction,
        content=payload.content,
        status=payload.status,
    )


@app.post("/api/messages/{message_id}/ack")
def ack_message(message_id: str, payload: MessageAck) -> dict[str, object]:
    message = db.ack_message(message_id, payload.status)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return message


def app_file() -> str:
    return "autorep_gateway.main:app"
