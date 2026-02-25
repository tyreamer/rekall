# Rekall Quickstart

Get a project reality blackboard running in 5 minutes.

## Prerequisites
- Python 3.10+
- A virtual environment (`venv`) is recommended, or use `pipx`.

## Install

### Windows PowerShell
```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -e .
```

### macOS / Linux bash
```bash
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

*(Optional: Use `pipx install .` for global CLI wrapper usage).*

## 1. Run the Demo
Experience a fully mocked project lifecycle:
```bash
rekall demo
```
Open the `boot_brief.md` printed in the output — this is the handoff your agent would receive.

## 2. Initialize Your Project
```bash
rekall init ./project-state
```

## 3. Preflight Check
```bash
rekall guard --store-dir ./project-state
```

## 4. Validate State
```bash
rekall validate ./project-state --strict
```

## 5. Generate Handoff
```bash
rekall handoff <project_id> --store-dir ./project-state -o ./pack
```
Open `./pack/boot_brief.md`.

## 6. Optional: MCP Server
Start the MCP server to expose the state to agents (like Claude Desktop or Cursor):
```bash
rekall serve --store-dir ./project-state
```
Validate the MCP surface:
```bash
rekall validate --mcp --server-cmd "rekall serve --store-dir ./project-state"
```

## Advanced Operations
- **`rekall checkpoint`**: Save a durable "save game" export of your state.
- **`rekall export`**: Create a portable state artifact snapshot.
- **`rekall import`**: Ingest state updates from another folder idempotently.
- **`rekall features`**: See the capability map and "Not Kanban" philosophy.

## What you just got
- **`project-state/` folder**: A portable ledger of truth (YAML/JSONL files) that agents can read and write.
- **`boot_brief.md`**: An executive summary generated from state, perfect for agent system prompts.
- **Evidence Refs**: All statuses are backed by real decisions, attempts, and timeline events—no more stale Kanban boards.

## Next Steps
- Read [Beta Guide](BETA.md) for what to try and how to report issues.
- Read [Connecting Clients](CONNECTING_CLIENTS.md) to wire up Claude Code, Cursor, or Antigravity.
