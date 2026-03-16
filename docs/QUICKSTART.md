# Rekall Quickstart

Get persistent agent memory in 2 minutes.

## Install

```bash
pip install rekall.tools
cd your-project
rekall init
```

This does everything:
- Creates the `project-state/` vault
- Installs auto-checkpoint git hook (every commit recorded)
- Sets up Claude Code session hooks (brief on start, audit on end)
- Configures Cursor MCP (`.cursor/mcp.json`)
- Generates IDE instruction files for all assistants

## What Happens Next

**Automatically (no action needed):**
- Every git commit creates a Rekall checkpoint
- Every Claude Code session starts with a brief of where you left off
- Every session end audits for missing recordings

**When you want to:**
```bash
rekall brief                    # See current context anytime
rekall checkpoint --summary "..." --commit auto   # Explicit milestone
rekall log                      # View execution timeline
```

**When something fails:**
```bash
rekall attempts add <id> --title "Tried X" --evidence "Failed because Y"
```
Next session will show: **DO NOT RETRY: Tried X**

**When you make a decision:**
```bash
rekall decisions propose --title "Use Postgres" --rationale "..." --tradeoffs "..."
```
Next session will show the pending decision until it's resolved.

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

**CLI agents (Codex, Aider):** Agent reads `AGENTS.md` and runs commands directly.

## That's It

Rekall works in the background. Your agents start warm. Failed paths aren't retried. Decisions aren't re-debated.

For more: [Beta Guide](BETA.md) | [MCP Tools](mcp-tools.md)
