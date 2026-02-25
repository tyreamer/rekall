# Project State Layer — MCP Tool Contract (v0.1)

**Status:** Draft (v0.1)  
**Purpose:** Implementation-ready tool contract for an MCP server that exposes a **Project State Layer** (portable project memory + coordination semantics) to chat agents and other clients.

This contract is designed to satisfy the **Invariants & Operating Rules** and the **Executive Status Query Contract** you already defined.

---

## 0) Contract Versioning

- `contract_version`: **0.1**
- Backward compatibility rule: servers **SHOULD** ignore unknown fields and preserve them on write (do not delete).
- Schema version rule: each project **MUST** declare `schema_version` (e.g., `0.1`).

---

## 1) MCP Integration Model (How this maps to MCP)

In MCP, clients discover tools via `tools/list`, then invoke them via `tools/call`.  
This document defines the **tool names**, **inputs**, **outputs**, **error semantics**, and **behavioral rules**.

> Notes:
> - This contract does not require the server to expose raw files. It exposes **structured objects** and **append-only events**.
> - A server MAY also expose `resources/*` (e.g., `state://project/<id>/snapshot`) but that is optional in v0.1.

---

## 2) Identity, Actor, Permissions

### 2.1 Actor

All **write** operations MUST include an `actor`. Read operations MAY include it.

```json
{
  "actor_type": "human | agent | system",
  "actor_id": "string",
  "display_name": "string (optional)"
}
```

### 2.2 Capabilities

Servers MUST enforce capability checks. Minimum set:

- `read`
- `write_work_items`
- `append_logs` (attempts/timeline/activity)
- `propose_decisions`
- `approve_decisions`
- `admin_override` (break claims, force updates)

How capabilities are assigned is implementation-specific (session identity, token, config file, etc.).  
If a caller lacks permission, return `FORBIDDEN`.

---

## 3) Common Types (Used Across Tools)

### 3.1 EvidenceRef

```json
{
  "kind": "project | work_item | attempt | decision | timeline | link | env | access_ref | activity",
  "id": "string",
  "note": "string (optional)"
}
```

### 3.2 Typed Link

```json
{
  "link_id": "string",
  "type": "repo | board | doc | dashboard | logs | traces | alerting | design | dataset | ticketing | runbook | demo | domain | model | mcp_server | notebook | other",
  "label": "string",
  "url": "string",
  "system": "github | jira | notion | slack | figma | datadog | sentry | gcp | aws | azure | cloudflare | other (optional)",
  "notes": "string (optional)",
  "status": "active | deprecated (optional)"
}
```

### 3.3 WorkItem Claim

```json
{
  "claimed_by": "string",
  "lease_until": "string (ISO 8601 timestamp)"
}
```

### 3.4 Error Object (Standard)

Tools should return errors in MCP error form. The **error `data`** SHOULD include:

```json
{
  "code": "NOT_FOUND | FORBIDDEN | CONFLICT | LEASE_EXPIRED | VALIDATION_ERROR | SECRET_DETECTED | RATE_LIMITED",
  "message": "string",
  "details": { "any": "object" }
}
```

---

## 4) Behavioral Rules (Normative)

### 4.1 Append-only tools are idempotent
For `attempt.append`, `decision.propose`, `timeline.append`, `activity.append`:
- If the same record ID already exists, the operation MUST be a no-op and return the existing record.

### 4.2 Mutable updates use optimistic concurrency
For `work.update`, `env.upsert`, `access.upsert`, `project.update`:
- MUST require `expected_version`
- MUST reject with `CONFLICT` if versions differ
- MUST return latest snapshot in error `details.latest`

### 4.3 Claim/lease is enforced
- Only the current claimant may mutate a WorkItem’s mutable fields.
- Claim operations are themselves mutations and MUST be audited.

### 4.4 Secrets are rejected
Servers MUST reject attempts to store secrets with `SECRET_DETECTED`.  
State stores **references only** (Vault paths, 1Password item links, Secret Manager names, etc.).

---

## 5) Tools Overview

