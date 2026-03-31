from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .dispatch_store import DispatchRoutingStore


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def _context() -> dict[str, str]:
    return {
        "gateway_url": _required_env("AUTOREP_GATEWAY_URL"),
        "runtime_id": _required_env("AUTOREP_RUNTIME_ID"),
        "session_id": _required_env("AUTOREP_SESSION_ID"),
        "agent_id": _required_env("AUTOREP_AGENT_ID"),
        "task_id": _required_env("AUTOREP_TASK_ID"),
        "state_root": _required_env("AUTOREP_STATE_ROOT"),
    }


def _load_json_file(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dispatch skill CLI for AutoReplication sessions.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    work_order = subparsers.add_parser("work-order")
    work_order.add_argument("--to-agent", required=True)
    work_order.add_argument("--payload-file", required=True)

    clarify = subparsers.add_parser("request-clarify")
    clarify.add_argument("--question", required=True)

    reply = subparsers.add_parser("reply")
    reply.add_argument("--result-file", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    ctx = _context()
    store = DispatchRoutingStore(Path(ctx["state_root"]) / "dispatch")

    if args.command == "work-order":
        command_id = store.enqueue_command(
            {
                "type": "create_dispatch",
                "task_id": ctx["task_id"],
                "kind": "work-order",
                "from_agent_id": ctx["agent_id"],
                "to_agent_id": args.to_agent,
                "status": "pending",
                "payload": _load_json_file(args.payload_file),
                "reply": None,
                "origin_session_id": ctx["session_id"],
            }
        )
        print(json.dumps({"ok": True, "queued_command_id": command_id, "kind": "work-order"}, ensure_ascii=True, indent=2))
        return 0

    if args.command == "request-clarify":
        parent_dispatch_id = store.active_dispatch_for_session(ctx["session_id"])
        if not parent_dispatch_id:
            raise SystemExit("Current session is not handling any dispatch; cannot request clarification")
        parent = store.dispatch_metadata(parent_dispatch_id)
        if parent is None or not parent.get("from_agent_id"):
            raise SystemExit(f"Missing local metadata for parent dispatch {parent_dispatch_id}")
        command_id = store.enqueue_command(
            {
                "type": "create_dispatch",
                "task_id": ctx["task_id"],
                "kind": "clarification-request",
                "from_agent_id": ctx["agent_id"],
                "to_agent_id": str(parent["from_agent_id"]),
                "parent_dispatch_id": parent_dispatch_id,
                "status": "pending",
                "payload": {"question": args.question},
                "reply": None,
                "origin_session_id": ctx["session_id"],
            }
        )
        print(json.dumps({"ok": True, "queued_command_id": command_id, "kind": "clarification-request"}, ensure_ascii=True, indent=2))
        return 0

    target_dispatch_id = store.peek_reply_target(ctx["session_id"])
    if not target_dispatch_id:
        raise SystemExit("Current session has no pending dispatch to reply to")
    command_id = store.enqueue_command(
        {
            "type": "reply_dispatch",
            "dispatch_id": target_dispatch_id,
            "session_id": ctx["session_id"],
            "reply": _load_json_file(args.result_file),
        }
    )
    print(json.dumps({"ok": True, "queued_command_id": command_id, "kind": "reply", "dispatch_id": target_dispatch_id}, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
