# Agent Continuity Protocol (ACP) v0.1

**Status:** Draft | **Version:** 0.1

## Protocol Overview

The **Agent Continuity Protocol (ACP)** is a minimal, portable data contract designed to give autonomous agents session continuity.

ACP is **not** a CLI or a set of commands. Instead, it defines a standard way to structure **working-state contexts** and **continuity events** (like milestones, decisions, and failed paths). 

By adopting ACP, agents can stop work on Friday and resume on Monday without suffering from "cold start" amnesia. They won't repeat failed approaches because "do-not-retry" memory is explicitly materialized into their boot context.

ACP consists of three core components:
1. **The ACP Context Envelope:** A point-in-time snapshot of the current working state.
2. **The ACP Event Envelope:** An append-only record of a continuity event.
3. **Materialization Semantics:** The rules for deriving a Context Envelope from a stream of Event Envelopes.

---

## 1. ACP Context Envelope

The **Context Envelope** is the resumable working-state payload an agent reads at session start. It explicitly frames what the agent should focus on and what it should avoid.

### Schema Requirements
- `protocol_version` (string): The ACP version, e.g., `"0.1"`
- `project_id` (string): Unique identifier for the repository/scope
- `session_id` (string, optional): Continuity scope identifier
- `current_focus` (string): The active objective or next action
- `recent_milestones` (array): The last few completed checkpoints 
- `failed_paths` (array): Explicit "DO NOT RETRY" warnings
- `open_decisions` (array): Architectural constraints or pending choices
- `blockers` (array): Execution blockers 
- `evidence_refs` (array, optional): Links to artifacts or logs
- `generated_at` (string ISO-8601): Timestamp of context materialization

### Example Payload
```json
{
  "protocol_version": "0.1",
  "project_id": "rekall-core",
  "current_focus": "Implement JWT middleware",
  "recent_milestones": [
    { "id": "evt_abc1", "title": "Setup PostgreSQL database", "timestamp": "2026-03-25T14:00:00Z" }
  ],
  "failed_paths": [
    { "title": "SQLite for analytics", "reason": "Too slow at 10k rows" }
  ],
  "open_decisions": [
    { "title": "Use Docker for local dev", "rationale": "Ensures parity with CI" }
  ],
  "blockers": [],
  "generated_at": "2026-03-25T14:30:00Z"
}
```

---

## 2. ACP Event Envelope

The **Event Envelope** is an append-only payload written dynamically during execution to record state changes.

### Schema Requirements
- `protocol_version` (string): e.g., `"0.1"`
- `event_id` (string): Unique identifier
- `event_type` (string): `checkpoint` | `decision` | `failed_attempt` | `blocker`
- `timestamp` (string ISO-8601)
- `actor_type` (string): `agent` | `human` | `system`
- `actor_id` (string): Identifier of the execution agent/user
- `summary` (string): High-level description
- `details` (string, optional): Extended rationale or evidence
- `evidence_refs` (array, optional): URIs, SHAs, or file paths
- `related_ids` (array, optional): Links to prior events
- `idempotency_key` (string, optional): For deduplication

### Minimal Event Types
- **`checkpoint`**: A milestone or task completion.
- **`decision`**: An architectural choice with rationale.
- **`failed_attempt`**: A dead-end path that must not be retried.
- **`blocker`**: A condition preventing forward progress.

### Example Payload
```json
{
  "protocol_version": "0.1",
  "event_id": "evt_9a8b7c",
  "event_type": "checkpoint",
  "timestamp": "2026-03-25T15:30:00Z",
  "actor_type": "agent",
  "actor_id": "claude-code",
  "summary": "Implement authentication flow",
  "details": "Added JWT login endpoints and middleware. Tests passing.",
  "evidence_refs": ["commit:a1b2c3d"]
}
```

---

## 3. Materialization Semantics

Materialization is the process of reading an append-only stream of **Events** and deriving a **Context Envelope**. Tool builders should adhere to the following rules:

1. **Checkpoints to Milestones:** The most recent `checkpoint` events (e.g., last 3) are populated into the `recent_milestones` list to provide chronological context.
2. **Attempt Failed to DO-NOT-RETRY:** All unresolved `failed_attempt` events are aggregated into the `failed_paths` array. The agent must read these before planning execution.
3. **Decisions to Constraints:** `decision` events establish constraints. They stay in the `open_decisions` array indefinitely, unless explicitly superseded by a newer decision mapped via `related_ids`.
4. **Blockers:** `blocker` events surface in the context envelope until a `checkpoint` explicitly marks them resolved.
5. **Brief Rendering:** The Context Envelope should be rendered into a format easily ingestible by an LLM (such as a concise markdown `Brief`) and injected into the agent's system prompt at session initialization.

---

## Conformance Guidance

A tool or generic runtime is ACP-compatible if it:
- Generates or consumes an **ACP Context Envelope** at session start.
- Appends state changes using the **ACP Event Envelope** standard.
- Respects the **Materialization Semantics** (e.g., surfacing failures as hard constraints).

**Note:** You do not need to use `Rekall` to implement ACP. Any tool can generate and parse these envelopes. However, if you want a complete, local-first UX that implements these semantics natively, you can use the Rekall reference implementation.
