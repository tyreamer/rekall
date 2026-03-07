"""
Generates a structured session brief — everything an agent needs to continue work.

This is the single highest-leverage read operation in Rekall:
one call returns current focus, open blockers, failed paths, pending decisions,
recommended next action, and drift/risk summary.
"""
from typing import Any, Dict, List, Optional

from rekall.core.state_store import StateStore


def generate_session_brief(
    store: StateStore, mode: Optional[str] = None
) -> Dict[str, Any]:
    """
    Build a structured brief for an agent entering or resuming a session.

    Returns a dict with sections:
      - project: identity + goal + phase
      - focus: what's currently in progress
      - blockers: what's stuck and why
      - failed_attempts: paths not to retry (most recent first)
      - pending_decisions: decisions awaiting human input
      - next_actions: recommended next steps
      - drift: session staleness warnings
      - recent_completions: what was finished recently
      - mode: current usage mode (lite/coordination/governed)
    """
    proj = store.project_config or {}
    work_items = list(store.work_items.values())
    effective_mode = mode or proj.get("rekall_mode", "coordination")

    # --- Project Identity ---
    project = {
        "project_id": proj.get("project_id", "unknown"),
        "goal": proj.get("goal") or proj.get("current_goal") or "not set",
        "phase": proj.get("phase", "not set"),
        "status": proj.get("status", "unknown"),
        "confidence": proj.get("confidence", "not set"),
        "constraints": proj.get("constraints", proj.get("invariants", [])),
    }

    # --- Current Focus (in-progress work) ---
    in_progress = [
        _summarize_work_item(w) for w in work_items
        if w.get("status") == "in_progress"
    ]

    # --- Blockers ---
    blocked = [
        _summarize_work_item(w) for w in work_items
        if w.get("status") == "blocked"
    ]

    # --- Failed Attempts (paths not to retry) ---
    all_attempts = sorted(
        store._load_stream("attempts", hot_only=True),
        key=lambda a: a.get("timestamp", ""),
        reverse=True,
    )
    failed_attempts = []
    for a in all_attempts:
        if str(a.get("outcome", "")).lower() == "failed":
            failed_attempts.append({
                "attempt_id": a.get("attempt_id"),
                "work_item_id": a.get("work_item_id", ""),
                "title": a.get("title", ""),
                "hypothesis": a.get("hypothesis", ""),
                "result": a.get("result", a.get("conclusion", "")),
                "timestamp": a.get("timestamp", ""),
            })
            if len(failed_attempts) >= 10:
                break

    # --- Pending Decisions ---
    all_decisions = sorted(
        store._load_stream("decisions", hot_only=True),
        key=lambda d: d.get("timestamp", ""),
        reverse=True,
    )
    pending_decisions = []
    for d in all_decisions:
        if d.get("status") in ("proposed", "pending", "PENDING"):
            pending_decisions.append({
                "decision_id": d.get("decision_id"),
                "title": d.get("title", ""),
                "context": d.get("context", ""),
                "options": d.get("options_considered", []),
                "timestamp": d.get("timestamp", ""),
            })
            if len(pending_decisions) >= 5:
                break

    # --- Recommended Next Actions ---
    next_actions = _compute_next_actions(
        work_items, blocked, pending_decisions, failed_attempts
    )

    # --- Recent Completions (last 5) ---
    recent_completions = []
    for w in sorted(work_items, key=lambda x: x.get("updated_at", ""), reverse=True):
        if w.get("status") == "done":
            recent_completions.append({
                "work_item_id": w.get("work_item_id"),
                "title": w.get("title", ""),
            })
            if len(recent_completions) >= 5:
                break

    # --- Drift ---
    drift = store.check_drift()

    brief: Dict[str, Any] = {
        "project": project,
        "mode": effective_mode,
        "focus": in_progress,
        "blockers": blocked,
        "failed_attempts": failed_attempts,
        "pending_decisions": pending_decisions,
        "next_actions": next_actions,
        "recent_completions": recent_completions,
    }
    if drift:
        brief["drift_warning"] = drift

    return brief


