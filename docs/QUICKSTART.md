# Rekall Public Beta Quickstart

Welcome to the Rekall v0.1.X Public Beta! This guide covers the installation, the basic commands to get started, and how to plug Rekall into your AI agents.

## Installation

Rekall is built in Python and can be run locally via `pip`. Ensure you have Python 3.9+ installed.

```bash
git clone https://github.com/your-org/rekall.git
cd rekall
pip install -e .
```

You can now run `rekall --help`.

## Trying the Demo
The easiest way to understand Rekall is to run the interactive demo sequence.
This sets up an isolated environment, injects state data, validates it, and generates a handoff output.

```bash
rekall demo
```

The output will prompt you to run a command similar to:
```bash
cat /tmp/tmp_demo_dir/handoff/boot_brief.md
```

## Running Your Own Project

To initialize an empty project state directory to start tracking your project:
```bash
rekall init ./project-state
```
This creates the canonical `project-state/` folder containing your `project.yaml` and `.jsonl` ledgers.

### 1. Validating State
Whenever you or an agent modifies the JSONL or YAML files, you should run validation:
```bash
rekall validate --store-dir ./project-state --strict
```
This will run a diagnostic on missing schema features, dangling dependencies, schema versions, ID uniqueness, sequence timestamps, and even test for accidental secret exposure.

### 2. Exporting / Importing
To share your project state or checkpoint it to another folder:
```bash
rekall export --store-dir ./project-state --out ./backup-state
```

To ingest an external state artifact from a design partner idempotently:
```bash
rekall import ./partner-state --store-dir ./project-state
```

### 3. Handoff Generation
At the end of a sprint (or before passing context to an agent):
```bash
rekall handoff my-project-id --store-dir ./project-state --out ./handoff-pack
```
This synthesizes a clean `boot_brief.md` giving an executive overview of blocks, attempts, and next steps.

## Connecting the MCP Server
If you use AI agents that support the **Model Context Protocol (MCP)**, you can expose your `project-state/` directly to them as tools!

If you are using Anthropic's Claude Desktop:
```json
{
  "mcpServers": {
    "rekall": {
      "command": "python",
      "args": [
        "-m",
        "rekall.server.mcp_server"
      ],
      "env": {
        "REKALL_STORE_DIR": "/absolute/path/to/your/project-state"
      }
    }
  }
}
```

Now your AI can read project definitions, get active work items, inject new decisions, and post timeline updates safely!
