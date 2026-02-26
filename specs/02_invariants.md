# Project State Layer — Invariants & Operating Rules (v0.1)

**Status:** Draft (v0.1)  
**Purpose:** Define the non-negotiable rules that make a “project state layer” durable, agent-native, merge-safe, and trustworthy—without becoming a full PM suite.

This document is intentionally **vendor-neutral** and **repo-structure-neutral**. It describes a **State Artifact** that can live anywhere (next to a repo, in its own directory, synced to a hub, etc.).

---

## 1) Core Concepts

### 1.1 State Artifact
A **State Artifact** is the canonical, portable representation of project state. It must be sufficient to:
- Resume work after long dormancy (“open it in a year”)
- Onboard a new human or agent quickly
- Answer executive status questions with evidence (no vibes)

A State Artifact may be stored:
- Locally (filesystem)
- Remotely (hosted hub)
- Both (local mirror + remote coordination)

### 1.2 State vs. Tasks
This system is **state-first**, not task-first. “Tasks” exist inside state, but the artifact also includes:
- Intent & constraints
- Decisions + trade-offs
- Attempts/experiments + outcomes
- Timeline of meaningful changes
- Environment map (“where is it running?”)
- Access references (never secrets)
- Typed links to external dependencies/tools

### 1.3 Evidence-First
Any summary (e.g., “on track,” “blocked,” “changed”) must be traceable to:
- Work items
- Attempts
- Decisions
- Timeline entries
- Typed links (Jira/GitHub/Notion/Slack/Figma/etc.)

---

## 2) Normative Language
- **MUST**: required for compliance
- **SHOULD**: recommended unless you have a strong reason not to
- **MAY**: optional

---

## 3) Data Classes & Mutability

### 3.1 Append-Only Logs (Merge-Safe Truth)
The following record types are **append-only**. They MUST NOT be edited or deleted in-place:
- Attempts (experiments / trials)
- Decisions (ADR-lite)
- Timeline events
- Activity/Audit events (provenance)

**Rationale:** Append-only records are naturally conflict-resistant and preserve history.

**Corrections:** If something is wrong, append a **Correction** event that references the original record ID (see §7).

### 3.2 Mutable State (Minimized)
Mutable state exists but should be minimized. Typical examples:
- Project metadata (name, goals, constraints, classification)
- Work item current status/fields (todo/in_progress/blocked/done)
- Environment map (URLs, hosting pointers)
- Access references (pointers only)

Mutable edits MUST:
- Produce an Audit/Activity event (§8)
- Use deterministic conflict strategy (optimistic concurrency) (§6)

---

## 4) Identity & IDs (Stability Rules)

### 4.1 Stable IDs
Every entity MUST have a stable ID that never changes:
- `project_id`
- `work_item_id`
- `attempt_id`
- `decision_id`
- `event_id` (timeline)
- `activity_id`
- `link_id`
- `access_ref_id`
- `env_id`

IDs MUST be globally unique within a project, and SHOULD be unique across projects to simplify aggregation.

**Recommended formats:**
- UUIDv7 (time-sortable) or UUIDv4
- Or prefixed IDs (e.g., `WI-...`, `DEC-...`) with strong uniqueness

### 4.2 Actor Identity
Every write MUST be attributable to an **Actor**:
- `actor_type`: `human | agent | system`
- `actor_id`: stable identifier
- optional: `display_name`

Agents SHOULD also include:
- `capabilities` scope (read/write/approve) (see §9)

---

## 5) Time, Ordering, and Determinism

### 5.1 Timestamps
All records MUST include `timestamp` in ISO 8601.

### 5.2 Ordering for Append-Only Logs
Canonical ordering MUST be deterministic:
1) `timestamp`
2) tie-breaker: `id` (lexicographic)

This avoids ambiguity during sync/merge.

### 5.3 “Last Known Good”
Systems MAY track “last known good” states (e.g., last good deploy timestamp) as fields in mutable config, but MUST back them with evidence links where possible.

---

## 6) Concurrency & Conflict Rules (No Git-Level Merge Hell)

### 6.1 Append-Only Writes MUST Be Idempotent
For append-only logs, the system MUST be able to accept retries without duplicates.

**Rule:** If a record with the same ID already exists, the write is a no-op.

### 6.2 Mutable Updates MUST Use Optimistic Concurrency
Mutable objects (especially WorkItems) MUST include a `version` integer (or ETag).

Updates MUST specify `expected_version`.
- If current version != expected_version → reject with conflict.
- Response SHOULD include the latest object snapshot to allow client resolution.

### 6.3 Deterministic Conflict Strategy
When conflicts occur, the system MUST behave predictably. Minimum requirement:
- Reject conflicting writes
- Provide latest snapshot
- Never silently overwrite

---

## 7) Corrections, Superseding, and Deprecation

### 7.1 Corrections (Append-Only)
To correct an append-only record:
- Append a new record of type `correction` (or include `correction_of: <id>`)
- Include reason + corrected fields

Original records MUST remain intact.

### 7.2 Superseding Decisions
Decisions MUST be append-only.
To replace a decision:
- Create a new Decision with `supersedes: <prior_decision_id>`
- Mark prior as `status: superseded` (if you store status)

### 7.3 Deprecating Links/Refs
Links/access refs MAY be deprecated by:
- Adding `status: deprecated` (mutable config), AND
- Appending a timeline note describing replacement

---

## 8) Provenance, Audit, and “Who Changed What”

### 8.1 Every Write Produces an Activity Event
Any mutation or append MUST emit an Activity/Audit record containing:
- `activity_id`
- `actor` (type/id)
- `action` (create/update/claim/release/append/propose/approve)
- `target_type` and `target_id`
- optional: `diff` (field-level changes)
- optional: `reason` (highly recommended)
- `timestamp`

