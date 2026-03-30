from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import settings


DEFAULT_CATALOG: dict[str, list[dict[str, Any]]] = {
    "machines": [
        {
            "id": "mac-mini",
            "name": "mac-mini",
            "host": "100.117.190.40",
            "kind": "local",
            "transport": "gateway-local",
            "default_role": "research",
            "workspace_path": "/Users/shanoriel/Projects/ARIS/Projects/AutoReplication/workspaces/mac-mini",
            "codex_home": "/Users/shanoriel/Projects/ARIS/Projects/AutoReplication/codex-homes/mac-mini",
        },
        {
            "id": "hjs-alienware",
            "name": "hjs-alienware",
            "host": "hjs-alienware",
            "kind": "remote",
            "transport": "gateway-http",
            "default_role": "experiment",
            "workspace_path": "/workspace/AutoReplication",
            "codex_home": "/workspace/.codex-autoreplication",
        },
    ],
    "presets": [
        {
            "id": "research-default",
            "name": "Research Default",
            "role": "research",
            "agent_md": "presets/research-default/AGENTS.md",
            "skills_profile": "presets/research-default/skills",
            "summary": "General research operator for planning, reading papers, and steering work.",
        },
        {
            "id": "experiment-default",
            "name": "Experiment Default",
            "role": "experiment",
            "agent_md": "presets/experiment-default/AGENTS.md",
            "skills_profile": "presets/experiment-default/skills",
            "summary": "Execution-focused operator for environment setup, implementation, and runs.",
        },
    ],
    "models": [
        {
            "id": "gpt-5.4-mini",
            "name": "GPT-5.4 Mini",
            "summary": "Fast and cheap. Use for lightweight loops and routing.",
            "cli_model": "gpt-5.4-mini",
            "config_overrides": [],
        },
        {
            "id": "gpt-5.4",
            "name": "GPT-5.4 Medium",
            "summary": "Balanced default for research and implementation work.",
            "cli_model": "gpt-5.4",
            "config_overrides": [],
        },
        {
            "id": "gpt-5.4-high",
            "name": "GPT-5.4 High",
            "summary": "Heavier reasoning profile for difficult design and review tasks.",
            "cli_model": "gpt-5.4",
            "config_overrides": ['model_reasoning_effort="high"'],
        },
    ],
}


def ensure_catalog_file() -> None:
    settings.catalog_path.parent.mkdir(parents=True, exist_ok=True)
    if not settings.catalog_path.exists():
        settings.catalog_path.write_text(
            json.dumps(DEFAULT_CATALOG, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )


def load_catalog() -> dict[str, list[dict[str, Any]]]:
    ensure_catalog_file()
    return json.loads(settings.catalog_path.read_text(encoding="utf-8"))


def find_by_id(items: list[dict[str, Any]], item_id: str | None) -> dict[str, Any] | None:
    if item_id is None:
        return None
    for item in items:
        if item.get("id") == item_id:
            return item
    return None
