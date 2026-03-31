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
    RuntimeInboxUpdate,
    RuntimeRegistration,
    SessionClaim,
    SessionCreate,
    SessionEventCreate,
    SessionInputCreate,
    SessionInputUpdate,
    SessionUpdate,
    TaskCreate,
    TaskUpdate,
)
from .service import catalog_snapshot, db, ensure_layout, health_snapshot, overview_snapshot, task_board_snapshot
from .task_bootstrap import bootstrap_primary_task_session


ensure_layout()

app = FastAPI(title=settings.app_name, version="0.2.0")
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")


VALID_DISPATCH_KINDS = {"work-order", "clarification-request"}
VALID_DISPATCH_STATUSES = {"pending", "accepted", "running", "replied", "failed"}


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


@app.get("/api/overview")
def overview() -> dict[str, object]:
    return overview_snapshot()


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


@app.get("/api/runtime/session-input-queue")
def runtime_session_input_queue(runtime_id: str, status: str = "pending") -> list[dict[str, object]]:
    return db.list_runtime_session_inputs(runtime_id, status=status)


@app.get("/api/runtime/inbox")
def runtime_inbox(runtime_id: str, status: str = "pending") -> list[dict[str, object]]:
    return db.list_runtime_inbox(runtime_id, status=status)


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
    if payload.created_by != "human":
        raise HTTPException(status_code=400, detail="tasks can only be created by human")
    entry_agent = db.get_agent(payload.entry_agent_id)
    if entry_agent is None:
        raise HTTPException(status_code=404, detail="entry_agent not found")
    if entry_agent.get("runtime_id") is None:
        raise HTTPException(status_code=400, detail="entry_agent must be assigned to a runtime")
    participant_agent_ids = list(dict.fromkeys([payload.entry_agent_id, *payload.participant_agent_ids]))
    missing_agents = [agent_id for agent_id in participant_agent_ids if db.get_agent(agent_id) is None]
    if missing_agents:
        raise HTTPException(status_code=404, detail=f"participant agents not found: {', '.join(missing_agents)}")
    task = db.create_task(
        title=payload.title,
        created_by=payload.created_by,
        entry_agent_id=payload.entry_agent_id,
        participant_agent_ids=participant_agent_ids,
        objective=payload.objective,
        status=payload.status,
        summary=payload.summary,
        stage_plan=payload.stage_plan,
        metadata=payload.metadata,
    )
    primary_session = bootstrap_primary_task_session(
        db,
        task=task,
        agent=entry_agent,
        initial_input=payload.initial_input,
    )
    task["entry_session_id"] = primary_session["id"]
    return task


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, object]:
    task = db.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.get("/api/tasks/{task_id}/board")
def get_task_board(task_id: str) -> dict[str, object]:
    board = task_board_snapshot(task_id)
    if board is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return board


@app.patch("/api/tasks/{task_id}")
def patch_task(task_id: str, payload: TaskUpdate) -> dict[str, object]:
    current_task = db.get_task(task_id)
    if current_task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if payload.entry_agent_id is not None and db.get_agent(payload.entry_agent_id) is None:
        raise HTTPException(status_code=404, detail="entry_agent not found")
    next_entry_agent_id = payload.entry_agent_id or current_task["entry_agent_id"]
    next_participant_agent_ids = payload.participant_agent_ids or current_task["participant_agent_ids"]
    combined_agent_ids = [agent_id for agent_id in [next_entry_agent_id, *next_participant_agent_ids] if agent_id]
    next_participant_agent_ids = list(dict.fromkeys(combined_agent_ids))
    if next_participant_agent_ids:
        missing_agents = [agent_id for agent_id in next_participant_agent_ids if db.get_agent(agent_id) is None]
        if missing_agents:
            raise HTTPException(status_code=404, detail=f"participant agents not found: {', '.join(missing_agents)}")
    task = db.update_task(
        task_id,
        status=payload.status,
        summary=payload.summary,
        entry_agent_id=payload.entry_agent_id,
        participant_agent_ids=next_participant_agent_ids,
        objective=payload.objective,
        stage_plan=payload.stage_plan,
        metadata=payload.metadata,
    )
    return task


@app.get("/api/dispatches")
def list_dispatches(
    from_agent_id: str | None = None,
    to_agent_id: str | None = None,
    task_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, object]]:
    return db.list_dispatches(
        from_agent_id=from_agent_id,
        to_agent_id=to_agent_id,
        task_id=task_id,
        status=status,
    )


