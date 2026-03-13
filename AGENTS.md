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

## Session protocol

### Starting a session

Before doing any work, get your bearings:

```bash
rekall brief --json    # One call: focus, blockers, failed paths, pending decisions, next actions
```

Or via MCP: call `session.brief` (or `project.bootstrap` which includes the brief).

> [!IMPORTANT]
> **COMPULSORY FIRST STEP**: Before starting any work, you MUST run `rekall brief --json` or call the `session.brief` MCP tool. This is the only way to avoid repeating failed paths and to understand the current live context.

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

This records a session note and warns about any unrecorded work.

## Current mode: `coordination`

Standard multi-session tracking. Log decisions and failed attempts.
Checkpoint after each meaningful unit of work.

> [!TIP]
> **YOLO vs. Protocol**: If the workspace uses "YOLO" or "Fast Execution" rules, these apply to *how* you write and run code. They do NOT exempt you from the Rekall session protocol. `rekall brief` must still be your first action.
