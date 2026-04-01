from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from autorep_gateway.db import GatewayDB
from autorep_gateway.task_bootstrap import bootstrap_primary_task_session


class TaskBootstrapTests(unittest.TestCase):
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
            metadata={"preset_id": "research-default", "default_model": "gpt-5.4-mini"},
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
            status="idle",
            summary=None,
            metadata={"preset_id": "experiment-default", "default_model": "gpt-5.4-mini"},
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_bootstrap_primary_session_and_initial_input(self) -> None:
        task = self.db.create_task(
            title="Bootstrap Task",
            created_by="human",
            entry_agent_id="research",
            participant_agent_ids=["research", "experiment"],
            objective="Use the research agent to start the task.",
            status="created",
            summary="task summary",
            stage_plan={},
            metadata={},
        )
        agent = self.db.get_agent("research")
        assert agent is not None
        session = bootstrap_primary_task_session(
            self.db,
            task=task,
            agent=agent,
            initial_input="Start this task and delegate to experiment when ready.",
        )
        sessions = self.db.list_sessions(task_id=task["id"])
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["id"], session["id"])
        self.assertEqual(session["agent_id"], "research")
        self.assertEqual(session["session_key"], f"task:{task['id']}:agent:research:primary")
        self.assertEqual(session["preset_id"], "research-default")
        self.assertEqual(session["model"], "gpt-5.4-mini")
        self.assertEqual(session["status"], "idle")
        queued_inputs = self.db.list_runtime_session_inputs("runtime-a")
        self.assertEqual(len(queued_inputs), 1)
        self.assertEqual(queued_inputs[0]["session_id"], session["id"])
        self.assertEqual(queued_inputs[0]["payload"]["content"], "Start this task and delegate to experiment when ready.")

    def test_bootstrap_falls_back_to_runtime_paths_when_machine_not_in_catalog(self) -> None:
        self.db.upsert_runtime(
            runtime_id="runtime-b",
            machine_id="smoke-machine",
            name="Runtime B",
            status="idle",
            summary=None,
            host=None,
            base_url=None,
            labels={},
            capabilities={
                "workspace_root": "/tmp/smoke/workspaces",
                "codex_home_root": "/tmp/smoke/codex-home",
            },
        )
        self.db.upsert_agent(
            agent_id="smoke-research",
            runtime_id="runtime-b",
            machine_id="smoke-machine",
            name="Smoke Research",
            kind="codex",
            host=None,
            role="research",
            transport="gateway-http",
            status="idle",
            summary=None,
            metadata={"model": "gpt-5.4-mini"},
        )
        task = self.db.create_task(
            title="Runtime Path Fallback",
            created_by="human",
            entry_agent_id="smoke-research",
            participant_agent_ids=["smoke-research"],
            objective="Verify runtime path fallback.",
            status="created",
            summary=None,
            stage_plan={},
            metadata={},
        )
        agent = self.db.get_agent("smoke-research")
        assert agent is not None
        session = bootstrap_primary_task_session(
            self.db,
            task=task,
            agent=agent,
            initial_input="Smoke",
        )
        self.assertEqual(session["workspace_path"], "/tmp/smoke/workspaces")
        self.assertEqual(session["codex_home"], "/tmp/smoke/codex-home")


if __name__ == "__main__":
    unittest.main()
