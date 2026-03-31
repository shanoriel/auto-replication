from __future__ import annotations

from typing import Any

from .catalog import find_by_id
from .db import GatewayDB
from .service import catalog_snapshot


def bootstrap_primary_task_session(
    db: GatewayDB,
    *,
    task: dict[str, Any],
    agent: dict[str, Any],
    initial_input: str | None,
) -> dict[str, Any]:
    catalog_data = catalog_snapshot()
    metadata = agent.get("metadata") or {}
    preset_id = str(metadata.get("preset_id") or "") or None
    model_id = str(metadata.get("default_model") or "") or None
    machine = find_by_id(catalog_data["machines"], agent.get("machine_id"))
    preset = find_by_id(catalog_data["presets"], preset_id)
    model = find_by_id(catalog_data["models"], model_id)

    resolved_workspace = machine.get("workspace_path") if machine else None
    base_codex_home = machine.get("codex_home") if machine else None
    resolved_codex_home = f"{base_codex_home}/presets/{preset['id']}" if base_codex_home and preset else base_codex_home
    resolved_model = model["id"] if model else model_id

    session = db.create_session(
        agent_id=str(agent["id"]),
        runtime_id=agent.get("runtime_id"),
        task_id=str(task["id"]),
        dispatch_id=None,
        title=f"{task['title']}::primary",
        session_key=f"task:{task['id']}:agent:{agent['id']}:primary",
        role=agent.get("role"),
        status="idle",
        lifecycle_status="idle",
        summary="Primary task session created from task bootstrap",
        workspace_path=resolved_workspace,
        codex_home=resolved_codex_home,
        backend_kind="codex",
        backend_session_id=None,
        machine_id=agent.get("machine_id"),
        preset_id=preset_id,
        model=resolved_model,
        initial_prompt=None,
    )
    db.add_event(
        session_id=session["id"],
        agent_id=str(agent["id"]),
        event_type="session.created",
        payload={
            "runtime_id": agent.get("runtime_id"),
            "task_id": task["id"],
            "dispatch_id": None,
            "title": session["title"],
            "role": agent.get("role"),
            "machine_id": agent.get("machine_id"),
            "preset_id": preset_id,
            "model": resolved_model,
            "source": "task.create",
        },
    )
    if initial_input:
        db.add_session_input(
            session_id=session["id"],
            runtime_id=session["runtime_id"],
            agent_id=session["agent_id"],
            kind="message",
            sender="operator",
            payload={"content": initial_input},
            metadata={"source": "task.create"},
        )
    return session
