# Rekall Roadmap

**Version**: v0.2 (Mar 2026)
**Focus**: Get to 100 real users. Distribution over features.

## Core Wedge (shipped, validated)

The problem: AI agents start every session cold, retry known failures, re-debate settled decisions.

The solution: `pip install rekall.tools && rekall init` gives agents persistent context.

**What works today:**
- `rekall init` — one command sets up everything (vault, hooks, IDE configs)
- `rekall brief` — auto-injected at session start via hooks
- `rekall checkpoint` — auto-records on git commit, manual for milestones
- `rekall attempts add` — records failures so agents see DO NOT RETRY
- `rekall decisions propose` — records architectural choices with rationale
- `rekall log` — unified execution timeline

## Current Priorities

### 1. Distribution (highest priority)
- [ ] Blog post: "How Rekall saved $X in API credits" with real session data
- [ ] Show HN submission
- [ ] MCP server directory listing (Anthropic, community)
- [ ] awesome-claude-code / awesome-cursor listings
- [ ] Integration guides for each agent type

### 2. Zero-friction adoption
- [x] One-command init (hooks + MCP + IDE configs)
- [x] Auto-checkpoint on git commit
- [x] Auto-brief via SessionStart hook
- [x] Auto-session-end via Stop hook
- [x] Checkpoint audit for missing decisions/attempts
- [ ] Anonymous opt-in usage telemetry

### 3. User feedback loop
- [ ] 10 real users providing feedback
- [ ] Track which commands are actually used
- [ ] Identify what users ask for vs what we assumed

## Infrastructure (shipped, not promoted)

These features are built and working but hidden from the primary surface until user demand justifies promotion:

- **Deterministic reducer** — computed state from snapshot + event replay
- **Time travel** — HeadMove events, rewind/resume commands
- **Policy engine** — allow/warn/block/require_approval from policy.yaml
- **Capability controls** — role-based gating for high-risk operations
- **Signed approvals** — HMAC-SHA256 signed events
- **Hash chain verification** — tamper-evident ledger across all streams
- **Forensic Explorer** — browser UI with Ledger + Trace views

These will be promoted when enterprise customers ask for them.

## Non-Negotiables
- Append-only immutability
- Local-first (no server required)
- Works with every major AI coding assistant
- Developer-friendly defaults (open, not bureaucratic)

---

*Last updated: 2026-03-16*
