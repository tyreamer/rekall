# Connecting Clients to Rekall

Rekall implements the Model Context Protocol (MCP) to seamlessly provide project context, decisions, and constraints to AI coding assistants. This guide explains how to start the server, validate your setup, and configure popular agents to use Rekall.

## Running the Server

To expose the Rekall workspace to an agent, start the server. By default, MCP clients communicate via standard input/output (stdio).

Run the following command in your project directory:

```bash
rekall serve --store-dir ./project-state
```

*Note: depending on how Rekall was installed (e.g., via `pipx`), you may need to provide the absolute path to the `rekall` binary if your client's environment does not inherit your `$PATH`.*

> **⚠️ Critical: stdout is reserved for JSON-RPC.**  
> stdio MCP servers communicate over stdout. Any log or print output written to stdout will corrupt the JSON-RPC stream. If you run Rekall under a wrapper or modify it, ensure all diagnostic logs go to **stderr**.

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

## Client Configuration

Below are the configuration steps for popular AI coding clients. Because each client manages its MCP config differently, refer to the linked official documentation for the most current setup surface.

### Codex App

> **Conceptual steps only.** Codex App's MCP configuration surface may vary by version. Refer to the [Codex MCP documentation](https://platform.openai.com/docs/guides/tools) for current config format.

**Conceptual Steps:**
1. Open the Codex app settings.
2. Navigate to the **MCP** or **Integrations** section.
3. Add a new server using the `stdio` transport.
4. Set the executable to `rekall` and arguments to `serve --store-dir ./project-state`.

**Illustrative config shape** *(not necessarily the exact file format)*:
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

### Cursor

**Conceptual Steps:**
1. Open Cursor's Settings and search for **MCP**.
2. Click **Add New MCP Server** and select the `stdio` type.
3. Enter the command to run Rekall.

Cursor also supports file-based config via `mcp.json` for stdio servers—see the [Cursor MCP docs](https://www.cursor.com/blog/mcp) for the current schema and file location. If the UI config is unreliable, using `mcp.json` directly is a more stable escape hatch.

**Example entry for `mcp.json`:**
```json
{
  "rekall": {
    "command": "rekall",
    "args": ["serve", "--store-dir", "./project-state"]
  }
}
```

*(If Cursor cannot find the executable, provide the absolute path, e.g. `~/.local/bin/rekall` or `C:\\Users\\username\\.local\\bin\\rekall`.)*

### Claude Code

**Conceptual Steps:**
1. Open your terminal where you plan to use Claude Code.
2. Register the Rekall server using the Claude CLI (it connects via stdio on launch).

**Example Command:**
```bash
claude mcp add --transport stdio rekall -- rekall serve --store-dir ./project-state
```

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

---

## Windows Installation Note

If you are using **pipx** on Windows:
1. Run `pipx install git+https://github.com/tyreamer/rekall.git`.
2. Ensure pipx is in your PATH by running `pipx ensurepath`.
3. **Important**: You must restart your terminal or IDE after installation for the `rekall` command to be recognized by MCP clients.

## Verifying Claude Code Connection

Once configured, you can verify Rekall is active in **Claude Code**:

1. **Check Status**: Run `claude mcp list` or `claude mcp get rekall`. It should show a green checkmark or "Connected".
2. **In-Session**: Type `/mcp` inside a Claude Code session to see the list of active tools (e.g., `project.list`, `rekall.exec.query`).

## Troubleshooting

### 1. `project-state/` not found
If the server fails to start because the state directory is missing, run:
```bash
rekall init
```
This initializes the required structure and onboarding artifacts.

### 2. MCP Failed to Connect
Run the built-in validator to check for protocol or environment issues:
```bash
rekall validate --mcp --server-cmd "rekall serve --store-dir ./project-state"
```

### 3. "Unexpected token" or "Stream corrupted"
This usually happens if something is printing to **stdout** during initialization. Rekall is designed to send all logs to **stderr** during `rekall serve`. If you are using a wrapper script, ensure it does not print any banners or status messages to stdout.
