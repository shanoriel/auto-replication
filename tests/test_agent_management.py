from __future__ import annotations

import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path

from autorep_gateway.db import GatewayDB
from autorep_gateway import service as gateway_service
from autorep_gateway.service import online_runtime_conflict, overview_snapshot
from autorep_runtime.main import AgentSpec, RuntimeManager
from autorep_runtime import main as runtime_main
from autorep_runtime.session_manager import FakeSessionBackend


PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Z0T8AAAAASUVORK5CYII="
)


class GatewayAgentManagementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db = GatewayDB(self.root / "gateway.db")
        self.original_service_db = gateway_service.db
        gateway_service.db = self.db
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

    def tearDown(self) -> None:
        gateway_service.db = self.original_service_db
        self.temp_dir.cleanup()

    def test_runtime_agent_op_lifecycle_and_snapshot_sync(self) -> None:
        op = self.db.create_runtime_agent_op(
            runtime_id="runtime-a",
            agent_id="research",
            op_type="create_agent",
            payload={"agent_id": "research", "name": "Research"},
        )
        self.assertEqual(op["status"], "pending")

        claimed = self.db.update_runtime_agent_op(op["id"], status="claimed", error_text=None)
        assert claimed is not None
        self.assertEqual(claimed["status"], "claimed")
        self.assertIsNotNone(claimed["claimed_at"])

        synced = self.db.sync_runtime_agent_snapshot(
            "runtime-a",
            shared_skills=[
                {
                    "skill_id": "planner",
                    "name": "Planner",
                    "description": "Shared planner skill",
                    "path": "/tmp/planner",
                    "source": "runtime",
                }
            ],
            available_models=["gpt-5.4"],
            agents=[
                {
                    "agent_id": "research",
                    "name": "Research",
                    "status": "idle",
                    "summary": "ready",
                    "model": "gpt-5.4",
                    "enabled": True,
                    "role_hint": "research",
                    "avatar_url": "/api/agent-assets/runtime-a/research/avatar.png",
                    "agent_md": "# Research",
                    "enabled_runtime_skills": ["planner"],
                    "enabled_agent_skills": [],
                    "runtime_skill_inventory": [],
                    "agent_skill_inventory": [],
                    "prompt_preview": {
                        "normalized_text": "Agent preview",
                        "agent_md": "# Research",
                        "skills_summary": "planner",
                    },
                    "present": True,
                }
            ],
        )
        assert synced is not None
        agent = self.db.get_agent("research")
        assert agent is not None
        self.assertEqual(agent["metadata"]["model"], "gpt-5.4")
        self.assertTrue(agent["metadata"]["present"])
        self.assertEqual(agent["metadata"]["prompt_preview"]["normalized_text"], "Agent preview")
        runtime = self.db.get_runtime("runtime-a")
        assert runtime is not None
        self.assertEqual(runtime["capabilities"]["agent_management"]["available_models"], ["gpt-5.4"])

        applied = self.db.update_runtime_agent_op(op["id"], status="applied", error_text=None)
        assert applied is not None
        self.assertIsNotNone(applied["applied_at"])

        self.db.sync_runtime_agent_snapshot("runtime-a", shared_skills=[], available_models=[], agents=[])
        agent = self.db.get_agent("research")
        assert agent is not None
        self.assertEqual(agent["status"], "offline")
        self.assertFalse(agent["metadata"]["present"])

    def test_same_machine_cannot_have_two_online_runtimes(self) -> None:
        self.db.upsert_runtime(
            runtime_id="runtime-b",
            machine_id="mac-mini",
            name="Runtime B",
            status="idle",
            summary=None,
            host=None,
            base_url=None,
            labels={},
            capabilities={},
        )
        conflict = online_runtime_conflict("mac-mini", "runtime-b")
        assert conflict is not None
        self.assertEqual(conflict["id"], "runtime-a")

    def test_overview_counts_only_online_visible_runtimes_and_agents(self) -> None:
        self.db.upsert_runtime(
            runtime_id="runtime-b",
            machine_id="other-machine",
            name="Runtime B",
            status="idle",
            summary=None,
            host=None,
            base_url=None,
            labels={},
            capabilities={},
        )
        with self.db.connect() as connection:
            connection.execute(
                "UPDATE runtimes SET last_heartbeat_at = ? WHERE id = ?",
                ("2000-01-01T00:00:00+00:00", "runtime-b"),
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
            metadata={"present": True},
        )
        self.db.upsert_agent(
            agent_id="experiment",
            runtime_id="runtime-a",
            machine_id="mac-mini",
            name="Experiment",
            kind="codex",
            host=None,
            role="experiment",
            transport="gateway-http",
            status="running",
            summary=None,
            metadata={"present": True},
        )
        self.db.upsert_agent(
            agent_id="stale-agent",
            runtime_id="runtime-b",
            machine_id="other-machine",
            name="Stale Agent",
            kind="codex",
            host=None,
            role="research",
            transport="gateway-http",
            status="running",
            summary=None,
            metadata={"present": True},
        )
        self.db.upsert_agent(
            agent_id="missing-agent",
            runtime_id="runtime-a",
            machine_id="mac-mini",
            name="Missing Agent",
            kind="codex",
            host=None,
            role="research",
            transport="gateway-http",
            status="idle",
            summary=None,
            metadata={"present": False},
        )

        overview = overview_snapshot()
        self.assertEqual(overview["runtimes"]["total"], 1)
        self.assertEqual(overview["agents"]["total"], 2)
        self.assertEqual(overview["agents"]["working"], 1)


