# Rekall Quickstart

Get persistent agent memory in 2 minutes using the **Agent Continuity Protocol (ACP)**.

## Install the Reference Implementation

```bash
pip install rekall.tools
cd your-project
rekall init
```

This bootstraps ACP in your repo:
- Creates the `project-state/` ACP vault
- Installs an auto-checkpoint git hook (every commit is recorded as an ACP checkpoint)
- Sets up Claude Code session hooks (ACP brief on start)
- Configures Cursor MCP (`.cursor/mcp.json`)
- Generates IDE instruction files for all assistants

## What Happens Next

**Automatically (no action needed):**
- Every git commit creates a Rekall checkpoint
- Every Claude Code session starts with an ACP brief of where you left off

**When you want to:**
```bash
rekall brief                    # See current context anytime (ACP Brief)
rekall checkpoint --summary "..." --commit auto   # Explicit milestone (ACP Checkpoint)
rekall log                      # View execution timeline (ACP Log)
```

**When something fails:**
```bash
rekall attempts add <id> --title "Tried X" --evidence "Failed because Y"
```
Next session the ACP brief will show: **DO NOT RETRY: Tried X**

**When you make a decision:**
```bash
rekall decisions propose --title "Use Postgres" --rationale "..." --tradeoffs "..."
```
Next session the ACP brief will show the pending decision until it's resolved.

## Agent Setup

**Claude Code:** Fully automatic after `rekall init`.

**Cursor:** MCP auto-configured. No manual steps.

**Windsurf:** Add to MCP settings:
```json
{
  "mcpServers": {
    "rekall": { "command": "rekall", "args": ["serve", "--store-dir", "./project-state"] }
  }
}
```

**CLI agents (Codex, Aider):** Agent reads the repo instructions and runs ACP commands natively.

## That's It

Rekall works in the background as your local-first ACP runtime. Your agents start warm. Failed paths aren't retried. Decisions aren't re-debated.

For more: [ACP Spec](acp.md) | [MCP Tools](mcp-tools.md)
