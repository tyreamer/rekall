# Rekall Roadmap

**Version**: v0.2 (Mar 2026)
**Status**: Phases 1, 3, 4 shipped. Phase 2 in progress.

Rekall's mission is to be the **persistent, immutable reality layer** for autonomous coding agents — while staying relentlessly developer-friendly.

### Non-Negotiables
- Append-only immutability. History is never truncated or deleted.
- Deterministic resumption: agents can stop and resume from Rekall state exactly as it was.
- Developer wedge: default experience is **OPEN and helpful** (saves time and API credits), never bureaucratic approval theater.
- Local-first. No hosted server required. Sharing happens via verifiable bundles.

We build in **"Proof of Physics" order** — first prove the foundational mechanics, then layer on the delightful features.

---

## PHASE 1: THE PHYSICS (Snapshot + Revert + Resume) — SHIPPED

Core capability: true time travel while preserving full immutable history.

1. **Computed State View + HEAD semantics** — Deterministic reducer computes active state from snapshot + event tail up to HEAD. Pure functions, no I/O.
2. **HeadMove event type** — Append-only HEAD movement replaces StateRevert. Full audit trail preserved.
3. **Snapshotting protocol** — Global snapshot with tamper-evident hash. Bootstrap = load snapshot + replay tail.
4. **CLI commands** — `rekall rewind --to <event_id|timestamp>` and `rekall resume` (hidden/advanced).

**Status**: Shipped in v0.2.0-beta.2. 36 reducer tests, determinism proven.

---

## PHASE 2: THE WEDGE (Async Breakpoint / Ask Human) — IN PROGRESS

Make agents gracefully pause and resume with human input — without hanging connections.

4. **Terminal breakpoint tool**
   MCP tool: `breakpoint.ask_human_for_decision(prompt, options, action_metadata)`
   - Appends a `WaitingOnHuman` event
   - Returns structured `STOP: WAITING_ON_HUMAN` so the agent runner exits cleanly

5. **Human decision + re-awaken flow**
   - CLI: `rekall decide <decision_id> --option <X> [--note "..."]`
     - Appends `Decision` + `HumanAnchor` events
   - CLI: `rekall resume`
     - Detects resolved `WaitingOnHuman` -> continues deterministically

**Definition of Done**
- Full cycle: agent pauses -> human decides later (even hours later) -> agent resumes exactly
- Demo script included

---

## PHASE 3: THE TOLLBOOTH (Policy + Capabilities) — SHIPPED

Guardrails that help instead of block.

6. **Real policy evaluator** — allow/warn/block/require_approval outcomes from `policy.yaml` rules.
7. **Scoped evaluation** — Rules match by org, project, environment, agent.
8. **Auditable policy decisions** — Every evaluation recorded as a `PolicyEvaluation` event.
9. **Capability controls** — Minimal role-based gating (approve_decisions, modify_policy, etc).
10. **Approval flow** — `ApprovalRequired` / `ApprovalGranted` events with HMAC-SHA256 signatures.

**Status**: Shipped. 18 policy tests, 14 provenance tests.

---

## PHASE 4: THE VAULT (Hash chain + Signatures) — SHIPPED

Tamper-evident history.

8. **Cryptographic integrity** — Every event gets `event_hash` + `prev_hash`. Hash chain verified across all 6 streams.
9. **Signed approvals** — HMAC-SHA256 signed with device-local secret.
10. **`rekall verify`** — Validates full chain integrity across timeline, work_items, decisions, attempts, activity, head_moves.
11. **Snapshot integrity** — Deterministic hash, tamper detection on load.

**Status**: Shipped. All streams hash-chained and verifiable.

---

## PHASE 5: "SYNC" WITHOUT A SERVER (Bundles) — PLANNED

9. **rekall bundle**
   - `rekall bundle --out <file.tar.gz>`
   - Includes snapshot, events, policy, manifest, and signatures
   - Anyone can `rekall verify` the bundle

---

## BONUS: FORENSIC EXPLORER — SHIPPED

Dual-mode browser UI for inspecting the execution record (`rekall explorer`).

- **Ledger View** — Dense evidence table with type/time filters, keyboard nav, virtual scroll, hash chain verification.
- **Trace View** — Causal neighborhood graph with adjustable depth (1/2/3 hops), dead-end markers, branch-point shapes.
- **Cross-mode sync** — `t` toggles modes with selection locked. "Trace →" / "← Ledger" buttons. Filters apply to both.
- **Live refresh** — Polls every 3s, new events flash on arrival.
- Zero external dependencies. Ships inside the pip package.

---

### Shipping Constraints
- Lead with **Time Travel + Policy + Forensic Explorer**
- No enforcement-by-default
- No feature sprawl

### Final Deliverable for v0.2
A single **demo runbook** showing:
1. Time travel saves credits: bad run -> rewind -> resume with new decision
2. Policy actuation: rules allow/warn/block/require_approval
3. Forensic Explorer: inspect the full execution record visually

---

**Feedback welcome** — this roadmap is public by design.
Open an issue or DM [@TyReamer](https://x.com/tyreamer) with thoughts.

*Last updated: 2026-03-15*
