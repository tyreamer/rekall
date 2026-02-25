# Rekall (rekall.io) — Project State Layer

[![CI](https://github.com/anthropic-labs/rekall/actions/workflows/ci.yml/badge.svg)](https://github.com/anthropic-labs/rekall/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-brightgreen.svg)](https://www.python.org/downloads/)

Rekall is a **ledger for your project state**. It's the shared source of truth that helps you and your AI agents stay on the same page about what's actually happening, what failed, and what's next.

Rekall is NOT "Kanban for agents." (Read: [Why Rekall is Not Kanban](docs/WHY_NOT_KANBAN.md))

---

### Demo

![Rekall demo](assets/demo/rekall_demo.gif)

It's a "project brain" you can share with your agents to answer the hard stuff:
- **What is this?** (Project context)
- **What's the status?** (Are we actually on track?)
- **What's blocking?** (And how do we fix it?)
- **What have we already tried?** (So we don't repeat mistakes)
- **What did we decide?** (The trade-offs and rationale)

Rekall doesn't replace Jira, Notion, or Slack. It **links to them** while providing the machine-readable state that agents actually need to be useful without drifting.

---

## Try it


### 1) See it in action
Run the demo to see how a project lifecycle looks in 30 seconds:

**Using pipx (Recommended for CLI apps):**
```bash
pipx install .
rekall demo
```

**Using venv:**
```bash
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -e .
rekall demo
```
*Note: `rekall demo` creates a temporal snapshot and will print an OS-specific open command (notepad/open/xdg-open) to view the executive handoff. Run that command!*

Once you understand what Rekall does, initialize an empty project state:
```bash
rekall init ./project-state
```
This prepares a fresh artifact directory for your own project.

### Tier 2: “Use it on your own project-state folder”
Once initialized, point the CLI or MCP server at your directory:

- **CLI Operations**:
  - `rekall features` (shows capability map and "Not Kanban" explainer)
  - `rekall status --store-dir ./my-project-state` (quick executive summary)
  - `rekall blockers --store-dir ./my-project-state` (fetch active blockers)
  - `rekall validate --store-dir ./my-project-state` (checks invariants and links)
  - `rekall export --store-dir ./my-project-state --out ./backup-state` (creates a portable state artifact export)
  - `rekall import ./backup-state --store-dir ./my-project-state` (idempotent folder-based ingestion)
  - `rekall handoff <project_id> --store-dir ./my-project-state -o ./pack` (generates `boot_brief.md` + snapshot)

- **MCP Server** (for Claude Desktop): `python -m rekall.server.mcp_server` (reads from stdin/stdout)

### Explore the Samples
- **Sample Artifact**: See `examples/sample_state_artifact/` to see how `project.yaml`, `work-items.jsonl`, `attempts.jsonl`, `decisions.jsonl`, etc., are structured.
- **Demo Scripts**: Check `examples/demo_scripts/` for simulated interactions.
- **Run the tests**: `python -m pytest tests/`
- **Smoke Client**: `python scripts/smoke_client.py` (verifies MCP tool contract)

---

## Repository layout

- `specs/` — the constitution (contracts + schema)
- `reference/` — shared definitions (glossary, link catalog, errors, security)
- `examples/` — sample state artifact + demo scripts + prompt pack
- `assets/` — diagrams (Mermaid)
- `roadmap/` — phases, open questions, design partner plan

---

## Start here (reading order)

1) [Quickstart](docs/QUICKSTART.md)
2) [Beta Guide](docs/BETA.md)
3) [Why Rekall is Not Kanban](docs/WHY_NOT_KANBAN.md)
4) [Connecting Clients](docs/CONNECTING_CLIENTS.md)
5) `specs/00_overview.md`  
6) `specs/01_non_negotiables.md`  
7) `specs/02_invariants_and_operating_rules.md`  
8) `specs/03_executive_status_query_contract.md`  
9) `specs/04_state_spec_schema_v0.1.md`  
10) `specs/05_mcp_tool_contract_v0.1.md`

---

## Diagrams

Mermaid diagrams live under `assets/diagrams/`:
- `system_overview.mmd`
- `state_artifact_model.mmd`
- `coordination_flow.mmd`
- `exec_query_flow.mmd`


---

## Idempotency Keys

