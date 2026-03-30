from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _http_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> Any:
    body = None
    headers: dict[str, str] = {}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{base_url}{path}",
        method=method,
        data=body,
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    role: str
    preset_id: str | None = None
    model: str | None = None
    summary: str | None = None


class RuntimeManager:
    def __init__(
        self,
        *,
        gateway_url: str,
        runtime_id: str,
        machine_id: str,
        name: str,
        host: str | None,
        workspace_root: Path,
        codex_home_root: Path,
        agents: list[AgentSpec],
        poll_interval_secs: float = 2.0,
    ) -> None:
        self.gateway_url = gateway_url.rstrip("/")
        self.runtime_id = runtime_id
        self.machine_id = machine_id
        self.name = name
        self.host = host
        self.workspace_root = workspace_root
        self.codex_home_root = codex_home_root
        self.agents = agents
        self.poll_interval_secs = poll_interval_secs
        self._stop_event = threading.Event()
        self._active_sessions: dict[str, threading.Thread] = {}

    def run_forever(self) -> None:
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.codex_home_root.mkdir(parents=True, exist_ok=True)
        self._register_runtime()
        self._register_agents()
        while not self._stop_event.is_set():
            self._tick()
            self._stop_event.wait(self.poll_interval_secs)

    def stop(self) -> None:
        self._stop_event.set()

    def _tick(self) -> None:
        self._heartbeat()
        self._launch_pending_dispatches()
        self._launch_pending_sessions()

    def _register_runtime(self) -> None:
        _http_json(
            self.gateway_url,
            "/api/runtimes/register",
            method="POST",
            payload={
                "runtime_id": self.runtime_id,
                "machine_id": self.machine_id,
                "name": self.name,
                "status": "idle",
                "summary": "Runtime process registered",
                "host": self.host,
                "base_url": None,
                "labels": {"machine_id": self.machine_id},
                "capabilities": {"session_execution": True, "dispatch_polling": True},
            },
        )

    def _register_agents(self) -> None:
        for agent in self.agents:
            _http_json(
                self.gateway_url,
                "/api/agents/register",
                method="POST",
                payload={
                    "agent_id": agent.agent_id,
                    "runtime_id": self.runtime_id,
                    "machine_id": self.machine_id,
                    "name": agent.agent_id,
                    "kind": "codex",
                    "host": self.host,
                    "role": agent.role,
                    "transport": "gateway-http",
                    "status": "idle",
                    "summary": agent.summary or f"{agent.role} agent on {self.machine_id}",
                    "metadata": {
                        "preset_id": agent.preset_id,
                        "default_model": agent.model,
                    },
                },
            )

    def _heartbeat(self) -> None:
        active = len(self._active_sessions)
        _http_json(
            self.gateway_url,
            f"/api/runtimes/{self.runtime_id}/heartbeat",
            method="POST",
            payload={
                "status": "busy" if active else "idle",
                "summary": f"{active} active session(s)",
                "labels": {"machine_id": self.machine_id},
                "capabilities": {"active_sessions": active},
            },
        )
        for agent in self.agents:
            _http_json(
                self.gateway_url,
                f"/api/agents/{agent.agent_id}/heartbeat",
                method="POST",
                payload={
                    "status": "busy" if active else "idle",
                    "summary": f"Attached to runtime {self.runtime_id}",
                    "metadata": {"runtime_id": self.runtime_id, "active_sessions": active},
                },
            )

    def _launch_pending_dispatches(self) -> None:
        query = urllib.parse.urlencode({"runtime_id": self.runtime_id, "status": "pending"})
        dispatches = _http_json(self.gateway_url, f"/api/runtime/dispatch-queue?{query}")
        for dispatch in dispatches:
            if dispatch.get("session_id"):
                continue
            session = self._create_session_for_dispatch(dispatch)
            worker = threading.Thread(
                target=self._run_initial_session,
                args=(session["id"],),
                daemon=True,
            )
            self._active_sessions[session["id"]] = worker
            worker.start()

    def _launch_pending_sessions(self) -> None:
        query = urllib.parse.urlencode({"runtime_id": self.runtime_id})
        for session in _http_json(self.gateway_url, f"/api/runtime/launch-queue?{query}"):
            if session["id"] in self._active_sessions:
                continue
            worker = threading.Thread(
                target=self._run_initial_session,
                args=(session["id"],),
                daemon=True,
            )
            self._active_sessions[session["id"]] = worker
            worker.start()

    def _create_session_for_dispatch(self, dispatch: dict[str, Any]) -> dict[str, Any]:
        agent = next((item for item in self.agents if item.agent_id == dispatch["to_agent_id"]), None)
        if agent is None:
            raise RuntimeError(f"Dispatch {dispatch['id']} targets unmanaged agent {dispatch['to_agent_id']}")
        task = _http_json(self.gateway_url, f"/api/tasks/{dispatch['task_id']}")
        prompt = self._dispatch_prompt(task, dispatch)
        return _http_json(
            self.gateway_url,
            "/api/sessions",
            method="POST",
            payload={
                "agent_id": agent.agent_id,
                "runtime_id": self.runtime_id,
                "task_id": dispatch["task_id"],
                "dispatch_id": dispatch["id"],
                "title": f"{dispatch['kind']}::{task['title']}",
                "role": agent.role,
                "status": "created",
                "summary": f"Auto-created for dispatch {dispatch['id']}",
                "workspace_path": str(self.workspace_root),
                "codex_home": str(self.codex_home_root),
                "machine_id": self.machine_id,
                "preset_id": agent.preset_id,
                "model": agent.model,
                "initial_prompt": prompt,
            },
        )

    def _dispatch_prompt(self, task: dict[str, Any], dispatch: dict[str, Any]) -> str:
        payload = json.dumps(dispatch["payload"], indent=2, ensure_ascii=True)
        lines = [
            f"You are handling AutoReplication dispatch `{dispatch['id']}`.",
            f"Task: {task['title']}",
            f"Dispatch kind: {dispatch['kind']}",
            f"From agent: {dispatch['from_agent_id']}",
            f"To agent: {dispatch['to_agent_id']}",
            "",
            "Payload:",
            payload,
            "",
            "Operate within the session workspace. Produce a concise result summary when done.",
        ]
        return "\n".join(lines)

    def _run_initial_session(self, session_id: str) -> None:
        try:
            session = self._require_session(session_id)
            self._prepare_session_files(session)
            command, env, last_message_path = self._build_initial_command(session)
            _http_json(
                self.gateway_url,
                f"/api/sessions/{session_id}/claim",
                method="POST",
                payload={
                    "runner_id": self.runtime_id,
                    "status": "launching",
                    "summary": f"Claimed by runtime {self.runtime_id}",
                },
            )
            _http_json(
                self.gateway_url,
                f"/api/sessions/{session_id}/events",
                method="POST",
                payload={"event_type": "runtime.command.started", "payload": {"command": command}},
            )
            self._run_process(
                session_id=session_id,
                command=command,
                env=env,
                last_message_path=last_message_path,
            )
        finally:
            self._active_sessions.pop(session_id, None)

    def _prepare_session_files(self, session: dict[str, Any]) -> None:
        workspace_root = Path(session["workspace_path"])
        workspace_path = workspace_root / "sessions" / session["id"]
        codex_home = Path(session["codex_home"])
        workspace_path.mkdir(parents=True, exist_ok=True)
        codex_home.mkdir(parents=True, exist_ok=True)
        self._bootstrap_codex_home(codex_home)
        (codex_home / "skills").mkdir(parents=True, exist_ok=True)
        session["workspace_path"] = str(workspace_path)
        catalog = _http_json(self.gateway_url, "/api/catalog")
        preset = next((item for item in catalog["presets"] if item["id"] == session.get("preset_id")), None)
        if preset is None:
            return
        root_dir = Path(__file__).resolve().parents[2]
        preset_agent_md = root_dir / preset["agent_md"]
        if preset_agent_md.exists():
            shutil.copyfile(preset_agent_md, workspace_path / "AGENTS.md")
        preset_skills_dir = root_dir / preset["skills_profile"]
        if preset_skills_dir.exists():
            target_skills = codex_home / "skills"
            for item in preset_skills_dir.iterdir():
                destination = target_skills / item.name
                if destination.exists():
                    if destination.is_dir():
                        shutil.rmtree(destination)
                    else:
                        destination.unlink()
                if item.is_dir():
                    shutil.copytree(item, destination)
                else:
                    shutil.copyfile(item, destination)

    def _bootstrap_codex_home(self, codex_home: Path) -> None:
        source_home = Path.home() / ".codex"
        bridge_files = ["auth.json", "config.toml", "models_cache.json", "version.json"]
        for name in bridge_files:
            source = source_home / name
            target = codex_home / name
            if not source.exists() or target.exists():
                continue
            try:
                target.symlink_to(source)
            except OSError:
                shutil.copyfile(source, target)

    def _build_initial_command(self, session: dict[str, Any]) -> tuple[list[str], dict[str, str], Path]:
        session_data_dir = self.workspace_root.parent / "data" / "sessions" / session["id"]
        session_data_dir.mkdir(parents=True, exist_ok=True)
        last_message_path = session_data_dir / "last_message.txt"
        command = [
            "codex",
            "exec",
            "--json",
            "--skip-git-repo-check",
            "--output-last-message",
            str(last_message_path),
            "-C",
            str(session["workspace_path"]),
        ]
        if session.get("model"):
            command.extend(["-m", session["model"]])
        command.append(session.get("initial_prompt") or f"Start session: {session['title']}")
        return command, self._build_env(session), last_message_path

    def _build_env(self, session: dict[str, Any]) -> dict[str, str]:
        env = os.environ.copy()
        env["CODEX_HOME"] = session["codex_home"]
        env["HOME"] = str(Path.home())
        return env

    def _run_process(
        self,
        *,
        session_id: str,
        command: list[str],
        env: dict[str, str],
        last_message_path: Path,
    ) -> None:
        session = self._require_session(session_id)
        process = subprocess.Popen(
            command,
            cwd=session["workspace_path"],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        _http_json(
            self.gateway_url,
            f"/api/sessions/{session_id}",
            method="PATCH",
            payload={
                "status": "running",
                "summary": "Codex process running",
                "codex_thread_id": session.get("codex_thread_id"),
            },
        )
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.rstrip("\n")
            if not line:
                continue
            self._handle_json_line(session, line)
        return_code = process.wait()

        last_message = ""
        if last_message_path.exists():
            last_message = last_message_path.read_text(encoding="utf-8").strip()
        if last_message:
            _http_json(
                self.gateway_url,
                f"/api/sessions/{session_id}/messages",
                method="POST",
                payload={
                    "content": last_message,
                    "sender": "agent",
                    "direction": "inbound",
                    "status": "delivered",
                },
            )
        summary = last_message.splitlines()[0][:240] if last_message else f"Codex exited with code {return_code}"
        session_status = "completed" if return_code == 0 else "failed"
        _http_json(
            self.gateway_url,
            f"/api/sessions/{session_id}",
            method="PATCH",
            payload={
                "status": session_status,
                "summary": summary,
                "codex_thread_id": session.get("codex_thread_id"),
            },
        )
        _http_json(
            self.gateway_url,
            f"/api/sessions/{session_id}/events",
            method="POST",
            payload={"event_type": "runtime.command.completed", "payload": {"return_code": return_code}},
        )
        if session.get("dispatch_id"):
            dispatch_status = "completed" if return_code == 0 else "failed"
            _http_json(
                self.gateway_url,
                f"/api/dispatches/{session['dispatch_id']}",
                method="PATCH",
                payload={
                    "status": dispatch_status,
                    "payload": {"runtime_summary": summary, "session_status": session_status},
                    "session_id": session_id,
                    "resolved": True,
                },
            )

    def _handle_json_line(self, session: dict[str, Any], line: str) -> None:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            _http_json(
                self.gateway_url,
                f"/api/sessions/{session['id']}/events",
                method="POST",
                payload={"event_type": "runtime.output.text", "payload": {"line": line}},
            )
            return
        event_type = payload.get("type", "runtime.output.json")
        normalized_type = f"codex.{event_type}"
        _http_json(
            self.gateway_url,
            f"/api/sessions/{session['id']}/events",
            method="POST",
            payload={"event_type": normalized_type, "payload": payload},
        )
        if event_type == "thread.started" and payload.get("thread_id"):
            session["codex_thread_id"] = str(payload["thread_id"])
            _http_json(
                self.gateway_url,
                f"/api/sessions/{session['id']}",
                method="PATCH",
                payload={
                    "status": "running",
                    "summary": "Codex thread started",
                    "codex_thread_id": session["codex_thread_id"],
                },
            )

    def _require_session(self, session_id: str) -> dict[str, Any]:
        return _http_json(self.gateway_url, f"/api/sessions/{session_id}")


def parse_agent_spec(raw: str) -> AgentSpec:
    parts = raw.split(":")
    if len(parts) not in {2, 3, 4}:
        raise argparse.ArgumentTypeError("agent spec must be agent_id:role[:preset_id[:model]]")
    agent_id = parts[0].strip()
    role = parts[1].strip()
    preset_id = parts[2].strip() if len(parts) >= 3 and parts[2].strip() else None
    model = parts[3].strip() if len(parts) == 4 and parts[3].strip() else None
    if not agent_id or not role:
        raise argparse.ArgumentTypeError("agent_id and role are required")
    return AgentSpec(agent_id=agent_id, role=role, preset_id=preset_id, model=model)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an AutoReplication runtime process.")
    parser.add_argument("--gateway-url", default="http://127.0.0.1:11451")
    parser.add_argument("--runtime-id", required=True)
    parser.add_argument("--machine-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--host")
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--codex-home-root", required=True)
    parser.add_argument(
        "--agent",
        action="append",
        type=parse_agent_spec,
        default=[],
        help="agent_id:role[:preset_id[:model]]",
    )
    parser.add_argument("--poll-interval-secs", type=float, default=2.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.agent:
        parser.error("at least one --agent is required")
    manager = RuntimeManager(
        gateway_url=args.gateway_url,
        runtime_id=args.runtime_id,
        machine_id=args.machine_id,
        name=args.name,
        host=args.host,
        workspace_root=Path(args.workspace_root),
        codex_home_root=Path(args.codex_home_root),
        agents=args.agent,
        poll_interval_secs=args.poll_interval_secs,
    )
    try:
        manager.run_forever()
    except KeyboardInterrupt:
        manager.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
