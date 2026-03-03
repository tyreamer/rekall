# AI Assistant Integrations

Rekall is designed to be assistant-agnostic. because it operates as a local-first service with Git hooks and a universal "Skill Pack," it doesn't matter which coding assistant you use.

---

## 1. How it works

1. **The Skill Pack**: `rekall onboard` generates a `rekall_skill.md` file in your vault. This file contains the instructions for any agent to follow.
2. **Integration Rules**: `rekall assistants init` generates IDE-specific instruction files that point back to that skill pack.
3. **The MCP Server**: Your assistant connects via the Rekall MCP server to read/write from the ledger.

---

## 2. Assistant-Specific Setup

### Cursor
- **Files**: `.cursor/rules/rekall.md`
- **What it does**: Tells Cursor to always follow the Rekall protocol and use MCP tools for checkpoints and decisions.

### GitHub Copilot
- **Files**: `.github/copilot-instructions.md`
- **What it does**: Provides a shared instruction set for Copilot Chat and extensions.

### Claude Code (CLI)
- **Files**: `.claude/settings.json`
- **What it does**: Inject custom instructions into the Claude CLI environment.

### Windsurf
- **Files**: `.windsurfrules`
- **What it does**: Native ruleset for the Windsurf IDE.

### Aider / CLI Agents / Humans
- **No specific file needed**.
- **The Safety Net**: Even if your agent doesn't support custom rules, the **Git hooks** (`post-commit` and `pre-push`) ensure that checkpoints are recorded before code is pushed.

---

## 3. Customizing the Instructions

If you want to change what Rekall tells your agents:
1. Edit `project-state/artifacts/rekall_skill.md`.
2. Run `rekall assistants init --force` if you want to regenerate the IDE-specific files with the default instructions.

---

## 4. Turning it off

To stop Rekall from instructing your assistants, simply delete the rule files:
```bash
rm .cursor/rules/rekall.md
rm .github/copilot-instructions.md
rm .claude/settings.json
rm .windsurfrules
```