Agents crash. Networks fail. Idempotency keys make sure high-impact actions—like sending an email or running a migration—only happen **exactly once**, even if the agent retries.

**How it works:** If you try to write a record with a key that already exists, Rekall just returns the existing record instead of creating a duplicate.

**Example JSON-RPC call:**
```json
{
  "method": "tools/call",
  "params": {
    "name": "attempt.append",
    "arguments": {
      "project_id": "my_project",
      "idempotency_key": "send-deploy-email-v2.1",
      "attempt": { "work_item_id": "wi_1", "title": "Send deploy notification", "outcome": "success" },
      "actor": { "actor_id": "deploy_agent" }
    }
  }
}
```

**CLI:**
```powershell
rekall attempts add wi_1 --title "Deploy email" --evidence "logs/out.log" --idempotency-key "send-deploy-email-v2.1"
rekall timeline add --summary "Migration complete" --idempotency-key "run-migration-001"
```

`rekall validate` warns (or fails with `--strict`) if duplicate idempotency keys are detected in JSONL files.

---

## Naming: State Artifact folder in real projects

**Recommendation:** use `project-state/` as the default folder name in projects.

Why:
- instantly understandable to anyone
- vendor/brand-neutral (better for adoption)
- works whether the tool is Rekall today or something else later

Rekall can still brand the experience (UI, CLI, MCP server, templates) without forcing a branded folder name.

**Optional:** support `.rekall/` as an implementation detail (cache, indexes, local metadata), but keep the canonical artifact folder human-readable and shareable.

---

## Checkpointing

Losing agent context mid-task is painful. `rekall checkpoint` is a "save game" for your project. It creates a durable export of your current state so you can roll back or branch off if things go sideways.

```powershell
# Save a checkpoint before a risky change
rekall checkpoint my_project -o ./checkpoints/pre-deploy --store-dir ./project-state --label "pre-deploy v2.1"

# JSON output for automation
rekall --json checkpoint my_project -o ./checkpoints/pre-deploy --store-dir ./project-state --label "pre-deploy v2.1"
```

Each checkpoint:
1. Exports the full state folder to `<out_dir>` (passes `rekall validate`)
2. Appends a `milestone` timeline event with the label, export path, and evidence ref
3. Supports `--event-id` for idempotent re-runs (same event_id → no duplicate timeline entries)

---

## MCP Self-Check

Verify the MCP server's tool surface is contract-aligned before wiring it into Claude Desktop or any agent runtime:

```bash
# Human-readable report (✅/⚠️/❌ per tool)
rekall validate --mcp --server-cmd "python -m rekall.server.mcp_server"

# Machine-readable JSON
rekall validate --mcp --server-cmd "python -m rekall.server.mcp_server" --json

# Strict mode (non-zero exit on any issue)
rekall validate --mcp --server-cmd "python -m rekall.server.mcp_server" --strict
```

**What it checks:**
- Launches the server as a subprocess (stdio JSON-RPC)
- Calls `tools/list` and verifies all required tool names exist (per `specs/05_mcp_tool_contract_v0.1.md`)
- Validates `inputSchema` is valid JSON Schema (type/object/properties/required)
- Runs safe read-only probe calls (`project.list`, `work.list`, `exec.query ON_TRACK`)

**`--json` output keys:** `ok`, `summary`, `missing_tools`, `schema_errors`, `call_failures`

---

## Troubleshooting

### Reporting Issues

If you find a bug, please use our [GitHub Issue Templates](.github/ISSUE_TEMPLATE/). 

**Note:** To help us debug, please run `rekall validate --json` and attach the output. If it's an MCP issue, use `rekall validate --mcp --json`.

### "Unsupported schema version"
Ensure your `schema-version.txt` exists at the root of the state directory and contains exactly `0.1`.

### "Validation failed during initialization"
Rekall enforces structural guarantees on load. If your JSONL files are malformed or missing required IDs, `rekall validate` will output the exact line number of the error. Run `rekall validate --strict --json` to get a structured diagnostic payload to pipe into jq or your agent.

### "Work item is claimed"
If a work item is leased by another actor, you cannot mutate its state. Either wait for the `lease_until` time to expire, or if you hold administrative privileges, use the `force` flag in the API.

---

## Status
`v0.1.0-beta.1` — Private beta (2026-02-25). See [CHANGELOG.md](CHANGELOG.md) for details.
