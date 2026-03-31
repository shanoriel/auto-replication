from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass
class BackendResult:
    backend_session_id: str
    events: list[dict[str, Any]]
    last_message: str
    return_code: int


class SessionBackend(Protocol):
    def run(self, session: dict[str, Any], input_text: str) -> BackendResult:
        ...


class LocalSessionStore:
    def __init__(self, state_root: Path) -> None:
        self.state_root = state_root
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.transcripts_dir = self.state_root / "transcripts"
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.state_root / "sessions.json"
        if not self.index_path.exists():
            self.index_path.write_text("{}", encoding="utf-8")

    def _load(self) -> dict[str, dict[str, Any]]:
        return json.loads(self.index_path.read_text(encoding="utf-8") or "{}")

    def _save(self, payload: dict[str, dict[str, Any]]) -> None:
        self.index_path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def upsert_from_session(self, session: dict[str, Any]) -> dict[str, Any]:
        records = self._load()
        current = records.get(session["id"], {})
        merged = {
            "session_id": session["id"],
            "session_key": session.get("session_key"),
            "runtime_id": session.get("runtime_id"),
            "agent_id": session.get("agent_id"),
            "title": session.get("title"),
            "backend_kind": session.get("backend_kind") or "codex",
            "backend_session_id": session.get("backend_session_id"),
            "workspace_path": session.get("workspace_path"),
            "codex_home": session.get("codex_home"),
            "model": session.get("model"),
            "status": session.get("status"),
        }
        current.update({key: value for key, value in merged.items() if value is not None})
        records[session["id"]] = current
        self._save(records)
        return current

    def get(self, session_id: str) -> dict[str, Any] | None:
        return self._load().get(session_id)

    def update_backend_session_id(self, session_id: str, backend_session_id: str) -> None:
        records = self._load()
        record = records.get(session_id, {"session_id": session_id})
        record["backend_session_id"] = backend_session_id
        records[session_id] = record
        self._save(records)

    def update_status(self, session_id: str, status: str) -> None:
        records = self._load()
        record = records.get(session_id, {"session_id": session_id})
        record["status"] = status
        records[session_id] = record
        self._save(records)

    def append_transcript(self, session_id: str, payload: dict[str, Any]) -> None:
        transcript_path = self.transcripts_dir / f"{session_id}.jsonl"
        with transcript_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True, sort_keys=True))
            handle.write("\n")


class CodexSessionBackend:
    def __init__(
        self,
        *,
        workspace_root: Path,
        codex_home_root: Path,
    ) -> None:
        self.workspace_root = workspace_root
        self.codex_home_root = codex_home_root

    def run(self, session: dict[str, Any], input_text: str) -> BackendResult:
        prepared = self._prepare_session(session)
        session_data_dir = self.workspace_root.parent / "data" / "sessions" / session["id"]
        session_data_dir.mkdir(parents=True, exist_ok=True)
        last_message_path = session_data_dir / "last_message.txt"
        command = self._build_command(prepared, input_text, last_message_path)
        process = subprocess.Popen(
            command,
            cwd=prepared["workspace_path"],
            env=self._build_env(prepared),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        backend_session_id = prepared.get("backend_session_id")
        events: list[dict[str, Any]] = []
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.rstrip("\n")
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                payload = {"type": "runtime.output.text", "line": line}
            events.append(payload)
            if payload.get("type") == "session_meta":
                backend_session_id = str(payload.get("payload", {}).get("id") or backend_session_id)
            elif payload.get("type") == "thread.started" and not backend_session_id:
                backend_session_id = str(payload.get("thread_id") or payload.get("payload", {}).get("thread_id"))
        return_code = process.wait()
        last_message = ""
        if last_message_path.exists():
            last_message = last_message_path.read_text(encoding="utf-8").strip()
        if not backend_session_id:
            raise RuntimeError(f"Codex did not report a resumable session id for session {session['id']}")
        return BackendResult(
            backend_session_id=backend_session_id,
            events=events,
            last_message=last_message,
            return_code=return_code,
        )

    def _prepare_session(self, session: dict[str, Any]) -> dict[str, Any]:
        prepared = dict(session)
        workspace_root = Path(prepared["workspace_path"] or self.workspace_root)
        workspace_path = workspace_root
        codex_home = Path(prepared["codex_home"] or self.codex_home_root)
        workspace_path.mkdir(parents=True, exist_ok=True)
        codex_home.mkdir(parents=True, exist_ok=True)
        self._bootstrap_codex_home(codex_home)
        (codex_home / "skills").mkdir(parents=True, exist_ok=True)
        prepared["workspace_path"] = str(workspace_path)
        prepared["codex_home"] = str(codex_home)
        return prepared

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

    def _build_command(self, session: dict[str, Any], input_text: str, last_message_path: Path) -> list[str]:
        command = [
            "codex",
            "exec",
        ]
        if session.get("backend_session_id"):
            command.extend(["resume", str(session["backend_session_id"])])
        command.extend(
            [
                "--json",
                "--skip-git-repo-check",
                "--output-last-message",
                str(last_message_path),
            ]
        )
        if session.get("model"):
            command.extend(["-m", str(session["model"])])
        command.append(input_text)
        return command

    def _build_env(self, session: dict[str, Any]) -> dict[str, str]:
        env = os.environ.copy()
        env["CODEX_HOME"] = str(session["codex_home"])
        env["HOME"] = str(Path.home())
        codex_bin = str(Path(session["codex_home"]) / "bin")
        existing_path = env.get("PATH")
        env["PATH"] = f"{codex_bin}{os.pathsep}{existing_path}" if existing_path else codex_bin
        root_dir = Path(__file__).resolve().parents[2]
        src_dir = root_dir / "src"
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else str(src_dir)
        if session.get("gateway_url"):
            env["AUTOREP_GATEWAY_URL"] = str(session["gateway_url"])
        if session.get("runtime_id"):
            env["AUTOREP_RUNTIME_ID"] = str(session["runtime_id"])
        if session.get("id"):
            env["AUTOREP_SESSION_ID"] = str(session["id"])
        if session.get("agent_id"):
            env["AUTOREP_AGENT_ID"] = str(session["agent_id"])
        if session.get("task_id"):
            env["AUTOREP_TASK_ID"] = str(session["task_id"])
        if session.get("state_root"):
            env["AUTOREP_STATE_ROOT"] = str(session["state_root"])
        return env


class FakeSessionBackend:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._counter = 0

    def run(self, session: dict[str, Any], input_text: str) -> BackendResult:
        self._counter += 1
        backend_session_id = session.get("backend_session_id") or f"fake-session-{self._counter}"
        self.calls.append(
            {
                "session_id": session["id"],
                "backend_session_id": backend_session_id,
                "input_text": input_text,
                "mode": "resume" if session.get("backend_session_id") else "start",
            }
        )
        events = [
            {
                "type": "session_meta",
                "payload": {"id": backend_session_id},
            }
        ]
        return BackendResult(
            backend_session_id=backend_session_id,
            events=events,
            last_message=f"echo:{input_text}",
            return_code=0,
        )
