# Glossary (v0.1)

This glossary defines the canonical terms used across the Project State Layer specs.  
If a term appears in multiple meanings, **this document wins**.

---

## Project State Layer
The **vendor-neutral project truth layer**: a structured representation of project intent + current state that humans and agents can query and update (with audit + rules). It links out to external systems but does not replace them.

## State Artifact
A **portable export/import bundle** representing a project’s state (often a folder with YAML/JSONL). It is designed to be:
- human-readable
- merge-safe (append-only logs + controlled patches)
- secret-safe (references only)
- resumable after dormancy

## Project
The entity described by `project.yaml`: identity, goals, constraints, phase, classification, top-level links, owners.

## Work Item
A structured unit of work (task/bug/spike/research/etc.) that agents can pick up.  
Work items support:
- status (todo/in_progress/blocked/done/parked)
- priority (p0–p3)
- dependencies (blocks/blocked_by)
- claim/lease coordination
- evidence links

## Work Graph
The directed dependency structure formed by work items and their `blocked_by/blocks` relationships.

## Claim / Lease
A coordination primitive that prevents duplicate work.
- **Claim**: an actor declares ownership of a work item.
- **Lease**: the claim expires at `lease_until` unless renewed.
Rules:
- only the claimant can mutate the work item’s mutable fields (unless admin override).
- non-claimants may still append attempts/timeline notes if allowed.

## Attempt
An append-only record of an experiment or trial:
- hypothesis → action → result → conclusion → next step
Attempts prevent agents/humans from repeating dead ends.

## Decision
An append-only record of a tradeoff:
- context → options → chosen decision → tradeoffs → impacts
Agents may propose; humans may approve depending on permissions.

## Timeline Event
An append-only “what changed” record: milestone/release/decision/blocker/risk/incident/status_change/note.

## Activity / Audit Event
An append-only provenance record emitted for every write:
- who/what changed something
- what target changed
- optional diff and reason

## Typed Link
A structured link to an external artifact or system (repo/doc/audit trail/logs/traces/etc.), with a `type`, `label`, `url`, optional `system`, and optional notes.

## Access Reference (AccessRef)
A secret-safe pointer to access or credentials:
- vault path / secret manager name / account alias
- never the secret value itself
Includes “how to request access” steps.

## Evidence-first
A rule: summaries must cite backing artifacts (work items, attempts, decisions, timeline events, typed links). No “vibes”.

## Executive Status Query Contract
A standardized set of leader questions (on track, blockers, changes since, next 7 days, etc.) with a required response shape:
- summary bullets
- confidence
- evidence references
- optional drivers/blockers/risks

## MCP Tool Contract
The implementation-ready interface (tool names + inputs/outputs + errors + semantics) exposed by an MCP server for this state layer.

## Local-first
A mode where the State Artifact works on disk without accounts/network dependency.

## Hosted Hub
An optional remote service that:
- arbitrates concurrency
- provides team permissions
- stores audit logs
- enables shared search
Local artifacts may mirror/cache from the hub.

## Optimistic Concurrency
A conflict strategy: mutable updates include `expected_version` and are rejected with `CONFLICT` if the object version has changed.

## Idempotency
A safety property: retrying the same append operation (same ID) does not create duplicates.
