# Open Questions (v0.1)

A living list of unresolved design choices. Keep this separate from the spec.

---

## Storage model
1) Work items as event stream (recommended) vs snapshot storage (simpler UX)
2) How strict to be about preserving unknown fields on write
3) How to represent “comments” (timeline notes vs dedicated append-only comments log)

## Sync & collaboration
4) Do we support offline multi-writer without a hub? (CRDT vs strict hub arbitration)
5) Minimum hub feature set for teams (permissions, ordering, notifications)
6) How to handle forked states (two diverged artifacts) — reconciliation strategy

## Status semantics
7) Should projects store explicit status always, or allow computed status by default?
8) What are the minimal risk fields, if any, to standardize?

## Integrations
9) First integration: GitHub Projects/Issues vs Notion vs Jira
10) How far do importers go (read-only metadata vs create back-links vs two-way sync)
11) NotebookLM integration: link-only vs MCP server interop vs API calls

## Security & governance
12) Should decision approval always be required in team/enterprise mode?
13) Secret detection: how aggressive should we be to avoid false positives?
14) Redaction policy for diffs/audit in hosted mode

## Naming / packaging
15) What is the standard name for the state artifact folder in projects? (`project-state/` vs `.state/` vs `state/`)
16) Reference implementation language/runtime (for adoption) — keep separate from spec.
