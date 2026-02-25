# Rekall (rekall.io) — Project State Layer

Rekall is a **state-first, agent-native project truth layer**.

It gives humans and AI agents a shared, portable “project brain” that answers:
- What is this project?
- What’s the current status and what’s blocking?
- What’s been tried (and what failed)?
- What decisions/trade-offs were made and why?
- Where is it running, and how do I access it (without storing secrets)?

Rekall **does not replace** Jira/Notion/GitHub/Slack/Figma. It **links out** to them via typed links, while standardizing the missing state that agents and leaders actually need.

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

## Quick start (POC)

### 1) Open the sample State Artifact
See: `examples/sample_state_artifact/`

It includes:
- `project.yaml` (goal, constraints, typed links)
- `work-items.jsonl` (work item event stream)
- `attempts.jsonl` (what we tried)
- `decisions.jsonl` (trade-offs)
- `timeline.jsonl` (what changed)
- `envs.yaml` + `access.yaml` (where it runs + access pointers)
- `activity.jsonl` (audit/provenance)
- `schema-version.txt`

### 2) Run a demo conversation
Use:
- `examples/demo_scripts/director_demo.md`
- `examples/demo_scripts/builder_demo.md`
- `examples/demo_scripts/demo_prompt_pack.md`

### 3) Validation & DX
- **Run the CLI**:
  - `rekall validate` (checks invariants and links)
  - `rekall export --out snapshot.json` (creates portable dump)
  - `rekall import snapshot.json` (idempotent ingestion)
  - `rekall handoff <project_id> -o ./pack` (generates `boot_brief.md` + snapshot)
- **Run the tests**: `python -m pytest tests/`
- **Run the local server**: `python -m rekall.server.mcp_server` (reads from stdin/stdout)
- **Run the smoke client** (verifies MCP tool contract): `python scripts/smoke_client.py`

See: `roadmap/poc_acceptance_criteria.md`

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

## Status
POC specs and contracts are at **v0.1** (2026-02-25).
