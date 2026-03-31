from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from autorep_gateway.db import GatewayDB
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
        if method == "GET" and path.startswith("/api/sessions/"):
            session_id = path.rsplit("/", 1)[-1]
            return self.db.get_session(session_id)
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
        raise AssertionError(f"Unhandled request: {method} {path}")


class PersistentSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db = GatewayDB(self.root / "gateway.db")
        self.api = FakeGatewayAPI(self.db)
        self.original_http_json = runtime_main._http_json
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

    def tearDown(self) -> None:
        runtime_main._http_json = self.original_http_json
        self.temp_dir.cleanup()

    def _build_manager(self, backend: FakeSessionBackend) -> RuntimeManager:
        return RuntimeManager(
            gateway_url="http://fake",
            runtime_id="runtime-a",
            machine_id="mac-mini",
            name="Runtime A",
            host=None,
            workspace_root=self.root / "workspaces",
            codex_home_root=self.root / "codex-homes",
            state_root=self.root / "runtime-state",
            agents=[AgentSpec(agent_id="research", role="research")],
            backend_registry={"codex": backend},
        )

    def _create_session(self, initial_input: str | None = None) -> dict:
        session = self.db.create_session(
            agent_id="research",
            runtime_id="runtime-a",
            task_id=None,
            dispatch_id=None,
            title="Primary Session",
            session_key="task:demo:agent:research:primary",
            role="research",
            status="idle",
            lifecycle_status="idle",
            summary=None,
            workspace_path=str(self.root / "workspaces"),
            codex_home=str(self.root / "codex-homes"),
            backend_kind="codex",
            backend_session_id=None,
            machine_id="mac-mini",
            preset_id=None,
            model=None,
            initial_prompt=None,
        )
        if initial_input:
            self.db.add_session_input(
                session_id=session["id"],
                runtime_id="runtime-a",
                agent_id="research",
                kind="message",
                sender="operator",
                payload={"content": initial_input},
                metadata={},
            )
        return session

    def test_session_key_reuses_same_session_record(self) -> None:
        first = self._create_session(initial_input="hello")
        second = self._create_session()
        self.assertEqual(first["id"], second["id"])
        queue = self.db.list_runtime_session_inputs("runtime-a")
        self.assertEqual(len(queue), 1)

    def test_runtime_keeps_backend_session_and_reuses_it_for_injection(self) -> None:
        session = self._create_session(initial_input="first turn")
        pending_inputs = self.db.list_runtime_session_inputs("runtime-a")
        self.assertEqual(len(pending_inputs), 1)

        first_backend = FakeSessionBackend()
        first_manager = self._build_manager(first_backend)
        first_manager._run_session_input(session["id"], pending_inputs[0]["id"])

        first_session = self.db.get_session(session["id"])
        assert first_session is not None
        self.assertEqual(first_session["status"], "idle")
        self.assertEqual(first_session["backend_session_id"], "fake-session-1")
        self.assertEqual(first_backend.calls[0]["mode"], "start")

        local_store_path = self.root / "runtime-state" / "sessions" / "sessions.json"
        self.assertTrue(local_store_path.exists())
        self.assertIn("fake-session-1", local_store_path.read_text(encoding="utf-8"))

        next_input = self.db.add_session_input(
            session_id=session["id"],
            runtime_id="runtime-a",
            agent_id="research",
            kind="message",
            sender="operator",
            payload={"content": "follow up"},
            metadata={},
        )

        second_backend = FakeSessionBackend()
        second_manager = self._build_manager(second_backend)
        second_manager._run_session_input(session["id"], next_input["id"])

        final_session = self.db.get_session(session["id"])
        assert final_session is not None
        self.assertEqual(final_session["backend_session_id"], "fake-session-1")
        self.assertEqual(final_session["status"], "idle")
        self.assertEqual(second_backend.calls[0]["mode"], "resume")
        self.assertEqual(second_backend.calls[0]["backend_session_id"], "fake-session-1")
        messages = self.db.list_messages(session_id=session["id"])
        self.assertEqual(len(messages), 2)


if __name__ == "__main__":
    unittest.main()
