# Rekall Vault — project-state

This directory is managed by Rekall. It stores all persistent
project state so that AI agents (and humans) can resume work
across sessions.

## Files

| Path | Purpose |
| ---- | ------- |
| `schema-version.txt` | Schema version used for forward migration. |
| `project.yaml` | Project metadata: goal, phase, status, confidence. |
| `manifest.json` | Cryptographic root and stream index. |
| `envs.yaml` | Environment definitions (e.g. local, staging). |
| `access.yaml` | Role definitions and permissions. |

## Streams (`streams/`)

Each stream is an append-only JSONL log stored under `streams/<name>/active.jsonl`.

| Stream | Purpose |
| ------ | ------- |
| `work_items` | Tasks and work units. |
| `activity` | High-level milestones. |
| `attempts` | What was tried, including failures. Do not retry these. |
| `decisions` | Architectural choices and tradeoffs. |
| `timeline` | Immutable event log of all state changes. |

Do not edit these files by hand unless you know what you are doing.