@app.post("/api/dispatches")
def create_dispatch(payload: DispatchCreate) -> dict[str, object]:
    if payload.kind not in VALID_DISPATCH_KINDS:
        raise HTTPException(status_code=400, detail="invalid dispatch kind")
    if payload.status not in VALID_DISPATCH_STATUSES:
        raise HTTPException(status_code=400, detail="invalid dispatch status")
    task = db.get_task(payload.task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if db.get_agent(payload.from_agent_id) is None:
        raise HTTPException(status_code=404, detail="from_agent not found")
    if db.get_agent(payload.to_agent_id) is None:
        raise HTTPException(status_code=404, detail="to_agent not found")
    task_agent_ids = set(task.get("participant_agent_ids", []))
    for agent_id in (payload.from_agent_id, payload.to_agent_id):
        if task_agent_ids and agent_id not in task_agent_ids:
            raise HTTPException(status_code=400, detail="dispatch agent must belong to task participants")
    if payload.parent_dispatch_id is not None:
        parent = db.get_dispatch(payload.parent_dispatch_id)
        if parent is None:
            raise HTTPException(status_code=404, detail="parent dispatch not found")
        if parent["task_id"] != payload.task_id:
            raise HTTPException(status_code=400, detail="parent dispatch must belong to same task")
        if payload.kind == "clarification-request" and payload.to_agent_id != parent["from_agent_id"]:
            raise HTTPException(status_code=400, detail="clarification to_agent must equal parent from_agent")
    if payload.kind == "clarification-request" and payload.parent_dispatch_id is None:
        raise HTTPException(status_code=400, detail="clarification-request requires parent_dispatch_id")
    return db.create_dispatch(
        task_id=payload.task_id,
        kind=payload.kind,
        status=payload.status,
        from_agent_id=payload.from_agent_id,
        to_agent_id=payload.to_agent_id,
        parent_dispatch_id=payload.parent_dispatch_id,
        payload=payload.payload,
        reply=payload.reply,
    )


@app.get("/api/dispatches/{dispatch_id}")
def get_dispatch(dispatch_id: str) -> dict[str, object]:
    dispatch = db.get_dispatch(dispatch_id)
    if dispatch is None:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    return dispatch


@app.patch("/api/dispatches/{dispatch_id}")
def patch_dispatch(dispatch_id: str, payload: DispatchUpdate) -> dict[str, object]:
    if payload.status is not None and payload.status not in VALID_DISPATCH_STATUSES:
        raise HTTPException(status_code=400, detail="invalid dispatch status")
    dispatch = db.update_dispatch(
        dispatch_id,
        status=payload.status,
        payload=payload.payload,
        reply=payload.reply,
        session_id=payload.session_id,
        accepted=payload.accepted,
        resolved=payload.resolved,
    )
    if dispatch is None:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    return dispatch


@app.get("/api/sessions")
def list_sessions(
    task_id: str | None = None,
    agent_id: str | None = None,
    dispatch_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, object]]:
    return db.list_sessions(task_id=task_id, agent_id=agent_id, dispatch_id=dispatch_id, status=status)


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
    resolved_status = payload.status
    if payload.session_key and payload.dispatch_id is None:
        resolved_status = "idle"

    session = db.create_session(
        agent_id=payload.agent_id,
        runtime_id=payload.runtime_id or agent.get("runtime_id"),
        task_id=payload.task_id,
        dispatch_id=payload.dispatch_id,
        title=payload.title,
        session_key=payload.session_key,
        role=resolved_role,
        status=resolved_status,
        lifecycle_status=payload.lifecycle_status or resolved_status,
        summary=payload.summary,
        workspace_path=resolved_workspace,
        codex_home=resolved_codex_home,
        backend_kind=payload.backend_kind,
        backend_session_id=payload.backend_session_id,
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
            accepted=True,
        )
    initial_input = payload.initial_input or payload.initial_prompt
    if initial_input:
        db.add_session_input(
            session_id=session["id"],
            runtime_id=session["runtime_id"],
            agent_id=session["agent_id"],
            kind="message",
            sender="operator",
            payload={"content": initial_input},
            metadata={"source": "session.create"},
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
        lifecycle_status=payload.lifecycle_status,
        summary=payload.summary,
        codex_thread_id=payload.codex_thread_id,
        backend_session_id=payload.backend_session_id,
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
        lifecycle_status=payload.status,
        summary=payload.summary or f"Claimed by {payload.runner_id}",
        codex_thread_id=session.get("codex_thread_id"),
        backend_session_id=session.get("backend_session_id"),
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


@app.post("/api/sessions/{session_id}/inputs")
def create_session_input(session_id: str, payload: SessionInputCreate) -> dict[str, object]:
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.get("runtime_id"):
        raise HTTPException(status_code=400, detail="Session has no owner runtime")
    return db.add_session_input(
        session_id=session_id,
        runtime_id=session["runtime_id"],
        agent_id=session["agent_id"],
        kind=payload.kind,
        sender=payload.sender,
        payload={"content": payload.content},
        metadata=payload.metadata,
    )


@app.patch("/api/session-inputs/{session_input_id}")
def patch_session_input(session_input_id: str, payload: SessionInputUpdate) -> dict[str, object]:
    session_input = db.update_session_input(
        session_input_id,
        status=payload.status,
        error_text=payload.error_text,
    )
    if session_input is None:
        raise HTTPException(status_code=404, detail="Session input not found")
    return session_input


@app.patch("/api/runtime/inbox/{item_id}")
def patch_runtime_inbox(item_id: str, payload: RuntimeInboxUpdate) -> dict[str, object]:
    item = db.update_runtime_inbox_item(item_id, status=payload.status)
    if item is None:
        raise HTTPException(status_code=404, detail="Runtime inbox item not found")
    return item


def app_file() -> str:
    return "autorep_gateway.main:app"
