from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DispatchRoutingStore:
    def __init__(self, state_root: Path) -> None:
        self.state_root = state_root
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.path = self.state_root / "dispatch_routes.json"
        self.outbox_dir = self.state_root / "outbox"
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(
                json.dumps(
                    {
                        "outbound_dispatch_to_session": {},
                        "inbound_dispatch_to_session": {},
                        "session_active_dispatch": {},
                        "session_reply_stack": {},
                        "dispatch_metadata": {},
                    },
                    ensure_ascii=True,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

    def _load(self) -> dict[str, dict[str, object]]:
        return json.loads(self.path.read_text(encoding="utf-8") or "{}")

    def _save(self, payload: dict[str, dict[str, object]]) -> None:
        self.path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def record_outbound(self, dispatch_id: str, session_id: str) -> None:
        payload = self._load()
        payload["outbound_dispatch_to_session"][dispatch_id] = session_id
        self._save(payload)

    def record_inbound(self, dispatch_id: str, session_id: str) -> None:
        payload = self._load()
        payload["inbound_dispatch_to_session"][dispatch_id] = session_id
        payload["session_active_dispatch"][session_id] = dispatch_id
        self._save(payload)

    def outbound_session(self, dispatch_id: str) -> str | None:
        return str(self._load()["outbound_dispatch_to_session"].get(dispatch_id) or "") or None

    def inbound_session(self, dispatch_id: str) -> str | None:
        return str(self._load()["inbound_dispatch_to_session"].get(dispatch_id) or "") or None

    def active_dispatch_for_session(self, session_id: str) -> str | None:
        return str(self._load()["session_active_dispatch"].get(session_id) or "") or None

    def clear_active_dispatch(self, session_id: str, dispatch_id: str) -> None:
        payload = self._load()
        if payload["session_active_dispatch"].get(session_id) == dispatch_id:
            payload["session_active_dispatch"].pop(session_id, None)
            self._save(payload)

    def push_reply_target(self, session_id: str, dispatch_id: str) -> None:
        payload = self._load()
        stack = list(payload["session_reply_stack"].get(session_id) or [])
        stack.append(dispatch_id)
        payload["session_reply_stack"][session_id] = stack
        self._save(payload)

    def peek_reply_target(self, session_id: str) -> str | None:
        stack = list(self._load()["session_reply_stack"].get(session_id) or [])
        return stack[-1] if stack else None

    def pop_reply_target(self, session_id: str, dispatch_id: str) -> None:
        payload = self._load()
        stack = list(payload["session_reply_stack"].get(session_id) or [])
        if stack and stack[-1] == dispatch_id:
            stack.pop()
        else:
            try:
                stack.remove(dispatch_id)
            except ValueError:
                pass
        payload["session_reply_stack"][session_id] = stack
        self._save(payload)

    def record_dispatch_metadata(self, dispatch: dict[str, object]) -> None:
        payload = self._load()
        payload["dispatch_metadata"][str(dispatch["id"])] = {
            "id": dispatch["id"],
            "kind": dispatch.get("kind"),
            "from_agent_id": dispatch.get("from_agent_id"),
            "to_agent_id": dispatch.get("to_agent_id"),
            "parent_dispatch_id": dispatch.get("parent_dispatch_id"),
            "status": dispatch.get("status"),
        }
        self._save(payload)

    def dispatch_metadata(self, dispatch_id: str) -> dict[str, object] | None:
        value = self._load()["dispatch_metadata"].get(dispatch_id)
        return dict(value) if isinstance(value, dict) else None

    def enqueue_command(self, payload: dict[str, object]) -> str:
        command_id = str(uuid.uuid4())
        envelope = {
            "id": command_id,
            "created_at": _utc_now(),
            "payload": payload,
        }
        (self.outbox_dir / f"{command_id}.json").write_text(
            json.dumps(envelope, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return command_id

    def list_pending_commands(self) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        for path in sorted(self.outbox_dir.glob("*.json")):
            items.append(json.loads(path.read_text(encoding="utf-8")))
        return items

    def remove_command(self, command_id: str) -> None:
        path = self.outbox_dir / f"{command_id}.json"
        if path.exists():
            path.unlink()
