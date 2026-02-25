# Project State Layer — Non‑Negotiables (v0.1)

**Status:** Locked principles (v0.1)  
**Purpose:** Guardrails that prevent scope drift into “just another PM tool” and ensure the product remains a **state-first, agent-native project truth layer**.

---

## A) Product Non‑Negotiables

### 1) State-first source of truth
- The product is a **canonical project state** (intent + current truth), not just tasks.
- Every project has a single authoritative state view that agents and humans read from.

### 2) Portable “State Artifact” (export/import)
- Each project can be represented as a **portable, human-readable** state artifact.
- You can open it **a year later** and understand: goal, scope, current status, decisions, attempts, research, environments, access pointers.
- Hosted sync is optional; **portability is mandatory**.

### 3) Agent-native interface (tools/MCP semantics)
- Agents must be able to: read project state, list work, claim work, append attempts, propose decisions, update status.
- The tool interface is **first-class**, not an integration afterthought.

### 4) Evidence-first summaries (no vibes)
- Any “status” answer must be backed by **evidence references** (IDs/typed links).
- The system must support “show me why” drill-down by design.

### 5) Append-only truth for churny knowledge
The following are **append-only**:
- attempts
- decisions
- timeline events
- activity/audit provenance

Corrections are handled by appending a correcting record—not editing history.

### 6) Coordination semantics (prevent agent chaos)
- Must support **claim/lease** on work items with renew/release.
- Must prevent silent duplication (two agents doing the same work).
- Coordination rules are explicit, not implied.

### 7) Provenance + audit by default
- Every write is attributable to a **human/agent/system** identity.
- Mutable changes have diffs/history.
- You can answer: “who changed this, when, and why?”

### 8) Never store secrets—only references
- No credentials/tokens/API keys/private keys in the state artifact.
- Only **pointers** (Vault path, 1Password item, Secret Manager name) + “how to request access.”
- Implementations should warn/block likely secrets.

### 9) Vendor-neutral integrations (link out, don’t replace)
- Jira/GitHub/Notion/Slack/Figma are **dependencies**, not competitors.
- Store **typed links** and optional read-only import, but do not force migrations.

### 10) Minimal core, extensible schema
- Core schema stays small and stable.
- Extensions happen via custom fields/tags/typed links.
- Backward compatibility is a rule.

### 11) Clear boundaries: what we are not
We are **not**:
- a code host
- a docs/wiki platform
- a full PM suite
- a chat app

We **are**:
- the vendor-neutral **project truth layer**
- portable project memory
- agent-native coordination substrate

---

## B) Engineering Non‑Negotiables

### 12) Sync is operation/event-based (not “merge arbitrary files”)
- Collaboration sync should operate on **append-only events** + controlled patches.
- Avoid Git-level arbitrary merge complexity as a primary mechanism.

### 13) Deterministic conflict strategy
- Append-only writes are idempotent (dedupe by ID).
- Mutable updates use optimistic concurrency (version/ETag) with explicit conflict responses.
- Never silently overwrite.

### 14) Local-only mode must remain possible
- A single builder must be able to use the system locally without accounts.
- Collaboration is additive, not required.

---

## C) Trust & Safety Non‑Negotiables (enterprise runway)

### 15) Least privilege by default
- Read vs write vs approve permissions.
- Capability-scoped agent keys/tokens.
- Project-scoped access boundaries.

### 16) Data classification & retention hooks
- Support a project-level classification label (public/internal/confidential/restricted).
- Support retention policy hooks without breaking the core.

---

## D) One-sentence statement (use in README)

**Vendor-neutral, portable, evidence-backed project state layer with agent-native coordination—append-only truth, explicit attempts/decisions/timeline, auditable provenance, never secrets, linking out to existing tools.**
