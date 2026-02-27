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
| Rekall version | `v0.1.0-beta.1` (or commit hash) |
| `rekall validate --json` output | `rekall validate ./project-state --strict --json` |
| AI client used | Cursor / Codex / Claude Code / Antigravity / CLI only |

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
| `rekall demo` | One-click mocked lifecycle |
| `rekall init ./project-state` | Bootstrap empty state folder |
| `rekall validate ./project-state --strict` | Check invariants |
| `rekall validate ./project-state --strict --json` | Machine-readable diagnostics |
| `rekall handoff <id> --store-dir ./project-state -o ./pack` | Generate boot brief |
| `rekall guard --store-dir ./project-state` | Preflight drift check |
| `rekall checkpoint <id> -o ./checkpoints/save1 --store-dir ./project-state` | Save-game |

---

## Thank You

Your feedback is shaping Rekall. We're optimizing for one thing:  
**Can a brand-new agent boot into your project and immediately do useful work?**

If it can't, tell us why — that's the most valuable signal.
