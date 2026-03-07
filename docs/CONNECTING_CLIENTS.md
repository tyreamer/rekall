# Connecting Clients to Rekall

Rekall works with any AI coding assistant. The setup depends on how your assistant runs:

- **CLI agents** (Claude Code, Codex, Aider): Run `rekall` commands directly in the terminal. **No MCP server needed.** Just install Rekall, run `rekall init`, and the agent reads `AGENTS.md` for the protocol.
- **IDE agents** (Cursor, Windsurf, Claude Desktop): Connect via MCP (Model Context Protocol). You add a one-time config entry and the IDE auto-launches the server. **You never run `rekall serve` manually.**

## CLI Agents (No Server)

If your agent can execute shell commands, it doesn't need MCP at all:

```bash
pip install rekall.tools
cd your-project
rekall init
rekall agents    # Generates AGENTS.md — the agent reads this for the protocol
```

The agent calls `rekall brief`, `rekall checkpoint`, `rekall session end`, etc. directly.

## IDE Agents (MCP — One-Time Config)

IDE-embedded agents communicate over MCP. You configure your IDE once to auto-launch `rekall serve`:

> **⚠️ Critical: stdout is reserved for JSON-RPC.**
> stdio MCP servers communicate over stdout. Any log or print output written to stdout will corrupt the JSON-RPC stream. If you run Rekall under a wrapper or modify it, ensure all diagnostic logs go to **stderr**.

*Note: depending on how Rekall was installed (e.g., via `pipx`), you may need to provide the absolute path to the `rekall` binary if your client's environment does not inherit your `$PATH`.*

## Validating the MCP Surface

Before connecting a client, test that the Rekall MCP server is correctly exposing its tools and that the surface contract is intact. Use `--server-cmd` to specify exactly how your validator starts the server—this should mirror the command your MCP client would use:

```bash
# Human-readable report
rekall validate --mcp --server-cmd "rekall serve --store-dir ./project-state"

# Strict mode + JSON output (suitable for CI or agent pipelines)
rekall validate --mcp --server-cmd "rekall serve --store-dir ./project-state" --strict --json
```

This command launches the server as a subprocess via stdio, calls `tools/list`, validates all required tool names and schemas, and (optionally) runs safe read-only probe calls.

---

## Agent Entry Point

Once connected, agents should immediately call one of these MCP tools:
- **`session.brief`** — One-call brief: current focus, blockers, failed attempts, pending decisions, and recommended next actions.
- **`project.bootstrap`** — Same as above, but also initializes vault metadata if needed.

Either tool returns everything an agent needs to resume work without reading chat history.

---

## Per-Client Configuration

### Claude Code (CLI — recommended: no MCP)

Claude Code can run shell commands directly, so **MCP is optional**. The simplest setup:

```bash
pip install rekall.tools
cd your-project
rekall init
rekall agents
```

Claude Code reads `AGENTS.md` and calls `rekall brief`, `rekall checkpoint`, etc. in the terminal.

**Optional MCP setup** (if you want MCP tools alongside CLI):
```bash
claude mcp add --transport stdio rekall -- rekall serve --store-dir ./project-state
```

### Cursor (MCP — one-time config)

1. Open Cursor's Settings and search for **MCP**.
2. Click **Add New MCP Server** and select the `stdio` type.
3. Enter the command to run Rekall.

Or add directly to `mcp.json`:
```json
{
  "rekall": {
    "command": "rekall",
    "args": ["serve", "--store-dir", "./project-state"]
  }
}
```

See the [Cursor MCP docs](https://www.cursor.com/blog/mcp) for the current schema and file location.

*(If Cursor cannot find the executable, provide the absolute path, e.g. `~/.local/bin/rekall` or `C:\\Users\\username\\.local\\bin\\rekall`.)*

### Windsurf (MCP — one-time config)

Add the Rekall server in Windsurf's MCP settings:
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

### Codex (CLI — no MCP)

Codex runs shell commands directly. Same setup as Claude Code:
```bash
pip install rekall.tools
cd your-project
rekall init
rekall agents
```

The agent reads `AGENTS.md` and uses CLI commands.

### Other MCP-compatible clients

For any IDE that supports MCP stdio servers, add this config shape:
```json
{
  "mcpServers": {
    "rekall": {
      "command": "rekall",
      "args": ["serve", "--store-dir", "./project-state"],
      "cwd": "/path/to/your/project"
    }
  }
}
```

---

## Windows Installation Note

If you are using **pipx** on Windows:
1. Run `pipx install git+https://github.com/tyreamer/rekall.git`.
2. Ensure pipx is in your PATH by running `pipx ensurepath`.
3. **Important**: You must restart your terminal or IDE after installation for the `rekall` command to be recognized by MCP clients.

## Verifying Claude Code Connection

Once configured, you can verify Rekall is active in **Claude Code**:

1. **Check Status**: Run `claude mcp list` or `claude mcp get rekall`. It should show a green checkmark or "Connected".
2. **In-Session**: Type `/mcp` inside a Claude Code session to see the list of active tools (e.g., `session.brief`, `project.bootstrap`, `rekall_checkpoint`).

## Troubleshooting

### 1. `project-state/` not found
If the server fails to start because the state directory is missing, run:
```bash
rekall init
```
This initializes the required structure and initialization artifacts.

### 2. MCP Failed to Connect
Run the built-in validator to check for protocol or environment issues:
```bash
rekall validate --mcp --server-cmd "rekall serve --store-dir ./project-state"
```

### 3. "Unexpected token" or "Stream corrupted"
This usually happens if something is printing to **stdout** during initialization. Rekall is designed to send all logs to **stderr** during `rekall serve`. If you are using a wrapper script, ensure it does not print any banners or status messages to stdout.
