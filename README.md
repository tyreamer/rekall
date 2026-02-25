# Rekall (rekall.io) — Project State Layer

Rekall is a **project reality blackboard + ledger**—the irrefutable truth of what a project is, what failed, and what's blocking.  
*(Note: Rekall includes work tracking, but it is **NOT** "Kanban for agents.")*

It gives humans and AI agents a shared, portable “project brain” that answers:
- What is this project?
- What’s the current status and what’s blocking?
- What’s been tried (and what failed)?
- What decisions/trade-offs were made and why?
- Where is it running, and how do I access it (without storing secrets)?

Rekall **does not replace** Jira/Notion/GitHub/Slack/Figma. It **links out** to them via typed links, while standardizing the missing state that agents and leaders actually need.

---

## Try it

### 3) Try Rekall (Zero-Friction Onboarding)
Run the fully mocked demo lifecycle to feel the magic in 30 seconds:

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
*Note: `rekall demo` creates a temporal snapshot and will print a `cat` command to view the executive handoff. Run that command!*

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
2) [Why Rekall is Not Kanban](docs/WHY_NOT_KANBAN.md)
3) `specs/00_overview.md`  
4) `specs/01_non_negotiables.md`  
5) `specs/02_invariants_and_operating_rules.md`  
6) `specs/03_executive_status_query_contract.md`  
7) `specs/04_state_spec_schema_v0.1.md`  
8) `specs/05_mcp_tool_contract_v0.1.md`

---

## Diagrams

Mermaid diagrams live under `assets/diagrams/`:
- `system_overview.mmd`
- `state_artifact_model.mmd`
- `coordination_flow.mmd`
- `exec_query_flow.mmd`

---

## Positioning (important)

Rekall includes work tracking, but it is **not** “Kanban for agents.”

Rekall is a **project reality blackboard + ledger**. It records the irrefutable truth of what the project is, what was decided, what failed, and what is currently happening. It links out to your Jira, Notion, and Figma, but acts as the unified, machine-readable brain for your AI agents to consult before they act.

- **Lead with:** project reality / shared blackboard / ledger / project memory layer  
- **Avoid leading with:** “Kanban board”, “task management”, “tickets”, “issue tracker”

Your demo should start with **exec Q&A + evidence**, then show attempts/decisions/timeline/env/access pointers.

---

## Idempotency Keys

Idempotency keys let agents deduplicate high-impact, one-shot actions—"send this email once," "run this migration once," "create this ticket once"—without relying on external infrastructure.

**Use when:** your agent might retry a call (crash/network) and the action must only execute once.

**How it works:** if two records share the same `idempotency_key` within the same JSONL file, the second write is a no-op returning the first record. Primary `attempt_id`/`event_id`/`decision_id` dedup still applies.

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

Crashes and lost context are the #1 agent grievance. `rekall checkpoint` is a local-first "save game"—a durable export of project state with a timeline marker so you always know when and why you saved.

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

If you encounter bugs or want to request a feature, please use the provided [GitHub Issue Templates](.github/ISSUE_TEMPLATE/). 
**Note:** For bug reports, you are required to attach the structured diagnostic output locally by running `rekall validate --json` (or `rekall validate --strict --json`). If the issue is MCP-related, please attach the output of `rekall validate --mcp --json`.

### "Unsupported schema version"
Ensure your `schema-version.txt` exists at the root of the state directory and contains exactly `0.1`.

### "Validation failed during initialization"
Rekall enforces structural guarantees on load. If your JSONL files are malformed or missing required IDs, `rekall validate` will output the exact line number of the error. Run `rekall validate --strict --json` to get a structured diagnostic payload to pipe into jq or your agent.

### "Work item is claimed"
If a work item is leased by another actor, you cannot mutate its state. Either wait for the `lease_until` time to expire, or if you hold administrative privileges, use the `force` flag in the API.

---

## Status
POC specs and contracts are at **v0.1** (2026-02-25).
