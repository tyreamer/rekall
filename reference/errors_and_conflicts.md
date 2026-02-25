# Errors & Conflicts (v0.1)

This document defines the canonical error codes and conflict behavior for the Project State Layer tooling (including MCP).

The goal is deterministic behavior: **no silent overwrites**, clear remediation steps, and merge-safe logs.

---

## 1) Canonical error codes

### `NOT_FOUND`
The referenced ID does not exist or is not visible to the caller.

**Client action:** verify ID, permissions, or project scope.

---

### `FORBIDDEN`
The caller lacks capability/permission for the operation, or attempted an unauthorized mutation (e.g., modifying a claimed work item).

**Client action:** request permissions or switch to read-only behavior.

---

### `CONFLICT`
Optimistic concurrency failure: `expected_version` does not match current version.

**Client action (recommended):**
1) re-fetch latest object
2) re-apply change as a new patch
3) retry with new `expected_version`

**Server should include:** latest snapshot in error details:
```json
{ "code":"CONFLICT", "details": { "latest": { ...object... } } }
```

---

### `LEASE_EXPIRED`
The work item claim is missing or expired (lease end passed), or caller is not the current claimant.

**Client action:**
- claim the item (if allowed), then retry
- or ask for human override if stale claim is blocking

---

### `VALIDATION_ERROR`
Input failed schema validation or violates invariant rules (missing required fields, invalid enums, bad timestamp).

**Client action:** fix payload and retry.

---

### `SECRET_DETECTED`
Input appears to contain a secret (API key/token/password/private key). Storing it violates invariants.

**Client action:** store secret in vault/secret manager and add an AccessRef pointer instead.

---

### `RATE_LIMITED` (optional)
Server is throttling requests.

**Client action:** backoff and retry.

---

## 2) Idempotency behavior (append-only logs)

For append-only operations (attempts/decisions/timeline/activity):
- if a record with the same ID already exists, the operation MUST be a no-op and return the existing record.

**Rationale:** safe retries and reliable sync.

---

## 3) Conflict philosophy

### 3.1 Append-only rarely conflicts
Because events are appended and idempotent by ID, conflicts are naturally minimized.

### 3.2 Mutable state must be controlled
Mutable objects (work item fields, env/access pointers, project metadata) MUST:
- require `expected_version`
- reject on mismatch (`CONFLICT`)
- never silently overwrite

---

## 4) Claim/lease enforcement rules

- If a work item is claimed and lease is valid:
  - only claimant may mutate work item fields
  - non-claimants may still append attempts/timeline if allowed by capability
- If lease expired:
  - anyone may claim (if authorized)
  - server may treat claim as invalid and return `LEASE_EXPIRED` for mutation attempts

---

## 5) Recommended client UX

### 5.1 On `CONFLICT`
Show a “state changed” message and present:
- what changed (diff)
- latest snapshot
- an option to retry

### 5.2 On `LEASE_EXPIRED`
Present:
- who holds the current claim (if any)
- when it expires
- button: “claim now” (if permitted)

### 5.3 On `SECRET_DETECTED`
Provide a guided path:
- “Move this to Vault/1Password/Secret Manager”
- “Add AccessRef pointer here”

---

## 6) Server response consistency

Servers SHOULD provide:
- error `code`
- human-friendly `message`
- machine-usable `details`

---

## 7) Conflict resolution semantics (v0.1)

The v0.1 POC intentionally avoids Git-style arbitrary file merging. Conflicts are handled deterministically:

### 7.1 Mutable objects (work items, project/env/access config)
- Clients MUST send `expected_version` with updates.
- Server MUST reject on mismatch with `CONFLICT`.
- Server SHOULD include the latest snapshot in error details as `latest`.

**Client remediation (required behavior):**
1) Fetch latest snapshot
2) Re-apply intent as a new patch
3) Retry with updated `expected_version`

### 7.2 Claimed work items
- If a valid lease exists and caller is not the claimant:
  - Server MUST reject with `FORBIDDEN` (or `LEASE_EXPIRED` if lease is expired).
- Admin overrides (if supported) MUST be explicitly requested and audited.

### 7.3 Append-only logs
- Attempts/decisions/timeline/activity MUST be idempotent by record ID.
- Duplicate IDs are treated as no-ops (return existing record).

### 7.4 Patch semantics recommendation
Use merge-patch semantics (RFC 7396-like) and restrict patches to allowed fields.
If a patch tries to modify forbidden fields, return `VALIDATION_ERROR`.