### Core Reads
- `project.get`
- `project.list`
- `work.get`
- `work.list`
- `attempt.list`
- `decision.list`
- `timeline.list`
- `activity.list`
- `env.list`
- `access.list`

### Core Writes (Coordination + Logs)
- `work.create`
- `work.update`
- `work.claim`
- `work.renew_claim`
- `work.release_claim`
- `attempt.append`
- `decision.propose`
- `decision.approve` (optional for MVP; keep contract)
- `timeline.append`

### Executive Query (POC leverage)
- `exec.query` (implements your Executive Status Query Contract response shape)

---

## 6) Tool Definitions (Input/Output Schemas)

Below are MCP-friendly definitions: each tool provides an `inputSchema` (JSON Schema) and the response payload.

### 6.1 `project.list`

**Description:** List projects visible to caller.

```json
{
  "type": "object",
  "properties": {
    "limit": { "type": "integer", "minimum": 1, "maximum": 200, "default": 50 },
    "cursor": { "type": "string" },
    "tag": { "type": "string" },
    "updated_since": { "type": "string", "description": "ISO timestamp" }
  },
  "additionalProperties": false
}
```

**Returns:**
```json
{
  "items": [
    {
      "project_id": "string",
      "name": "string",
      "one_liner": "string",
      "schema_version": "string",
      "updated_at": "string"
    }
  ],
  "next_cursor": "string (optional)"
}
```

---

### 6.2 `project.get`

**Description:** Get a project’s canonical metadata + high-level links.

```json
{
  "type": "object",
  "required": ["project_id"],
  "properties": {
    "project_id": { "type": "string" },
    "include": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": ["summary", "links", "constraints", "owners", "classification"]
      },
      "default": ["summary", "links", "constraints", "owners", "classification"]
    }
  },
  "additionalProperties": false
}
```

**Returns:**
```json
{
  "project": {
    "project_id": "string",
    "schema_version": "0.1",
    "version": 1,
    "name": "string",
    "one_liner": "string",
    "current_goal": "string",
    "phase": "discovery|mvp|build|harden|launch|maintain",
    "status": "on_track|at_risk|off_track|paused",
    "confidence": "low|medium|high",
    "non_goals": [],
    "constraints": {},
    "data_classification": "public|internal|confidential|restricted",
    "retention_policy": "none|30d|180d|1y|custom",
    "typed_links": [],
    "owners": {},
    "updated_at": "string"
  }
}
```

---

### 6.3 `project.update`

**Description:** Update mutable project metadata (minimal surface).

```json
{
  "type": "object",
  "required": ["project_id", "expected_version", "patch", "actor"],
  "properties": {
    "project_id": { "type": "string" },
    "expected_version": { "type": "integer", "minimum": 0 },
    "patch": { "type": "object", "description": "Partial update (RFC 7396-like merge patch semantics recommended)" },
    "actor": { "$ref": "#/definitions/Actor" },
    "reason": { "type": "string" }
  },
  "additionalProperties": false,
  "definitions": {
    "Actor": {
      "type": "object",
      "required": ["actor_type", "actor_id"],
      "properties": {
        "actor_type": { "type": "string", "enum": ["human", "agent", "system"] },
        "actor_id": { "type": "string" },
        "display_name": { "type": "string" }
      },
      "additionalProperties": false
    }
  }
}
```

**Returns:**
```json
{ "project": { "...": "updated project", "version": 2 } }
```

Errors: `CONFLICT`, `FORBIDDEN`, `VALIDATION_ERROR`

---

## Work Items

### 6.4 `work.list`

**Description:** List work items with filters.

```json
{
  "type": "object",
  "required": ["project_id"],
  "properties": {
    "project_id": { "type": "string" },
    "limit": { "type": "integer", "minimum": 1, "maximum": 500, "default": 100 },
    "cursor": { "type": "string" },
    "status": {
      "type": "array",
      "items": { "type": "string", "enum": ["todo", "in_progress", "blocked", "done", "parked"] }
    },
    "type": {
      "type": "array",
      "items": { "type": "string", "enum": ["task", "bug", "spike", "research", "decision_needed", "chore"] }
    },
    "priority": {
      "type": "array",
      "items": { "type": "string", "enum": ["p0", "p1", "p2", "p3"] }
    },
    "tag": { "type": "string" },
    "owner": { "type": "string" },
    "claimed_by": { "type": "string" },
    "blocked_only": { "type": "boolean" },
    "updated_since": { "type": "string", "description": "ISO timestamp" }
  },
  "additionalProperties": false
}
```

