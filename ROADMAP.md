# Rekall Roadmap

**Version**: v0.2 Planning (Feb 2026)  
**Status**: v0.1 is live today. This is the exact plan for v0.2.

Rekall’s mission is to be the **persistent, immutable reality layer** for autonomous coding agents — while staying relentlessly developer-friendly.

### Non-Negotiables
- Append-only immutability. History is never truncated or deleted.
- Deterministic resumption: agents can stop and resume from Rekall state exactly as it was.
- Developer wedge: default experience is **OPEN and helpful** (saves time and API credits), never bureaucratic approval theater.
- No web UI, no audit trail, no collaborative editing, no embeddings or vector execution record features.
- No hosted server in the first 90 days. Sharing happens via verifiable bundles only.

We build in **“Proof of Physics” order** — first prove the foundational mechanics, then layer on the delightful features.

---

## PHASE 1: THE PHYSICS (Snapshot + Revert + Resume)

Core capability: true time travel while preserving full immutable history.

1. **Computed State View + HEAD semantics**  
   - Maintain an append-only `events.jsonl` (attempts, decisions, timeline, etc.).
   - Introduce a deterministic **state reducer** that computes the *current active view* from:
     - `snapshot.json` (base state)
     - tail of `events.jsonl` up to the active HEAD
   - New event type: `HeadMove` (replaces “StateRevert”)
     - Fields: `head_move_id`, `to_event_id` or `to_timestamp`, `reason`, `created_by`

2. **Snapshotting protocol**  
   - `snapshot.json` stores base view + metadata (`snapshot_event_id`, `last_event_hash`, `created_at`)
   - Bootstrap: load snapshot → replay only necessary tail events (respecting `HeadMove` events)

3. **CLI commands (non-destructive)**
   - `rekall rewind --to <event_id|timestamp>` — appends a `HeadMove` event (never deletes history)
   - `rekall resume` — rehydrates agent context from the computed active view

**Definition of Done**  
- Reducer is fully deterministic  
- Full audit history is always preserved  
- Demo: “bad future” exists in log → `rewind` to earlier point → active view excludes bad branch while history remains intact

---

## PHASE 2: THE WEDGE (Async Breakpoint / Ask Human)

Make agents gracefully pause and resume with human input — without hanging connections.

4. **Terminal breakpoint tool**  
   MCP tool: `breakpoint.ask_human_for_decision(prompt, options, action_metadata)`  
   - Appends a `WaitingOnHuman` event  
   - Returns structured `STOP: WAITING_ON_HUMAN` so the agent runner exits cleanly

5. **Human decision + re-awaken flow**
   - CLI: `rekall decide <decision_id> --option <X> [--note "..."]`  
     - Appends `Decision` + `HumanAnchor` events
   - CLI: `rekall resume`  
     - Detects resolved `WaitingOnHuman` → continues deterministically

**Definition of Done**  
- Full cycle: agent pauses → human decides later (even hours later) → agent resumes exactly  
- Demo script included

---

## PHASE 3: THE TOLLBOOTH (Policy, but OPEN by default + Shadow Mode)

Guardrails that help instead of block.

6. **policy.yaml (Tier 0 default)**  
   - Auto-generated with sane defaults  
   - Everything starts as **Tier 0** (allow + log)

7. **Policy preflight (shadow mode only in v0.1)**  
   MCP tool: `policy.preflight(action, target, context)` → `ALLOW` or `WARN`  
   - Always appends `policy_check` event with `would_deny` flag  
   - Never blocks in v0.1 (records what *would* have been blocked)

**Definition of Done**  
- Developers run freely  
- Logs clearly show “this action would be blocked in stricter environments”

---

## PHASE 4: THE VAULT (Hash chain + Signatures)

Tamper-evident history.

8. **Cryptographic integrity**  
   - Every event gets `event_hash` + `prev_hash`  
   - HumanAnchor events are signed (local keypair in v0.1)  
   - CLI: `rekall verify` — validates full chain + signatures

---

## PHASE 5: “SYNC” WITHOUT A SERVER (Bundles)

9. **rekall bundle**  
   - `rekall bundle --out <file.tar.gz>`  
   - Includes snapshot, events, policy, manifest, and signatures  
   - Anyone can `rekall verify` the bundle

---

### Shipping Constraints
- Keep the v0.2 announcement simple: lead with **Time Travel + Async Breakpoints + Shadow Governance**
- No server, no dashboard, no enforcement-by-default
- No feature sprawl

### Final Deliverable for v0.2
A single **demo runbook** showing:
1. Time travel saves credits: bad run → rewind → resume with new decision
2. Async breakpoint: agent stops cleanly → human decides later → resume
3. Shadow governance: policy_check logs would-deny actions without blocking dev

---

**Feedback welcome** — this roadmap is public by design.  
Open an issue or DM [@TyReamer](https://x.com/tyreamer) with thoughts before we start building v0.2.

*Last updated: 2026-02-26*
