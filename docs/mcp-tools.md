# MCP Tool Reference

This page documents the core Model Context Protocol (MCP) tools exposed by the Rekall server. Use these tools to integrate Rekall into your own AI agent systems.

---

## 1. `project.bootstrap`

**Description**: The entry point for any agent session. It ensures the vault is healthy, sets initial metadata, and returns the project status.

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
  "recommendations": ["..."]
}
```

---

## 2. `project.meta.get` / `patch`

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

## 3. `rekall_checkpoint`

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

## 4. `exec.query`

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
