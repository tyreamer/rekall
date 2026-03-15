# Rekall — Git for AI Execution

Your autonomous agent just spent 47 minutes and $41 re-trying a failed migration it already proved wouldn't work.

Rekall prevents repeat execution loops by giving agents a persistent, local execution record. One folder next to your code. Stop paying for the same mistake twice.

```bash
pip install rekall.tools
rekall init          # Initialize the vault
```

Works with: **Claude Code** | **Cursor** | **Windsurf** | **Copilot** | **Codex** | **Aider** | any MCP client

## The Core Loop

Rekall provides a dead-simple, 6-command surface area designed for daily habit formation:

1. `rekall init` — Set up the append-only ledger in your repository.
2. `rekall brief` — Read current focus, blockers, failed paths (DO NOT RETRY), and next actions.
3. *(Do work...)*
4. `rekall checkpoint` — Record a milestone, task completion, or decision.
5. `rekall log` — View the unified event timeline (checkpoints + attempts + decisions).
6. `rekall verify` — Cryptographically verify the integrity of the ledger.

## How It Works

Rekall has two integration paths depending on your AI coding assistant:

### CLI-based agents (Claude Code, Codex, Aider, terminal tools)
These agents run shell commands directly. No server needed — the agent calls `rekall` commands just like you would.

### IDE-based agents (Cursor, Windsurf, Claude Desktop)
These agents connect to Rekall via MCP (Model Context Protocol). Your IDE auto-launches the server from its config.

**MCP tools available:** `rekall.brief`, `rekall.checkpoint`, `rekall.log`, `rekall.verify`, `rekall.attempt`, `rekall.decision`, `rekall.init`

## Setup by Assistant Type

### Claude Code / Terminal Agents
```bash
pip install rekall.tools
cd your-project
rekall init
```
The agent discovers the vault and runs CLI commands. For MCP support:
```bash
claude mcp add rekall -- rekall serve --store-dir ./project-state
```

### Cursor
```bash
pip install rekall.tools
cd your-project
rekall init    # Auto-generates .cursor/mcp.json
```
Cursor MCP is auto-configured. No manual setup needed.

### Windsurf
```bash
pip install rekall.tools
cd your-project
rekall init
```
Add to your Windsurf MCP settings:
```json
{
  "mcpServers": {
    "rekall": {
      "command": "rekall",
      "args": ["serve", "--store-dir", "./project-state"]
    }
  }
}
```

## The "Aha" Experience (60 Seconds)
Want to see the value immediately? Try this in any repo:

```bash
# 1. Initialize
rekall init

# 2. Get the context (it will be empty, but notice the format)
rekall brief

# 3. Simulate a failure an agent might make
rekall checkpoint --title "Tried migrating to v4" --type attempt_failed --summary "API changed, old auth tokens don't work"

# 4. Read the brief again. The agent will see the DO NOT RETRY warning!
rekall brief

# 5. Review history (shows checkpoints, attempts, and decisions)
rekall log

# 6. Verify ledger integrity
rekall verify

# 7. See local usage stats
rekall stats
```

## Forensic Explorer

Inspect your execution record visually with the built-in Forensic Explorer:

```bash
rekall explorer
```

Opens a local browser UI with two modes:
- **Ledger View** — Dense, filterable event table with keyboard navigation, hash chain verification, and detail panel
- **Lineage View** — SVG causality graph showing event relationships across streams

Features: live auto-refresh, virtual scrolling for large histories, minimap navigation, jump-to-latest shortcuts.

## How State is Stored

Rekall is a local-first, append-only ledger. All data lives in your repository:

```text
project-state/
├── project.yaml       # User-facing metadata (Goal, Phase)
├── manifest.json      # Cryptographic root of the vault
├── streams/
│   ├── timeline/      # Checkpoints, milestones, session events
│   ├── attempts/      # Failed and succeeded attempts
│   ├── decisions/     # Architectural decisions
│   ├── work_items/    # Task state events
│   ├── activity/      # Policy evaluations, approvals
│   └── head_moves/    # Time travel (rewind/resume)
└── snapshot.json      # Computed state snapshot (optional)
```

Every record is tamper-evident and can be cryptographically verified using `rekall verify`.

## Advanced Features

- **Auto-checkpoint on commit:** `rekall hooks install --auto-checkpoint`
- **Time travel:** `rekall rewind --to-timestamp <ts>` + `rekall resume`
- **Policy engine:** allow/warn/block/require_approval rules via `policy.yaml`
- **Capability controls:** Role-based gating for high-risk operations
- **Signed approvals:** HMAC-SHA256 signed approval events

---

**Star this repo** if this solves a real pain for you.
Follow [@TyReamer](https://x.com/tyreamer) for updates.

### Status
`v0.2.0-beta.2` — Private beta. See [CHANGELOG.md](CHANGELOG.md) for details.