**Returns:**
```json
{
  "items": [
    {
      "work_item_id": "string",
      "type": "task",
      "title": "string",
      "status": "todo",
      "priority": "p1",
      "owner": "string",
      "claim": { "claimed_by": "string", "lease_until": "string" },
      "version": 3,
      "updated_at": "string"
    }
  ],
  "next_cursor": "string (optional)"
}
```

---

### 6.5 `work.get`

```json
{
  "type": "object",
  "required": ["project_id", "work_item_id"],
  "properties": {
    "project_id": { "type": "string" },
    "work_item_id": { "type": "string" },
    "include": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": ["core", "definition_of_done", "dependencies", "evidence_links", "history_stub"]
      },
      "default": ["core", "definition_of_done", "dependencies", "evidence_links"]
    }
  },
  "additionalProperties": false
}
```

**Returns:**
```json
{
  "work_item": {
    "work_item_id": "string",
    "version": 3,
    "type": "task",
    "title": "string",
    "intent": "string",
    "definition_of_done": ["..."],
    "status": "in_progress",
    "priority": "p1",
    "tags": ["..."],
    "owner": "string",
    "claim": { "claimed_by": "string", "lease_until": "string" },
    "dependencies": { "blocked_by": ["..."], "blocks": ["..."] },
    "evidence_links": [],
    "created_at": "string",
    "updated_at": "string"
  }
}
```

---

### 6.6 `work.create`

**Description:** Create a new work item. Server MAY generate ID if omitted, but clients SHOULD provide it.

```json
{
  "type": "object",
  "required": ["project_id", "work_item", "actor"],
  "properties": {
    "project_id": { "type": "string" },
    "work_item": {
      "type": "object",
      "required": ["type", "title", "intent", "status", "priority"],
      "properties": {
        "work_item_id": { "type": "string" },
        "type": { "type": "string", "enum": ["task", "bug", "spike", "research", "decision_needed", "chore"] },
        "title": { "type": "string" },
        "intent": { "type": "string" },
        "definition_of_done": { "type": "array", "items": { "type": "string" } },
        "status": { "type": "string", "enum": ["todo", "in_progress", "blocked", "done", "parked"] },
        "priority": { "type": "string", "enum": ["p0", "p1", "p2", "p3"] },
        "tags": { "type": "array", "items": { "type": "string" } },
        "owner": { "type": "string" },
        "dependencies": {
          "type": "object",
          "properties": {
            "blocked_by": { "type": "array", "items": { "type": "string" } },
            "blocks": { "type": "array", "items": { "type": "string" } }
          },
          "additionalProperties": false
        },
        "evidence_links": { "type": "array", "items": { "type": "object" } }
      },
      "additionalProperties": false
    },
    "actor": { "$ref": "#/definitions/Actor" },
    "reason": { "type": "string" }
  },
  "additionalProperties": false,
  "definitions": {
    "Actor": {
      "type": "object",
      "required": ["actor_type", "actor_id"],
      "properties": {
        "actor_type": { "type": "string", "enum": ["human", "agent", "system"] },
        "actor_id": { "type": "string" },
        "display_name": { "type": "string" }
      },
      "additionalProperties": false
    }
  }
}
```

**Returns:** `{ "work_item": { ... , "version": 1 } }`

---

### 6.7 `work.update`

**Description:** Update a work item (mutable fields only). Enforces claim + version.

