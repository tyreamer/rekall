# Rekall Agent Skill Pack

This file defines the operating contract for any AI agent integrating with this Rekall vault.

## 1. Startup Routine
Every time you start work, get your bearings first:
- **MCP**: Call `session.brief` for a one-call brief, or `project.bootstrap` to initialize + brief.
- **CLI**: Run `rekall brief --json` or `rekall session start`.

This returns: current focus, blockers, failed attempts (do not retry), pending decisions, and recommended next actions.

## 2. Decision & Attempt Logging
Rekall is an append-only execution ledger. Do not rely on your internal memory for long-term state.
- **Log Decisions**: Call `decision.propose` (MCP) or `rekall decisions propose` (CLI) for any architectural or significant logic change.
- **Log Attempts**: Call `attempt.append` (MCP) or `rekall attempts add` (CLI) for every unit of work. Include evidence (test results, file paths).

## 3. Approval Breakpoints
- If a decision is high-risk or requires human sign-off, propose it with a "PENDING" status.
- Stop and wait for human `rekall decide` if you reach an ambiguity you cannot resolve with 90% confidence.

## 4. Session End
When finishing work, record a handoff note:
- **CLI**: `rekall session end --summary "Where I stopped and what comes next"`
- This warns about uncheckpointed commits, missing attempts, and pending decisions.

## 5. Idempotency & Secrets
- Use `idempotency_key` (e.g. hash of inputs) to avoid duplicate logs on retries.
- **NO SECRETS**: Never log API keys, tokens, or passwords. Redact them to `[REDACTED]` before calling Rekall tools.

## 6. Active Checkpointing
After completing a meaningful unit of work, checkpoint it:
- **CLI**: `rekall checkpoint --type task_done --title "..." --summary "..." --commit auto`
- **MCP**: Call `rekall_checkpoint` with `{"type": "task_done", "title": "...", "summary": "...", "git_commit": "auto"}`
