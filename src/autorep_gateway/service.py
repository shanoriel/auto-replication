from __future__ import annotations

from pathlib import Path
from typing import Any

from .catalog import load_catalog
from .config import settings
from .db import GatewayDB


db = GatewayDB(settings.db_path)
db.repair_session_states()


def ensure_layout() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.static_dir.mkdir(parents=True, exist_ok=True)


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


def project_root() -> Path:
    return settings.root_dir


def catalog_snapshot() -> dict[str, list[dict[str, Any]]]:
    return load_catalog()
