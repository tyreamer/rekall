# Rekall — The ACP Reference Implementation

Your agent just spent 40 minutes re-trying a migration it already proved wouldn't work. You watched it happen. Again.

**Rekall** is the local-first reference implementation of the **Agent Continuity Protocol (ACP)**. 

While ACP defines the underlying data contract for continuity, **Rekall provides the developer-friendly UX**. It gives AI coding agents a persistent memory of what happened, what failed, and what was decided, so the next session starts with context instead of amnesia.

```bash
pip install rekall.tools
cd your-project
rekall init
```

That's it. Every git commit is now auto-checkpointed. Every new session starts with a warm boot.

Works with: **Claude Code** | **Cursor** | **Windsurf** | **Copilot** | **Codex** | **Aider**

---

## What is ACP?

Where MCP standardizes tool access, **ACP standardizes session continuity**. 

ACP is **not** a CLI or a menu of commands. It is a minimal, open data contract composed of two parts:
1. **The ACP Context Envelope:** What an agent reads at boot (failed paths, decisions, recent milestones).
2. **The ACP Event Envelope:** What an agent writes during execution (checkpoints, failed attempts).

Read the [ACP v0.1 Spec](docs/acp.md).

## Rekall: The UX for ACP

Rekall provides the implementation layer on top of the ACP contract. 

**Automatically (no action needed):**
1. **Every git commit** appends an ACP `checkpoint` event to the local ledger.
2. **Every session start** materializes the event stream into an ACP Context Envelope and injects it into the agent's prompt. 

**The CLI UX:**
```bash
rekall brief                    # Renders the current ACP Context Envelope
rekall checkpoint --summary "."   # Appends an ACP 'checkpoint' Event
rekall log                      # Renders the chronological history of ACP Events
```

If something fails, record it so agents never retry it:
```bash
rekall attempts add <id> --title "Tried X" --evidence "Failed because Y"
```

If you make an architectural decision, record it so agents don't re-debate it:
```bash
rekall decisions propose --title "Use Postgres" --rationale "..."
```

## Setup by Agent Type

**Claude Code:** Fully automatic session hooks (`rekall init`).
**Cursor:** MCP auto-configured repository rules (`rekall init`).
**Windsurf / Other MCP clients:** Add `rekall serve --store-dir ./project-state` to MCP settings.
**CLI agents (Codex, Aider):** Agents read the repo instructions and run native commands.

## How It Works Under The Hood

Rekall creates a `project-state/` folder in your repo. This is your local ACP event stream. Your git history stays clean, and your agents always start warm.

---

**Star this repo** if this solves a real pain for you.
Follow [@TyReamer](https://x.com/tyreamer) for updates.

`v0.2` — [CHANGELOG.md](CHANGELOG.md) | [ACP Spec](docs/acp.md) | [Docs](docs/) | [Quickstart](docs/QUICKSTART.md)
