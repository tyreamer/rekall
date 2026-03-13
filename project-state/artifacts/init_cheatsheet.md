# Initialization Cheat Sheet: Rekall
**Generated**: 2026-03-13 09:10:36
**execution ledger Last Updated**: 2026-03-13T13:08:45.474830+00:00

## What is Rekall?
Rekall is a project state execution ledger for AI agents and human collaborators.
It tracks decisions, attempts, and work items as a machine-readable event stream.

## Project Reality Snapshot
- [VERIFIABLE RECORD] HEAD: 6cd42f5dcf47... 
- Status computed as PAUSED or LOW ACTIVITY (no active work).
- **Total Work Items**: 3

## Risks / Unknowns
No critical risks identified by guard.

## Blockers
No blockers detected.

## State Artifact Layout
```text
project-state/
├── project.yaml          # Project identity & goals
├── manifest.json         # Stream index
├── streams/              # Partitioned event streams
│   └── work_items/
│       ├── active.jsonl  # Hot events
│       └── snapshot.json # Fast-load state
└── artifacts/            # Generated summaries & briefs
```

## How to update state
If you try something and fail, add an attempt:
`rekall attempts add REQ-1 --title "Tried changing font size" --evidence "UI broke"`
If you make an architectural choice, propose a decision:
`rekall decisions propose --title "Use Postgres" --rationale "Need relational data" --tradeoffs "Heavier than SQLite"`

## Next Recommended Commands
```bash
rekall brief
rekall log
rekall checkpoint
```

## Links
- [Quickstart Guide](https://github.com/run-rekall/rekall#quick-start-for-humans--agents)
- [BETA.md](https://github.com/run-rekall/rekall/blob/main/docs/BETA.md)
- [GitHub Discussions](https://github.com/run-rekall/rekall/discussions)