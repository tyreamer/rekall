# Project State Spec — Schema (v0.1)

**Status:** Draft (v0.1)  
**Purpose:** Define the portable **State Artifact** format (files + objects) used as the canonical project state representation.

This spec is **storage-agnostic**. A server may store state in a DB or local files, but MUST be able to export/import a State Artifact conforming to this schema.

See also:
- `02_invariants_and_operating_rules.md` (append-only, claims, versions, no secrets)
- `05_mcp_tool_contract_v0.1.md` (tool interface)

---

## 1) State Artifact layout (recommended, non-binding)

A State Artifact MAY be represented as a directory such as:

```
project-state/
  schema-version.txt
  project.yaml
  envs.yaml
  access.yaml
  work-items.jsonl
  attempts.jsonl
  decisions.jsonl
  timeline.jsonl
  activity.jsonl
```

Implementations MAY rename files, but MUST preserve:
- object semantics
- append-only requirements
- deterministic ordering rules
- ability to round-trip export/import

---

## 2) Formats & encoding

- YAML files: UTF-8, `\n` line endings preferred
- JSONL files: UTF-8, one JSON object per line, newline-delimited

### 2.1 YAML vs JSONL guidance
- Use YAML for relatively stable configuration:
  - Project metadata
  - Environment map
  - Access references (pointers only)
- Use JSONL for append-only logs:
  - Attempts
  - Decisions
  - Timeline
  - Activity/Audit
- Work items are **conceptually mutable**; this spec supports two compliant representations:
  - **(Recommended)** Event stream in `work-items.jsonl` (append-only WorkItem events)  
  - **(Allowed)** Snapshot in `work-items.yaml/json` (requires stronger conflict controls)

---

## 3) Versioning

### 3.1 Schema version
- `schema-version.txt` MUST contain: `0.1`

### 3.2 Mutable versioning
Mutable objects MUST have a `version` integer in the tool/API surface (MCP contract).  
If stored in YAML, implementations SHOULD also store a top-level version in the file.

---

## 4) Common Types

### 4.1 Actor
```yaml
actor_type: human | agent | system
actor_id: string
display_name: string?   # optional
```

### 4.2 TypedLink
```yaml
link_id: string
type: repo | board | doc | dashboard | logs | traces | alerting | design | dataset | ticketing | runbook | demo | domain | model | mcp_server | notebook | other
label: string
url: string
system: github | jira | notion | slack | figma | datadog | sentry | gcp | aws | azure | cloudflare | other?
notes: string?
status: active | deprecated?
```

---

## 5) `project.yaml` — Project

**Purpose:** Durable identity + intent + constraints + high-level links.

### 5.1 Required fields
```yaml
schema_version: "0.1"
project_id: string
name: string
one_liner: string
current_goal: string
phase: discovery | mvp | build | harden | launch | maintain
data_classification: public | internal | confidential | restricted
```

### 5.2 Recommended fields
```yaml
version: 1
status: on_track | at_risk | off_track | paused
confidence: low | medium | high
non_goals: []
constraints: {}           # free-form, but should remain small
tech_stack_summary: string
typed_links: []           # list[TypedLink]
owners:
  human_owners: []
  primary_agent: string?
tags: []
updated_at: 2026-02-25T00:00:00Z
```

Notes:
- `status` may be computed by clients if absent, but computation must be disclosed in executive answers.

---

## 6) `envs.yaml` — Environment Map

**Purpose:** “Where is this running?” plus observability entry points.

### 6.1 Structure
```yaml
schema_version: "0.1"
version: 1
environments:
  - env_id: dev | staging | prod | sandbox | local | other
    name: string
    urls:
      - type: app | api | admin | other
        url: string
    hosting:
      provider: string
      account_ref_id: string?      # references access.yaml
      region: string?
      runtime: string?             # serverless/container/vm/managed/other
    observability_links: []        # list[TypedLink]
    deployment_notes: string?
    last_known_good:
      timestamp: string?
      notes: string?
```

---

## 7) `access.yaml` — Access References (Pointers only)

**Purpose:** Track accounts/roles/secret locations without storing secrets.

### 7.1 Structure
```yaml
schema_version: "0.1"
version: 1
access_refs:
  - access_ref_id: string
    type: cloud_account | secret | api_credential | domain | email | sso_role | vpn | other
    system: aws | gcp | azure | cloudflare | 1password | vault | okta | other
    identifier: string             # e.g., "vault:path/to/item" or "gcp-project-id"
    owner: string?
    request_access_steps:
      - string
    security_notes: string?
    status: active | deprecated?
```

Rules:
- The server MUST reject attempts to store credential values (see invariants doc).

---

## 8) Work Items

**Purpose:** The work graph agents pick up and coordinate on.

This spec supports two formats.

### 8.1 Recommended: `work-items.jsonl` as an **event stream**
Each line is a `WorkItemEvent` object. This makes sync/merge substantially simpler.

