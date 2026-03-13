# Rekall v0.2: Grounded Current State

This document represents the absolute truth of the Rekall repository as derived from direct inspection of the codebase (`cli.py`, `mcp_server.py`, `state_store.py`), tests, and current execution constraints.

---

## 1. Product Definition (As Implemented Today)

**What is Rekall, in one sentence, based on the implementation as it exists now?**
Rekall is a local-first, append-only, git-portable JSONL event ledger that provides AI coding agents with a persistent execution memory so they never repeat past mistakes.

**What is the current daily habit loop?**
1. `rekall init` (sets up the `project-state` vault)
2. `rekall brief` (reads focus, blockers, rejected paths)
3. *... do work ...*
4. `rekall checkpoint` (writes progress, intent, or failure back to the ledger)
5. `rekall log` (chronological review)
6. `rekall verify` (validates the cryptographic integrity of the ledger)

**What is the difference between:**
- **Current implemented product:** Fully implements the v0.2 shape. The internal `StateStore` handles JSONL append-only streams effectively.
- **Intended v0.2 shape:** Restrict the agent tool surface to a tight loop (`init`, `brief`, `checkpoint`, `log`, `verify`). This is now exactly what the deployed MCP code reflects.
- **North Star end state:** The thesis that "every AI session has a persistent memory" is enforced natively by the MCP CLI substrate, ensuring agents organically fall into the habit loop without complex decision trees, treating the Skill layer as purely functional UI over the real database substrate.

---

## 2. Public Surface Area

### CLI Commands (`cli.py`)
- **First-Class / Visible:** `demo`, `init`, `brief`, `checkpoint`, `log`, `verify`.
- **Hidden / Internal Substrate:** `serve` (Essential plumbing used exclusively by IDEs/agents to launch the MCP server over stdio. Suppressed from manual human help output).
- **Suppressed / Hidden / Aliased / Legacy:** The CLI contains a massive footprint of suppressed commands (`help=argparse.SUPPRESS`). These include: `features`, `doctor`, `validate`, `export`, `snapshot`, `gc`, `import`, `handoff` (now prints a deprecation warning), `blockers` (alias), `resume` (alias), `checkout`, `guard`, `attempts`, `decisions`, `decide`, `bundle`, `timeline`, `lock`, `status`, `meta`, `onboard`, `hooks`, `commit`, `session`, `mode`, `agents`, `sync`, `assistants`.

### MCP / Skill Layer (`mcp_server.py`)
- **Current First-Class MCP Tools Visible:** 
  - `rekall.init`
  - `rekall.brief`
  - `rekall.checkpoint`
  - `rekall.log`
  - `rekall.verify`
- **Aliases, Compatibility Wrappers, or Legacy:** `rekall.status`, `rekall.record`, and `rekall.handoff` were explicitly eliminated in recent refactors to definitively simplify public tooling.

---

## 3. Core Primitives

The core primitives are defined in `src/rekall/core/state_store.py` as underlying append-only JSONL streams.

- **attempts:** Evidence of what failed to prevent retries. Stored in `attempts.jsonl`.
  - Core. Internal data layer surfaced via `checkpoint --type attempt_failed` and read via `brief`.
- **decisions:** Architectural choices and generic approvals. Stored in `decisions.jsonl`.
  - Core. Internal data layer surfaced via `checkpoint --type decision` and read via `brief`.
- **checkpoints:** Abstract markers built by pushing milestones or statuses into `timeline.jsonl` and/or `active.jsonl` (Work Items).
  - Core. **User-Facing** (via `rekall checkpoint`).
- **timeline:** Chronological execution history of the system. Stored in `timeline.jsonl`.
  - Core. Internal data layer read via `rekall log`.
- **blockers:** Derived state of blocked work items or tracked failure constraints.
  - Core. Internal concept surfaced through `rekall brief` readings.
- **work items:** Active task state tracker. Stored in `work_items` directory over `active.jsonl` and snapshot configurations.
  - Core. Internal data layer managed through complex interactions with `checkpoint`.
- **guard/policy:** Auxiliary constraining checks on intent and payload schemas.
  - Auxiliary. Internal tooling inside `StateStore`.
- **handoff:** A legacy abstraction intended to bundle logs for agent handoffs. 
  - Legacy. **Deprecated** in favor of using `brief`.
- **verify/integrity:** Cryptographic tools for building and auditing hash chains (`prev_hash`/`event_hash`).
  - Core. **User-Facing** (via `rekall verify`).

---

## 4. Refactor Truth