class FakeGatewayAPI:
    def __init__(self, db: GatewayDB) -> None:
        self.db = db

    def handle(self, path: str, method: str = "GET", payload=None):
        payload = payload or {}
        if method == "GET" and path == "/api/catalog":
            return {"models": [{"id": "gpt-5.4"}, {"id": "gpt-5.4-mini"}]}
        if method == "POST" and path == "/api/runtimes/register":
            return self.db.upsert_runtime(
                runtime_id=payload["runtime_id"],
                machine_id=payload["machine_id"],
                name=payload["name"],
                status=payload["status"],
                summary=payload.get("summary"),
                host=payload.get("host"),
                base_url=payload.get("base_url"),
                labels=payload.get("labels") or {},
                capabilities=payload.get("capabilities") or {},
            )
        if method == "POST" and path.startswith("/api/runtimes/") and path.endswith("/heartbeat"):
            runtime_id = path.split("/")[3]
            return self.db.update_runtime_heartbeat(
                runtime_id,
                status=payload["status"],
                summary=payload.get("summary"),
                labels=payload.get("labels") or {},
                capabilities=payload.get("capabilities") or {},
            )
        if method == "POST" and path.startswith("/api/runtimes/") and path.endswith("/agent-sync"):
            runtime_id = path.split("/")[3]
            return self.db.sync_runtime_agent_snapshot(
                runtime_id,
                shared_skills=payload.get("shared_skills") or [],
                available_models=payload.get("available_models") or [],
                agents=payload.get("agents") or [],
            )
        if method == "GET" and path.startswith("/api/runtime/agent-op-queue?"):
            runtime_id = path.split("runtime_id=", 1)[1].split("&", 1)[0]
            status = path.split("status=", 1)[1].split("&", 1)[0]
            return self.db.list_runtime_agent_ops(runtime_id, statuses=[status])
        if method == "PATCH" and path.startswith("/api/runtime/agent-ops/"):
            op_id = path.rsplit("/", 1)[-1]
            return self.db.update_runtime_agent_op(op_id, status=payload["status"], error_text=payload.get("error_text"))
        if method == "POST" and path.startswith("/api/agents/") and path.endswith("/heartbeat"):
            agent_id = path.split("/")[3]
            return self.db.update_agent_heartbeat(
                agent_id,
                status=payload["status"],
                summary=payload.get("summary"),
                metadata=payload.get("metadata") or {},
            )
        raise AssertionError(f"Unhandled request: {method} {path}")


class RuntimeAgentManagementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db = GatewayDB(self.root / "gateway.db")
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
        self.api = FakeGatewayAPI(self.db)
        self.original_http_json = runtime_main._http_json
        runtime_main._http_json = lambda base_url, path, method="GET", payload=None: self.api.handle(
            path,
            method=method,
            payload=payload,
        )

    def tearDown(self) -> None:
        runtime_main._http_json = self.original_http_json
        self.temp_dir.cleanup()

    def test_runtime_applies_agent_ops_and_prepares_session_files(self) -> None:
        manager = RuntimeManager(
            gateway_url="http://fake",
            runtime_id="runtime-a",
            machine_id="mac-mini",
            name="Runtime A",
            host=None,
            workspace_root=self.root / "workspaces",
            codex_home_root=self.root / "codex-home",
            state_root=self.root / "runtime-state",
            agents=[AgentSpec(agent_id="research", role="research", model="gpt-5.4-mini")],
            backend_registry={"codex": FakeSessionBackend()},
        )
        (self.root / "runtime-state" / "runtime-skills" / "planner").mkdir(parents=True, exist_ok=True)
        ((self.root / "runtime-state" / "runtime-skills" / "planner") / "SKILL.md").write_text(
            "# Planner\n\nShared runtime planning skill.\n",
            encoding="utf-8",
        )

        self.db.create_runtime_agent_op(
            runtime_id="runtime-a",
            agent_id="research",
            op_type="update_agent_config",
            payload={
                "agent_id": "research",
                "name": "Research",
                "model": "gpt-5.4",
                "summary": "updated",
                "enabled": True,
                "agent_md": "# Research\n\nUpdated instructions.\n",
                "enabled_runtime_skills": ["planner"],
                "enabled_agent_skills": [],
                "avatar_data_url": PNG_DATA_URL,
                "avatar_url": "/api/agent-assets/runtime-a/research/avatar.png",
                "role_hint": "research",
            },
        )

        manager._process_runtime_agent_ops()
        manager._sync_agent_snapshot()

        agent = manager._agent_store.get_agent("research")
        assert agent is not None
        self.assertEqual(agent["model"], "gpt-5.4")
        self.assertEqual(agent["enabled_runtime_skills"], ["planner"])
        self.assertTrue((self.root / "runtime-state" / "agents" / "research" / "avatar.png").exists())

        session = {
            "id": "session-1",
            "agent_id": "research",
            "workspace_path": str(self.root / "workspace-root"),
            "codex_home": str(self.root / "codex-home"),
        }
        manager._prepare_session_files(session)

        workspace_agent_dir = self.root / "workspace-root" / "research"
        self.assertTrue((workspace_agent_dir / "AGENT.md").exists())
        self.assertTrue((workspace_agent_dir / "AGENTS.md").exists())
        self.assertIn("Updated instructions", (workspace_agent_dir / "AGENT.md").read_text(encoding="utf-8"))
        self.assertTrue((self.root / "codex-home" / "skills" / "planner").exists())

        synced_agent = self.db.get_agent("research")
        assert synced_agent is not None
        self.assertEqual(synced_agent["metadata"]["model"], "gpt-5.4")
        ops = self.db.list_runtime_agent_ops("runtime-a")
        self.assertEqual(ops[0]["status"], "applied")

    def test_runtime_startup_fails_when_initial_registration_fails(self) -> None:
        runtime_main._http_json = lambda *args, **kwargs: (_ for _ in ()).throw(
            urllib.error.URLError(ConnectionRefusedError("gateway down"))
        )
        manager = RuntimeManager(
            gateway_url="http://fake",
            runtime_id="runtime-a",
            machine_id="mac-mini",
            name="Runtime A",
            host=None,
            workspace_root=self.root / "workspaces",
            codex_home_root=self.root / "codex-home",
            state_root=self.root / "runtime-state",
            agents=[AgentSpec(agent_id="research", role="research", model="gpt-5.4-mini")],
            backend_registry={"codex": FakeSessionBackend()},
        )

        with self.assertRaises(urllib.error.URLError):
            manager.run_forever()

    def test_runtime_retries_after_losing_gateway_during_normal_operation(self) -> None:
        manager = RuntimeManager(
            gateway_url="http://fake",
            runtime_id="runtime-a",
            machine_id="mac-mini",
            name="Runtime A",
            host=None,
            workspace_root=self.root / "workspaces",
            codex_home_root=self.root / "codex-home",
            state_root=self.root / "runtime-state",
            agents=[AgentSpec(agent_id="research", role="research", model="gpt-5.4-mini")],
            poll_interval_secs=0.01,
            backend_registry={"codex": FakeSessionBackend()},
        )
        manager._process_runtime_agent_ops = lambda: None
        manager._flush_dispatch_outbox = lambda: None
        manager._process_session_inputs = lambda: None
        manager._process_runtime_inbox = lambda: None
        manager._launch_pending_dispatches = lambda: None
        manager._launch_pending_sessions = lambda: None

        call_counts = {"register": 0, "heartbeat": 0}

        def flaky_http_json(base_url: str, path: str, method: str = "GET", payload=None):
            if method == "POST" and path == "/api/runtimes/register":
                call_counts["register"] += 1
                result = self.api.handle(path, method=method, payload=payload)
                if call_counts["register"] >= 2:
                    manager.stop()
                return result
            if method == "POST" and path == "/api/runtimes/runtime-a/heartbeat":
                call_counts["heartbeat"] += 1
                if call_counts["heartbeat"] == 1:
                    raise urllib.error.URLError(ConnectionRefusedError("gateway down"))
            return self.api.handle(path, method=method, payload=payload)

        runtime_main._http_json = flaky_http_json

        errors: list[Exception] = []

        def runner() -> None:
            try:
                manager.run_forever()
            except Exception as exc:
                errors.append(exc)

        worker = threading.Thread(target=runner, daemon=True)
        worker.start()
        worker.join(timeout=1.0)

        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertGreaterEqual(call_counts["register"], 2)
        self.assertGreaterEqual(call_counts["heartbeat"], 1)


if __name__ == "__main__":
    unittest.main()