#### 8.1.1 WorkItemEvent
```json
{
  "event_id": "string",
  "type": "WORK_ITEM_CREATED | WORK_ITEM_PATCHED | WORK_ITEM_CLAIMED | WORK_ITEM_RELEASED",
  "project_id": "string",
  "work_item_id": "string",
  "timestamp": "ISO 8601",
  "actor": { "actor_type": "human|agent|system", "actor_id": "string" },
  "expected_version": 3,
  "patch": { "any": "object" },
  "reason": "string (optional)"
}
```

Rules:
- Events are append-only and ordered by `(timestamp, event_id)`.
- The current WorkItem snapshot is computed by replay.
- For PATCHED events, `expected_version` MUST be validated by the server.

#### 8.1.2 WorkItem snapshot shape (computed)
A materialized work item MUST include:
```json
{
  "work_item_id": "string",
  "version": 4,
  "type": "task|bug|spike|research|decision_needed|chore",
  "title": "string",
  "intent": "string",
  "definition_of_done": ["string"],
  "status": "todo|in_progress|blocked|done|parked",
  "priority": "p0|p1|p2|p3",
  "tags": ["string"],
  "owner": "string (optional)",
  "claim": { "claimed_by": "string", "lease_until": "ISO 8601" },
  "dependencies": { "blocked_by": ["string"], "blocks": ["string"] },
  "evidence_links": [ /* TypedLink */ ],
  "created_at": "ISO 8601",
  "updated_at": "ISO 8601"
}
```

### 8.2 Allowed: snapshot list (YAML/JSON)
If you store a snapshot list, you MUST still:
- enforce optimistic concurrency (version)
- emit activity/audit events for all writes
- ensure deterministic conflict behavior
- strongly prefer using the tool interface as the “arbiter” (avoid manual merge)

---

## 9) `attempts.jsonl` — Attempts (append-only)

**Purpose:** Prevent loops and preserve learning.

Each line is an `Attempt`:

```json
{
  "attempt_id": "string",
  "project_id": "string",
  "work_item_id": "string (optional)",
  "hypothesis": "string",
  "action_taken": "string",
  "result": "string",
  "conclusion": "string",
  "next_step": "string (optional)",
  "artifacts": [ /* TypedLink */ ],
  "performed_by": { "actor_type": "human|agent|system", "actor_id": "string" },
  "timestamp": "ISO 8601"
}
```

Rules:
- Append-only
- Idempotent by `attempt_id`

---

## 10) `decisions.jsonl` — Decisions (append-only)

Each line is a `Decision`:

```json
{
  "decision_id": "string",
  "project_id": "string",
  "title": "string",
  "context": "string",
  "options_considered": [
    { "option": "string", "pros": ["string"], "cons": ["string"] }
  ],
  "decision": "string",
  "tradeoffs": ["string"],
  "impacts": "string (optional)",
  "linked_work_items": ["string"],
  "artifacts": [ /* TypedLink */ ],
  "decided_by": { "actor_type": "human|agent|system", "actor_id": "string" },
  "status": "proposed|approved|superseded",
  "supersedes": "string (optional)",
  "timestamp": "ISO 8601"
}
```

Rules:
- Append-only
- Approval gates are enforced in the tool layer (agents can propose; humans approve)

---

## 11) `timeline.jsonl` — Timeline Events (append-only)

```json
{
  "event_id": "string",
  "project_id": "string",
  "type": "milestone|release|decision|blocker|risk|incident|status_change|note",
  "summary": "string",
  "details": "string (optional)",
  "related_ids": ["string"],
  "evidence_links": [ /* TypedLink */ ],
  "created_by": { "actor_type": "human|agent|system", "actor_id": "string" },
  "timestamp": "ISO 8601"
}
```

---

## 12) `activity.jsonl` — Activity/Audit (append-only)

Every write (append or mutation) MUST emit an Activity event:

```json
{
  "activity_id": "string",
  "project_id": "string",
  "actor": { "actor_type": "human|agent|system", "actor_id": "string", "display_name": "string (optional)" },
  "action": "create|update|claim|release|append|propose|approve",
  "target_type": "project|work_item|attempt|decision|timeline|env|access_ref|link",
  "target_id": "string",
  "diff": { "any": "object (optional)" },
  "reason": "string (optional)",
  "timestamp": "ISO 8601"
}
```

Rules:
- Append-only
- Must exist for every write path exposed via tooling

---

## 13) Compliance checklist (v0.1)

A State Artifact is compliant if:
- It declares `schema_version: 0.1`
- Attempts/Decisions/Timeline/Activity are append-only + idempotent
- Work items support claim/lease + optimistic concurrency (even if stored as events)
- Secrets are never stored (access is pointers only)
- Executive answers can cite evidence IDs/links

---

## 14) Research & knowledge (v0.1 guidance)

Rekall should capture “what we know” and “what we learned” as part of project state.

**In v0.1 (recommended):**
- Represent research as `WorkItem.type = research` with:
  - definition of done (“what question are we answering?”)
  - attempts entries as the experiment log
  - typed links to sources (docs, NotebookLM, papers, threads)

**Future (v0.2+):**
- Add a dedicated append-only `research.jsonl` stream if needed for higher-volume notes or richer RAG indexing.

This keeps v0.1 minimal while still supporting a true knowledge stream.