def format_brief_human(brief: Dict[str, Any]) -> str:
    """Format a session brief as human-readable text."""
    lines = []
    p = brief["project"]
    mode = brief.get("mode", "coordination")

    lines.append("=" * 55)
    lines.append("  REKALL SESSION BRIEF")
    lines.append("=" * 55)
    lines.append(f"  Project : {p['project_id']}")
    lines.append(f"  Goal    : {p['goal']}")
    lines.append(f"  Phase   : {p['phase']}  |  Status: {p['status']}")
    lines.append(f"  Mode    : {mode}")

    if p.get("constraints"):
        constraints = p["constraints"]
        if isinstance(constraints, dict):
            constraints = [f"{k}: {v}" for k, v in constraints.items()]
        if constraints:
            lines.append(f"  Rules   : {'; '.join(str(c) for c in constraints[:3])}")

    # Focus
    lines.append("")
    focus = brief.get("focus", [])
    lines.append(f"--- Current Focus ({len(focus)}) ---")
    if focus:
        for w in focus:
            lines.append(f"  [{w['work_item_id'][:12]}] {w['title']}")
    else:
        lines.append("  (nothing in progress)")

    # Blockers
    blocked = brief.get("blockers", [])
    if blocked:
        lines.append(f"\n--- Blockers ({len(blocked)}) ---")
        for w in blocked:
            line = f"  [{w['work_item_id'][:12]}] {w['title']}"
            if w.get("blocked_by"):
                line += f"  (blocked by: {', '.join(w['blocked_by'])})"
            lines.append(line)

    # Failed Attempts
    failed = brief.get("failed_attempts", [])
    if failed:
        lines.append("\n--- Failed Attempts — DO NOT RETRY ---")
        for a in failed[:5]:
            lines.append(f"  [{a['attempt_id'][:12]}] {a['title']}")
            if a.get("result"):
                lines.append(f"    Result: {a['result'][:120]}")

    # Pending Decisions
    pending = brief.get("pending_decisions", [])
    if pending:
        lines.append("\n--- Pending Decisions (need human input) ---")
        for d in pending:
            lines.append(f"  [{d['decision_id'][:12]}] {d['title']}")

    # Next Actions
    actions = brief.get("next_actions", [])
    if actions:
        lines.append("\n--- Recommended Next Actions ---")
        for i, action in enumerate(actions[:5], 1):
            lines.append(f"  {i}. {action}")

    # Drift
    if brief.get("drift_warning"):
        lines.append("\n--- Drift Warning ---")
        lines.append(f"  {brief['drift_warning']}")

    lines.append("")
    lines.append("=" * 55)
    return "\n".join(lines)


def _summarize_work_item(w: Dict[str, Any]) -> Dict[str, Any]:
    deps = w.get("dependencies", {})
    blocked_by = deps.get("blocked_by", []) if isinstance(deps, dict) else []
    return {
        "work_item_id": w.get("work_item_id", ""),
        "title": w.get("title", ""),
        "priority": w.get("priority", "p2"),
        "owner": w.get("owner", ""),
        "blocked_by": blocked_by,
    }


def _compute_next_actions(
    work_items: List[Dict],
    blocked: List[Dict],
    pending_decisions: List[Dict],
    failed_attempts: List[Dict],
) -> List[str]:
    """Compute actionable recommendations based on current state."""
    actions: List[str] = []

    if pending_decisions:
        actions.append(
            f"Resolve {len(pending_decisions)} pending decision(s) — "
            f"run `rekall decide <id>` or wait for human."
        )

    if blocked:
        actions.append(
            f"Investigate {len(blocked)} blocker(s) before starting new work."
        )

    # Find highest-priority todo
    todos = [w for w in work_items if w.get("status") == "todo"]
    todos.sort(key=lambda w: w.get("priority", "p9"))
    if todos:
        top = todos[0]
        actions.append(
            f"Next task: [{top.get('work_item_id', '')}] {top.get('title', '')} "
            f"(priority: {top.get('priority', 'p2')})"
        )

    if failed_attempts:
        actions.append(
            f"Review {len(failed_attempts)} failed attempt(s) to avoid retrying known-bad paths."
        )

    if not actions:
        actions.append("No pending work items. Consider defining new tasks or checkpointing.")

    return actions