### 8.2 Diff Requirements
For mutable updates, a `diff` SHOULD be recorded.
At minimum:
- field names changed
- before/after values (if safe)
- if sensitive, record “changed” without values

---

## 9) Coordination Semantics (Prevent Agent Chaos)

### 9.1 Claim/Lease Model (Required)
Work items MUST support **claim/lease** to prevent duplicated effort.

A claim MUST include:
- `claimed_by` (actor_id)
- `lease_until` (timestamp)

Default lease SHOULD be 30 minutes.

### 9.2 Claim Rules
- Only the **current claimant** MAY mutate the WorkItem’s mutable fields:
  - status
  - owner
  - priority
  - definition_of_done
  - dependencies
  - core fields that change meaning of the work item
- Non-claimants MAY still append:
  - attempts
  - timeline events
  - comments/notes (if modeled as append-only)

### 9.3 Lease Expiration
- If `lease_until` has passed, anyone MAY claim.
- A claimant MAY renew before expiry.
- A claimant MAY release at any time.

### 9.4 Human Override
A privileged human (or admin) MUST be able to:
- Break a stale claim
- Reassign ownership
- Mark an agent as misbehaving (policy decision)

All overrides MUST be audited.

---

## 10) Secret Handling (Hard Rule)

### 10.1 Never Store Secrets
The State Artifact MUST NOT contain:
- API keys
- tokens
- passwords
- private keys
- session cookies
- raw credentials of any kind

### 10.2 Store References Only
Instead, store **Access References**:
- vault path / secret manager name
- 1Password item link
- cloud account alias/project ID
- role name / group / how to request access

### 10.3 Input Guardrails (Recommended)
Systems SHOULD detect likely secrets (patterns, prefixes, entropy) and:
- block storing the value
- instruct user to move secret to a vault and store a reference

---

## 11) Typed Links (Vendor-Neutral Integration)

### 11.1 Links Must Be Typed
External dependencies MUST be modeled as typed links, not raw URLs.

Minimum fields:
- `link_id`
- `type` (repo/doc/audit trail/dashboard/logs/traces/runbook/demo/etc.)
- `label`
- `url`
- optional: `system` (github/jira/notion/slack/figma/etc.)
- optional: `notes`

### 11.2 “Link Out, Don’t Replace”
Integrations SHOULD:
- link out to source systems
- optionally import read-only metadata
- avoid forcing migration of existing workflows

---

## 12) Executive Status Readiness (Evidence-First Outputs)

### 12.1 Evidence Requirement
Any computed status (“on track”, “at risk”, “blocked”) MUST include:
- confidence (low/med/high)
- evidence references (IDs + typed links)
- the top drivers (“because X, Y, Z”)

### 12.2 No Invented Metrics
Unless explicitly stored, systems MUST NOT claim metrics.
If you compute heuristics (e.g., “blocker older than 7 days”), they MUST be derived from recorded timestamps and fields.

---

## 13) Versioning & Compatibility

### 13.1 Schema Version
The State Artifact MUST declare `schema_version` (e.g., `0.1`).

### 13.2 Backward Compatibility
Readers SHOULD be backward compatible:
- ignore unknown fields
- preserve them on write (don’t delete)
- fail gracefully with actionable errors

### 13.3 Extensibility
The schema SHOULD support:
- custom tags
- custom fields (namespaced)
- additional link types
without breaking core rules.

---

## 14) Local-First + Hosted Sync (Principles)

### 14.1 Local-Only Must Work
A single user MUST be able to use the system locally without any hosted dependency.

### 14.2 Sync Strategy Should Be Operation-Based
Collaboration SHOULD sync:
- append-only events
- controlled patches with optimistic concurrency
not arbitrary file merges.

### 14.3 Idempotent Transport
Sync MUST tolerate retries and partial failures:
- dedupe by IDs
- cursor-based “pull since last” for logs

---

## 15) Minimal Error Semantics (Recommended)
When exposed via an API/MCP server, operations SHOULD use clear error categories:
- `NOT_FOUND` (unknown ID)
- `FORBIDDEN` (insufficient capability)
- `CONFLICT` (version mismatch or claim violation)
- `LEASE_EXPIRED` (claim invalid)
- `VALIDATION_ERROR` (schema invalid)
- `SECRET_DETECTED` (unsafe content)
- `RATE_LIMITED` (optional)

---

## 16) Reference Layout (Non-Binding)
This is a suggested organization for a State Artifact. Implementations MAY vary.

- `project.*` (project identity + constraints)
- `envs.*` (environment map)
- `access.*` (access references)
- `work-items.*` (work graph / work items)
- `attempts.*` (append-only)
- `decisions.*` (append-only)
- `timeline.*` (append-only)
- `activity.*` (append-only)

**Important:** The rules in this doc apply regardless of file names or storage layer.

---

## 17) Compliance Checklist (v0.1)
A project is “v0.1 compliant” if:
- [ ] All entities use stable IDs
- [ ] Attempts/Decisions/Timeline/Activity are append-only
- [ ] Every write emits an Activity/Audit event
- [ ] WorkItems support claim/lease and enforce claim rules
- [ ] Mutable updates use optimistic concurrency
- [ ] Secrets are not stored; only references exist
- [ ] Links are typed
- [ ] Schema version is declared
- [ ] Executive summaries can cite evidence IDs/links

---

## 18) Design Intent (What This Is Not)
This system is NOT:
- a code host
- a docs/wiki platform
- a full PM suite
- a chat app

It IS:
- the **vendor-neutral project truth layer**
- the **portable verifiable AI execution record**
- the **agent-native coordination substrate**