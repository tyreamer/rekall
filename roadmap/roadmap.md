# Roadmap (v0.1)

This roadmap keeps future direction separate from the specs so the core contract stays stable.

---

## Phase 0 — POC (prove the thesis)
**Goal:** Show “project truth via agent” with a portable state artifact.

Deliverables:
- State Artifact v0.1 export/import
- Local-first MCP server implementing v0.1 tool contract
- Claim/lease + optimistic concurrency
- Append-only attempts/decisions/timeline/activity
- Executive Status Query Contract implemented via `exec.query`
- Minimal CLI “handoff pack” generator (markdown brief + snapshot)

Success criteria:
- An agent can answer Q1–Q10 with evidence + confidence
- Duplicate work is prevented via claims
- A dormant project can be resumed quickly using only the state artifact

---

## Phase 1 — Beta (make it usable day-to-day)
**Goal:** Add minimal UX and one integration.

Deliverables:
- Lightweight UI client (Board, Attempts, Decisions, Timeline, Envs/Access)
- One read-only integration (GitHub Issues/Projects OR Notion)
- Typed link helper (“add link” guided UI)
- Staleness warnings (freshness checks)
- Improved secret detection and redaction

---

## Phase 2 — Team (collaboration without Git merge pain)
**Goal:** Optional hosted hub for shared truth + permissions.

Deliverables:
- Hosted hub that stores event logs + arbitrates concurrency
- Project-scoped permissions + roles
- Search across projects
- Activity stream + diffs UI
- Notifications (`state.changed`) for real-time updates
- Import/mirror local state artifact ↔ hub (ops-based sync)

---

## Phase 3 — Enterprise (credibility + compliance)
**Goal:** Enterprise-ready control plane features.

Deliverables:
- SSO/SAML/OIDC integration
- Policy controls (who can approve decisions, mark done, break claims)
- Data retention enforcement + export controls
- Audit integrations (SIEM-friendly)
- Higher-trust “status agent” mode (read-only by default)

---

## Phase 4 — Ecosystem (be the substrate)
**Goal:** Become the standard “project truth surface” for agent tools.

Deliverables:
- Public spec evolution (v0.2+)
- More adapters (Jira, Slack threads summarization, Figma boards, etc.)
- Community templates for common project types
- “Attempt dedupe / loop guard” intelligence features (optional)
