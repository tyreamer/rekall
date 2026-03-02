# Rekall — Stop paying for the same mistake twice

Your autonomous agent just spent 47 minutes and $41 re-trying a failed migration it already proved wouldn't work.

Rekall prevents repeat execution loops by giving agents a persistent, local execution record. No server. No UI. One folder next to your code.

```bash
pip install rekall.tools
rekall init          # Initialize the vault
rekall serve         # Connect your agent via MCP
```

## The Flow
1. **Initialize**: `rekall init` creates the `project-state/` vault.
2. **Connect**: Link your agent (Claude, Cursor, etc.) via the Rekall MCP server.
3. **Automate**: The agent logs every attempt and architectural decision to the ledger.
4. **Approve**: If the agent hits a high-risk breakpoint, it pauses and requests human approval.
5. **Resume**: You grant permission via `rekall decide <id>`, and the agent continues.

> [!IMPORTANT]
> **Rekall does not modify your agent config files** (CLAUDE.md, Cursor rules, etc.). It exposes MCP tools and provides an optional `skill.md` pack you can manually reference in your agent's instructions.

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

## Core Commands

| Command | Usage |
| :--- | :--- |
| `init` | Create a fresh vault and skill pack. |
| `serve` | Launch the MCP server for agent integration. |
| `status` | Get an executive summary of the current state. |
| `guard` | Preflight check for agents: goals, risks, and recent work. |
| `decide` | Grant/deny permission for a pending approval. |
| `resume` | Signal the agent to continue after an approval. |
| `verify` | Check the cryptographic integrity of the ledger. |
| `blockers` | List active blockers preventing progress. |
| `demo` | Run a mocked project lifecycle to see Rekall in action. |

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
`v0.1.0-beta.1` — Private beta (2026-03-02). See [CHANGELOG.md](CHANGELOG.md) for details.
