# Rekall Quickstart

Get a verifiable AI execution record running in 5 minutes.

## Prerequisites
- Python 3.10+

## Install

```bash
pip install rekall.tools
```

## The 5-Minute Tour

### 1. Initialize
```bash
cd /path/to/your-repo
rekall init
```
This creates:
- `project-state/` vault folder
- `AGENTS.md` operating contract
- IDE instruction files (`.cursor/mcp.json`, `CLAUDE.md`, `.windsurfrules`, etc.)

### 2. Get a Session Brief
```bash
rekall brief
```
Returns: current focus, blockers, failed attempts (DO NOT RETRY), pending decisions, and usage stats. Fresh vaults show a quick-start guide.

### 3. Do Work, Checkpoint Progress
```bash
# After completing something meaningful:
rekall checkpoint --summary "Implemented auth flow" --commit auto
```

### 4. Record Failures (So Agents Don't Repeat Them)
```bash
rekall attempts add <work-item-id> --title "Tried SQLite for analytics" --evidence "Too slow at 10k rows"
```
Next time an agent runs `rekall brief`, it will see: **DO NOT RETRY: Tried SQLite for analytics**

### 5. View History
```bash
rekall log          # Unified timeline: checkpoints + attempts + decisions
rekall stats        # Usage metrics: checkpoints, retries prevented, tokens saved
rekall verify       # Cryptographic integrity check
```

### 6. Forensic Explorer
```bash
rekall explorer     # Opens browser at http://127.0.0.1:7700
```
Two views, one record:
- **Ledger** — dense event table with filters, search, keyboard nav (`j`/`k`/`Enter`/`/`)
- **Trace** — causal neighborhood graph (press `t` to toggle, adjust depth 1/2/3)

Filter by time (1h/24h/7d/30d) or type (Checkpoints/Attempts/Decisions). Both views stay in sync.

---

## Connect Your Agent

**Claude Code:** Already works via CLI. For MCP:
```bash
claude mcp add rekall -- rekall serve --store-dir ./project-state
```

**Cursor:** Auto-configured. `rekall init` generates `.cursor/mcp.json`.

**Windsurf:** Add to MCP settings:
```json
{
  "mcpServers": {
    "rekall": { "command": "rekall", "args": ["serve", "--store-dir", "./project-state"] }
  }
}
```

**CLI agents (Codex, Aider):** Just run `rekall init`. The agent reads `AGENTS.md`.

## Auto-Checkpoint on Git Commit

```bash
rekall hooks install --auto-checkpoint
```
Every `git commit` silently records a Rekall checkpoint. Zero behavior change.

## What You Get
- **`project-state/`** — Portable, append-only execution ledger
- **`AGENTS.md`** — Universal protocol for any AI assistant
- **Session brief** — One-call context that prevents repeat failures
- **Hash chain verification** — Every event is tamper-evident

## Next Steps
- Read [Beta Guide](BETA.md) for what to try and how to report issues.
- Read [MCP Tools Reference](mcp-tools.md) for the full tool API.
- Read [Connecting Clients](CONNECTING_CLIENTS.md) for detailed IDE setup.
