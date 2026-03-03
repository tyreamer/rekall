# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0-beta.2] - 2026-03-02

### Added
- **Git hooks support**: Added `rekall hooks install` to provide post-commit reminders and pre-push safety checks.
- **One-call checkpoint**: The `rekall checkpoint` command and MCP tool now support a unified `--commit auto` flow to sync progress and Git history in a single step.
- **Session staleness warnings**: Added session tracking to detect when an agent starts work without a fresh checkpoint or bootstrap.
- **Assistant setup files generator**: Added `rekall assistants init` to automatically create IDE-specific instruction files for Cursor, Copilot, Claude, and Windsurf.

## [0.1.0-beta.1] - 2026-02-25

### Added
- **`rekall guard`**: Drift guard / preflight check. Surfaces project constraints, recent decisions, recent attempts, risks/blockers, and operational environment. Supports `--strict`, `--json`, and `--emit-timeline`.
- **`rekall checkpoint`**: Local "save game" — exports full state folder + appends a `milestone` timeline event. Supports `--label` and `--event-id` for idempotent re-runs.
- **Idempotency keys**: Optional `idempotency_key` on `attempt.append`, `timeline.append`, and `decision.propose` to prevent duplicate high-impact actions.
- **MCP self-check**: `rekall validate --mcp --server-cmd "..."` launches server as subprocess, validates `tools/list`, schemas, and runs read-only probe calls.
- **`rekall validate` positional arg**: `rekall validate ./project-state` now works (positional store_dir, matches `init` UX).
- **CLI sub-commands**: `rekall attempts add`, `rekall decisions propose`, `rekall timeline add` with `--idempotency-key`.
- **Beta feedback issue template**: Structured GitHub template enforcing OS, Python version, client, and `validate --json` output.
- **`docs/BETA.md`**: One-page beta guide — 3 tasks, out-of-scope list, filing instructions.
- **CI matrix**: GitHub Actions on `ubuntu-latest`, `macos-latest`, `windows-latest` × Python 3.10–3.13 with `rekall demo` smoke test.

### Changed
- `rekall demo` output now includes `rekall guard` recommendation as next step.
- `QUICKSTART.md` tightened for the 5-minute success path.

## [0.1.0] - 2026-02-25

### Added
- **Core CLI Utility**: A standalone `rekall` CLI enabling validation, state inspection, and manipulation.
  - `rekall init`: Bootstraps an empty `project-state/` folder.
  - `rekall validate`: Runs an invariant check and verification scan. Includes `--strict` mode and `--json` outputs.
  - `rekall demo`: Stages an empty repository, produces mock events, and outputs a handoff pack.
  - `rekall export`: Ejects the latest state into a directory payload.
  - `rekall import`: Ingests an external state artifact payload seamlessly through ID deduplication.
  - `rekall snapshot`: Wraps the entire state directory into a single `snapshot.json` schema-compliant blob.
  - `rekall handoff`: Auto-generates a synthesized `boot_brief.md` aggregating project statuses, blockages, and explicit evidence links.
- **MCP Server Compatibility**: Implemented `rekall.server.mcp_server`, adhering to the Model Context Protocol.

### Internal
- Python `setuptools` build configuration (`setup.py` & `pyproject.toml`)
- Extensive Pytest suite covering regressions, API, state serialization, ID collisions, and strict evaluations.
