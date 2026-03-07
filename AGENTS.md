# AGENTS.md

This file defines how AI coding assistants should operate in this repository.
It is assistant-agnostic: the same contract applies to Claude Code, Cursor,
Codex, Gemini, Windsurf, Aider, or any tool that reads repo instructions.

## Where things live

| What | Where | Who maintains it |
| :--- | :--- | :--- |
| Stable behavior rules | CLAUDE.md / .cursor/rules / .github/copilot-instructions.md | Human |
| Durable project knowledge | README.md, docs/, or thin MEMORY.md | Human |
| **Live execution state** | **Rekall vault** (`project-state/`) | **Agent + Human** |

Do NOT duplicate live execution state (in-progress work, blockers, failed attempts,
pending decisions) into MEMORY.md or other markdown files. Rekall is the single
source of truth for volatile project state.

## How to call Rekall

If you can run shell commands (Claude Code, Codex, Aider, terminal): use `rekall` CLI commands directly.
If you are an MCP-connected IDE agent (Cursor, Windsurf): use the equivalent MCP tools.

| Action | CLI command | MCP tool |
| :--- | :--- | :--- |
| Get session brief | `rekall brief --json` | `session.brief` |
| Bootstrap project | `rekall init` | `project.bootstrap` |
| Log a checkpoint | `rekall checkpoint --summary "…"` | `checkpoint` (or `rekall_checkpoint`) |
| End a session | `rekall session end --summary "…"` | *(call via CLI)* |

## Session protocol

### Starting a session

Before doing any work, get your bearings:

```bash
rekall brief --json    # One call: focus, blockers, failed paths, pending decisions, next actions
```

Or via MCP: call `session.brief` (or `project.bootstrap` which includes the brief).

This tells you:
- What's currently in progress
- What's blocked and why
- What approaches already failed (do not retry these)
- What decisions need human input
- What to work on next

### During work

Log meaningful state changes — not every keystroke, but turning points:

- **Tried something that failed?** Log it so the next session doesn't repeat it:
  `rekall attempts add <work_item_id> --title "..." --evidence "..."`
- **Made an architectural choice?** Record the tradeoff:
  `rekall decisions propose --title "..." --rationale "..." --tradeoffs "..."`
- **Finished a task?** Checkpoint it:
  `rekall checkpoint --type task_done --title "..." --summary "..." --commit auto`

### Ending a session

Before stopping or handing off:

```bash
rekall session end --summary "Where I stopped and what comes next"
```

This records a handoff note and warns about any unrecorded work.

## Usage modes

Set with `rekall mode <mode>`:

- **lite** — Lightweight tracking. Only checkpoint at session boundaries. For small/simple repos.
- **coordination** (default) — Standard multi-session tracking. Log decisions and failed attempts.
- **governed** — Full governance with mandatory checkpoints and human approvals for high-risk actions.

## Current project context

Rekall is a local-first, git-portable project state layer for AI agents.
The north star is that agents coordinate by default through Rekall, and humans govern explicitly.
