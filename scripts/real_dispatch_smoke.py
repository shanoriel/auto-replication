from __future__ import annotations

import argparse
import json
import shutil
import socket
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

import uvicorn

from autorep_gateway.db import GatewayDB
from autorep_gateway import main as gateway_main
from autorep_gateway import service as gateway_service
from autorep_runtime.main import AgentSpec, RuntimeManager


ROOT = Path(__file__).resolve().parents[1]
STATE_ROOT = ROOT / "data" / "real-dispatch-smoke"
DB_PATH = STATE_ROOT / "gateway.db"
WORKSPACE_ROOT = STATE_ROOT / "workspaces"
CODEX_HOME_ROOT = STATE_ROOT / "codex-home"
RUNTIME_STATE_ROOT = STATE_ROOT / "runtime-state"
SUMMARY_PATH = STATE_ROOT / "summary.json"
CONVERSATION_PATH = STATE_ROOT / "conversation.md"
DISPATCH_BRIDGE_ROOT = Path("/tmp") / "autorep-dispatch-real-dispatch-smoke"

RUNTIME_ID = "runtime-dispatch-smoke"
RESEARCH_AGENT_ID = "research"
EXPERIMENT_AGENT_ID = "experiment"
TOKEN = "TOKEN-42"


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
        f"{base_url.rstrip('/')}{path}",
        method=method,
        data=body,
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def _wait_until(predicate, timeout_secs: float, step_secs: float = 1.0, label: str = "condition") -> Any:
    deadline = time.time() + timeout_secs
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            value = predicate()
            last_error = None
        except Exception as exc:
            last_error = exc
            value = None
        if value:
            return value
        time.sleep(step_secs)
    if last_error is not None:
        raise TimeoutError(f"Timed out waiting for {label}: {last_error}") from last_error
    raise TimeoutError(f"Timed out waiting for {label}")


def _reset_state() -> None:
    if STATE_ROOT.exists():
        shutil.rmtree(STATE_ROOT)
    if DISPATCH_BRIDGE_ROOT.exists():
        shutil.rmtree(DISPATCH_BRIDGE_ROOT)
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    CODEX_HOME_ROOT.mkdir(parents=True, exist_ok=True)
    RUNTIME_STATE_ROOT.mkdir(parents=True, exist_ok=True)
    DISPATCH_BRIDGE_ROOT.mkdir(parents=True, exist_ok=True)


def _configure_state_root(state_root: Path) -> None:
    global STATE_ROOT, DB_PATH, WORKSPACE_ROOT, CODEX_HOME_ROOT, RUNTIME_STATE_ROOT, SUMMARY_PATH, CONVERSATION_PATH, DISPATCH_BRIDGE_ROOT
    STATE_ROOT = state_root
    DB_PATH = STATE_ROOT / "gateway.db"
    WORKSPACE_ROOT = STATE_ROOT / "workspaces"
    CODEX_HOME_ROOT = STATE_ROOT / "codex-home"
    RUNTIME_STATE_ROOT = STATE_ROOT / "runtime-state"
    SUMMARY_PATH = STATE_ROOT / "summary.json"
    CONVERSATION_PATH = STATE_ROOT / "conversation.md"
    DISPATCH_BRIDGE_ROOT = Path("/tmp") / f"autorep-dispatch-{STATE_ROOT.name}"


