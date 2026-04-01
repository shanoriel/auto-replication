from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        try:
            return super().__exit__(exc_type, exc_val, exc_tb)
        finally:
            self.close()


def dict_factory(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for index, column in enumerate(cursor.description):
        result[column[0]] = row[index]
    return result


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)


class GatewayDB:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, factory=ClosingConnection)
        connection.row_factory = dict_factory
        return connection

    def _init_db(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS runtimes (
                    id TEXT PRIMARY KEY,
                    machine_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT,
                    host TEXT,
                    base_url TEXT,
                    labels_json TEXT NOT NULL,
                    capabilities_json TEXT NOT NULL,
                    last_heartbeat_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY,
                    runtime_id TEXT,
                    machine_id TEXT,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    host TEXT,
                    role TEXT,
                    transport TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT,
                    metadata_json TEXT NOT NULL,
                    last_heartbeat_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(runtime_id) REFERENCES runtimes(id)
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    entry_agent_id TEXT,
                    participant_agents_json TEXT NOT NULL,
                    objective TEXT,
                    summary TEXT,
                    stage_plan_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(entry_agent_id) REFERENCES agents(id)
                );

                CREATE TABLE IF NOT EXISTS dispatches (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    from_agent_id TEXT NOT NULL,
                    to_agent_id TEXT NOT NULL,
                    parent_dispatch_id TEXT,
                    payload_json TEXT NOT NULL,
                    reply_json TEXT,
                    session_id TEXT,
                    accepted_at TEXT,
                    resolved_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id),
                    FOREIGN KEY(from_agent_id) REFERENCES agents(id),
                    FOREIGN KEY(to_agent_id) REFERENCES agents(id)
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    runtime_id TEXT,
                    task_id TEXT,
                    dispatch_id TEXT,
                    title TEXT NOT NULL,
                    session_key TEXT,
                    role TEXT,
                    status TEXT NOT NULL,
                    lifecycle_status TEXT,
                    summary TEXT,
                    workspace_path TEXT,
                    codex_home TEXT,
                    codex_thread_id TEXT,
                    backend_kind TEXT,
                    backend_session_id TEXT,
                    machine_id TEXT,
                    preset_id TEXT,
                    model TEXT,
                    initial_prompt TEXT,
                    last_input_at TEXT,
                    last_output_at TEXT,
                    closed_at TEXT,
                    close_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_event_at TEXT,
                    FOREIGN KEY(agent_id) REFERENCES agents(id),
                    FOREIGN KEY(runtime_id) REFERENCES runtimes(id),
                    FOREIGN KEY(task_id) REFERENCES tasks(id),
                    FOREIGN KEY(dispatch_id) REFERENCES dispatches(id)
                );

                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id),
                    FOREIGN KEY(agent_id) REFERENCES agents(id)
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    delivered_at TEXT,
                    FOREIGN KEY(session_id) REFERENCES sessions(id),
                    FOREIGN KEY(agent_id) REFERENCES agents(id)
                );

                CREATE TABLE IF NOT EXISTS session_inputs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    runtime_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_text TEXT,
                    created_at TEXT NOT NULL,
                    delivered_at TEXT,
                    processed_at TEXT,
                    FOREIGN KEY(session_id) REFERENCES sessions(id),
                    FOREIGN KEY(runtime_id) REFERENCES runtimes(id),
                    FOREIGN KEY(agent_id) REFERENCES agents(id)
                );

                CREATE TABLE IF NOT EXISTS runtime_inbox (
                    id TEXT PRIMARY KEY,
                    runtime_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    dispatch_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    processed_at TEXT,
                    FOREIGN KEY(runtime_id) REFERENCES runtimes(id),
                    FOREIGN KEY(dispatch_id) REFERENCES dispatches(id)
                );

                CREATE TABLE IF NOT EXISTS runtime_agent_ops (
                    id TEXT PRIMARY KEY,
                    runtime_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    op_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_text TEXT,
                    created_at TEXT NOT NULL,
                    claimed_at TEXT,
                    applied_at TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(runtime_id) REFERENCES runtimes(id)
                );
                """
            )
            self._ensure_columns(connection)

    def _ensure_columns(self, connection: sqlite3.Connection) -> None:
        self._ensure_table_columns(
            connection,
            "agents",
            {
                "runtime_id": "TEXT",
                "machine_id": "TEXT",
            },
        )
        self._ensure_table_columns(
            connection,
            "tasks",
            {
                "entry_agent_id": "TEXT",
                "participant_agents_json": "TEXT NOT NULL DEFAULT '[]'",
                "objective": "TEXT",
                "stage_plan_json": "TEXT NOT NULL DEFAULT '{}'",
            },
        )
        self._ensure_table_columns(
            connection,
            "sessions",
            {
                "session_key": "TEXT",
                "machine_id": "TEXT",
                "preset_id": "TEXT",
                "model": "TEXT",
                "initial_prompt": "TEXT",
                "runtime_id": "TEXT",
                "task_id": "TEXT",
                "dispatch_id": "TEXT",
                "lifecycle_status": "TEXT",
                "backend_kind": "TEXT",
                "backend_session_id": "TEXT",
                "last_input_at": "TEXT",
                "last_output_at": "TEXT",
                "closed_at": "TEXT",
                "close_reason": "TEXT",
            },
        )
        self._ensure_table_columns(
            connection,
            "dispatches",
            {
                "reply_json": "TEXT",
            },
        )

    def _ensure_table_columns(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        columns: dict[str, str],
    ) -> None:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        column_names = {row["name"] for row in rows}
        for column_name, column_type in columns.items():
            if column_name not in column_names:
                connection.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                )

    def upsert_runtime(
        self,
        *,
        runtime_id: str | None,
        machine_id: str,
        name: str,
        status: str,
        summary: str | None,
        host: str | None,
        base_url: str | None,
        labels: dict[str, Any],
        capabilities: dict[str, Any],
    ) -> dict[str, Any]:
        record_id = runtime_id or str(uuid.uuid4())
        now = utc_now()
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT created_at FROM runtimes WHERE id = ?",
                (record_id,),
            ).fetchone()
            created_at = existing["created_at"] if existing else now
            connection.execute(
                """
                INSERT INTO runtimes (
                    id, machine_id, name, status, summary, host, base_url,
                    labels_json, capabilities_json, last_heartbeat_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    machine_id = excluded.machine_id,
                    name = excluded.name,
                    status = excluded.status,
                    summary = excluded.summary,
                    host = excluded.host,
                    base_url = excluded.base_url,
                    labels_json = excluded.labels_json,
                    capabilities_json = excluded.capabilities_json,
                    last_heartbeat_at = excluded.last_heartbeat_at,
                    updated_at = excluded.updated_at
                """,
                (
                    record_id,
                    machine_id,
                    name,
                    status,
                    summary,
                    host,
                    base_url,
                    _json_dumps(labels),
                    _json_dumps(capabilities),
                    now,
                    created_at,
                    now,
                ),
            )
        return self.get_runtime(record_id)

    def update_runtime_heartbeat(
        self,
        runtime_id: str,
        *,
        status: str,
        summary: str | None,
        labels: dict[str, Any],
        capabilities: dict[str, Any],
    ) -> dict[str, Any] | None:
        current = self.get_runtime(runtime_id)
        if current is None:
            return None
        next_labels = dict(current["labels"])
        next_labels.update(labels)
        next_capabilities = dict(current["capabilities"])
        next_capabilities.update(capabilities)
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE runtimes
                SET status = ?, summary = ?, labels_json = ?, capabilities_json = ?,
                    last_heartbeat_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    summary,
                    _json_dumps(next_labels),
                    _json_dumps(next_capabilities),
                    now,
                    now,
                    runtime_id,
                ),
            )
        return self.get_runtime(runtime_id)

    def list_runtimes(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM runtimes ORDER BY updated_at DESC, created_at DESC"
            ).fetchall()
        return [self._decode_runtime(row) for row in rows]

    def get_runtime(self, runtime_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM runtimes WHERE id = ?",
                (runtime_id,),
            ).fetchone()
        return self._decode_runtime(row) if row else None

    def upsert_agent(
        self,
        *,
        agent_id: str | None,
        runtime_id: str | None,
        machine_id: str | None,
        name: str,
        kind: str,
        host: str | None,
        role: str | None,
        transport: str,
        status: str,
        summary: str | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        record_id = agent_id or str(uuid.uuid4())
        now = utc_now()
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT created_at FROM agents WHERE id = ?",
                (record_id,),
            ).fetchone()
            created_at = existing["created_at"] if existing else now
            connection.execute(
                """
                INSERT INTO agents (
                    id, runtime_id, machine_id, name, kind, host, role, transport, status,
                    summary, metadata_json, last_heartbeat_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    runtime_id = excluded.runtime_id,
                    machine_id = excluded.machine_id,
                    name = excluded.name,
                    kind = excluded.kind,
                    host = excluded.host,
                    role = excluded.role,
                    transport = excluded.transport,
                    status = excluded.status,
                    summary = excluded.summary,
                    metadata_json = excluded.metadata_json,
                    last_heartbeat_at = excluded.last_heartbeat_at,
                    updated_at = excluded.updated_at
                """,
                (
                    record_id,
                    runtime_id,
                    machine_id,
                    name,
                    kind,
                    host,
                    role,
                    transport,
                    status,
                    summary,
                    _json_dumps(metadata),
                    now,
                    created_at,
                    now,
                ),
            )
        return self.get_agent(record_id)

    def update_agent_heartbeat(
        self,
        agent_id: str,
        *,
        status: str,
        summary: str | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any] | None:
        current = self.get_agent(agent_id)
        if current is None:
            return None
        merged = dict(current["metadata"])
        merged.update(metadata)
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE agents
                SET status = ?, summary = ?, metadata_json = ?, last_heartbeat_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, summary, _json_dumps(merged), now, now, agent_id),
            )
        return self.get_agent(agent_id)

    def list_agents(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM agents ORDER BY updated_at DESC, created_at DESC"
            ).fetchall()
        return [self._decode_agent(row) for row in rows]

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        return self._decode_agent(row) if row else None

    def list_runtime_agents(self, runtime_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM agents
                WHERE runtime_id = ?
                ORDER BY updated_at DESC, created_at DESC
                """,
                (runtime_id,),
            ).fetchall()
        return [self._decode_agent(row) for row in rows]

    def create_task(
        self,
        *,
        title: str,
        created_by: str,
        entry_agent_id: str,
        participant_agent_ids: list[str],
        objective: str,
        status: str,
        summary: str | None,
        stage_plan: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        record_id = str(uuid.uuid4())
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks (
                    id, title, status, created_by, entry_agent_id, participant_agents_json,
                    objective, summary, stage_plan_json, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    title,
                    status,
                    created_by,
                    entry_agent_id,
                    _json_dumps({"agent_ids": participant_agent_ids}),
                    objective,
                    summary,
                    _json_dumps(stage_plan),
                    _json_dumps(metadata),
                    now,
                    now,
                ),
            )
        return self.get_task(record_id)

    def list_tasks(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM tasks ORDER BY updated_at DESC, created_at DESC"
            ).fetchall()
        return [self._decode_task(row) for row in rows]

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._decode_task(row) if row else None

    def update_task(
        self,
        task_id: str,
        *,
        status: str | None = None,
        summary: str | None = None,
        entry_agent_id: str | None = None,
        participant_agent_ids: list[str] | None = None,
        objective: str | None = None,
        stage_plan: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        current = self.get_task(task_id)
        if current is None:
            return None
        next_status = status or current["status"]
        next_summary = summary if summary is not None else current["summary"]
        next_entry_agent_id = entry_agent_id if entry_agent_id is not None else current["entry_agent_id"]
        next_participant_agent_ids = (
            participant_agent_ids
            if participant_agent_ids is not None
            else list(current["participant_agent_ids"])
        )
        next_objective = objective if objective is not None else current["objective"]
        next_stage_plan = stage_plan if stage_plan is not None else dict(current["stage_plan"])
        next_metadata = dict(current["metadata"])
        if metadata:
            next_metadata.update(metadata)
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE tasks
                SET status = ?, summary = ?, entry_agent_id = ?, participant_agents_json = ?,
                    objective = ?, stage_plan_json = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    next_status,
                    next_summary,
                    next_entry_agent_id,
                    _json_dumps({"agent_ids": next_participant_agent_ids}),
                    next_objective,
                    _json_dumps(next_stage_plan),
                    _json_dumps(next_metadata),
                    now,
                    task_id,
                ),
            )
        return self.get_task(task_id)

    def create_dispatch(
        self,
        *,
        task_id: str,
        kind: str,
        status: str,
        from_agent_id: str,
        to_agent_id: str,
        parent_dispatch_id: str | None,
        payload: dict[str, Any],
        reply: dict[str, Any] | None,
    ) -> dict[str, Any]:
        record_id = str(uuid.uuid4())
        now = utc_now()
        resolved_at = now if status in {"replied", "failed"} and reply is not None else None
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO dispatches (
                    id, task_id, kind, status, from_agent_id, to_agent_id, parent_dispatch_id,
                    payload_json, reply_json, session_id, accepted_at, resolved_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    task_id,
                    kind,
                    status,
                    from_agent_id,
                    to_agent_id,
                    parent_dispatch_id,
                    _json_dumps(payload),
                    _json_dumps(reply) if reply is not None else None,
                    None,
                    None,
                    resolved_at,
                    now,
                    now,
                ),
            )
        return self.get_dispatch(record_id)

    def list_dispatches(
        self,
        *,
        from_agent_id: str | None = None,
        to_agent_id: str | None = None,
        task_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM dispatches WHERE 1 = 1"
        params: list[Any] = []
        if from_agent_id is not None:
            query += " AND from_agent_id = ?"
            params.append(from_agent_id)
        if to_agent_id is not None:
            query += " AND to_agent_id = ?"
            params.append(to_agent_id)
        if task_id is not None:
            query += " AND task_id = ?"
            params.append(task_id)
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY updated_at DESC, created_at DESC"
        with self.connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._decode_dispatch(row) for row in rows]

    def list_dispatches_for_runtime(
        self,
        runtime_id: str,
        *,
        statuses: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT d.*
            FROM dispatches d
            JOIN agents a ON a.id = d.to_agent_id
            WHERE a.runtime_id = ?
        """
        params: list[Any] = [runtime_id]
        if statuses:
            query += f" AND d.status IN ({','.join('?' for _ in statuses)})"
            params.extend(statuses)
        query += " ORDER BY d.created_at ASC"
        with self.connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._decode_dispatch(row) for row in rows]

    def get_dispatch(self, dispatch_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM dispatches WHERE id = ?",
                (dispatch_id,),
            ).fetchone()
        return self._decode_dispatch(row) if row else None

    def update_dispatch(
        self,
        dispatch_id: str,
        *,
        status: str | None = None,
        payload: dict[str, Any] | None = None,
        reply: dict[str, Any] | None = None,
        session_id: str | None = None,
        accepted: bool | None = None,
        resolved: bool | None = None,
    ) -> dict[str, Any] | None:
        current = self.get_dispatch(dispatch_id)
        if current is None:
            return None
        next_status = status or current["status"]
        next_payload = dict(current["payload"])
        if payload:
            next_payload.update(payload)
        next_reply = dict(current["reply"]) if current["reply"] is not None else None
        if reply is not None:
            next_reply = reply
        next_session_id = session_id if session_id is not None else current["session_id"]
        accepted_at = current["accepted_at"]
        resolved_at = current["resolved_at"]
        now = utc_now()
        if accepted is True and accepted_at is None:
            accepted_at = now
        if resolved is True:
            resolved_at = now
        elif next_status in {"replied", "failed"} and next_reply is not None and resolved_at is None:
            resolved_at = now
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE dispatches
                SET status = ?, payload_json = ?, reply_json = ?, session_id = ?, accepted_at = ?, resolved_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    next_status,
                    _json_dumps(next_payload),
                    _json_dumps(next_reply) if next_reply is not None else None,
                    next_session_id,
                    accepted_at,
                    resolved_at,
                    now,
                    dispatch_id,
                ),
            )
            if next_status in {"replied", "failed"} and next_reply is not None and current["status"] != next_status:
                origin_agent = self.get_agent(current["from_agent_id"])
                if origin_agent is not None and origin_agent.get("runtime_id"):
                    self._create_runtime_inbox_entry(
                        connection,
                        runtime_id=str(origin_agent["runtime_id"]),
                        kind="dispatch_reply",
                        dispatch_id=dispatch_id,
                        payload={
                            "dispatch_id": dispatch_id,
                            "kind": current["kind"],
                            "status": next_status,
                            "reply": next_reply,
                            "from_agent_id": current["from_agent_id"],
                            "to_agent_id": current["to_agent_id"],
                        },
                    )
        return self.get_dispatch(dispatch_id)

    def _create_runtime_inbox_entry(
        self,
        connection: sqlite3.Connection,
        *,
        runtime_id: str,
        kind: str,
        dispatch_id: str,
        payload: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO runtime_inbox (
                id, runtime_id, kind, dispatch_id, payload_json, status, created_at, processed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                runtime_id,
                kind,
                dispatch_id,
                _json_dumps(payload),
                "pending",
                utc_now(),
                None,
            ),
        )

    def create_session(
        self,
        *,
        agent_id: str,
        runtime_id: str | None,
        task_id: str | None,
        dispatch_id: str | None,
        title: str,
        session_key: str | None,
        role: str | None,
        status: str,
        lifecycle_status: str | None,
        summary: str | None,
        workspace_path: str | None,
        codex_home: str | None,
        backend_kind: str | None,
        backend_session_id: str | None,
        machine_id: str | None,
        preset_id: str | None,
        model: str | None,
        initial_prompt: str | None,
    ) -> dict[str, Any]:
        if runtime_id and session_key:
            with self.connect() as connection:
                existing = connection.execute(
                    """
                    SELECT * FROM sessions
                    WHERE runtime_id = ? AND session_key = ? AND status != 'terminated'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (runtime_id, session_key),
                ).fetchone()
            if existing is not None:
                return self._decode_session(existing)
        record_id = str(uuid.uuid4())
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (
                    id, agent_id, runtime_id, task_id, dispatch_id, title, session_key, role, status,
                    lifecycle_status, summary, workspace_path, codex_home, codex_thread_id,
                    backend_kind, backend_session_id, machine_id, preset_id, model, initial_prompt,
                    last_input_at, last_output_at, closed_at, close_reason, created_at, updated_at,
                    last_event_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    agent_id,
                    runtime_id,
                    task_id,
                    dispatch_id,
                    title,
                    session_key,
                    role,
                    status,
                    lifecycle_status or status,
                    summary,
                    workspace_path,
                    codex_home,
                    None,
                    backend_kind,
                    backend_session_id,
                    machine_id,
                    preset_id,
                    model,
                    initial_prompt,
                    None,
                    None,
                    None,
                    None,
                    now,
                    now,
                    None,
                ),
            )
        return self.get_session(record_id)

    def update_session(
        self,
        session_id: str,
        *,
        status: str | None,
        lifecycle_status: str | None,
        summary: str | None,
        codex_thread_id: str | None,
        backend_session_id: str | None,
    ) -> dict[str, Any] | None:
        current = self.get_session(session_id)
        if current is None:
            return None
        now = utc_now()
        next_status = status or current["status"]
        next_lifecycle_status = lifecycle_status or current["lifecycle_status"]
        next_summary = summary if summary is not None else current["summary"]
        next_thread_id = codex_thread_id if codex_thread_id is not None else current["codex_thread_id"]
        next_backend_session_id = (
            backend_session_id if backend_session_id is not None else current["backend_session_id"]
        )
        closed_at = current["closed_at"]
        if next_status == "terminated" and closed_at is None:
            closed_at = now
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE sessions
                SET status = ?, lifecycle_status = ?, summary = ?, codex_thread_id = ?,
                    backend_session_id = ?, closed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    next_status,
                    next_lifecycle_status,
                    next_summary,
                    next_thread_id,
                    next_backend_session_id,
                    closed_at,
                    now,
                    session_id,
                ),
            )
        return self.get_session(session_id)

    def repair_session_states(self) -> int:
        repaired = 0
        with self.connect() as connection:
            sessions = connection.execute(
                """
                SELECT id, status, summary
                FROM sessions
                WHERE status IN ('running', 'launching')
                """
            ).fetchall()
            for session in sessions:
                completed_event = connection.execute(
                    """
                    SELECT payload_json
                    FROM events
                    WHERE session_id = ? AND event_type = 'runtime.command.completed'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (session["id"],),
                ).fetchone()
                if completed_event is None:
                    continue
                payload = json.loads(completed_event["payload_json"])
                return_code = int(payload.get("return_code", 1))
                next_status = "completed" if return_code == 0 else "failed"
                next_summary = (
                    session["summary"]
                    if session["summary"] and session["summary"] != "Codex process running"
                    else f"Codex exited with code {return_code}"
                )
                connection.execute(
                    """
                    UPDATE sessions
                    SET status = ?, summary = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (next_status, next_summary, utc_now(), session["id"]),
                )
                repaired += 1
        return repaired

    def list_sessions(
        self,
        *,
        task_id: str | None = None,
        agent_id: str | None = None,
        dispatch_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM sessions WHERE 1 = 1"
        params: list[Any] = []
        if task_id is not None:
            query += " AND task_id = ?"
            params.append(task_id)
        if agent_id is not None:
            query += " AND agent_id = ?"
            params.append(agent_id)
        if dispatch_id is not None:
            query += " AND dispatch_id = ?"
            params.append(dispatch_id)
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY updated_at DESC, created_at DESC"
        with self.connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._decode_session(row) for row in rows]

    def list_sessions_by_status(self, statuses: list[str]) -> list[dict[str, Any]]:
        placeholders = ",".join("?" for _ in statuses)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM sessions WHERE status IN ({placeholders}) ORDER BY updated_at ASC, created_at ASC",
                tuple(statuses),
            ).fetchall()
        return [self._decode_session(row) for row in rows]

    def list_runtime_launch_queue(self, runtime_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM sessions
                WHERE runtime_id = ? AND status = 'created'
                ORDER BY created_at ASC
                """,
                (runtime_id,),
            ).fetchall()
        return [self._decode_session(row) for row in rows]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return self._decode_session(row) if row else None

    def delete_session(self, session_id: str) -> bool:
        with self.connect() as connection:
            connection.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM session_inputs WHERE session_id = ?", (session_id,))
            cursor = connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            return cursor.rowcount > 0

    def add_event(
        self,
        *,
        session_id: str,
        agent_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        record_id = str(uuid.uuid4())
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO events (id, session_id, agent_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (record_id, session_id, agent_id, event_type, _json_dumps(payload), now),
            )
            connection.execute(
                "UPDATE sessions SET last_event_at = ?, updated_at = ? WHERE id = ?",
                (now, now, session_id),
            )
        return self.list_events(session_id=session_id, limit=1)[0]

    def list_events(self, *, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM events
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [self._decode_event(row) for row in rows]

    def add_message(
        self,
        *,
        session_id: str,
        agent_id: str,
        sender: str,
        direction: str,
        content: str,
        status: str,
    ) -> dict[str, Any]:
        record_id = str(uuid.uuid4())
        now = utc_now()
        delivered_at = now if status == "delivered" else None
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO messages (
                    id, session_id, agent_id, sender, direction, content, status,
                    created_at, updated_at, delivered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    session_id,
                    agent_id,
                    sender,
                    direction,
                    content,
                    status,
                    now,
                    now,
                    delivered_at,
                ),
            )
            if direction == "inbound":
                connection.execute(
                    "UPDATE sessions SET last_output_at = ?, updated_at = ? WHERE id = ?",
                    (now, now, session_id),
                )
        return self.list_messages(session_id=session_id, limit=1)[0]

    def add_session_input(
        self,
        *,
        session_id: str,
        runtime_id: str,
        agent_id: str,
        kind: str,
        sender: str,
        payload: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        record_id = str(uuid.uuid4())
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO session_inputs (
                    id, session_id, runtime_id, agent_id, kind, sender, payload_json,
                    metadata_json, status, error_text, created_at, delivered_at, processed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    session_id,
                    runtime_id,
                    agent_id,
                    kind,
                    sender,
                    _json_dumps(payload),
                    _json_dumps(metadata),
                    "pending",
                    None,
                    now,
                    None,
                    None,
                ),
            )
            connection.execute(
                "UPDATE sessions SET last_input_at = ?, updated_at = ? WHERE id = ?",
                (now, now, session_id),
            )
        return self.get_session_input(record_id)

    def list_runtime_session_inputs(
        self,
        runtime_id: str,
        *,
        status: str = "pending",
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM session_inputs
                WHERE runtime_id = ? AND status = ?
                ORDER BY created_at ASC
                """,
                (runtime_id, status),
            ).fetchall()
        return [self._decode_session_input(row) for row in rows]

    def get_session_input(self, session_input_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM session_inputs WHERE id = ?",
                (session_input_id,),
            ).fetchone()
        return self._decode_session_input(row) if row else None

    def update_session_input(
        self,
        session_input_id: str,
        *,
        status: str,
        error_text: str | None = None,
    ) -> dict[str, Any] | None:
        current = self.get_session_input(session_input_id)
        if current is None:
            return None
        now = utc_now()
        delivered_at = current["delivered_at"]
        processed_at = current["processed_at"]
        if status == "delivered" and delivered_at is None:
            delivered_at = now
        if status in {"processed", "failed"}:
            processed_at = now
            if delivered_at is None:
                delivered_at = now
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE session_inputs
                SET status = ?, error_text = ?, delivered_at = ?, processed_at = ?
                WHERE id = ?
                """,
                (status, error_text, delivered_at, processed_at, session_input_id),
            )
        return self.get_session_input(session_input_id)

    def list_runtime_inbox(
        self,
        runtime_id: str,
        *,
        status: str = "pending",
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM runtime_inbox
                WHERE runtime_id = ? AND status = ?
                ORDER BY created_at ASC
                """,
                (runtime_id, status),
            ).fetchall()
        return [self._decode_runtime_inbox(row) for row in rows]

    def get_runtime_inbox_item(self, item_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM runtime_inbox WHERE id = ?",
                (item_id,),
            ).fetchone()
        return self._decode_runtime_inbox(row) if row else None

    def update_runtime_inbox_item(self, item_id: str, *, status: str) -> dict[str, Any] | None:
        current = self.get_runtime_inbox_item(item_id)
        if current is None:
            return None
        processed_at = current["processed_at"]
        if status == "processed":
            processed_at = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE runtime_inbox
                SET status = ?, processed_at = ?
                WHERE id = ?
                """,
                (status, processed_at, item_id),
            )
        return self.get_runtime_inbox_item(item_id)

    def create_runtime_agent_op(
        self,
        *,
        runtime_id: str,
        agent_id: str,
        op_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        record_id = str(uuid.uuid4())
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO runtime_agent_ops (
                    id, runtime_id, agent_id, op_type, payload_json, status, error_text,
                    created_at, claimed_at, applied_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    runtime_id,
                    agent_id,
                    op_type,
                    _json_dumps(payload),
                    "pending",
                    None,
                    now,
                    None,
                    None,
                    now,
                ),
            )
        return self.get_runtime_agent_op(record_id)

    def list_runtime_agent_ops(
        self,
        runtime_id: str,
        *,
        statuses: list[str] | None = None,
        agent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM runtime_agent_ops WHERE runtime_id = ?"
        params: list[Any] = [runtime_id]
        if agent_id is not None:
            query += " AND agent_id = ?"
            params.append(agent_id)
        if statuses:
            query += f" AND status IN ({','.join('?' for _ in statuses)})"
            params.extend(statuses)
        query += " ORDER BY created_at ASC"
        with self.connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._decode_runtime_agent_op(row) for row in rows]

    def get_runtime_agent_op(self, op_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM runtime_agent_ops WHERE id = ?",
                (op_id,),
            ).fetchone()
        return self._decode_runtime_agent_op(row) if row else None

    def update_runtime_agent_op(
        self,
        op_id: str,
        *,
        status: str,
        error_text: str | None = None,
    ) -> dict[str, Any] | None:
        current = self.get_runtime_agent_op(op_id)
        if current is None:
            return None
        claimed_at = current["claimed_at"]
        applied_at = current["applied_at"]
        now = utc_now()
        if status == "claimed" and claimed_at is None:
            claimed_at = now
        if status == "applied":
            applied_at = now
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE runtime_agent_ops
                SET status = ?, error_text = ?, claimed_at = ?, applied_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    error_text,
                    claimed_at,
                    applied_at,
                    now,
                    op_id,
                ),
            )
        return self.get_runtime_agent_op(op_id)

    def sync_runtime_agent_snapshot(
        self,
        runtime_id: str,
        *,
        shared_skills: list[dict[str, Any]],
        available_models: list[str],
        agents: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        runtime = self.get_runtime(runtime_id)
        if runtime is None:
            return None
        now = utc_now()
        next_capabilities = dict(runtime["capabilities"])
        next_capabilities["agent_management"] = {
            "shared_skills": shared_skills,
            "available_models": available_models,
            "synced_at": now,
        }
        incoming_ids = {str(item["agent_id"]) for item in agents}
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE runtimes
                SET capabilities_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (_json_dumps(next_capabilities), now, runtime_id),
            )
            for snapshot in agents:
                agent_id = str(snapshot["agent_id"])
                existing = connection.execute(
                    "SELECT created_at, kind, host, transport FROM agents WHERE id = ?",
                    (agent_id,),
                ).fetchone()
                created_at = existing["created_at"] if existing else now
                metadata = {
                    "enabled": bool(snapshot.get("enabled", True)),
                    "model": snapshot.get("model"),
                    "agent_md": snapshot.get("agent_md") or "",
                    "avatar_url": snapshot.get("avatar_url"),
                    "enabled_runtime_skills": list(snapshot.get("enabled_runtime_skills") or []),
                    "enabled_agent_skills": list(snapshot.get("enabled_agent_skills") or []),
                    "runtime_skill_inventory": list(snapshot.get("runtime_skill_inventory") or []),
                    "agent_skill_inventory": list(snapshot.get("agent_skill_inventory") or []),
                    "prompt_preview": dict(snapshot.get("prompt_preview") or {}),
                    "role_hint": snapshot.get("role_hint"),
                    "present": bool(snapshot.get("present", True)),
                }
                connection.execute(
                    """
                    INSERT INTO agents (
                        id, runtime_id, machine_id, name, kind, host, role, transport, status,
                        summary, metadata_json, last_heartbeat_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        runtime_id = excluded.runtime_id,
                        machine_id = excluded.machine_id,
                        name = excluded.name,
                        kind = excluded.kind,
                        host = excluded.host,
                        role = excluded.role,
                        transport = excluded.transport,
                        status = excluded.status,
                        summary = excluded.summary,
                        metadata_json = excluded.metadata_json,
                        last_heartbeat_at = excluded.last_heartbeat_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        agent_id,
                        runtime_id,
                        runtime.get("machine_id"),
                        snapshot.get("name") or agent_id,
                        existing["kind"] if existing and existing.get("kind") else "codex",
                        existing["host"] if existing else None,
                        snapshot.get("role_hint"),
                        existing["transport"] if existing and existing.get("transport") else "gateway-http",
                        snapshot.get("status") or "idle",
                        snapshot.get("summary"),
                        _json_dumps(metadata),
                        now,
                        created_at,
                        now,
                    ),
                )
            stale_rows = connection.execute(
                "SELECT * FROM agents WHERE runtime_id = ?",
                (runtime_id,),
            ).fetchall()
            for stale in stale_rows:
                if stale["id"] in incoming_ids:
                    continue
                metadata = json.loads(stale["metadata_json"] or "{}")
                metadata["present"] = False
                connection.execute(
                    """
                    UPDATE agents
                    SET status = ?, summary = ?, metadata_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        "offline",
                        "Agent not present in runtime snapshot",
                        _json_dumps(metadata),
                        now,
                        stale["id"],
                    ),
                )
        return self.get_runtime(runtime_id)

    def ack_message(self, message_id: str, status: str) -> dict[str, Any] | None:
        now = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE messages
                SET status = ?, updated_at = ?, delivered_at = ?
                WHERE id = ?
                """,
                (status, now, now if status == "delivered" else None, message_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_message(message_id)

    def list_messages(
        self,
        *,
        session_id: str,
        limit: int = 50,
        status: str | None = None,
        direction: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM messages WHERE session_id = ?"
        params: list[Any] = [session_id]
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        if direction is not None:
            query += " AND direction = ?"
            params.append(direction)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self.connect() as connection:
            return connection.execute(query, tuple(params)).fetchall()

    def get_message(self, message_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            return connection.execute(
                "SELECT * FROM messages WHERE id = ?",
                (message_id,),
            ).fetchone()

    def list_agent_outbox(self, agent_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT * FROM messages
                WHERE agent_id = ? AND direction = 'outbound' AND status = 'queued'
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (agent_id, limit),
            ).fetchall()

    def _decode_runtime(self, row: dict[str, Any]) -> dict[str, Any]:
        decoded = dict(row)
        decoded["labels"] = json.loads(decoded.pop("labels_json"))
        decoded["capabilities"] = json.loads(decoded.pop("capabilities_json"))
        return decoded

    def _decode_agent(self, row: dict[str, Any]) -> dict[str, Any]:
        decoded = dict(row)
        decoded["metadata"] = json.loads(decoded.pop("metadata_json"))
        return decoded

    def _decode_task(self, row: dict[str, Any]) -> dict[str, Any]:
        decoded = dict(row)
        participant_raw = decoded.pop("participant_agents_json", "[]") or "[]"
        participant_agents = json.loads(participant_raw)
        if isinstance(participant_agents, dict):
            decoded["participant_agent_ids"] = participant_agents.get("agent_ids", [])
        else:
            decoded["participant_agent_ids"] = participant_agents
        decoded["stage_plan"] = json.loads(decoded.pop("stage_plan_json", "{}") or "{}")
        decoded["metadata"] = json.loads(decoded.pop("metadata_json") or "{}")
        return decoded

    def _decode_dispatch(self, row: dict[str, Any]) -> dict[str, Any]:
        decoded = dict(row)
        decoded["payload"] = json.loads(decoded.pop("payload_json") or "{}")
        reply_json = decoded.pop("reply_json", None)
        decoded["reply"] = json.loads(reply_json) if reply_json else None
        return decoded

    def _decode_session(self, row: dict[str, Any]) -> dict[str, Any]:
        return dict(row)

    def _decode_event(self, row: dict[str, Any]) -> dict[str, Any]:
        decoded = dict(row)
        decoded["payload"] = json.loads(decoded.pop("payload_json"))
        return decoded

    def _decode_session_input(self, row: dict[str, Any]) -> dict[str, Any]:
        decoded = dict(row)
        decoded["payload"] = json.loads(decoded.pop("payload_json") or "{}")
        decoded["metadata"] = json.loads(decoded.pop("metadata_json") or "{}")
        return decoded

    def _decode_runtime_inbox(self, row: dict[str, Any]) -> dict[str, Any]:
        decoded = dict(row)
        decoded["payload"] = json.loads(decoded.pop("payload_json") or "{}")
        return decoded

    def _decode_runtime_agent_op(self, row: dict[str, Any]) -> dict[str, Any]:
        decoded = dict(row)
        decoded["payload"] = json.loads(decoded.pop("payload_json") or "{}")
        return decoded