```json
{
  "type": "object",
  "required": ["project_id", "work_item_id", "expected_version", "patch", "actor"],
  "properties": {
    "project_id": { "type": "string" },
    "work_item_id": { "type": "string" },
    "expected_version": { "type": "integer", "minimum": 0 },
    "patch": { "type": "object", "description": "Merge patch recommended; server validates allowed fields" },
    "actor": { "$ref": "#/definitions/Actor" },
    "reason": { "type": "string" },
    "force": { "type": "boolean", "default": false, "description": "Requires admin_override capability" }
  },
  "additionalProperties": false,
  "definitions": {
    "Actor": {
      "type": "object",
      "required": ["actor_type", "actor_id"],
      "properties": {
        "actor_type": { "type": "string", "enum": ["human", "agent", "system"] },
        "actor_id": { "type": "string" },
        "display_name": { "type": "string" }
      },
      "additionalProperties": false
    }
  }
}
```

**Behavior:**
- If `force=false`, caller must hold the active claim (or work item is unclaimed).
- If claim exists and caller isn’t claimant → `FORBIDDEN` (or `LEASE_EXPIRED` if expired).
- If version mismatch → `CONFLICT` with latest snapshot.

**Returns:** `{ "work_item": { ... , "version": 4 } }`

---

### 6.8 `work.claim`

**Description:** Claim a work item with a lease. Mutates item.

```json
{
  "type": "object",
  "required": ["project_id", "work_item_id", "expected_version", "actor"],
  "properties": {
    "project_id": { "type": "string" },
    "work_item_id": { "type": "string" },
    "expected_version": { "type": "integer", "minimum": 0 },
    "lease_seconds": { "type": "integer", "minimum": 60, "maximum": 86400, "default": 1800 },
    "actor": { "$ref": "#/definitions/Actor" },
    "force": { "type": "boolean", "default": false, "description": "Break existing claim; requires admin_override" },
    "reason": { "type": "string" }
  },
  "additionalProperties": false,
  "definitions": {
    "Actor": {
      "type": "object",
      "required": ["actor_type", "actor_id"],
      "properties": {
        "actor_type": { "type": "string", "enum": ["human", "agent", "system"] },
        "actor_id": { "type": "string" },
        "display_name": { "type": "string" }
      },
      "additionalProperties": false
    }
  }
}
```

**Returns:** `{ "work_item": { ... , "claim": { ... }, "version": 5 } }`

Errors: `CONFLICT`, `FORBIDDEN`, `LEASE_EXPIRED`

---

### 6.9 `work.renew_claim`

```json
{
  "type": "object",
  "required": ["project_id", "work_item_id", "expected_version", "actor"],
  "properties": {
    "project_id": { "type": "string" },
    "work_item_id": { "type": "string" },
    "expected_version": { "type": "integer", "minimum": 0 },
    "lease_seconds": { "type": "integer", "minimum": 60, "maximum": 86400, "default": 1800 },
    "actor": { "$ref": "#/definitions/Actor" },
    "reason": { "type": "string" }
  },
  "additionalProperties": false,
  "definitions": {
    "Actor": {
      "type": "object",
      "required": ["actor_type", "actor_id"],
      "properties": {
        "actor_type": { "type": "string", "enum": ["human", "agent", "system"] },
        "actor_id": { "type": "string" },
        "display_name": { "type": "string" }
      },
      "additionalProperties": false
    }
  }
}
```

Behavior: caller must be current claimant (unless admin override).

---

### 6.10 `work.release_claim`

```json
{
  "type": "object",
  "required": ["project_id", "work_item_id", "expected_version", "actor"],
  "properties": {
    "project_id": { "type": "string" },
    "work_item_id": { "type": "string" },
    "expected_version": { "type": "integer", "minimum": 0 },
    "actor": { "$ref": "#/definitions/Actor" },
    "reason": { "type": "string" },
    "force": { "type": "boolean", "default": false, "description": "Requires admin_override" }
  },
  "additionalProperties": false,
  "definitions": {
    "Actor": {
      "type": "object",
      "required": ["actor_type", "actor_id"],
      "properties": {
        "actor_type": { "type": "string", "enum": ["human", "agent", "system"] },
        "actor_id": { "type": "string" },
        "display_name": { "type": "string" }
      },
      "additionalProperties": false
    }
  }
}
```

---

## Attempts (Append-only)

### 6.11 `attempt.append`

