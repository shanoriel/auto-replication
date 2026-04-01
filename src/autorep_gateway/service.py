from __future__ import annotations

from pathlib import Path
from typing import Any
from datetime import datetime, timedelta, timezone

from .catalog import load_catalog
from .config import settings
from .db import GatewayDB


db = GatewayDB(settings.db_path)
db.repair_session_states()


def ensure_layout() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.static_dir.mkdir(parents=True, exist_ok=True)
    settings.agent_asset_dir.mkdir(parents=True, exist_ok=True)


def runtime_is_online(runtime: dict[str, Any], *, stale_after_seconds: int = 15) -> bool:
    raw = runtime.get("last_heartbeat_at")
    if not raw:
        return False
    try:
        last = datetime.fromisoformat(str(raw))
    except ValueError:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last <= timedelta(seconds=stale_after_seconds)


def online_runtime_conflict(machine_id: str, runtime_id: str | None = None) -> dict[str, Any] | None:
    for runtime in db.list_runtimes():
        if runtime.get("machine_id") != machine_id:
            continue
        if runtime_id and runtime.get("id") == runtime_id:
            continue
        if runtime_is_online(runtime):
            return runtime
    return None


def health_snapshot() -> dict[str, Any]:
    runtimes = db.list_runtimes()
    agents = db.list_agents()
    tasks = db.list_tasks()
    dispatches = db.list_dispatches()
    sessions = db.list_sessions()
    return {
        "app": settings.app_name,
        "port": settings.port,
        "runtimes": len(runtimes),
        "agents": len(agents),
        "tasks": len(tasks),
        "dispatches": len(dispatches),
        "sessions": len(sessions),
        "data_dir": str(settings.data_dir),
        "db_path": str(settings.db_path),
    }


def _count_by_status(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def overview_snapshot() -> dict[str, Any]:
    runtimes = db.list_runtimes()
    agents = db.list_agents()
    tasks = db.list_tasks()
    dispatches = db.list_dispatches()
    sessions = db.list_sessions()
    online_runtimes = [item for item in runtimes if runtime_is_online(item)]
    online_runtime_ids = {str(item.get("id")) for item in online_runtimes}
    visible_agents = [
        item
        for item in agents
        if str(item.get("runtime_id") or "") in online_runtime_ids
        and dict(item.get("metadata") or {}).get("present", True)
    ]
    active_agent_statuses = {"running", "working", "busy", "launching"}
    active_dispatch_statuses = {"pending", "accepted", "running"}
    active_task_statuses = {"created", "active", "running"}
    return {
        "gateway": {
            "status": "ok",
            "app": settings.app_name,
            "port": settings.port,
        },
        "runtimes": {
            "total": len(online_runtimes),
            "by_status": _count_by_status(online_runtimes),
        },
        "agents": {
            "total": len(visible_agents),
            "working": sum(1 for item in visible_agents if str(item.get("status")) in active_agent_statuses),
            "by_status": _count_by_status(visible_agents),
        },
        "tasks": {
            "total": len(tasks),
            "running": sum(1 for item in tasks if str(item.get("status")) in active_task_statuses),
            "by_status": _count_by_status(tasks),
        },
        "dispatches": {
            "total": len(dispatches),
            "waiting_reply": sum(1 for item in dispatches if str(item.get("status")) in active_dispatch_statuses),
            "by_status": _count_by_status(dispatches),
        },
        "sessions": {
            "total": len(sessions),
            "by_status": _count_by_status(sessions),
        },
    }


def task_board_snapshot(task_id: str) -> dict[str, Any] | None:
    task = db.get_task(task_id)
    if task is None:
        return None
    all_agents = {item["id"]: item for item in db.list_agents()}
    all_runtimes = {item["id"]: item for item in db.list_runtimes()}
    dispatches = db.list_dispatches(task_id=task_id)
    sessions = db.list_sessions(task_id=task_id)
    participant_agents = [all_agents[agent_id] for agent_id in task.get("participant_agent_ids", []) if agent_id in all_agents]
    session_ids = {session["id"] for session in sessions}
    active_dispatch_statuses = {"pending", "accepted", "running"}
    active_agent_ids = set()
    for session in sessions:
        if session.get("status") in {"created", "launching", "running"}:
            active_agent_ids.add(session["agent_id"])
    for dispatch in dispatches:
        if dispatch.get("status") in active_dispatch_statuses:
            active_agent_ids.add(dispatch["from_agent_id"])
            active_agent_ids.add(dispatch["to_agent_id"])
    active_agents = [all_agents[agent_id] for agent_id in task.get("participant_agent_ids", []) if agent_id in active_agent_ids and agent_id in all_agents]
    runtime_ids = {agent.get("runtime_id") for agent in participant_agents if agent.get("runtime_id")}
    runtimes = [all_runtimes[runtime_id] for runtime_id in runtime_ids if runtime_id in all_runtimes]

    activity_cards: list[dict[str, Any]] = []
    for dispatch in dispatches[:20]:
        activity_cards.append(
            {
                "id": dispatch["id"],
                "kind": "dispatch",
                "created_at": dispatch["updated_at"] or dispatch["created_at"],
                "title": dispatch["payload"].get("title") or dispatch["kind"],
                "status": dispatch["status"],
                "from_agent_id": dispatch["from_agent_id"],
                "to_agent_id": dispatch["to_agent_id"],
                "dispatch_id": dispatch["id"],
                "summary": dispatch["reply"]["summary"] if dispatch.get("reply") else dispatch["payload"].get("goal") or dispatch["payload"].get("question") or "",
            }
        )
    if task.get("entry_agent_id") in all_agents:
        activity_cards.append(
            {
                "id": f"{task['id']}::task-start",
                "kind": "system",
                "created_at": task["created_at"],
                "agent_id": task["entry_agent_id"],
                "message": "Task Start!",
                "task_id": task["id"],
            }
        )
    activity_cards.sort(key=lambda item: item.get("created_at") or "", reverse=True)

    return {
        "task": task,
        "runtimes": runtimes,
        "participant_agents": participant_agents,
        "active_agents": active_agents,
        "dispatches": dispatches,
        "sessions": sessions,
        "activity": activity_cards[:24],
        "counts": {
            "participant_agents": len(participant_agents),
            "active_agents": len(active_agents),
            "open_dispatches": sum(1 for item in dispatches if item.get("status") in active_dispatch_statuses),
            "running_sessions": sum(1 for item in sessions if item.get("status") in {"created", "launching", "running"}),
            "completed_sessions": sum(1 for item in sessions if item.get("status") == "completed"),
            "fault_sessions": sum(1 for item in sessions if item.get("status") == "failed"),
        },
    }


def project_root() -> Path:
    return settings.root_dir


def catalog_snapshot() -> dict[str, list[dict[str, Any]]]:
    return load_catalog()
