# MCP Tool Reference

Rekall exposes 7 tools via the Model Context Protocol. Launch with `rekall serve --store-dir ./project-state`.

---

## `rekall.brief`

One-call session brief. Returns focus, blockers, failed attempts (DO NOT RETRY), pending decisions, and next actions. **Call this at the start of every session.**

```json
// Input: no parameters required
{}
```

The explorer's session gate auto-injects this on the first tool call if the agent forgets.

---

## `rekall.checkpoint`

Record a milestone, task completion, failed attempt, or decision.

```json
{
  "project_id": "string (required)",
  "title": "string (required)",
  "summary": "string",
  "type": "milestone | task_done | decision | attempt_failed",
  "git_commit": "'auto' or specific SHA",
  "tags": ["string"]
}
```

---

## `rekall.attempt`

Record a failed or successful attempt. Future sessions will see DO NOT RETRY warnings.

```json
{
  "title": "string (required) — what was attempted",
  "outcome": "failed | succeeded (default: failed)",
  "evidence": "string — why it failed or evidence of outcome",
  "work_item_id": "string (optional)"
}
```

---

## `rekall.decision`

Propose a decision with rationale and tradeoffs.

```json
{
  "title": "string (required) — the decision",
  "rationale": "string — why this is proposed",
  "tradeoffs": "string — tradeoffs considered"
}
```

---

## `rekall.log`

View recent unified history (checkpoints + attempts + decisions).

```json
{
  "limit": 20
}
```

---

## `rekall.verify`

Verify cryptographic integrity and hash chain of the ledger. Returns per-stream verification status.

```json
{}
```

---

## `rekall.init`

Initialize or repair a Rekall vault. Sets project goals and metadata.

```json
{
  "goal": "string (optional)",
  "phase": "string (optional)",
  "status": "string (optional)",
  "confidence": "number (optional)"
}
```

---

## Session Gate

The MCP server automatically injects the session brief into the first non-brief tool response if the agent hasn't called `rekall.brief` first. This ensures agents always receive execution context, even if they skip the brief step.
