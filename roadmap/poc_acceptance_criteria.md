# POC Acceptance Criteria (v0.1)

This checklist defines what “POC is done” means for Rekall.

A POC is successful when a project can be resumed quickly and a chat agent can answer executive questions with evidence—without race conditions, overwrites, or secret leakage.

---

## A) State Artifact compliance

- [ ] State Artifact exports/imports cleanly
- [ ] `schema-version.txt` is present and equals `0.1`
- [ ] `project.yaml`, `envs.yaml`, `access.yaml` parse successfully
- [ ] JSONL files are newline-delimited (one JSON object per line)

---

## B) Invariants enforced

### Append-only logs
- [ ] Attempts are append-only (no edits/deletes)
- [ ] Decisions are append-only (superseding handled via new decision)
- [ ] Timeline is append-only
- [ ] Activity/Audit is append-only

### Idempotency
- [ ] `attempt.append` is idempotent by `attempt_id`
- [ ] `decision.propose` is idempotent by `decision_id`
- [ ] `timeline.append` is idempotent by `event_id`
- [ ] Writes can be retried without duplicate records

### Secrets
- [ ] Server rejects secret-like inputs with `SECRET_DETECTED`
- [ ] `access.yaml` stores pointers only (vault path/secret name/account alias)
- [ ] No secrets appear in diffs/audit events

---

## C) Coordination & concurrency

### Claim/lease
- [ ] Work items support claim/lease (`work.claim`, `work.renew_claim`, `work.release_claim`)
- [ ] Non-claimant `work.update` is rejected (FORBIDDEN/LEASE_EXPIRED)
- [ ] Lease expiry behaves deterministically (expired leases can be reclaimed)
- [ ] Admin override (optional for POC) is audited if used

### Optimistic concurrency
- [ ] Mutable updates require `expected_version`
- [ ] Version mismatch returns `CONFLICT` with latest snapshot in error details
- [ ] Server never silently overwrites

---

## D) Executive Status Query Contract (Q1–Q10)

For each query type:
- [ ] Response includes 1–3 summary bullets
- [ ] Response includes `confidence` (low/medium/high)
- [ ] Response includes 3–10 evidence references (IDs/typed links)
- [ ] If data is missing, response says so and confidence is low
- [ ] No invented metrics

Minimum queries to pass POC:
- [ ] ON_TRACK
- [ ] BLOCKERS
- [ ] CHANGED_SINCE
- [ ] NEXT_7_DAYS
- [ ] RECENT_DECISIONS
- [ ] FAILED_ATTEMPTS
- [ ] WHERE_RUNNING_ACCESS
- [ ] RESUME_IN_30

---

## E) Audit/provenance

- [ ] Every write emits an ActivityEvent with actor + action + target
- [ ] Audit events are append-only and ordered deterministically
- [ ] Audit provides enough info to answer: “who changed this, when, and why?”

---

## F) Demo readiness

- [ ] Director demo script runs end-to-end without manual explanation
- [ ] Builder demo can claim work, append attempt, propose decision
- [ ] Sample state artifact produces believable outputs with evidence refs

---

## G) POC “win condition”

The POC passes when:
- A director can ask: “Are we on track?” and get an evidence-backed answer, and
- A builder can resume the project after dormancy using only the state artifact, and
- An agent can safely pick work without stepping on others (claim/lease + versions).


## H) Positioning guard (avoid “Kanban clone”)

- [ ] Demos do **not** lead with a “board/kanban/task management” framing.
- [ ] Director demo starts with **exec Q&A** (evidence-first), not a board view.
- [ ] Demo highlights attempts + decisions + timeline + env/access pointers as first-class state.

