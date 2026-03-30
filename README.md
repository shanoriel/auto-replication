# AutoReplication

Browser-based control plane and runtime worker for Codex-driven research and experiment sessions.

Please read [DESIGN.md](/Users/shanoriel/Projects/AutoReplication/DESIGN.md) first for the top-level design, then [ROADMAP.md](/Users/shanoriel/Projects/AutoReplication/ROADMAP.md) for the staged implementation plan.

The repository now ships one git repo with two separately launched processes:

- `Gateway`: HTTP API + SQLite + browser UI
- `Runtime`: poll-based worker that registers with the gateway, launches Codex sessions, and reports results back

The long-term product direction is described in [DESIGN.md](/Users/shanoriel/Projects/AutoReplication/DESIGN.md), and the staged delivery path is described in [ROADMAP.md](/Users/shanoriel/Projects/AutoReplication/ROADMAP.md).

## Current Capabilities

- create and inspect tasks, dispatches, sessions, agents, and runtimes through the gateway API
- persist control-plane state in SQLite
- launch `codex exec` from a standalone runtime process
- create sessions automatically from pending dispatches assigned to runtime-owned agents
- capture Codex JSON event output and store it as session events
- capture the final assistant message and store it as an inbound message
- inspect machine catalog and gateway health from the browser UI

## Architecture

The gateway process is pure control plane. It owns:

- the SQLite database
- the HTTP API
- the browser UI
- the catalog

The runtime process is pure execution plane. It owns:

- runtime registration and heartbeat
- agent registration for that runtime
- polling pending dispatches and launch queue entries
- creating or claiming sessions assigned to that runtime
- launching `codex exec`
- reporting events, messages, and completion state back to the gateway

## Repository Layout

```text
AutoReplication/
├── DESIGN.md                # top-level product and architecture design
├── presets/                  # preset-specific AGENTS.md files
├── src/autorep_gateway/      # FastAPI app, DB layer, catalog, gateway entrypoint
├── src/autorep_runtime/      # standalone runtime worker entrypoint
├── static/                   # single-page browser UI
├── ROADMAP.md
├── README.md
└── pyproject.toml
```

Runtime-generated state is intentionally outside git:

- `data/`
- `codex-homes/`
- `workspaces/`

Important generated files include:

- `data/gateway.db`: SQLite database
- `data/catalog.json`: machine, preset, and model catalog generated from defaults on first run unless already present
- `data/sessions/<session-id>/last_message.txt`: captured last assistant message from Codex

## Requirements

- Python 3.11+
- `codex` CLI available on `PATH`
- a usable local Codex home at `~/.codex` if you want auth/config bridged into session-specific `CODEX_HOME`

The project metadata currently declares:

- `fastapi`
- `pydantic`
- `uvicorn`

## Setup

If you are using the existing local environment:

```bash
mamba activate autoreplication
```

Or install the package in editable mode:

```bash
pip install -e .
```

## Run

From the repository root, start the gateway:

```bash
PYTHONPATH=src python -m autorep_gateway
```

Then open:

```text
http://127.0.0.1:11451
```

Then start a runtime in a second terminal:

```bash
PYTHONPATH=src python -m autorep_runtime \
  --gateway-url http://127.0.0.1:11451 \
  --runtime-id mac-mini-runtime \
  --machine-id mac-mini \
  --name "Mac Mini Runtime" \
  --workspace-root /Users/shanoriel/Projects/AutoReplication/workspaces/mac-mini \
  --codex-home-root /Users/shanoriel/Projects/AutoReplication/codex-homes/mac-mini \
  --agent research:research:research-default:gpt-5.4 \
  --agent experiment:experiment:experiment-default:gpt-5.4-mini
```

The default gateway settings live in [`src/autorep_gateway/config.py`](/Users/shanoriel/Projects/AutoReplication/src/autorep_gateway/config.py). The gateway listens on port `11451`, stores state under `data/`, and serves the static UI from `static/`.

## Presets, Machines, and Models

The gateway reads its catalog from `data/catalog.json`. On first startup, it seeds that file from [`src/autorep_gateway/catalog.py`](/Users/shanoriel/Projects/AutoReplication/src/autorep_gateway/catalog.py).

Default seeded entries include:

- machines: `mac-mini`, `hjs-alienware`
- presets: `research-default`, `experiment-default`
- models: `gpt-5.4-mini`, `gpt-5.4`, `gpt-5.4-high`

The catalog seeds machine, preset, and model defaults. A runtime can use those IDs when creating sessions, but ownership and execution are now decided by explicit runtime registration.

## Session File Layout

When a runtime session is launched, the runtime prepares:

- a per-session workspace under `<workspace_path>/sessions/<session-id>`
- a preset-scoped `CODEX_HOME`
- an `AGENTS.md` copied from the selected preset when available
- a preset-specific skills directory under that `CODEX_HOME`

It also bridges selected files from `~/.codex` into the session home:

- `auth.json`
- `config.toml`
- `models_cache.json`
- `version.json`

## Current Gaps

These are still not fully implemented in the current codebase:

- richer dispatch state transitions beyond the MVP loop
- approval-blocked state handling and watchdog logic
- multi-runtime scheduling policy
- automated tests

## Notes

- `CODEX_HOME` is scoped by machine and preset
- session workspaces are isolated per session
- session states can be repaired on process restart if a completion event was already recorded
