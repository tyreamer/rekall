# Agent Continuity Protocol (ACP) v0.1

**Status:** Draft | **Version:** 0.1

## What is ACP?

The Agent Continuity Protocol (ACP) is a minimal, portable standard for agent session continuity across work sessions.

When AI coding agents (or other autonomous systems) stop and restart, they typically suffer from "cold start" amnesia. They forget what was tried, what failed, and what architectural decisions were made. 

ACP defines a standardized way to store and retrieve these critical continuity events. Its primary validated wedge is **warm-start continuity**: ensuring your next agent session won't start from zero.

## The Problem It Solves

- **Repeating failed work:** Agents retrying the same incorrect approach because they don't know it already failed.
- **Relitigating decisions:** Agents undoing or questioning established architectural choices.
- **Lost execution timelines:** No cohesive record of what the agent actually achieved across disparate sessions.

## ACP Core Philosophy

- **Continuity-First:** ACP is about warm starts, not enterprise governance or strict policy enforcement. Features requiring strict agent discipline are deferred; features tied to natural workflows (like session start or task completion) are prioritized.
- **Portable and Minimal:** The schema is small, basic JSON/YAML. It can live alongside any codebase without deep IDE integration. 
- **Implementation-Agnostic:** Any tool can implement ACP. `Rekall` serves as the reference implementation, but you do not need Rekall to be ACP-compliant.

## Minimum Primitives

ACP defines four minimal core primitives:

1. **Brief**: Read current working context at session start.
2. **Checkpoint**: Write milestone/progress/task completion.
3. **Decision**: Record an important agent/human decision with rationale.
4. **Attempt Failed**: Record a failed path so the next session does not retry it.
5. **Log**: Read execution history sequence.

> **Note on Verification and Governance:** Mechanisms like hash-chain integrity, remote policy enforcement, and provenance tracking may exist underneath in specific implementations (like Rekall), but they are **outside** the minimal ACP adoption surface. Compliance with ACP only requires adhering to the core primitives for continuity.

---

## Schema & Semantics

The schemas below optimize for cross-tool adoption.

### 1. Brief
**Purpose:** Surface immediate context at session initialization to eliminate the cold start.
- **Required fields:** `active_decisions` (list), `recent_failures` (list), `last_checkpoint` (object).
- **Optional fields:** `project_goal`, `guidelines`.

**Example Payload:**
```json
{
  "last_checkpoint": {
    "title": "Setup PostgreSQL database",
    "timestamp": "2026-03-25T14:00:00Z"
  },
  "recent_failures": [
    { "title": "SQLite for analytics", "reason": "Too slow at 10k rows" }
  ],
  "active_decisions": [
    { "title": "Use Docker for local dev", "rationale": "Ensures parity with CI" }
  ]
}
```

**Human-Readable Rendering:**
```text
CURRENT CONTEXT:
Last Milestone: Setup PostgreSQL database (2 hours ago)
DO NOT RETRY: SQLite for analytics (Too slow at 10k rows)
PENDING DECISIONS: Use Docker for local dev (Ensures parity with CI)
```

### 2. Checkpoint
**Purpose:** Record a milestone or progress logically tied to a task completion (or git commit).
- **Required fields:** `checkpoint_id`, `timestamp`, `title`, `summary`.
- **Optional fields:** `commit_hash`, `author`.

**Example Payload:**
```json
{
  "checkpoint_id": "chk_9a8b7c",
  "timestamp": "2026-03-25T15:30:00Z",
  "title": "Implement authentication flow",
  "summary": "Added JWT login endpoints and middleware. Tests passing.",
  "commit_hash": "a1b2c3d"
}
```

### 3. Decision
**Purpose:** Record an architectural or context-heavy decision so the agent understands constraints without re-debating them.
- **Required fields:** `decision_id`, `timestamp`, `title`, `rationale`.
- **Optional fields:** `tradeoffs`, `status` (proposed, accepted).

**Example Payload:**
```json
{
  "decision_id": "dec_1x2y3z",
  "timestamp": "2026-03-24T10:00:00Z",
  "title": "Use Next.js App Router",
  "rationale": "Better streaming support and RSC integration.",
  "status": "accepted"
}
```

### 4. Attempt Failed
**Purpose:** Record a failed path. This acts as an explicit "DO NOT RETRY" guardrail for the next session.
- **Required fields:** `attempt_id`, `timestamp`, `title`, `evidence`.
- **Optional fields:** `related_task`.

**Example Payload:**
```json
{
  "attempt_id": "fail_4m5n6p",
  "timestamp": "2026-03-24T11:15:00Z",
  "title": "Use standard node fetch for large files",
  "evidence": "Memory limit exceeded. Need streams."
}
```

### 5. Log Entry (Execution History)
**Purpose:** Provide the timeline of what actions occurred across sessions.
- **Required fields:** `event_id`, `timestamp`, `event_type` (e.g., checkpoint, decision, attempt_failed), `payload`.

**Example Payload:**
```json
{
  "event_id": "evt_abc123",
  "timestamp": "2026-03-25T15:30:00Z",
  "event_type": "checkpoint",
  "payload": {
    "title": "Implement authentication flow"
  }
}
```

---

## Standardization & Adoption

**Version:** ACP v0.1

### Conformance Checklist
A tool or protocol extension is ACP-compatible if it:
- [ ] Generates a Brief upon session start containing at minimum the last checkpoint and recent failed attempts.
- [ ] Provides a mechanism to write a Checkpoint upon task completion or commit.
- [ ] Allows explicit recording of Failed Attempts and Decisions.
- [ ] Can emit a chronological Execution Log of these events.

### Rekall as the Reference Implementation
[Rekall](https://github.com/tyreamer/rekall) serves as the local-first, ACP-compatible continuity layer reference implementation. It maps directly to these primitives:
- `rekall init` = Bootstrap ACP in repo
- `rekall brief` = ACP brief read
- `rekall checkpoint` = ACP checkpoint write
- `rekall log` = ACP execution history read

Other tools may implement ACP natively by interacting with the underlying JSON schemas directly or building their own ACP runtime. You do not need the full Rekall feature set (validation, policy engines, explorer) to achieve minimal ACP continuity.