```json
{
  "type": "object",
  "required": ["project_id", "attempt", "actor"],
  "properties": {
    "project_id": { "type": "string" },
    "attempt": {
      "type": "object",
      "required": ["hypothesis", "action_taken", "result", "conclusion"],
      "properties": {
        "attempt_id": { "type": "string", "description": "Client-generated strongly recommended (idempotency)" },
        "work_item_id": { "type": "string" },
        "hypothesis": { "type": "string" },
        "action_taken": { "type": "string" },
        "result": { "type": "string" },
        "conclusion": { "type": "string" },
        "next_step": { "type": "string" },
        "artifacts": { "type": "array", "items": { "type": "object" } },
        "timestamp": { "type": "string" }
      },
      "additionalProperties": false
    },
    "actor": { "$ref": "#/definitions/Actor" },
    "reason": { "type": "string" }
  },
  "additionalProperties": false,
  "definitions": {
    "Actor": {
      "type": "object",
      "required": ["actor_type", "actor_id"],
      "properties": {
        "actor_type": { "type": "string", "enum": ["human", "agent", "system"] },
        "actor_id": { "type": "string" },
        "display_name": { "type": "string" }
      },
      "additionalProperties": false
    }
  }
}
```

**Returns:** `{ "attempt": { ... } }`

---

### 6.12 `attempt.list`

```json
{
  "type": "object",
  "required": ["project_id"],
  "properties": {
    "project_id": { "type": "string" },
    "work_item_id": { "type": "string" },
    "limit": { "type": "integer", "minimum": 1, "maximum": 500, "default": 100 },
    "cursor": { "type": "string" },
    "since": { "type": "string", "description": "ISO timestamp" }
  },
  "additionalProperties": false
}
```

---

## Decisions (Append-only + approval gate)

### 6.13 `decision.propose`

```json
{
  "type": "object",
  "required": ["project_id", "decision", "actor"],
  "properties": {
    "project_id": { "type": "string" },
    "decision": {
      "type": "object",
      "required": ["title", "context", "options_considered", "decision", "tradeoffs"],
      "properties": {
        "decision_id": { "type": "string" },
        "title": { "type": "string" },
        "context": { "type": "string" },
        "options_considered": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["option", "pros", "cons"],
            "properties": {
              "option": { "type": "string" },
              "pros": { "type": "array", "items": { "type": "string" } },
              "cons": { "type": "array", "items": { "type": "string" } }
            },
            "additionalProperties": false
          }
        },
        "decision": { "type": "string" },
        "tradeoffs": { "type": "array", "items": { "type": "string" } },
        "impacts": { "type": "string" },
        "linked_work_items": { "type": "array", "items": { "type": "string" } },
        "artifacts": { "type": "array", "items": { "type": "object" } },
        "supersedes": { "type": "string" },
        "status": { "type": "string", "enum": ["proposed", "approved", "superseded"], "default": "proposed" },
        "timestamp": { "type": "string" }
      },
      "additionalProperties": false
    },
    "actor": { "$ref": "#/definitions/Actor" },
    "reason": { "type": "string" }
  },
  "additionalProperties": false,
  "definitions": {
    "Actor": {
      "type": "object",
      "required": ["actor_type", "actor_id"],
      "properties": {
        "actor_type": { "type": "string", "enum": ["human", "agent", "system"] },
        "actor_id": { "type": "string" },
        "display_name": { "type": "string" }
      },
      "additionalProperties": false
    }
  }
}
```

---

### 6.14 `decision.approve`

**Description:** Approve a proposed decision. MUST require `approve_decisions`.

```json
{
  "type": "object",
  "required": ["project_id", "decision_id", "actor", "reason"],
  "properties": {
    "project_id": { "type": "string" },
    "decision_id": { "type": "string" },
    "actor": { "$ref": "#/definitions/Actor" },
    "reason": { "type": "string" }
  },
  "additionalProperties": false,
  "definitions": {
    "Actor": {
      "type": "object",
      "required": ["actor_type", "actor_id"],
      "properties": {
        "actor_type": { "type": "string", "enum": ["human", "agent", "system"] },
        "actor_id": { "type": "string" },
        "display_name": { "type": "string" }
      },
      "additionalProperties": false
    }
  }
}
```

