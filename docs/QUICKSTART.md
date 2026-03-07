# Rekall Quickstart

Get a verifiable AI execution record running in 5 minutes.

## Prerequisites
- Python 3.10+
- A virtual environment (`venv`) is recommended, or use `pipx`.

## Install

### Task 1 — Run the Demo (~2 min)

```bash
pip install rekall.tools
rekall demo
```

*(Optional: Use `pipx install .` for global CLI wrapper usage).*

## The 5-Minute Tour

### 1. Initialize
```bash
cd /path/to/your-repo
rekall init
```
This creates a `project-state/` vault folder.

### 2. Get a Session Brief
```bash
rekall brief
```
One call returns: current focus, blockers, failed attempts (paths not to retry), pending decisions, and recommended next actions. On a fresh vault this will be empty — that's expected.

### 3. Start a Session
```bash
rekall session start
```
Same as `brief`, but also starts session tracking (drift detection).

### 4. Generate the Operating Contract
```bash
rekall agents
```
This creates `AGENTS.md` at your repo root — a universal protocol that any AI assistant (Claude Code, Cursor, Codex, Gemini, Windsurf) can discover and follow.

### 5. Connect Your Agent

**CLI agents (Claude Code, Codex, Aider):** You're done — the agent reads `AGENTS.md` and runs `rekall` commands directly.

**IDE agents (Cursor, Windsurf):** Add a one-time MCP config entry. See [Connecting Clients](CONNECTING_CLIENTS.md). Your IDE auto-launches the server — you never run `rekall serve` manually.

### 6. End the Session
```bash
rekall session end --summary "Initialized Rekall, ready for first task"
```
This records a handoff note and warns about any bypass patterns.

---

## Advanced Operations
- **`rekall checkpoint`**: Record milestones and task completions with optional git commit attachment.
- **`rekall guard`**: Preflight check for constraints, decisions, risks, and blockers.
- **`rekall mode lite|coordination|governed`**: Set usage mode (lightweight vs full governance).
- **`rekall export`**: Create a portable state artifact snapshot.
- **`rekall verify`**: Check cryptographic integrity of the ledger.

## What you just got
- **`project-state/` folder**: A portable execution ledger (YAML/JSONL files) that agents can read and write.
- **`AGENTS.md`**: A universal operating contract for any AI assistant.
- **Session brief**: One-call working context that's faster than reading chat history or MEMORY.md.

## Next Steps
- Read [Beta Guide](BETA.md) for what to try and how to report issues.
- Read [Connecting Clients](CONNECTING_CLIENTS.md) to wire up Claude Code, Cursor, or Codex.
