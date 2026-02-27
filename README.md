# Rekall — Stop paying for the same mistake twice

Your autonomous agent just spent 47 minutes and $41 re-trying a failed migration it already proved wouldn't work.

Rekall prevents repeat execution loops by giving agents a persistent, local execution record.

One folder next to your code. No server. No UI. One command to initialize.

```bash
pip install rekall.tools
rekall init
```

Run your agent normally.

When it needs a human decision, it pauses and prints a `decision_id`.

Come back later:
```bash
rekall decide <decision_id> --option "use SQLite"
rekall resume
```

The agent continues where it left off.

Every attempt, decision, and outcome becomes part of a tamper-evident, cryptographically verifiable execution record.

---

## What Rekall is / isn't

### IS
- Verifiable AI execution record
- Tamper-evident audit trail
- Local-first, git-portable append-only ledger

### IS NOT
- Chat transcript
- Vector store
- Stateful chat memory
- PM board
- Jira replacement

---

---

*See the [Hero Example](docs/HERO_EXAMPLE.md) for a technical walkthrough of cryptographic evidence in action.*

---

![Rekall demo](assets/demo/rekall_demo.gif)
*15-second demo: agent lifecycle with attempts, decisions, and handoff*

---

## See it in 30 seconds
```bash
# Install directly from PyPI
pip install rekall.tools

# Run the mocked demo lifecycle
rekall demo
```

## Quick Start (for humans & agents)
```bash
cd /path/to/your-repo
rekall init          # ← creates cheat sheet + project-state/

# Core Commands
rekall status           # ← Quick executive summary of the current reality
rekall guard            # ← Preflight check: summarized goals, risks, and recent work
rekall serve            # ← [MCP] Launch stdio server for AI agents (Claude Code, etc.)
rekall blockers         # ← List active blockers and their estimated impact
```

### What does the actual state look like?
Rekall is just a folder of human-readable files that agents can easily parse and update. No complex database, no hidden state.

```text
project-state/
├── project.yaml       # Metadata, goals, and constraints
├── activity.jsonl     # High-level work items (Todo/In-Progress)
├── attempts.jsonl     # Typed execution ledger of what has been tried
├── decisions.jsonl    # Explicit architectural trade-offs
└── timeline.jsonl     # Immutable event log
```

**Example Record (attempts.jsonl):**
```json
{
  "attempt_id": "a1b2c3d4",
  "work_item_id": "wi_105",
  "title": "Migrate DB to Postgres",
  "outcome": "failed",
  "rationale": "RDS instance was not reachable in subnet 'sn-99'",
  "evidence_refs": ["logs/deploy_error.log"]
}
```

```bash
# Get a quick executive summary with integrity proof
rekall status --store-dir ./project-state

[ rekall status ]
✅ INTEGRITY OK | Anchor: SIGNED | HEAD: da573d4bbba1...
Goal/Phase: Cloud Migration v1 (Phase 3: RDS Move)
Active HEAD: 2026-02-26T20:29:53Z
HEAD ID:     da573d4bbba142759e66289b7cf6cd72

=== Shadow Policy Constraints ===
Audit Trail: 45 preflight checks recorded.
Status: Pass (0 active would-deny items)

=== Provenance Anchors ===
Latest Anchor: anch-895a6595 [SIGNED]
Evidence:      2026-02-26T20:29:53Z
```

---

## Core Concepts
Rekall is a **verifiable AI execution record + execution ledger**, not a task manager. It provides the missing state layer that agents need:

- **Attempts**: A typed execution ledger of what has been tried. Agents learn from past failures instead of repeating them.
- **Decisions**: Explicit records of trade-offs. Context is preserved permanently.
- **Timeline**: An immutable event log of milestones and state changes.
- **Environment Pointers**: Typed references to environments and access methods.

*Rekall also provides native **Idempotency** (preventing duplicate agent actions) and **Checkpointing** (durable save-points).*

---

## Agent Operating Instructions
If you are an AI agent, you should read the project's state to understand the context, and contribute back to the execution ledger securely so the next agent isn't starting from scratch.

### 1. Read the State
Before making changes, understand the current context and invariants:
```bash
cat project-state/artifacts/init_cheatsheet.md  # Best place to start
rekall status
rekall guard
```

### 2. Contribute to the execution ledger
If you hit a roadblock, make a decision, or try an approach that fails—record it!

**Idempotency Keys**: You can safely run these commands multiple times. Rekall uses idempotency keys to avoid duplicate records:
```bash
# Append a failed attempt so others don't repeat your mistakes
rekall attempts add REQ-1 \
  --title "Tried migrating to Postgres RDS" \
  --evidence "logs/deploy_error.log" \
  --idempotency-key "pg-rds-migration-v1"

# Propose an architectural decision
rekall decisions propose \
  --title "Use SQLite instead of Postgres" \
  --rationale "Keep it simple and local-first" \
  --tradeoffs "Harder to scale horizontally" \
  --idempotency-key "use-sqlite-v1"
```

### 3. Call to Action
Run `rekall handoff <project_id>` when you're done to generate a `boot_brief.md` for the next agent session!

---

## When to use Rekall
| Use Rekall when... | Do NOT use Rekall when... |
| :--- | :--- |
| Operating autonomous AI agents | You just need a visual Trello audit trail |
| Losing context between pair-sessions | You want two-way sync with Jira/Linear |
| You need a local, git-portable state | You are building non-technical products |

---

## Go Deeper
1. [Quickstart](docs/QUICKSTART.md) — Initialize your own project.
2. [Beta Guide](docs/BETA.md) — What to try and how to provide feedback.
3. [Positioning Lock](docs/POSITIONING_LOCK.md) — The single authoritative source of truth for our verbiage and mission.
4. [Connecting Clients](docs/CONNECTING_CLIENTS.md) — Claude Desktop, Cursor, and more.
5. [Advanced Docs](docs/) — Idempotency, Checkpointing, and MCP Validation.


---

## Ready to give your agents an execution record?
```bash
# Zero-friction install
pip install rekall.tools

# Try the demo
rekall demo
```

⭐ **Star this repo** if this solves a real pain for you.  
🐦 **Follow [@TyReamer](https://x.com/tyreamer)** for updates and beta announcements.

---

### Status
`v0.1.0-beta.1` — Private beta (2026-02-25). See [CHANGELOG.md](CHANGELOG.md) for details.

*Note: `rekall.io` domain is reserved for future hosted services.*
