# Hero Example: Verifiable AI Execution Record

This document showcases Rekall's ability to capture a verifiable, replayable AI execution record with cryptographic integrity and human provenance.

## The Tour
1. **Initialize Vault**: `rekall init hero-vault`
2. **Action Proposed**: Agent proposes a destructive command `sudo rm -rf /`.
3. **Shadow Audit**: `PolicyCheck` records a `DENY` effect due to destructive command rules (non-blocking).
4. **Consensus Breakpoint**: System requires a `WaitingOnHuman` decision request.
5. **Human Anchor**: User approves the action with a signed `HumanAnchor` (HMAC-SHA256).
6. **Ledger Verification**: Cryptographic hash chains link all events.

## 1. `rekall status` (Lead with Evidence)
```text
[ rekall status ]
✅ INTEGRITY OK | Anchor: SIGNED | HEAD: da573d4bbba1...
Goal/Phase: No goal defined (Unknown phase)
Active HEAD: 2026-02-26T20:29:53.479111+00:00
HEAD ID:     da573d4bbba142759e66289b7cf6cd72

=== Last Attempt ===
None

=== Pending Approvals ===
None

=== Shadow Policy Constraints ===
Audit Trail: 1 preflight checks recorded.
Latest WOULD-DENY: warn-destructive-shell (2026-02-26T20:29:53.479111)

=== Provenance Anchors ===
Latest Anchor: anch-895a6595 [SIGNED]
Evidence:      2026-02-26T20:29:53.522155+00:00
```

## 2. `rekall verify` (Chain Integrity)
```text
[ rekall verify ] - Integrity: ✅
  ✅ work_items           (0 events)
  ✅ activity             (4 events)
  ✅ attempts             (0 events)
  ✅ decisions            (1 events)
  ✅ timeline             (1 events)
  ✅ actions              (2 events)
  ✅ anchors              (1 events)
```

## 3. `exec.query` (MCP Status)
```json
{
  "summary": [
    "[VERIFIABLE RECORD] HEAD: da573d4bbba1... Policy: DENY. Anchor: SIGNED.",
    "Project has 0 items in-progress and 0 active blockers.",
    "Goal: Unknown."
  ],
  "evidence": [
    "policy_check: status=deny rule=warn-destructive-shell [hash: da573d4b...]",
    "provenance_anchor: anch-895a6595 [SIGNED]"
  ]
}
```