---

### 6.15 `decision.list`

```json
{
  "type": "object",
  "required": ["project_id"],
  "properties": {
    "project_id": { "type": "string" },
    "status": { "type": "array", "items": { "type": "string", "enum": ["proposed", "approved", "superseded"] } },
    "limit": { "type": "integer", "minimum": 1, "maximum": 500, "default": 100 },
    "cursor": { "type": "string" },
    "since": { "type": "string" }
  },
  "additionalProperties": false
}
```

---

## Timeline (Append-only)

### 6.16 `timeline.append`

```json
{
  "type": "object",
  "required": ["project_id", "event", "actor"],
  "properties": {
    "project_id": { "type": "string" },
    "event": {
      "type": "object",
      "required": ["type", "summary"],
      "properties": {
        "event_id": { "type": "string" },
        "type": { "type": "string", "enum": ["milestone", "release", "decision", "blocker", "risk", "incident", "status_change", "note"] },
        "summary": { "type": "string" },
        "details": { "type": "string" },
        "related_ids": { "type": "array", "items": { "type": "string" } },
        "evidence_links": { "type": "array", "items": { "type": "object" } },
        "timestamp": { "type": "string" }
      },
      "additionalProperties": false
    },
    "actor": { "$ref": "#/definitions/Actor" },
    "reason": { "type": "string" }
  },
  "additionalProperties": false,
  "definitions": {
    "Actor": {
      "type": "object",
      "required": ["actor_type", "actor_id"],
      "properties": {
        "actor_type": { "type": "string", "enum": ["human", "agent", "system"] },
        "actor_id": { "type": "string" },
        "display_name": { "type": "string" }
      },
      "additionalProperties": false
    }
  }
}
```

---

### 6.17 `timeline.list`

```json
{
  "type": "object",
  "required": ["project_id"],
  "properties": {
    "project_id": { "type": "string" },
    "limit": { "type": "integer", "minimum": 1, "maximum": 1000, "default": 200 },
    "cursor": { "type": "string" },
    "since": { "type": "string" }
  },
  "additionalProperties": false
}
```

---

## Activity / Audit

### 6.18 `activity.list`

```json
{
  "type": "object",
  "required": ["project_id"],
  "properties": {
    "project_id": { "type": "string" },
    "limit": { "type": "integer", "minimum": 1, "maximum": 1000, "default": 200 },
    "cursor": { "type": "string" },
    "since": { "type": "string" },
    "actor_id": { "type": "string" },
    "target_type": { "type": "string" }
  },
  "additionalProperties": false
}
```

---

## Environments & Access (Pointers only)

### 6.19 `env.list`

```json
{
  "type": "object",
  "required": ["project_id"],
  "properties": {
    "project_id": { "type": "string" }
  },
  "additionalProperties": false
}
```

### 6.20 `env.upsert`

```json
{
  "type": "object",
  "required": ["project_id", "env_id", "expected_version", "patch", "actor"],
  "properties": {
    "project_id": { "type": "string" },
    "env_id": { "type": "string" },
    "expected_version": { "type": "integer", "minimum": 0 },
    "patch": { "type": "object" },
    "actor": { "$ref": "#/definitions/Actor" },
    "reason": { "type": "string" }
  },
  "additionalProperties": false,
  "definitions": {
    "Actor": {
      "type": "object",
      "required": ["actor_type", "actor_id"],
      "properties": {
        "actor_type": { "type": "string", "enum": ["human", "agent", "system"] },
        "actor_id": { "type": "string" },
        "display_name": { "type": "string" }
      },
      "additionalProperties": false
    }
  }
}
```

### 6.21 `access.list`

```json
{
  "type": "object",
  "required": ["project_id"],
  "properties": {
    "project_id": { "type": "string" }
  },
  "additionalProperties": false
}
```

### 6.22 `access.upsert`

**Secret-safety:** server MUST scan inputs and reject secrets.

