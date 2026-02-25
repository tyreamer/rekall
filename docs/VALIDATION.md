# Validation & MCP Self-Check

Rekall enforces structural guarantees on load. If your JSONL files are malformed or missing required IDs, `rekall validate` outputs the exact line number of error.

## MCP Self-Check
Verify the MCP server's tool surface is contract-aligned before wiring it into Claude Desktop or any agent runtime:

```bash
# Human-readable report (check/warn/fail per tool)
rekall validate --mcp --server-cmd "python -m rekall.server.mcp_server"

# Machine-readable JSON
rekall validate --mcp --server-cmd "python -m rekall.server.mcp_server" --json

# Strict mode (non-zero exit on any issue)
rekall validate --mcp --server-cmd "python -m rekall.server.mcp_server" --strict
```

### What it checks:
- Launches the server as a subprocess (stdio JSON-RPC)
- Calls `tools/list` and verifies all required tool names exist
- Validates `inputSchema` is valid JSON Schema
- Runs safe read-only probe calls (`project.list`, `work.list`, `exec.query ON_TRACK`)

## State Troubleshooting
- **"Unsupported schema version"**: Ensure `schema-version.txt` exists at the root of the state directory and contains exactly `0.1`.
- **"Work item is claimed"**: If a work item is leased by another actor, you cannot mutate its state until the `lease_until` expires or you use the `force` flag.
