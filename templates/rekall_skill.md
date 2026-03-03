# Rekall Agent Skill Pack

This file defines the operating contract for any AI agent integrating with this Rekall vault.

## 1. Startup Routine
Every time you start work, you MUST call `project.bootstrap`.
- This ensures the vault is healthy.
- It returns the current `goal`, `phase`, and `status`.
- It provides important paths and next-step recommendations.

## 2. Decision & Attempt Logging
Rekall is an append-only execution ledger. Do not rely on your internal memory for long-term state.
- **Log Decisions**: Call `decisions.propose` for any architectural or significant logic change.
- **Log Attempts**: Call `attempts.add` for every unit of work (e.g. "Implementing auth", "Fixing bug X"). Include evidence (test results, file paths).

## 3. Approval Breakpoints
- If a decision high-risk or requires human sign-off, use the `decisions` API with a "PENDING" state (or follow the specific MCP tool guidance for breakpoints).
- Stop and wait for human `rekall decide` if you reach an ambiguity you cannot resolve with 90% confidence.

## 4. Idempotency & Secrets
- Use `idempotency_key` (e.g. hash of inputs) to avoid duplicate logs on retries.
- **NO SECRETS**: Never log API keys, tokens, or passwords. Redact them to `[REDACTED]` before calling Rekall tools.