```json
{
  "type": "object",
  "required": ["project_id", "access_ref_id", "expected_version", "patch", "actor"],
  "properties": {
    "project_id": { "type": "string" },
    "access_ref_id": { "type": "string" },
    "expected_version": { "type": "integer", "minimum": 0 },
    "patch": { "type": "object" },
    "actor": { "$ref": "#/definitions/Actor" },
    "reason": { "type": "string" }
  },
  "additionalProperties": false,
  "definitions": {
    "Actor": {
      "type": "object",
      "required": ["actor_type", "actor_id"],
      "properties": {
        "actor_type": { "type": "string", "enum": ["human", "agent", "system"] },
        "actor_id": { "type": "string" },
        "display_name": { "type": "string" }
      },
      "additionalProperties": false
    }
  }
}
```

Errors: `SECRET_DETECTED`, `CONFLICT`, `FORBIDDEN`

---

## Executive Query (Contracted Answers)

### 6.23 `exec.query`

**Description:** Answer executive questions using the canonical response shape from your Executive Status Query Contract.

```json
{
  "type": "object",
  "required": ["project_id", "query_type"],
  "properties": {
    "project_id": { "type": "string" },
    "query_type": {
      "type": "string",
      "enum": [
        "ON_TRACK",
        "BLOCKERS",
        "CHANGED_SINCE",
        "NEXT_7_DAYS",
        "TOP_RISKS",
        "RECENT_DECISIONS",
        "FAILED_ATTEMPTS",
        "RISKIEST_ASSUMPTION",
        "WHERE_RUNNING_ACCESS",
        "RESUME_IN_30"
      ]
    },
    "since": { "type": "string", "description": "ISO timestamp, required for CHANGED_SINCE" },
    "actor": {
      "type": "object",
      "properties": {
        "actor_type": { "type": "string", "enum": ["human", "agent", "system"] },
        "actor_id": { "type": "string" },
        "display_name": { "type": "string" }
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

**Returns (ExecutiveResponse):**
```json
{
  "summary": ["1-3 bullets"],
  "confidence": "low|medium|high",
  "drivers": ["2-4 bullets (optional)"],
  "blockers": [
    {
      "work_item_id": "string",
      "title": "string",
      "owner": "string",
      "age_days": 3,
      "unblock_path": "string"
    }
  ],
  "risks": [
    { "risk": "string", "owner": "string", "mitigation": "string" }
  ],
  "evidence": [
    { "kind": "work_item", "id": "WI-...", "note": "optional" },
    { "kind": "decision", "id": "DEC-..." }
  ],
  "followups": ["string", "string"]
}
```

**Rules:**
- MUST include `evidence` references.
- MUST not invent metrics.
- If required state is missing, MUST say so and set confidence `low`.

---

## 7) Notifications (Optional but Recommended)

Servers MAY emit an MCP notification when state changes:
- `state.changed`

Payload SHOULD include:
- `project_id`
- the `activity` event
- optional: `targets` list

This enables live UIs and “always-on” agents.

---

## 8) Minimal Acceptance Tests (v0.1)

A server is “contract-compliant” if:

- Reads:
  - `project.get`, `work.list`, `attempt.list`, `decision.list`, `timeline.list` function correctly with pagination/cursors where applicable.
- Coordination:
  - `work.claim` prevents non-claimant `work.update`.
  - Lease expiry allows new claim.
  - `work.update` enforces `expected_version`.
- Append-only:
  - `attempt.append` and `decision.propose` are idempotent by ID.
- Secrets:
  - `access.upsert` rejects secret-like content (`SECRET_DETECTED`).
- Executive queries:
  - `exec.query` returns evidence-backed responses for all `query_type` values.

---

## 9) Implementation Notes (Non-Normative)

- Storage MAY be:
  - local folder + JSONL/YAML
  - database
  - hybrid with export/import
- Regardless of storage, servers MUST preserve append-only semantics and audit provenance.

---

## 10) Tool Naming (Optional Alternative)

If you prefer namespaced tools, you MAY prefix with `psl.` (Project State Layer), e.g.:
- `psl.project.get`
- `psl.work.list`
- `psl.exec.query`

Keep names stable once published.
