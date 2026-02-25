# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
