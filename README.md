# Rekall — The ACP Reference Implementation

Your agent just spent 40 minutes re-trying a migration it already proved wouldn't work. You watched it happen. Again.

**Rekall** is the local-first reference implementation of the **Agent Continuity Protocol (ACP)**. It gives AI coding agents a persistent, portable memory of what happened, what failed, and what was decided. 

The next session starts with context, not from zero.

```bash
pip install rekall.tools
cd your-project
rekall init
```

That's it. Every git commit is now auto-checkpointed. Every new session starts with an ACP brief of where you left off.

Works with: **Claude Code** | **Cursor** | **Windsurf** | **Copilot** | **Codex** | **Aider**

---

## What is ACP?

ACP (Agent Continuity Protocol) is a minimal, portable standard for agent session continuity. 

Where MCP standardizes *tool access* for agents, **ACP standardizes *session continuity*** across work sessions. It defines a minimal set of primitives—briefs, checkpoints, decisions, and failed attempts—so that your next agent session starts warm instead of cold.

Read the [ACP v0.1 Spec](docs/acp.md).

## What Happens After `rekall init`

1. **Every git commit** auto-records an ACP checkpoint to the local ledger.
2. **Every session start** auto-injects an ACP brief: last checkpoint, failed attempts (DO NOT RETRY), and pending decisions.
3. **Your agent sees the brief** before it starts working — no cold start amnesia.

No behavior change required. No new commands to learn. It just works.

## The Minimal Commands You'll Actually Use

Rekall implements the core ACP mapping:

```bash
rekall brief                    # Read the ACP Brief (what to work on, what to avoid)
rekall checkpoint --summary "..." --commit auto   # Write an ACP Checkpoint (record a milestone)
rekall log                      # Read the ACP Execution History
```

If something fails, record an ACP Attempt Failed so agents never retry it:
```bash
rekall attempts add <id> --title "Tried X" --evidence "Failed because Y"
```

If you make an architectural decision, record an ACP Decision so agents don't re-debate it:
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
rekall init    # Auto-configures session hooks
```

**Cursor:**
```bash
rekall init    # Auto-configures .cursor/mcp.json and repository rules
```

**Windsurf / Other MCP clients:**
```bash
rekall init
# Then add to MCP settings: rekall serve --store-dir ./project-state
```

**CLI agents (Codex, Aider):**
```bash
rekall init    # Agent reads instructions and natively uses ACP CLI commands
```

## How It Works Under The Hood

Rekall creates a `project-state/` folder in your repo. This is your local ACP runtime—an append-only ledger of continuity events. Your agents read from it automatically. Your git history stays clean.

```text
project-state/
├── project.yaml       # Project metadata
├── manifest.json      # Cryptographic root
├── streams/
│   ├── timeline/      # ACP checkoints and milestones
│   ├── attempts/      # ACP attempts (what failed)
│   └── decisions/     # ACP decisions and rationale
└── ...
```

---

**Star this repo** if this solves a real pain for you.
Follow [@TyReamer](https://x.com/tyreamer) for updates.

`v0.2` — [CHANGELOG.md](CHANGELOG.md) | [ACP Spec](docs/acp.md) | [Docs](docs/) | [Quickstart](docs/QUICKSTART.md)
