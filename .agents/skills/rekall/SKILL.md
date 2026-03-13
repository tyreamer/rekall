# Rekall Skill: Local-First Execution Ledger

This skill teaches the assistant how to use Rekall to track decisions, attempts, and project state. Rekall is a "Git for execution" used to prevent repeated mistakes and ensure high-context session handoffs.

## Core Workflow (The Loop)

You MUST follow this loop for all meaningful engineering work:

1. **rekall.init**: Call at project start to ensure vault exists and goals are set.
2. **rekall.brief**: Call at every session start. Use the returned context to avoid retrying failed attempts and to honor past decisions.
3. **rekall.record**: Use during work to log:
   - `type="decision"`: Architectural choices, trade-offs, and approvals.
   - `type="attempt"`: What you tried and why it failed. Use this to prevent future retries.
   - `type="work_item"`: Creation or updates of tasks.
4. **rekall.checkpoint**: Call after every successful unit of work (e.g., a feature implemented or a bug fixed). Always include a meaningful `--title`.
5. **rekall.log**: Call to review recent history if you feel out of sync.
6. **rekall.verify**: Call before concluding work or recommending a push. Ensure all CI/CD checks pass.
7. **rekall.handoff**: Call when wrapping up the session or switching tasks.

## Principles

- **Opinionated UX**: Favor small, meaningful checkpoints over massive "dump-all" logs.
- **Local-First**: All state lives in the `.rekall/` or `project-state/` folder.
- **Verification First**: Never claim a task is "done" without running `rekall.verify`.
- **Don't Guess**: If the ledger says a path failed, investigate the previous failure before trying again.

## Tool Guide

- `rekall.init(goal, phase, status)`: Setup project identity.
- `rekall.brief()`: The single source of truth for "what's next".
- `rekall.status(project_id)`: High-level health check.
- `rekall.record(type, data, reason)`: Append granular facts.
- `rekall.checkpoint(title, summary, type, git_commit)`: Durable progress marker.
- `rekall.log(limit)`: Sequence of events.
- `rekall.verify()`: Runs `ruff`, `mypy`, and `pytest`.
- `rekall.handoff(project_id, out_dir)`: Generates the `boot_brief.md` for the next session.

## When to Checkpoint
- After an atomic code change that passes tests.
- After a successful refactor.
- After resolving a major blocker.

## When to Record a Decision
- Choosing a library or framework.
- Defining a data schema.
- Deciding on an API contract.
