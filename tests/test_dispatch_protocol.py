from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from autorep_gateway.db import GatewayDB
from autorep_runtime.dispatch_cli import main as dispatch_cli_main
from autorep_runtime.main import AgentSpec, RuntimeManager
from autorep_runtime import main as runtime_main
from autorep_runtime.session_manager import FakeSessionBackend


class FakeGatewayAPI:
    def __init__(self, db: GatewayDB) -> None:
        self.db = db

    def handle(self, path: str, method: str = "GET", payload=None):
        payload = payload or {}
        if method == "GET" and path.startswith("/api/runtime/session-input-queue?"):
            runtime_id = path.split("runtime_id=", 1)[1].split("&", 1)[0]
            status = "pending"
            if "status=" in path:
                status = path.split("status=", 1)[1].split("&", 1)[0]
            return self.db.list_runtime_session_inputs(runtime_id, status=status)
        if method == "GET" and path.startswith("/api/runtime/inbox?"):
            runtime_id = path.split("runtime_id=", 1)[1].split("&", 1)[0]
            status = "pending"
            if "status=" in path:
                status = path.split("status=", 1)[1].split("&", 1)[0]
            return self.db.list_runtime_inbox(runtime_id, status=status)
        if method == "GET" and path.startswith("/api/runtime/dispatch-queue?"):
            runtime_id = path.split("runtime_id=", 1)[1].split("&", 1)[0]
            status = "pending"
            if "status=" in path:
                status = path.split("status=", 1)[1].split("&", 1)[0]
            return self.db.list_dispatches_for_runtime(runtime_id, statuses=[status])
        if method == "GET" and path.startswith("/api/sessions/"):
            return self.db.get_session(path.rsplit("/", 1)[-1])
        if method == "GET" and path.startswith("/api/tasks/"):
            return self.db.get_task(path.rsplit("/", 1)[-1])
        if method == "GET" and path.startswith("/api/dispatches/"):
            return self.db.get_dispatch(path.rsplit("/", 1)[-1])
        if method == "POST" and path == "/api/dispatches":
            return self.db.create_dispatch(
                task_id=payload["task_id"],
                kind=payload["kind"],
                status=payload["status"],
                from_agent_id=payload["from_agent_id"],
                to_agent_id=payload["to_agent_id"],
                parent_dispatch_id=payload.get("parent_dispatch_id"),
                payload=payload.get("payload") or {},
                reply=payload.get("reply"),
            )
        if method == "POST" and path == "/api/sessions":
            return self.db.create_session(
                agent_id=payload["agent_id"],
                runtime_id=payload.get("runtime_id"),
                task_id=payload.get("task_id"),
                dispatch_id=payload.get("dispatch_id"),
                title=payload["title"],
                session_key=payload.get("session_key"),
                role=payload.get("role"),
                status=payload["status"],
                lifecycle_status=payload.get("lifecycle_status") or payload["status"],
                summary=payload.get("summary"),
                workspace_path=payload.get("workspace_path"),
                codex_home=payload.get("codex_home"),
                backend_kind="codex",
                backend_session_id=None,
                machine_id=payload.get("machine_id"),
                preset_id=payload.get("preset_id"),
                model=payload.get("model"),
                initial_prompt=payload.get("initial_prompt"),
            )
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
        if method == "PATCH" and path.startswith("/api/runtime/inbox/"):
            item_id = path.rsplit("/", 1)[-1]
            return self.db.update_runtime_inbox_item(item_id, status=payload["status"])
        if method == "PATCH" and path.startswith("/api/dispatches/"):
            dispatch_id = path.rsplit("/", 1)[-1]
            return self.db.update_dispatch(
                dispatch_id,
                status=payload.get("status"),
                payload=payload.get("payload"),
                reply=payload.get("reply"),
                session_id=payload.get("session_id"),
                accepted=payload.get("accepted"),
                resolved=payload.get("resolved"),
            )
        raise AssertionError(f"Unhandled request: {method} {path}")


class DispatchProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db = GatewayDB(self.root / "gateway.db")
        self.api = FakeGatewayAPI(self.db)
        self.original_runtime_http = runtime_main._http_json
        runtime_main._http_json = lambda base_url, path, method="GET", payload=None: self.api.handle(
            path,
            method=method,
            payload=payload,
        )

        self.db.upsert_runtime(
            runtime_id="runtime-a",
            machine_id="mac-mini",
            name="Runtime A",
            status="idle",
            summary=None,
            host=None,
            base_url=None,
            labels={},
            capabilities={},
        )
        self.db.upsert_runtime(
            runtime_id="runtime-b",
            machine_id="linux-box",
            name="Runtime B",
            status="idle",
            summary=None,
            host=None,
            base_url=None,
            labels={},
            capabilities={},
        )
        self.db.upsert_agent(
            agent_id="research",
            runtime_id="runtime-a",
            machine_id="mac-mini",
            name="Research",
            kind="codex",
            host=None,
            role="research",
            transport="gateway-http",
            status="idle",
            summary=None,
            metadata={},
        )
        self.db.upsert_agent(
            agent_id="experiment",
            runtime_id="runtime-b",
            machine_id="linux-box",
            name="Experiment",
            kind="codex",
            host=None,
            role="experiment",
            transport="gateway-http",
            status="idle",
            summary=None,
            metadata={},
        )
        self.task = self.db.create_task(
            title="Dispatch Task",
            created_by="human",
            entry_agent_id="research",
            participant_agent_ids=["research", "experiment"],
            objective="Verify dispatch protocol",
            status="created",
            summary=None,
            stage_plan={},
            metadata={},
        )
        self.research_session = self.db.create_session(
            agent_id="research",
            runtime_id="runtime-a",
            task_id=self.task["id"],
            dispatch_id=None,
            title="Research Primary",
            session_key="task:dispatch:research:primary",
            role="research",
            status="idle",
            lifecycle_status="idle",
            summary=None,
            workspace_path=str(self.root / "workspaces" / "a"),
            codex_home=str(self.root / "codex" / "a"),
            backend_kind="codex",
            backend_session_id=None,
            machine_id="mac-mini",
            preset_id=None,
            model=None,
            initial_prompt=None,
        )

    def tearDown(self) -> None:
        runtime_main._http_json = self.original_runtime_http
        self.temp_dir.cleanup()

    def _build_manager(self, runtime_id: str, agent_id: str, role: str, backend: FakeSessionBackend) -> RuntimeManager:
        return RuntimeManager(
            gateway_url="http://fake",
            runtime_id=runtime_id,
            machine_id="machine",
            name=runtime_id,
            host=None,
            workspace_root=self.root / "workspaces" / runtime_id,
            codex_home_root=self.root / "codex" / runtime_id,
            state_root=self.root / "state" / runtime_id,
            agents=[AgentSpec(agent_id=agent_id, role=role)],
            backend_registry={"codex": backend},
        )

    def _run_cli(self, dispatch_state_root: Path, session_id: str, agent_id: str, argv: list[str]) -> None:
        old_env = os.environ.copy()
        payload_file = self.root / "payload.json"
        try:
            os.environ["AUTOREP_GATEWAY_URL"] = "http://fake"
            os.environ["AUTOREP_RUNTIME_ID"] = "runtime-a" if agent_id == "research" else "runtime-b"
            os.environ["AUTOREP_SESSION_ID"] = session_id
            os.environ["AUTOREP_AGENT_ID"] = agent_id
            os.environ["AUTOREP_TASK_ID"] = self.task["id"]
            os.environ["AUTOREP_STATE_ROOT"] = str(dispatch_state_root)
            with contextlib.redirect_stdout(io.StringIO()):
                dispatch_cli_main(argv)
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    def test_work_order_reply_returns_to_origin_session(self) -> None:
        payload_file = self.root / "work_order.json"
        payload_file.write_text(json.dumps({"goal": "run smoke"}), encoding="utf-8")

        manager_a = self._build_manager("runtime-a", "research", "research", FakeSessionBackend())
        self._run_cli(manager_a.dispatch_state_root, self.research_session["id"], "research", ["work-order", "--to-agent", "experiment", "--payload-file", str(payload_file)])
        manager_a._flush_dispatch_outbox()

        dispatch = self.db.list_dispatches(task_id=self.task["id"])[0]
        self.assertEqual(dispatch["kind"], "work-order")
        self.assertEqual(manager_a._dispatch_store.outbound_session(dispatch["id"]), self.research_session["id"])

        manager_b = self._build_manager("runtime-b", "experiment", "experiment", FakeSessionBackend())
        session_b = manager_b._create_session_for_dispatch(dispatch)
        manager_b._run_dispatch_session(session_b["id"], dispatch["id"])

        result_file = self.root / "result.json"
        result_file.write_text(json.dumps({"summary": "done"}), encoding="utf-8")
        self._run_cli(manager_b.dispatch_state_root, session_b["id"], "experiment", ["reply", "--result-file", str(result_file)])
        manager_b._flush_dispatch_outbox()

        inbox_items = self.db.list_runtime_inbox("runtime-a")
        self.assertEqual(len(inbox_items), 1)
        manager_a._run_runtime_inbox_item(self.research_session["id"], inbox_items[0]["id"])

        messages = self.db.list_messages(session_id=self.research_session["id"])
        self.assertEqual(self.db.get_dispatch(dispatch["id"])["status"], "replied")
        self.assertIn("dispatch", messages[0]["content"].lower())

    def test_clarification_request_routes_back_to_origin_session(self) -> None:
        payload_file = self.root / "work_order.json"
        payload_file.write_text(json.dumps({"goal": "run smoke"}), encoding="utf-8")

        manager_a = self._build_manager("runtime-a", "research", "research", FakeSessionBackend())
        self._run_cli(manager_a.dispatch_state_root, self.research_session["id"], "research", ["work-order", "--to-agent", "experiment", "--payload-file", str(payload_file)])
        manager_a._flush_dispatch_outbox()
        work_order = self.db.list_dispatches(task_id=self.task["id"])[0]

        manager_b = self._build_manager("runtime-b", "experiment", "experiment", FakeSessionBackend())
        session_b = manager_b._create_session_for_dispatch(work_order)
        manager_b._run_dispatch_session(session_b["id"], work_order["id"])

        self._run_cli(manager_b.dispatch_state_root, session_b["id"], "experiment", ["request-clarify", "--question", "Which simulator version?"])
        manager_b._flush_dispatch_outbox()
        dispatches = self.db.list_dispatches(task_id=self.task["id"])
        clarification = next(item for item in dispatches if item["kind"] == "clarification-request")

        manager_a._run_clarification_dispatch(self.research_session["id"], clarification["id"])
        answer_file = self.root / "clarification_reply.json"
        answer_file.write_text(json.dumps({"answer": "Use simulator v1"}), encoding="utf-8")
        self._run_cli(manager_a.dispatch_state_root, self.research_session["id"], "research", ["reply", "--result-file", str(answer_file)])
        manager_a._flush_dispatch_outbox()

        inbox_items = self.db.list_runtime_inbox("runtime-b")
        self.assertEqual(len(inbox_items), 1)
        manager_b._run_runtime_inbox_item(session_b["id"], inbox_items[0]["id"])

        self.assertEqual(self.db.get_dispatch(clarification["id"])["status"], "replied")
        messages = self.db.list_messages(session_id=session_b["id"])
        self.assertIn("simulator", messages[0]["content"].lower())


if __name__ == "__main__":
    unittest.main()
