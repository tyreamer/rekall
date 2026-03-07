# Rekall Private Beta Guide

This is a quick guide to help you kick the tires on Rekall. We're looking for feedback on one thing: **Can Rekall help an agent understand your project reality in seconds?**

---

## What to Try (3 tasks)

### Task 1 — Run the Demo (~2 min)

```bash
pip install rekall.tools
rekall demo
```

Open the `boot_brief.md` printed in the output. Read it — this is the executive handoff your agent would receive.

### Task 2 — Initialize & Validate Your Own Project (~3 min)

```bash
rekall init ./project-state
rekall validate ./project-state --strict
```

Both commands should exit cleanly. Try `--json` for machine-readable output.

### Task 3 — Generate a Handoff Pack (~3 min)

```bash
rekall handoff new_project_123 --store-dir ./project-state -o ./pack
```

Open `./pack/boot_brief.md` and `./pack/snapshot.json`. This is what an agent would boot from.

---

## What NOT to Try (out of scope for this beta)

- **No connectors / integrations** — Rekall does not sync with Jira, Notion, or Linear yet.
- **No hosted sync** — Everything is local-first, on-disk.
- **No UI / dashboard** — CLI and MCP server only.
- **No multi-user collaboration** — Single-writer model for now.

---

## How to File Issues

Please use our **[Beta Feedback](https://github.com/tyreamer/rekall/issues/new?template=beta_feedback.yml)** template on GitHub.

| Required artifact | How to get it |
|---|---|
| OS + Python version | `python --version` |
| Rekall version | `v0.1.0-beta.2` (or commit hash) |
| `rekall validate --json` output | `rekall validate ./project-state --strict --json` |
| AI client used | Cursor / Codex / Claude Code / Gemini / Windsurf / CLI only |

**Optional but very helpful:**
- Zip and attach your `project-state/` folder (or at least `schema-version.txt` + all `.jsonl` files)

---

## How to Share Your `project-state/` Folder

```powershell
# PowerShell
Compress-Archive -Path ./project-state -DestinationPath ./project-state.zip

# bash / zsh
zip -r project-state.zip ./project-state
```

Attach the zip to your GitHub issue. The folder contains no secrets by design (Rekall never stores credentials).

---

## Quick Reference

| Command | Purpose |
|---|---|
| `rekall brief --json` | One-call session brief (focus, blockers, failed attempts, decisions, next actions) |
| `rekall session start` | Start a work session with brief |
| `rekall session end --summary "..."` | End session with bypass detection |
| `rekall mode lite\|coordination\|governed` | Set governance level |
| `rekall agents` | Generate AGENTS.md (universal operating contract) |
| `rekall demo` | One-click mocked lifecycle |
| `rekall init` | Bootstrap empty state folder |
| `rekall checkpoint --summary "..." --commit auto` | Log milestone with git commit |
| `rekall validate --strict` | Check invariants |
| `rekall guard` | Preflight drift check |
| `rekall handoff <id> -o ./pack` | Generate boot brief |

---

## Thank You

Your feedback is shaping Rekall. We're optimizing for one thing:  
**Can a brand-new agent boot into your project and immediately do useful work?**

If it can't, tell us why — that's the most valuable signal.
