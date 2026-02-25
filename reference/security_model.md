# Security Model (v0.1)

This document defines baseline security requirements that keep the Project State Layer safe for individuals today and credible for enterprise adoption later.

---

## 1) Principles

### 1.1 Least privilege
Default to read-only. Elevate permissions only when necessary.

### 1.2 Project-scoped access
Permissions must be scoped at least by `project_id`. Avoid global “all projects” access unless explicit.

### 1.3 Auditability
Every write is attributable to an actor and recorded in append-only audit logs.

### 1.4 No secrets in state
The state layer stores **references** to secrets, never secret values.

---

## 2) Actor types

- `human`: real user
- `agent`: automation client / LLM agent
- `system`: server-side system actor

Every write must include `actor_type` and `actor_id`.

---

## 3) Capabilities (minimum set)

Recommended capabilities for v0.1:

- `read`
- `write_work_items`
- `append_logs` (attempts/timeline/activity)
- `propose_decisions`
- `approve_decisions`
- `admin_override` (break claims, force updates)

Servers MUST enforce these capabilities. If not authorized, return `FORBIDDEN`.

---

## 4) Approval gates

For safety:
- agents may **propose** decisions
- humans (or privileged actors) **approve** decisions
- marking work items “done” may be restricted to humans or claimants depending on policy

All approvals must be audited.

---

## 5) Claim/lease + safety

Claim/lease reduces accidental or adversarial chaos:
- prevents two agents from mutating the same work item
- creates predictable ownership for changes
- supports time-bounded automation

Admins must be able to break stale claims (audited).

---

## 6) Secret protection

### 6.1 Hard rule
Never store secrets:
- keys, tokens, passwords, private keys, session cookies, etc.

### 6.2 AccessRefs only
Store:
- vault path / secret name
- account alias
- role/group name
- access request steps

### 6.3 Detection (recommended)
Servers should scan inputs and reject likely secrets:
- common prefixes (e.g., `AKIA`, `ghp_`, `xoxb-`)
- high entropy strings
- PEM key markers

Return `SECRET_DETECTED`.

---

## 7) Data classification & retention

Projects should declare:
- `data_classification` (public/internal/confidential/restricted)
- `retention_policy` (none/30d/180d/1y/custom)

The server should enforce policy where applicable (especially for hosted mode).

---

## 8) Logging and privacy

- Audit logs should avoid storing sensitive data in diffs.
- If a diff includes sensitive fields, store only “changed” markers, not values.
- Consider redaction rules per field for hosted mode.

---

## 9) Threat model notes (POC)

Common risks:
- agent writes incorrect status/decisions → mitigated by approval gates + evidence-first rules
- secret leakage via user paste → mitigated by detection + references-only policy
- accidental overwrites → mitigated by optimistic concurrency + claims + audit

This baseline is sufficient for early pilots; enterprise deployment adds SSO, centralized policy, and stronger tenant isolation.