- **Brief Refactor (`src/rekall/core/brief.py`):** Eliminated the need for agents to query multiple fragmented commands (`blockers`, `status`, `resume`) by consolidating them into a single, high-fidelity context injection tool (`brief`). It simplified consumption significantly.
- **Skill Layer Refactor (`src/rekall/server/mcp_server.py`):** 
  - The MCP surface was aggressively pared down.
  - `rekall.record` was too generic and permitted agents to write arbitrary payloads without lifecycle strictures. It was **narrowed** by outright removal, forcing agents to use the `rekall.checkpoint` concept structure. 
  - `rekall.status` and `rekall.handoff` were removed because they were completely redundant alongside `log` and `brief`.
  - The refactor successfully **simplified** the product surface back to its purest form.

---

## 5. Drift Analysis

### Difference from Intended v0.2 Surface
`init`, `brief`, `checkpoint`, `log`, `verify`, and `serve` are the absolute core. 
- *Drift Correction:* `status`, `record`, and `handoff` represented drift away from the tight 5-verb loop. By deleting them from `mcp_server.py`, the drift toward a sprawling interface was actively repaired.
- *Verify Semantics Correction:* `verify` (`rekall.verify`) had drifted into acting like a generic CI runner (`verify.ps1`/`verify.sh`). It has now been firmly bound back to its internal ledger duties: running `StateStore.validate_all()` and `StateStore.verify_stream_integrity()`.

### Difference from North Star
- The project is fully **local-first** and purely **append-only** over JSON files (`appended_jsonl_idempotent()` pattern is pristine). By removing the wide Skill layer and letting CLI commands wrap state interactions, the substrate explicitly anchors the product. 

---

## 6. Codebase Map

- **Defines the real product:**
  - `src/rekall/core/state_store.py`: The database, hash chains, schemas, and core append operations.
  - `src/rekall/core/brief.py`: Synthesizer of state into contextual readouts.
  - `src/rekall/server/mcp_server.py`: The single-pane tool interface that AI environments load.
  - `src/rekall/cli.py`: The interface humans and non-MCP systems load.
- **Compatibility Glue:** 
  - The majority of function aliases mapping multiple deprecated concepts like `lock` or `guard` down into internal calls over `cli.py` and `StateStore`.
- **Dead / Legacy / Quarantine Candidates:**
  - `cmd_handoff` inside `cli.py` has been stubbed.
  - Individual fine-grained manipulations (`cmd_alias_blockers`, `cmd_alias_resume`, `cmd_attempts_add`, `cmd_timeline_add`, `cmd_decisions_propose`) are currently actively hidden in argparse. They should likely be quarantined or removed in v0.3 since all intent can flow via `checkpoint`.
- **Most Important for Future Edits:** `src/rekall/core/state_store.py` limits boundaries on invariants; `src/rekall/server/mcp_server.py` defines the limits of agent tool manipulation.

---

## 7. Proof Points

- **Demonstrably Can Do Today:**
  - Track JSONL events consistently (`append_jsonl_idempotent` cleanly ensures deduplicated tracking).
  - Provide a synthesized snapshot of unapproved decisions and blockers to agents sequentially (`generate_session_brief()`).
  - **Tamper-evident verification** via deep scanning (`verify_stream_integrity` explicitly verifies matching `prev_hash` to expected `event_hash`).
- **Partially Implemented:** Strict schema schemas for custom domains exist implicitly across multiple functions but lack an explicit external validation tree. 
- **Aspirational:** Complete *cross-agent utility* natively relies on agents consistently checking their own `brief` vs a pure proactive push system. *Anti-repeat value* functions robustly today *provided* agents call `checkpoint --type attempt_failed` upon hitting walls.

---

## 8. Recommendations

- **Remain First-Class:** `init`, `brief`, `checkpoint`, `log`, `verify`.
- **Remain Hidden/Suppressed:** High-granularity commands (e.g., `features`, `onboard`, `meta`). 
- **Removed Next:** The `handoff` deprecation notice functions out of `cli.py` should be purged.
- **Rename:** No specific renames immediately required. However, developers might explore clarifying `checkpoint --type [task_done|decision|attempt_failed|milestone]` by adding strict constraints mapping back to specific streams inside the help outputs.

---
### Audit Data
1. **Exact files inspected:** `src/rekall/cli.py`, `src/rekall/server/mcp_server.py`, `src/rekall/core/state_store.py`.
2. **Exact tests run:** `python -m pytest tests/` (142 passed, 1 skipped) and `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1` (0 failures).
3. **Before vs After Public MCP Surface:** 
   - *Before:* `init`, `brief`, `status`, `record`, `checkpoint`, `log`, `verify`, `handoff`.
   - *After:* `init`, `brief`, `checkpoint`, `log`, `verify`.