def _write_research_seed_files() -> None:
    agent_workspace = WORKSPACE_ROOT / "research-default"
    agent_workspace.mkdir(parents=True, exist_ok=True)
    payload = {
        "title": "Clarification handshake smoke",
        "goal": "Ask exactly one clarification question, wait for the answer, then return a formal reply.",
        "required_clarification_question": "What final token should appear in the result?",
        "expected_clarification_answer": f"Use {TOKEN}",
        "final_reply_contract": {
            "result": "completed",
            "token": TOKEN,
            "summary": f"Experiment confirmed token {TOKEN}",
        },
        "notes": [
            "Ask exactly one clarification request before the final reply.",
            "After the clarification reply arrives, send the final reply through autorep-dispatch reply.",
        ],
    }
    (agent_workspace / "work_order.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    clarification_reply = {
        "answer": f"Use {TOKEN}",
        "summary": f"The final token should be {TOKEN}.",
    }
    (agent_workspace / "clarification_reply.json").write_text(
        json.dumps(clarification_reply, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _research_initial_prompt() -> str:
    return "\n".join(
        [
            "This is a staged AutoReplication dispatch smoke test.",
            "Current turn only:",
            f"- Run exactly `autorep-dispatch work-order --to-agent {EXPERIMENT_AGENT_ID} --payload-file work_order.json` from the session workspace.",
            "- After that command succeeds, reply with exactly `WORK_ORDER_SENT` and stop.",
            "Future turns:",
            "- If this session later receives a clarification request about the final token, answer it with `autorep-dispatch reply --result-file clarification_reply.json`.",
            "- After sending that clarification reply, respond with exactly `CLARIFICATION_REPLY_SENT` and stop.",
            "- After the experiment agent sends the final formal reply back to this session, answer the user with exactly:",
            f"FINAL_REPORT_OK token={TOKEN}",
            "Do not ask the user any questions.",
        ]
    )


def _format_dispatch_conversation(dispatches: list[dict[str, Any]], research_messages: list[dict[str, Any]]) -> str:
    work_order = next(item for item in dispatches if item["kind"] == "work-order")
    clarification = next(item for item in dispatches if item["kind"] == "clarification-request")
    final_report = research_messages[0]["content"] if research_messages else ""
    lines = [
        "# Real Dispatch Smoke Conversation",
        "",
        f"A (research) -> B (experiment) [work-order]: {work_order['payload'].get('goal')}",
        f"B (experiment) -> A (research) [clarification]: {clarification['payload'].get('question')}",
        f"A (research) -> B (experiment) [clarification reply]: {clarification['reply'].get('answer')}",
        f"B (experiment) -> A (research) [formal reply]: {work_order['reply'].get('summary')}",
        f"A (research) -> User [final report]: {final_report}",
        "",
    ]
    return "\n".join(lines)


class LocalGatewayServer:
    def __init__(self, db: GatewayDB, host: str, port: int) -> None:
        self.db = db
        self.host = host
        self.port = port
        gateway_service.db = db
        gateway_main.db = db
        config = uvicorn.Config(gateway_main.app, host=host, port=port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        self.thread.start()
        _wait_until(
            lambda: _http_json(self.base_url, "/health").get("status") == "ok",
            timeout_secs=20,
            step_secs=0.25,
            label="gateway server",
        )

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


def run_smoke(timeout_secs: float) -> dict[str, Any]:
    _reset_state()
    db = GatewayDB(DB_PATH)
    port = _find_free_port()
    gateway = LocalGatewayServer(db, "127.0.0.1", port)
    gateway.start()

    runtime = RuntimeManager(
        gateway_url=gateway.base_url,
        runtime_id=RUNTIME_ID,
        machine_id="mac-mini",
        name="Real Dispatch Smoke Runtime",
        host="127.0.0.1",
        workspace_root=WORKSPACE_ROOT,
        codex_home_root=CODEX_HOME_ROOT,
        state_root=RUNTIME_STATE_ROOT,
        dispatch_state_root=DISPATCH_BRIDGE_ROOT,
        agents=[
            AgentSpec(agent_id=RESEARCH_AGENT_ID, role="research", preset_id="research-default", model="gpt-5.4-mini"),
            AgentSpec(agent_id=EXPERIMENT_AGENT_ID, role="experiment", preset_id="experiment-default", model="gpt-5.4-mini"),
        ],
        poll_interval_secs=1.0,
    )
    runtime_thread = threading.Thread(target=runtime.run_forever, daemon=True)
    runtime_thread.start()

    try:
        _wait_until(
            lambda: len(_http_json(gateway.base_url, "/api/agents")) >= 2,
            timeout_secs=20,
            step_secs=0.5,
            label="runtime agent registration",
        )
        _write_research_seed_files()
        task = _http_json(
            gateway.base_url,
            "/api/tasks",
            method="POST",
            payload={
                "title": "Real dispatch smoke",
                "created_by": "human",
                "entry_agent_id": RESEARCH_AGENT_ID,
                "participant_agent_ids": [RESEARCH_AGENT_ID, EXPERIMENT_AGENT_ID],
                "objective": "Verify A/B dispatch, clarification, and final reply over the real runtime path.",
                "initial_input": _research_initial_prompt(),
                "status": "created",
                "summary": "Real codex dispatch smoke",
                "stage_plan": {},
                "metadata": {},
            },
        )
        research_session_id = str(task["entry_session_id"])

        final_report = _wait_until(
            lambda: next(
                (
                    message["content"]
                    for message in _http_json(
                        gateway.base_url,
                        f"/api/sessions/{research_session_id}/messages?limit=20",
                    )
                    if TOKEN in message["content"] and "FINAL_REPORT_OK" in message["content"]
                ),
                None,
            ),
            timeout_secs=timeout_secs,
            step_secs=2.0,
            label="final research report",
        )
        dispatches = _http_json(gateway.base_url, f"/api/dispatches?task_id={task['id']}")
        sessions = _http_json(gateway.base_url, f"/api/sessions?task_id={task['id']}")
        research_messages = _http_json(gateway.base_url, f"/api/sessions/{research_session_id}/messages?limit=20")
        conversation = _format_dispatch_conversation(dispatches, research_messages)
        summary = {
            "gateway_url": gateway.base_url,
            "task_id": task["id"],
            "research_session_id": research_session_id,
            "dispatches": dispatches,
            "sessions": sessions,
            "final_report": final_report,
            "dispatch_bridge_root": str(DISPATCH_BRIDGE_ROOT),
            "conversation_path": str(CONVERSATION_PATH),
        }
        SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        CONVERSATION_PATH.write_text(conversation, encoding="utf-8")
        return summary
    finally:
        runtime.stop()
        runtime_thread.join(timeout=10)
        gateway.stop()


def show_results() -> dict[str, Any]:
    if not SUMMARY_PATH.exists():
        raise SystemExit("No real dispatch smoke result found. Run `run` first.")
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a real A/B dispatch smoke test against the local AutoReplication runtime.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="Run the real dispatch smoke.")
    run.add_argument("--timeout-secs", type=float, default=300.0)
    run.add_argument("--state-root", default=str(STATE_ROOT))
    subparsers.add_parser("show", help="Show the latest saved smoke result.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        _configure_state_root(Path(args.state_root))
        result = run_smoke(timeout_secs=args.timeout_secs)
    else:
        result = show_results()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
