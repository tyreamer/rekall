# Project State Layer — Overview (v0.1)

**Status:** Draft (v0.1)  
**What this is:** A **vendor-neutral, portable project state layer** that humans and AI agents can read/write via tools (e.g., MCP) to understand a project, coordinate work, and answer leadership status questions **with evidence**.

This is **not** a replacement for Jira/Notion/GitHub/Slack/Figma. Those remain the systems of record for their domains. The Project State Layer is the **shared “truth surface”** that links out to them, standardizes the missing pieces (attempts/decisions/timeline/env/access pointers), and enables agent coordination.

---

## Why this exists

Modern “agent-driven” building has a coordination gap:

- Context lives in local files, chat logs, and personal kanbans
- New collaborators (human or agent) need repeated re-explanations
- After dormancy, projects become hard to resume
- Leaders can’t reliably ask: “Are we on track? What’s blocking? What changed?” without a manual status ritual

**Project State Layer solves this by making project state explicit, durable, and toolable.**

---

## Core outcomes

1. **Resume after dormancy**  
   Open the state artifact after months and quickly know: goal, scope, environment, access pointers, key decisions, what was tried, current blockers, and next work.

2. **Agent plug-and-play**  
   Spin up an agent anywhere, connect it to the state layer, and it can immediately:
   - find unblocked work
   - claim tasks safely (lease)
   - append attempts and propose decisions
   - generate evidence-backed summaries

3. **Executive status via chat**  
   A director/manager asks a connected agent:  
   “Is this on track?” “What’s blocking?” “What changed since last week?”  
   The agent answers concisely, with confidence and evidence references.

---

## The state artifact

A project’s state is represented as a **State Artifact**. It may be stored locally, remotely, or both. The artifact is designed to be:

- **Portable** (export/import)
- **Human-readable** (YAML/JSONL)
- **Merge-safe** (append-only logs + controlled patches)
- **Auditable** (provenance and diffs)
- **Secret-safe** (references only; never raw credentials)

See: `04_state_spec_schema_v0.1.md` and `02_invariants_and_operating_rules.md`.

---

## Canonical primitives

- **Work Items**: the work graph (tasks/spikes/bugs) agents can pick up  
- **Attempts**: append-only experiment log (prevents loops)  
- **Decisions**: append-only decision log with trade-offs  
- **Timeline**: append-only “what changed” feed  
- **Environment Map**: where it runs + observability links  
- **Access References**: pointers to credentials/accounts (never secrets)  
- **Typed Links**: vendor-neutral references to external systems  
- **Activity/Audit**: immutable provenance of every write

---

## Interfaces

### Tool/API interface (first-class)
The state layer MUST be usable programmatically so agents can act.

Primary contract: `05_mcp_tool_contract_v0.1.md`

### Human interface (secondary)
A UI is a client of the same state, not the source of truth.
MVP UI typically includes: audit trail, Attempts, Decisions, Timeline, Environments/Access.

---

## Positioning: avoid “audit trail clone” confusion

Rekall includes work tracking, but it is **not** “audit trail for agents.”

**Lead with:** project reality / shared execution trail / execution ledger / verifiable AI execution record layer  
**Do not lead with:** “audit trail audit trail”, “task management”, “tickets”, “issue tracker”

The differentiator to demonstrate first is:
- evidence-backed executive queries (status with citations)
- attempt log + decision log (what we tried, why we chose)
- timeline + provenance (what changed, who did it)
- environment + access pointers (how to operate it, without secrets)

A audit trail view can exist later as a client, but it should never be the headline.

---

## Document map (build pre-reqs)

- `01_non_negotiables.md` — what cannot change
- `02_invariants_and_operating_rules.md` — the “laws of physics” (append-only, claims, versions, no secrets)
- `03_executive_status_query_contract.md` — standardized leadership questions + required response shape
- `04_state_spec_schema_v0.1.md` — the portable state artifact schema (files + objects)
- `05_mcp_tool_contract_v0.1.md` — implementation-ready MCP tool contract

---

## What “done” looks like for the POC

A POC is successful when a project can:

- Answer Q1–Q10 executive queries with evidence + confidence
- Prevent duplicate agent work via claim/lease
- Preserve learning via attempts + decisions
- Be resumed quickly after inactivity using only the state artifact

