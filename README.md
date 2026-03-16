# Rekall — Stop AI Agents From Repeating Failed Work

Your agent just spent 40 minutes re-trying a migration it already proved wouldn't work. You watched it happen. Again.

Rekall gives AI agents a persistent memory of what happened, what failed, and what was decided. Next session starts with context, not from zero.

```bash
pip install rekall.tools
cd your-project
rekall init
```

That's it. Every git commit is now auto-checkpointed. Every new session starts with a brief of where you left off.

Works with: **Claude Code** | **Cursor** | **Windsurf** | **Copilot** | **Codex** | **Aider**

## What Happens After `rekall init`

1. **Every git commit** auto-records a checkpoint to the Rekall ledger
2. **Every session start** auto-injects context: last checkpoint, failed attempts (DO NOT RETRY), pending decisions
3. **Your agent sees the brief** before it starts working — no cold start

No behavior change required. No new commands to learn. It just works.

## The Commands You'll Actually Use

```bash
rekall brief                    # What to work on, what to avoid
rekall checkpoint --summary "..." --commit auto   # Record a milestone
rekall log                      # View the execution timeline
```

If something fails, record it so agents never retry it:
```bash
rekall attempts add <id> --title "Tried X" --evidence "Failed because Y"
```

If you make an architectural decision, record it so agents don't re-debate it:
```bash
rekall decisions propose --title "Use Postgres" --rationale "..." --tradeoffs "..."
```

## The 60-Second Demo

```bash
pip install rekall.tools
cd your-project
rekall init

# Simulate a failure
rekall checkpoint --title "Tried SQLite for analytics" --type attempt_failed --summary "Too slow at 10k rows"

# Now read the brief — the agent will see DO NOT RETRY
rekall brief
```

## Setup by Agent Type

**Claude Code:**
```bash
rekall init    # Auto-configures hooks + .claude/settings.json
```

**Cursor:**
```bash
rekall init    # Auto-configures .cursor/mcp.json + rules
```

**Windsurf / Other MCP clients:**
```bash
rekall init
# Add to MCP settings: rekall serve --store-dir ./project-state
```

**Any CLI agent (Codex, Aider):**
```bash
rekall init    # Agent reads AGENTS.md + runs rekall commands
```

## How It Works

Rekall creates a `project-state/` folder in your repo — an append-only ledger of checkpoints, attempts, and decisions. Every record is hash-chained. Your agents read from it. Your git history stays clean.

```text
project-state/
├── project.yaml       # Project metadata
├── manifest.json      # Cryptographic root
├── streams/
│   ├── timeline/      # Checkpoints and milestones
│   ├── attempts/      # What was tried (and what failed)
│   └── decisions/     # Architectural choices with rationale
└── ...
```

---

**Star this repo** if this solves a real pain for you.
Follow [@TyReamer](https://x.com/tyreamer) for updates.

`v0.2` — [CHANGELOG.md](CHANGELOG.md) | [Docs](docs/) | [Beta Guide](docs/BETA.md)
