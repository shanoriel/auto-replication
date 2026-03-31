from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from autorep_gateway.db import GatewayDB
from autorep_runtime.main import AgentSpec, RuntimeManager
from autorep_runtime import main as runtime_main


ROOT = Path(__file__).resolve().parents[1]
STATE_ROOT = ROOT / "data" / "real-smoke"
DB_PATH = STATE_ROOT / "gateway.db"
WORKSPACE_ROOT = STATE_ROOT / "workspaces"
CODEX_HOME_ROOT = STATE_ROOT / "codex-home"
RUNTIME_STATE_ROOT = STATE_ROOT / "runtime-state"
METADATA_PATH = STATE_ROOT / "metadata.json"

RUNTIME_ID = "runtime-smoke"
AGENT_ID = "research-smoke"
SESSION_KEY = "smoke:research:primary"


class LocalGatewayAPI:
    def __init__(self, db: GatewayDB) -> None:
        self.db = db

    def handle(self, path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
        payload = payload or {}
        if method == "GET" and path.startswith("/api/runtime/session-input-queue?"):
            runtime_id = path.split("runtime_id=", 1)[1].split("&", 1)[0]
            status = "pending"
            if "status=" in path:
                status = path.split("status=", 1)[1].split("&", 1)[0]
            return self.db.list_runtime_session_inputs(runtime_id, status=status)
        if method == "GET" and path.startswith("/api/sessions/"):
            return self.db.get_session(path.rsplit("/", 1)[-1])
        if method == "POST" and path.endswith("/messages"):
            session_id = path.split("/")[3]
            session = self.db.get_session(session_id)
            assert session is not None
            return self.db.add_message(
                session_id=session_id,
                agent_id=session["agent_id"],
                sender=payload["sender"],
                direction=payload["direction"],
                content=payload["content"],
                status=payload["status"],
            )
        if method == "POST" and path.endswith("/events"):
            session_id = path.split("/")[3]
            session = self.db.get_session(session_id)
            assert session is not None
            return self.db.add_event(
                session_id=session_id,
                agent_id=session["agent_id"],
                event_type=payload["event_type"],
                payload=payload["payload"],
            )
        if method == "PATCH" and path.startswith("/api/sessions/"):
            session_id = path.rsplit("/", 1)[-1]
            return self.db.update_session(
                session_id,
                status=payload.get("status"),
                lifecycle_status=payload.get("lifecycle_status"),
                summary=payload.get("summary"),
                codex_thread_id=payload.get("codex_thread_id"),
                backend_session_id=payload.get("backend_session_id"),
            )
        if method == "PATCH" and path.startswith("/api/session-inputs/"):
            session_input_id = path.rsplit("/", 1)[-1]
            return self.db.update_session_input(
                session_input_id,
                status=payload["status"],
                error_text=payload.get("error_text"),
            )
        raise RuntimeError(f"Unhandled request: {method} {path}")


def ensure_layout() -> None:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    CODEX_HOME_ROOT.mkdir(parents=True, exist_ok=True)
    RUNTIME_STATE_ROOT.mkdir(parents=True, exist_ok=True)


def ensure_seed_data(db: GatewayDB) -> None:
    db.upsert_runtime(
        runtime_id=RUNTIME_ID,
        machine_id="mac-mini",
        name="Smoke Runtime",
        status="idle",
        summary="Persistent smoke runtime",
        host=None,
        base_url=None,
        labels={"purpose": "real-smoke"},
        capabilities={"session_execution": True},
    )
    db.upsert_agent(
        agent_id=AGENT_ID,
        runtime_id=RUNTIME_ID,
        machine_id="mac-mini",
        name="Research Smoke",
        kind="codex",
        host=None,
        role="research",
        transport="gateway-http",
        status="idle",
        summary="Persistent smoke agent",
        metadata={},
    )


def ensure_session(db: GatewayDB) -> dict[str, Any]:
    session = db.create_session(
        agent_id=AGENT_ID,
        runtime_id=RUNTIME_ID,
        task_id=None,
        dispatch_id=None,
        title="Real Session Smoke",
        session_key=SESSION_KEY,
        role="research",
        status="idle",
        lifecycle_status="idle",
        summary="Persistent smoke session",
        workspace_path=str(WORKSPACE_ROOT),
        codex_home=str(CODEX_HOME_ROOT),
        backend_kind="codex",
        backend_session_id=None,
        machine_id="mac-mini",
        preset_id=None,
        model=None,
        initial_prompt=None,
    )
    return session


def run_input(message: str) -> dict[str, Any]:
    ensure_layout()
    db = GatewayDB(DB_PATH)
    ensure_seed_data(db)
    session = ensure_session(db)
    session_input = db.add_session_input(
        session_id=session["id"],
        runtime_id=RUNTIME_ID,
        agent_id=AGENT_ID,
        kind="message",
        sender="operator",
        payload={"content": message},
        metadata={},
    )
    api = LocalGatewayAPI(db)
    original_http_json = runtime_main._http_json
    runtime_main._http_json = lambda base_url, path, method="GET", payload=None: api.handle(
        path,
        method=method,
        payload=payload,
    )
    try:
        manager = RuntimeManager(
            gateway_url="http://local-smoke",
            runtime_id=RUNTIME_ID,
            machine_id="mac-mini",
            name="Smoke Runtime",
            host=None,
            workspace_root=WORKSPACE_ROOT,
            codex_home_root=CODEX_HOME_ROOT,
            state_root=RUNTIME_STATE_ROOT,
            agents=[AgentSpec(agent_id=AGENT_ID, role="research")],
        )
        manager._run_session_input(session["id"], session_input["id"])
    finally:
        runtime_main._http_json = original_http_json
    latest_session = db.get_session(session["id"])
    assert latest_session is not None
    messages = db.list_messages(session_id=session["id"])
    latest_message = messages[0]["content"] if messages else None
    metadata = {
        "session_id": latest_session["id"],
        "backend_session_id": latest_session["backend_session_id"],
        "workspace_root": str(WORKSPACE_ROOT),
        "codex_home_root": str(CODEX_HOME_ROOT),
        "runtime_state_root": str(RUNTIME_STATE_ROOT),
        "latest_message": latest_message,
    }
    METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=True, indent=2), encoding="utf-8")
    return metadata


def show_state() -> dict[str, Any]:
    if not METADATA_PATH.exists():
        raise SystemExit("No smoke metadata found. Run `start` first.")
    return json.loads(METADATA_PATH.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run or inspect the persistent real Codex smoke session.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Create or reuse the persistent smoke session and send a first message.")
    start.add_argument(
        "--message",
        default="Reply with exactly FIRST_OK and do not use tools.",
    )

    send = subparsers.add_parser("send", help="Send a follow-up message to the existing smoke session.")
    send.add_argument(
        "--message",
        required=True,
    )

    subparsers.add_parser("show", help="Show the persisted smoke session metadata.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "start":
        result = run_input(args.message)
    elif args.command == "send":
        result = run_input(args.message)
    else:
        result = show_state()
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
