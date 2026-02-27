# Rekall Quickstart

Get a verifiable AI execution record running in 5 minutes.

## Prerequisites
- Python 3.10+
- A virtual environment (`venv`) is recommended, or use `pipx`.

## Install

### Task 1 — Run the Demo (~2 min)

```bash
pip install rekall.tools
rekall demo
```

*(Optional: Use `pipx install .` for global CLI wrapper usage).*

## The 5-Minute Tour
Experience the core value of Rekall in under 5 minutes with zero schema knowledge required.

### 1. Initialize
First, let's create a fresh execution ledger and generate an initialization cheat sheet:
```bash
cd /path/to/your-repo
rekall init
```
*(This creates a `project-state/` folder and an initialization cheat sheet)*

### 2. Check the Status
Next, run the executive status command to see the active HEAD, the last attempt, and any unresolved human blockers:
```bash
rekall status
```
*Notice how every claim cites an exact event ID (e.g., `[ID: act-1234abcd]`).*

### 3. Query with Evidence (MCP Tool)
Now, imagine your AI agent wants to know why the last task failed or what policy constraints exist. It can call the `rekall.exec.query` MCP tool with natural language:
```json
// Agent calls MCP tool: rekall.exec.query
{
  "project_id": "your-repo-name",
  "query": "Why did the agent stop? What would have been blocked in prod?"
}
```
Rekall serves the exact execution ledger events back to the agent with strict systemic rules: **The agent MUST cite exact event IDs for every claim.**

The agent will respond with precise, evidence-backed answers:
> "The agent stopped because the database migration failed with a VPC timeout `[ID: att-1b2c3d]`. In production, the attempt to force-delete the database `[ID: act-4x5y6z]` would have been blocked by the shadow policy."

---

## 1. Run the Demo
Experience a fully mocked project lifecycle:
```bash
rekall demo
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
- **`rekall features`**: See the capability map and "Not audit trail" philosophy.

## What you just got
- **`project-state/` folder**: A portable execution ledger of truth (YAML/JSONL files) that agents can read and write.
- **`boot_brief.md`**: An executive summary generated from state, perfect for agent system prompts.
- **Evidence Refs**: All statuses are backed by real decisions, attempts, and timeline events—no more stale audit trail boards.

## Next Steps
- Read [Beta Guide](BETA.md) for what to try and how to report issues.
- Read [Connecting Clients](CONNECTING_CLIENTS.md) to wire up Claude Code, Cursor, or Antigravity.
