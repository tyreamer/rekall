# Rekall — Git for AI Execution

Your autonomous agent just spent 47 minutes and $41 re-trying a failed migration it already proved wouldn't work.

Rekall prevents repeat execution loops by giving agents a persistent, local execution record. No server. No UI. One folder next to your code. Stop paying for the same mistake twice.

```bash
pip install rekall.tools
rekall init          # Initialize the vault
```

## The Core Loop (v0.2)
Rekall provides a dead-simple, 6-command surface area designed for daily habit formation:

1. `rekall init` — Set up the append-only ledger in your repository.
2. `rekall brief` — Read current focus, blockers, failed paths (DO NOT RETRY), and next actions.
3. *(Do work...)*
4. `rekall checkpoint` — Record a milestone, task completion, or decision.
5. `rekall log` — View the event timeline (looks like `git log`).
6. `rekall verify` — Cryptographically verify the integrity of the ledger.

**(Optional: `rekall serve` to launch the MCP server for IDEs)**

## How It Works

Rekall has two integration paths depending on your AI coding assistant:

### CLI-based agents (Claude Code, Codex, Aider, terminal tools)
These agents run shell commands directly. No server needed — the agent calls `rekall` commands just like you would.

### IDE-based agents (Cursor, Windsurf, Claude Desktop)
These agents can't run shell commands. They connect to Rekall via MCP (Model Context Protocol). Your IDE auto-launches the server from its config — **you never run `rekall serve` manually**.

## Setup by Assistant Type

### Claude Code / Terminal Agents
```bash
pip install rekall.tools
cd your-project
rekall init
```
The agent discovers the vault and runs CLI commands.

### Cursor / Windsurf (MCP)
```bash
pip install rekall.tools
cd your-project
rekall init
```
Then add this to your MCP config (Cursor: `mcp.json`, Windsurf: settings):
```json
{
  "rekall": {
    "command": "rekall",
    "args": ["serve", "--store-dir", "./project-state"]
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

# 5. Review history
rekall log

# 6. Verify ledger integrity
rekall verify
```

## How State is Stored

Rekall is a local-first, append-only ledger. All data lives in your repository:

```text
project-state/
├── project.yaml       # User-facing metadata (Goal, Phase)
├── manifest.json      # Cryptographic root of the vault
├── timeline.jsonl     # Append-only ledger of all events
└── ... (internal derived streams for work items and decisions)
```

Every record is tamper-evident and can be cryptographically verified using `rekall verify`.

---

⭐ **Star this repo** if this solves a real pain for you.  
🐦 **Follow [@TyReamer](https://x.com/tyreamer)** for updates and beta announcements.

### Status
`v0.2.0-beta.1` — Private beta. See [CHANGELOG.md](CHANGELOG.md) for details.
