# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is Rekall?

Rekall is a local-first, append-only project state ledger for AI agents. It gives autonomous agents persistent execution records to prevent repeat loops. All state lives in a `project-state/` vault directory within the repo. Distributed as `rekall.tools` on PyPI.

## Development Setup

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

## Common Commands

```bash
# Run full test suite
pytest tests/ -v

# Run a single test file
pytest tests/test_cli.py -v

# Run a single test
pytest tests/test_cli.py::test_name -v

# Lint
ruff check .

# Type check
mypy src/rekall

# Full verification (run before pushing)
bash scripts/verify.sh            # Unix/Mac
# powershell -ExecutionPolicy Bypass -File scripts/verify.ps1  # Windows

# Smoke test
rekall demo --quiet
```

## Architecture

### Package Layout (`src/rekall/`)

- **`cli.py`** — All CLI commands via argparse. Entry point: `rekall.cli:main`. Every CLI subcommand is a `cmd_*` function. New CLI commands must have tests in `tests/test_cli.py`.
- **`core/state_store.py`** — `StateStore` class: the central data layer. Manages the vault (JSONL ledgers, `manifest.json`, `project.yaml`). Handles append operations, HMAC integrity, secret scanning, optimistic concurrency (`expected_version`), and drift detection.
- **`core/policy.py`** — `PolicyEngine`: rule-based allow/deny checks loaded from `policy.yaml`.
- **`core/brief.py`** — `generate_session_brief()`: the single highest-leverage read operation. One call returns focus, blockers, failed attempts, pending decisions, next actions. Used by `rekall brief`, `session.brief` MCP tool, and `project.bootstrap`.
- **`core/executive_queries.py`** — Structured queries (`ON_TRACK`, `BLOCKERS`, `FAILED_ATTEMPTS`, etc.) against the vault for status reporting.
- **`core/handoff_generator.py`** — Generates "boot briefs" for agent session handoffs.
- **`core/trace_renderer.py`** — Renders execution traces for display.
- **`server/mcp_server.py`** — MCP (Model Context Protocol) server. Exposes vault operations as MCP tools for agent integration. Uses a module-level `StateStore` singleton. Key tools: `session.brief`, `project.bootstrap`, `attempt.append`, `decision.propose`, `rekall_checkpoint`.
- **`server/dashboard.py`** — Web dashboard for vault visualization.

### Key Data Files (in `project-state/`)

- `manifest.json` — Cryptographic root (schema version, HMAC key)
- `project.yaml` — Agent-managed metadata (goal, phase, status, confidence)
- `attempts.jsonl` — Execution ledger (every unit of work)
- `decisions.jsonl` — Architectural tradeoffs
- `activity.jsonl` — High-level work items/milestones
- `timeline.jsonl` — Immutable event log

### Design Invariants

- All ledger records are append-only and tamper-evident (HMAC chains)
- Secret scanning runs on all text fields before writes (`SECRET_PATTERNS` in `state_store.py`)
- YAML/JSONL schemas must match `specs/04_state_spec_schema_v0.1.md`
- The MCP server must never print to stdout (diagnostics go to stderr)
- Python 3.9+ compatibility required; only runtime dependency is `pyyaml`

### Operating Model

See `AGENTS.md` for the assistant-agnostic operating contract. Key separation:
- **CLAUDE.md** = stable dev behavior rules (this file)
- **AGENTS.md** = universal session protocol for any AI assistant
- **Rekall vault** = live execution state (focus, blockers, failed attempts, decisions)

Usage modes (`rekall mode <mode>`): `lite` (minimal), `coordination` (default), `governed` (full).

## Commit Convention

Use conventional-style prefixes: `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `style:`.
