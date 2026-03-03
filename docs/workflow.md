# Rekall Workflow Guide

This guide covers the day-to-day habits and configurations for making Rekall the source of truth for your AI execution records.

> **The Rule of Thumb:** After every git commit, run `rekall checkpoint --summary "..." --commit auto`.

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

## 2. Session Tracking & Staleness

Rekall tracks "sessions" via intent anchors. When an agent starts work, it should "resume" or "bootstrap" a session.

### Staleness Warnings
If you (or your agent) start work without a fresh checkpoint, Rekall may warn about "session staleness." This happens if:
- The last checkpoint was too long ago.
- There are multiple git commits that haven't been recorded in the ledger.

You will see these warnings in `rekall status` or when an agent calls `project.bootstrap`.

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
