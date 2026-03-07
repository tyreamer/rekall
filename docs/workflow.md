# Rekall Workflow Guide

This guide covers the day-to-day habits and configurations for making Rekall the source of truth for your AI execution records.

> **The Rule of Thumb:** Start with `rekall brief`, checkpoint after tasks, end with `rekall session end`.

---

## 0. Two Integration Paths

Rekall works with any AI coding assistant through two paths:

### CLI agents (Claude Code, Codex, Aider, terminal tools)
These agents run shell commands directly. They call `rekall brief`, `rekall checkpoint`, etc. just like a human would. **No server needed.**

### IDE agents (Cursor, Windsurf, Claude Desktop)
These agents can't run shell commands — they communicate via MCP (Model Context Protocol). Your IDE auto-launches `rekall serve` from its config file. The agent calls MCP tools like `session.brief` and `rekall_checkpoint` instead of CLI commands. **You never run `rekall serve` manually.**

The session lifecycle is the same either way — only the calling mechanism differs.

---

## 1. Git Hooks

Rekall can automate reminders and safety checks via Git hooks.

### Installation
```bash
rekall hooks install
```
This installs:
- **post-commit**: Prints a reminder to run `rekall checkpoint` after every commit.
- **pre-push**: Checks if your recent commits have been checkpointed. If too many are missing, it warns you.

### Enforcement
If you want to *forbid* pushing code that hasn't been checkpointed:
```bash
rekall hooks install --enforce
```
This will cause `git push` to fail if the number of uncheckpointed commits exceeds the threshold (default: 1).

### Uninstallation
```bash
rekall hooks uninstall
```

---

## 2. Session Lifecycle

Rekall provides a lightweight session protocol for agents and humans.

### Starting a Session
```bash
rekall session start    # Shows brief + starts tracking
# or just:
rekall brief            # One-call: focus, blockers, failed paths, next actions
```

Via MCP, agents can call `session.brief` or `project.bootstrap` (which now includes the full brief).

### Ending a Session
```bash
rekall session end --summary "Implemented JWT auth, tests passing, DB migration still blocked"
```

This records a handoff note in the timeline and runs **bypass detection**, warning about:
- Uncheckpointed git commits
- In-progress work with no recorded attempts
- Unresolved pending decisions

### Staleness Warnings
If you start work without a fresh checkpoint, Rekall warns about "session staleness." This happens if:
- The last checkpoint was too long ago.
- There are multiple git commits that haven't been recorded in the ledger.

You will see these warnings in `rekall brief` or when an agent calls `session.brief`.

### Usage Modes
Set with `rekall mode <mode>`:
- **`lite`** — Checkpoint at session boundaries only. For small or low-risk repos.
- **`coordination`** (default) — Log decisions and attempts. Checkpoint after each task.
- **`governed`** — Full governance. Mandatory checkpoints. Human approvals required for high-risk actions.

---

## 3. The Checkpoint Tool

The `checkpoint` command is your primary way to sync Git history with the Rekall ledger.

### Examples

**Log a task completion:**
```bash
rekall checkpoint --type task_done --title "Implemented Auth" --summary "Added JWT and login route." --commit auto
```

**Log a decision:**
```bash
rekall checkpoint --type decision --title "Switched to SQLite" --summary "Postgres was overkill for this phase." --commit auto
```

**Log an artifact:**
```bash
rekall checkpoint --type artifact --title "Architecture Diagram" --summary "Uploaded to S3: s3://bucket/arch.png"
```

### When to log vs. When to pause
- **Log (Checkpoint)**: Use this for **history**. If you finished a feature, fixed a bug, or made a choice you're confident in, just log it.
- **Pause (Approval)**: Use the `decisions` MCP tool (or `rekall decide` flow) when you need **permission**. If an action is high-risk or the agent is unsure, it should stop and wait for a human.

---

## 4. Troubleshooting

### How to disable Rekall temporarily
If Rekall is blocking your workflow (e.g., pre-push checks failing) and you need to move fast:
1. Uninstall hooks: `rekall hooks uninstall`.
2. Delete the `project-state/` folder (Warning: this loses your execution history).
3. Use `--no-verify` on git commands if you don't want to uninstall hooks.

### Common Issues
- **"Corrupted state files"**: Run `rekall doctor` to identify malformed JSONL files.
- **"Secret detected"**: Rekall's safety layer blocked a log containing a potential API key. Redact the secret and try again.
