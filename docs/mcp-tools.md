# MCP Tool Reference

This page documents the core Model Context Protocol (MCP) tools exposed by the Rekall server. Use these tools to integrate Rekall into your own AI agent systems.

---

## 1. `session.brief`

**Description**: One-call session brief. Returns everything an agent needs to continue work: current focus, blockers, failed attempts (do not retry), pending decisions, recommended next actions, and drift warnings. Call this at the start of every session.

### Input Schema
```json
{}
```
No parameters required.

### Output Shape
```json
{
  "project": {
    "project_id": "string",
    "goal": "string",
    "phase": "string",
    "status": "string",
    "confidence": "string",
    "constraints": ["string"]
  },
  "mode": "lite | coordination | governed",
  "focus": [{ "work_item_id": "string", "title": "string", "priority": "string" }],
  "blockers": [{ "work_item_id": "string", "title": "string", "blocked_by": ["string"] }],
  "failed_attempts": [{ "attempt_id": "string", "title": "string", "result": "string", "timestamp": "string" }],
  "pending_decisions": [{ "decision_id": "string", "title": "string", "context": "string" }],
  "next_actions": ["string"],
  "recent_completions": [{ "work_item_id": "string", "title": "string" }],
  "drift_warning": "string (optional)"
}
```

---

## 2. `project.bootstrap`

**Description**: Idempotent entry point. Ensures the vault is healthy, sets initial metadata, and returns the project status along with a full session brief.

### Input Schema
```json
{
  "goal": "string (optional)",
  "phase": "string (optional)",
  "status": "string (optional)",
  "confidence": "number (optional)",
  "actor": "object (optional)"
}
```

### Output Shape
```json
{
  "status": "success",
  "message": "Project bootstrapped successfully.",
  "vault_path": "/path/to/project-state",
  "metadata": { "goal": "...", "phase": "...", "status": "..." },
  "session_brief": { "...same shape as session.brief output..." }
}
```

---

## 3. `project.meta.get` / `patch`

**Description**: Read or update the high-level project metadata (Goal, Phase, Status, etc.).

### `project.meta.get` Output
```json
{
  "metadata": {
    "project_id": "rekall",
    "goal": "Build a verifiable execution ledger",
    "phase": "beta",
    "status": "on_track"
  }
}
```

### `project.meta.patch` Input
```json
{
  "patch": { "status": "blocked", "confidence": 0.5 },
  "actor": { "actor_id": "assistant_1" },
  "idempotency_key": "unique_request_id"
}
```

---

## 4. `rekall_checkpoint`

**Description**: The primary tool for syncing progress and decisions to the immutable ledger. It automatically handles Git integration if requested.

### Input Schema
```json
{
  "project_id": "string (required)",
  "type": "string (default: milestone)", // task_done | decision | attempt_failed | artifact | milestone
  "title": "string (optional)",
  "summary": "string (optional)",
  "tags": ["string"],
  "git_commit": "string (optional)", // 'auto' for HEAD, or a specific SHA
  "actor": "object (optional)"
}
```

### Example: Successful Checkpoint
```json
{
  "ok": true,
  "type": "task_done",
  "id": "uuid-1234-5678",
  "git_sha": "a1b2c3d"
}
```

---

## 5. `exec.query`

**Description**: Query the execution ledger using either canonical types or natural language questions.

### Input Schema
```json
{
  "project_id": "string (required)",
  "query_type": "string (optional)", // ON_TRACK | BLOCKERS | RECENT_DECISIONS | FAILED_ATTEMPTS
  "query": "string (optional)", // Natural language question
  "since": "string (optional)" // ISO timestamp
}
```

### Example: Natural Language Query
**Prompt**: `exec.query({ "project_id": "rekall", "query": "Why did the last migration fail?" })`
**Response**: A synthesized summary based on the recent `attempts` and `decisions` logs.
