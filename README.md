# Rekall — Stop paying for the same mistake twice

Your autonomous agent just spent 47 minutes and $41 re-trying a failed migration it already proved wouldn't work.

Rekall prevents repeat execution loops by giving agents a persistent, local execution record. No server. No UI. One folder next to your code.

```bash
pip install rekall.tools
rekall init          # Initialize the vault
rekall agents        # Generate AGENTS.md (universal operating contract)
```

## How It Works

Rekall has two integration paths depending on your AI coding assistant:

### CLI-based agents (Claude Code, Codex, Aider, terminal tools)

These agents run shell commands directly. No server needed — the agent calls `rekall` commands just like you would.

### IDE-based agents (Cursor, Windsurf, Claude Desktop)

These agents can't run shell commands. They connect to Rekall via MCP (Model Context Protocol), a JSON-RPC bridge that exposes the same operations as tools. Your IDE auto-launches the server from its config — **you never run `rekall serve` manually**.

## Setup by Assistant Type

### Claude Code (CLI — no server needed)

```bash
# One-time setup
pip install rekall.tools
cd your-project
rekall init
rekall agents
```

That's it. Claude Code reads `AGENTS.md` and runs `rekall` commands directly in the terminal.

### Cursor / Windsurf (MCP — one-time config)

```bash
# One-time setup
pip install rekall.tools
cd your-project
rekall init
rekall agents
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

Your IDE auto-launches the server. See [Connecting Clients](docs/CONNECTING_CLIENTS.md) for full details.

### Codex / Other Terminal Agents

Same as Claude Code — install, `rekall init`, `rekall agents`. The agent reads `AGENTS.md` and runs CLI commands.

## The Session Lifecycle

Regardless of which agent you use, the workflow is the same:

```
rekall brief              → Agent reads: focus, blockers, failed paths, next actions
# ... agent works ...
rekall checkpoint ...     → Agent logs milestones and decisions
rekall session end ...    → Agent records handoff note + bypass detection
```

> **Rule of thumb:** start with `rekall brief`, checkpoint after tasks, end with `rekall session end`.

More: [docs/workflow.md](docs/workflow.md)

> [!IMPORTANT]
> **Rekall does not modify your agent config files** (CLAUDE.md, Cursor rules, etc.). Run `rekall agents` to generate an `AGENTS.md` file that any coding assistant can discover. Run `rekall assistants init` for IDE-specific instruction files.

---

## Decisions vs. Approvals (Breakpoints)

To eliminate UX confusion, Rekall distinguishes between continuous logging and gated permissions:

### 1. Decision Records (Agent-Logged)
Agents document their own architectural tradeoffs and logic changes automatically. These are appended to `decisions.jsonl` for a permanent audit trail.
*   **Actor**: Agent
*   **Frequency**: High (Continuous history)
*   **CLI**: `rekall status` to view history.

### 2. Approvals & Breakpoints (Human-Gated)
When an agent reaches an ambiguity or a high-risk action, it generates a `decision_id` and pauses execution.
*   **Actor**: Human
*   **Frequency**: Low (Exception handling)
*   **CLI**: `rekall decide <id> --option "..."` then `rekall resume`.

**Rule of Thumb**: Decisions are for **history**; Approvals are for **permission**.

---

## Agent-Owned Metadata

In Rekall, the agent is responsible for maintaining the project's altitude. Metadata like **Goal**, **Phase**, **Status**, and **Confidence** are stored in `project-state/project.yaml`.

*   Humans can override these via `rekall meta set`, but in a healthy loop, the agent maintains them via MCP (`project.bootstrap` or `project.meta.patch`).
*   The human's role is to **govern** the state via `rekall status`, not to micromanage the YAML.

---

## How the State is Stored

Rekall is a local-first, git-portable, append-only ledger. All data lives in your repository:

```text
project-state/
├── project.yaml       # Agent-managed metadata (Goal, Phase, Status)
├── manifest.json      # Cryptographic root of the vault
├── activity.jsonl     # High-level work items and milestones
├── attempts.jsonl     # The "Execution Ledger": every unit of work tried
├── decisions.jsonl    # Architectural tradeoffs and logic changes
└── timeline.jsonl     # Immutable event log of all state changes
```

Every record is tamper-evident and can be cryptographically verified using `rekall verify`.

---

## Command Reference

### Session commands (agent workflow)

| Command | Purpose |
| :--- | :--- |
| `rekall brief` | One-call read: focus, blockers, failed paths, pending decisions, next actions. Add `--json` for machine output. |
| `rekall session start` | Same as `brief`, but also starts session tracking (drift detection). |
| `rekall session end --summary "…"` | Record handoff note + run bypass detection (uncheckpointed commits, pending decisions). |

### Logging commands (during work)

| Command | Purpose |
| :--- | :--- |
| `rekall checkpoint --summary "…"` | Record a milestone, task completion, or decision. Add `--commit auto` to attach a git commit. |
| `rekall guard` | Preflight check: goals, risks, constraints, recent work. |
| `rekall decide <id> --option "…"` | Grant/deny permission for a pending human approval. |

### Configuration commands (one-time or rare)

| Command | Purpose |
| :--- | :--- |
| `rekall init` | Create a fresh `project-state/` vault in the current directory. |
| `rekall agents` | Generate `AGENTS.md` — the universal operating contract for any AI assistant. |
| `rekall mode <mode>` | Set usage mode: `lite`, `coordination`, or `governed`. |
| `rekall hooks install` | Install git hooks for checkpoint reminders. Add `--enforce` to block pushes. |
| `rekall serve` | Launch the MCP server. **Only used by IDE configs — never run manually.** |

### Remote sync (optional)

| Command | Purpose |
| :--- | :--- |
| `rekall sync` | Push unsynced vault events to a remote Rekall Hub. |

Sync is optional and additive. Configure via environment variables:

```bash
export REKALL_HUB_URL=https://your-hub.example.com
export REKALL_HUB_TOKEN=your-bearer-token
export REKALL_HUB_ORG_ID=your-org  # optional, defaults to 'default'
```

When configured, sync also runs automatically on `rekall session end` and `rekall checkpoint`.

### Diagnostic commands

| Command | Purpose |
| :--- | :--- |
| `rekall status` | Executive summary of current project state. |
| `rekall validate --strict` | Check vault invariants. Add `--mcp` to test the MCP surface. |
| `rekall verify` | Cryptographic integrity check of the ledger. |
| `rekall demo` | Run a mocked project lifecycle to see Rekall in action. |

---

## Ready to give your agents an execution record?

```bash
# Install directly from PyPI
pip install rekall.tools

# Run the mocked demo
rekall demo
```

⭐ **Star this repo** if this solves a real pain for you.  
🐦 **Follow [@TyReamer](https://x.com/tyreamer)** for updates and beta announcements.

---

### Status
`v0.1.0-beta.2` — Private beta. See [CHANGELOG.md](CHANGELOG.md) for details.
