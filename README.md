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

1) `specs/00_overview.md`  
2) `specs/01_non_negotiables.md`  
3) `specs/02_invariants_and_operating_rules.md`  
4) `specs/03_executive_status_query_contract.md`  
5) `specs/04_state_spec_schema_v0.1.md`  
6) `specs/05_mcp_tool_contract_v0.1.md`

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


## Naming: State Artifact folder in real projects

**Recommendation:** use `project-state/` as the default folder name in projects.

Why:
- instantly understandable to anyone
- vendor/brand-neutral (better for adoption)
- works whether the tool is Rekall today or something else later

Rekall can still brand the experience (UI, CLI, MCP server, templates) without forcing a branded folder name.

**Optional:** support `.rekall/` as an implementation detail (cache, indexes, local metadata), but keep the canonical artifact folder human-readable and shareable.

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

### "Unsupported schema version"
Ensure your `schema-version.txt` exists at the root of the state directory and contains exactly `0.1`.

### "Validation failed during initialization"
Rekall enforces structural guarantees on load. If your JSONL files are malformed or missing required IDs, `rekall validate` will output the exact line number of the error. Run `rekall validate --strict --json` to get a structured diagnostic payload to pipe into jq or your agent.

### "Work item is claimed"
If a work item is leased by another actor, you cannot mutate its state. Either wait for the `lease_until` time to expire, or if you hold administrative privileges, use the `force` flag in the API.

---

## Status
POC specs and contracts are at **v0.1** (2026-02-25).
