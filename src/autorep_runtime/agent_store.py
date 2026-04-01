from __future__ import annotations

import base64
import binascii
import json
import shutil
from pathlib import Path
from typing import Any


def _json_dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


class LocalAgentStore:
    def __init__(self, state_root: Path, *, runtime_id: str) -> None:
        self.state_root = state_root
        self.runtime_id = runtime_id
        self.agents_root = self.state_root / "agents"
        self.runtime_skills_root = self.state_root / "runtime-skills"
        self.agents_root.mkdir(parents=True, exist_ok=True)
        self.runtime_skills_root.mkdir(parents=True, exist_ok=True)

    def ensure_seed_agents(self, agent_specs: list[dict[str, Any]]) -> None:
        if any(self.agents_root.iterdir()):
            return
        for spec in agent_specs:
            self._write_agent_files(
                {
                    "agent_id": spec["agent_id"],
                    "name": spec["agent_id"],
                    "model": spec.get("model"),
                    "summary": spec.get("summary") or f"{spec.get('role') or 'agent'} agent",
                    "enabled": True,
                    "enabled_runtime_skills": [],
                    "enabled_agent_skills": self._seed_preset_skills(spec),
                    "avatar_data_url": None,
                    "avatar_url": None,
                    "role_hint": spec.get("role"),
                    "agent_md": self._seed_agent_md(spec),
                }
            )

    def list_agents(self) -> list[dict[str, Any]]:
        agents: list[dict[str, Any]] = []
        for agent_dir in sorted(self.agents_root.iterdir(), key=lambda item: item.name.lower()):
            if not agent_dir.is_dir():
                continue
            loaded = self.get_agent(agent_dir.name)
            if loaded is not None:
                agents.append(loaded)
        return agents

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        agent_dir = self.agents_root / agent_id
        config_path = agent_dir / "agent.json"
        agent_md_path = agent_dir / "AGENT.md"
        if not config_path.exists() or not agent_md_path.exists():
            return None
        config = json.loads(config_path.read_text(encoding="utf-8") or "{}")
        runtime_inventory = self._scan_skills(self.runtime_skills_root, source="runtime")
        agent_inventory = self._scan_skills(agent_dir / "skills", source="agent")
        agent = {
            "agent_id": config.get("agent_id") or agent_id,
            "name": config.get("name") or agent_id,
            "model": config.get("model"),
            "summary": config.get("summary"),
            "enabled": bool(config.get("enabled", True)),
            "enabled_runtime_skills": list(config.get("enabled_runtime_skills") or []),
            "enabled_agent_skills": list(config.get("enabled_agent_skills") or []),
            "avatar_filename": config.get("avatar_filename"),
            "role_hint": config.get("role_hint"),
            "agent_md": agent_md_path.read_text(encoding="utf-8"),
            "runtime_skill_inventory": runtime_inventory,
            "agent_skill_inventory": agent_inventory,
        }
        prompt_preview = self._build_prompt_preview(agent)
        avatar_url = None
        if agent["avatar_filename"]:
            avatar_url = f"/api/agent-assets/{self.runtime_id}/{agent_id}/{agent['avatar_filename']}"
        return {
            **agent,
            "status": "idle",
            "prompt_preview": prompt_preview,
            "avatar_url": avatar_url,
            "present": True,
        }

    def apply_op(self, op: dict[str, Any]) -> dict[str, Any]:
        payload = dict(op.get("payload") or {})
        op_type = str(op.get("op_type") or "")
        if op_type not in {
            "create_agent",
            "update_agent_config",
            "update_agent_skills",
            "enable_agent",
            "disable_agent",
        }:
            raise RuntimeError(f"Unsupported runtime agent op type: {op_type}")
        self._write_agent_files(payload)
        agent = self.get_agent(str(payload["agent_id"]))
        if agent is None:
            raise RuntimeError(f"Agent `{payload['agent_id']}` missing after apply")
        return agent

    def build_sync_payload(self, *, available_models: list[str]) -> dict[str, Any]:
        shared_skills = self._scan_skills(self.runtime_skills_root, source="runtime")
        agents = []
        for agent in self.list_agents():
            agents.append(
                {
                    "agent_id": agent["agent_id"],
                    "name": agent["name"],
                    "status": "idle",
                    "summary": agent.get("summary"),
                    "model": agent.get("model"),
                    "enabled": agent.get("enabled", True),
                    "role_hint": agent.get("role_hint"),
                    "avatar_url": agent.get("avatar_url"),
                    "agent_md": agent.get("agent_md") or "",
                    "enabled_runtime_skills": agent.get("enabled_runtime_skills") or [],
                    "enabled_agent_skills": agent.get("enabled_agent_skills") or [],
                    "runtime_skill_inventory": shared_skills,
                    "agent_skill_inventory": agent.get("agent_skill_inventory") or [],
                    "prompt_preview": agent.get("prompt_preview") or {},
                    "present": True,
                }
            )
        return {
            "shared_skills": shared_skills,
            "available_models": available_models,
            "agents": agents,
        }

    def prepare_session_files(self, session: dict[str, Any], *, workspace_path: Path, codex_home: Path) -> None:
        agent = self.get_agent(str(session["agent_id"]))
        if agent is None:
            raise RuntimeError(f"Local agent `{session['agent_id']}` not found")
        workspace_path.mkdir(parents=True, exist_ok=True)
        codex_home.mkdir(parents=True, exist_ok=True)
        skill_target = codex_home / "skills"
        skill_target.mkdir(parents=True, exist_ok=True)
        for item in skill_target.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        agent_md = agent.get("agent_md") or ""
        # Keep AGENTS.md for current Codex compatibility while AGENT.md remains local truth.
        (workspace_path / "AGENT.md").write_text(agent_md, encoding="utf-8")
        (workspace_path / "AGENTS.md").write_text(agent_md, encoding="utf-8")
        for skill_id in agent.get("enabled_runtime_skills") or []:
            self._copy_skill(self.runtime_skills_root, skill_id, skill_target)
        for skill_id in agent.get("enabled_agent_skills") or []:
            self._copy_skill(self.agents_root / str(session["agent_id"]) / "skills", skill_id, skill_target)

    def _write_agent_files(self, payload: dict[str, Any]) -> None:
        agent_id = str(payload["agent_id"])
        agent_dir = self.agents_root / agent_id
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / "skills").mkdir(parents=True, exist_ok=True)
        config_path = agent_dir / "agent.json"
        existing = {}
        if config_path.exists():
            existing = json.loads(config_path.read_text(encoding="utf-8") or "{}")
        avatar_filename = existing.get("avatar_filename")
        if payload.get("avatar_data_url"):
            avatar_filename = self._write_avatar(agent_dir, str(payload["avatar_data_url"]))
        config = {
            "agent_id": agent_id,
            "name": payload.get("name") or existing.get("name") or agent_id,
            "model": payload.get("model"),
            "summary": payload.get("summary"),
            "enabled": bool(payload.get("enabled", True)),
            "enabled_runtime_skills": list(payload.get("enabled_runtime_skills") or []),
            "enabled_agent_skills": list(payload.get("enabled_agent_skills") or []),
            "avatar_filename": avatar_filename,
            "role_hint": payload.get("role_hint"),
        }
        config_path.write_text(_json_dump(config), encoding="utf-8")
        (agent_dir / "AGENT.md").write_text(str(payload.get("agent_md") or ""), encoding="utf-8")

    def _seed_agent_md(self, spec: dict[str, Any]) -> str:
        preset_id = spec.get("preset_id")
        if preset_id:
            preset_path = Path(__file__).resolve().parents[2] / "presets" / str(preset_id) / "AGENTS.md"
            if preset_path.exists():
                return preset_path.read_text(encoding="utf-8")
        role = spec.get("role") or "agent"
        return (
            f"# {role.title()} Agent\n\n"
            f"You are the {role} agent for AutoReplication.\n"
        )

    def _seed_preset_skills(self, spec: dict[str, Any]) -> list[str]:
        preset_id = spec.get("preset_id")
        if not preset_id:
            return []
        preset_skill_dir = Path(__file__).resolve().parents[2] / "presets" / str(preset_id) / "skills"
        if not preset_skill_dir.exists():
            return []
        target_root = self.agents_root / str(spec["agent_id"]) / "skills"
        target_root.mkdir(parents=True, exist_ok=True)
        enabled: list[str] = []
        for item in preset_skill_dir.iterdir():
            destination = target_root / item.name
            if item.is_dir():
                shutil.copytree(item, destination, dirs_exist_ok=True)
            else:
                shutil.copyfile(item, destination)
            enabled.append(item.stem if item.is_file() else item.name)
        return enabled

    def _scan_skills(self, root: Path, *, source: str) -> list[dict[str, Any]]:
        if not root.exists():
            return []
        skills = []
        for item in sorted(root.iterdir(), key=lambda candidate: candidate.name.lower()):
            if item.name.startswith("."):
                continue
            skill_id = item.stem if item.is_file() else item.name
            name = skill_id
            description = None
            skill_md = item / "SKILL.md" if item.is_dir() else item
            if skill_md.exists():
                name, description = self._read_skill_metadata(skill_md, fallback=skill_id)
            skills.append(
                {
                    "skill_id": skill_id,
                    "name": name,
                    "description": description,
                    "path": str(item),
                    "source": source,
                }
            )
        return skills

    def _read_skill_metadata(self, path: Path, *, fallback: str) -> tuple[str, str | None]:
        name = fallback
        description = None
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#") and name == fallback:
                name = line.lstrip("#").strip() or fallback
                continue
            if not line.startswith("#") and description is None:
                description = line
                break
        return name, description

    def _build_prompt_preview(self, agent: dict[str, Any]) -> dict[str, Any]:
        enabled_runtime_ids = set(agent.get("enabled_runtime_skills") or [])
        enabled_agent_ids = set(agent.get("enabled_agent_skills") or [])
        runtime_skill_lines = [
            f"- Runtime: {skill['name']}"
            for skill in agent.get("runtime_skill_inventory") or []
            if skill["skill_id"] in enabled_runtime_ids
        ]
        agent_skill_lines = [
            f"- Agent: {skill['name']}"
            for skill in agent.get("agent_skill_inventory") or []
            if skill["skill_id"] in enabled_agent_ids
        ]
        skill_lines = runtime_skill_lines + agent_skill_lines
        normalized_text = "\n".join(
            [
                f"Agent: {agent['name']} ({agent['agent_id']})",
                f"Model: {agent.get('model') or 'unset'}",
                f"Enabled: {'yes' if agent.get('enabled', True) else 'no'}",
                "",
                "AGENT.md",
                agent.get("agent_md") or "",
                "",
                "Enabled skills",
                "\n".join(skill_lines) if skill_lines else "- none",
            ]
        ).strip()
        return {
            "normalized_text": normalized_text,
            "agent_md": agent.get("agent_md") or "",
            "skills_summary": "\n".join(skill_lines) if skill_lines else "none",
        }

    def _write_avatar(self, agent_dir: Path, data_url: str) -> str:
        if "," not in data_url:
            raise RuntimeError("Invalid avatar data url")
        header, encoded = data_url.split(",", 1)
        try:
            payload = base64.b64decode(encoded, validate=True)
        except binascii.Error as exc:
            raise RuntimeError("Invalid avatar payload") from exc
        extension = ".png"
        if "image/jpeg" in header:
            extension = ".jpg"
        elif "image/webp" in header:
            extension = ".webp"
        for item in agent_dir.iterdir():
            if item.is_file() and item.name.startswith("avatar."):
                item.unlink()
        filename = f"avatar{extension}"
        (agent_dir / filename).write_bytes(payload)
        return filename

    def _copy_skill(self, source_root: Path, skill_id: str, target_root: Path) -> None:
        matches = [source_root / skill_id, source_root / f"{skill_id}.md", source_root / f"{skill_id}.txt"]
        source = next((item for item in matches if item.exists()), None)
        if source is None:
            for item in source_root.iterdir():
                current_id = item.stem if item.is_file() else item.name
                if current_id == skill_id:
                    source = item
                    break
        if source is None:
            raise RuntimeError(f"Skill `{skill_id}` not found in {source_root}")
        destination = target_root / source.name
        if destination.exists():
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copyfile(source, destination)
