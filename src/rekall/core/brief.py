"""
Unified Rekall Brief — the single orient/read command for humans and agents.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from rekall.core.state_store import StateStore


class CheckpointModel(TypedDict):
    summary: str
    timestamp: str
    git_sha: Optional[str]


class BlockerModel(TypedDict):
    title: str
    severity: str  # low|medium|high


class DecisionModel(TypedDict):
    decision_id: str
    title: str
    status: str  # proposed|pending


class WarningModel(TypedDict):
    type: str  # e.g. "repeat_risk"
    message: str
    source_attempt_id: Optional[str]


class BriefModel(TypedDict, total=False):
    project: str
    goal: Optional[str]
    generated_at: str
    summary: Dict[str, Any]
    warnings: List[WarningModel]
    blockers: List[BlockerModel]
    open_decisions: List[DecisionModel]
    constraints: List[str]
    recommended_actions: List[str]


def generate_brief_model(store: StateStore) -> BriefModel:
    """
    Synthesize the project ledger into a unified BriefModel.

    Uses the deterministic reducer to compute state when available,
    falling back to direct stream reads for backward compatibility.
    """
    proj = store.project_config or {}
    project_id = proj.get("project_id", Path(store.base_dir).name if store.base_dir else "unknown")

    # Use the deterministic reducer to compute state
    try:
        computed = store.compute_state()
        return _brief_from_computed_state(computed, proj, project_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(
            "compute_state() failed, falling back to stream reads: %s", e
        )

    # Fallback: direct stream reads (backward compat)
    return _brief_from_streams(store, proj, project_id)


def _brief_from_computed_state(computed, proj: dict, project_id: str) -> BriefModel:
    """Build a BriefModel from a ComputedState (deterministic path)."""
    goal = proj.get("goal") or proj.get("description")
    last_cp: Optional[CheckpointModel] = None
    if computed.last_checkpoint:
        last_cp = {
            "summary": computed.last_checkpoint.get("summary", "No summary"),
            "timestamp": computed.last_checkpoint.get("timestamp", ""),
            "git_sha": computed.last_checkpoint.get("git_sha"),
        }

    blockers: List[BlockerModel] = []
    for w in computed.work_items.values():
        if w.get("status") == "blocked":
            blockers.append({
                "title": w.get("title", "Untitled Work Item"),
                "severity": w.get("priority", "medium"),
            })

    open_decisions: List[DecisionModel] = []
    for d in computed.open_decisions[:5]:
        open_decisions.append({
            "decision_id": d.get("decision_id", ""),
            "title": d.get("title", ""),
            "status": d.get("status", ""),
        })

    warnings: List[WarningModel] = []
    for a in computed.failed_attempts[:3]:
        warnings.append({
            "type": "repeat_risk",
            "message": f"Failed: {a.get('title') or 'Unknown attempt'}",
            "source_attempt_id": a.get("attempt_id"),
        })

    constraints = proj.get("constraints", [])
    if isinstance(constraints, str):
        constraints = [constraints]

    next_action = "Start working and run 'rekall checkpoint' to record progress."
    if open_decisions:
        next_action = f"Resolve pending decision: {open_decisions[0]['title']}"
    elif blockers:
        next_action = f"Unblock: {blockers[0]['title']}"
    elif last_cp:
        next_action = f"Continue after '{last_cp['summary']}'"

    return {
        "project": project_id,
        "goal": goal if goal and goal != "N/A" else None,
        "generated_at": datetime.now().isoformat(),
        "summary": {"next_action": next_action, "last_checkpoint": last_cp},
        "warnings": warnings,
        "blockers": blockers,
        "open_decisions": open_decisions,
        "constraints": constraints,
        "recommended_actions": _compute_generic_recommendations(blockers, open_decisions, last_cp),
    }


def _brief_from_streams(store: StateStore, proj: dict, project_id: str) -> BriefModel:
    """Build a BriefModel from direct stream reads (legacy fallback)."""
    all_events = store._load_stream("timeline", hot_only=True)
    checkpoints = [e for e in all_events if e.get("type") == "milestone" or e.get("event") == "checkpoint"]
    last_cp: Optional[CheckpointModel] = None
    if checkpoints:
        cp = sorted(checkpoints, key=lambda x: x.get("timestamp", ""), reverse=True)[0]
        last_cp = {
            "summary": cp.get("summary", cp.get("title", "No summary provided")),
            "timestamp": cp.get("timestamp", ""),
            "git_sha": cp.get("git_sha"),
        }

    work_items = list(store.work_items.values())
    blockers: List[BlockerModel] = []
    for w in work_items:
        if w.get("status") == "blocked":
            blockers.append({
                "title": w.get("title", "Untitled Work Item"),
                "severity": w.get("priority", "medium"),
            })

    all_decisions = store._load_stream("decisions", hot_only=True)
    open_decisions: List[DecisionModel] = []
    for d in sorted(all_decisions, key=lambda x: x.get("timestamp", ""), reverse=True):
        if d.get("status") in ("proposed", "pending"):
            open_decisions.append({
                "decision_id": d.get("decision_id", ""),
                "title": d.get("title", ""),
                "status": d.get("status", ""),
            })
            if len(open_decisions) >= 5:
                break

    all_attempts = store._load_stream("attempts", hot_only=True)
    warnings: List[WarningModel] = []
    failed_attempts = [a for a in all_attempts if str(a.get("outcome", "")).lower() == "failed"]
    for a in sorted(failed_attempts, key=lambda x: x.get("timestamp", ""), reverse=True):
        warnings.append({
            "type": "repeat_risk",
            "message": f"Failed: {a.get('title') or a.get('hypothesis') or 'Unknown attempt'}",
            "source_attempt_id": a.get("attempt_id"),
        })
        if len(warnings) >= 3:
            break

    constraints = proj.get("constraints", [])
    if isinstance(constraints, str):
        constraints = [constraints]

    next_action = "Start working and run 'rekall checkpoint' to record progress."
    if open_decisions:
        next_action = f"Resolve pending decision: {open_decisions[0]['title']}"
    elif blockers:
        next_action = f"Unblock: {blockers[0]['title']}"
    elif last_cp:
        next_action = f"Continue after '{last_cp['summary']}'"

    goal = proj.get("goal") or proj.get("description")
    return {
        "project": project_id,
        "goal": goal if goal and goal != "N/A" else None,
        "generated_at": datetime.now().isoformat(),
        "summary": {"next_action": next_action, "last_checkpoint": last_cp},
        "warnings": warnings,
        "blockers": blockers,
        "open_decisions": open_decisions,
        "constraints": constraints,
        "recommended_actions": _compute_generic_recommendations(blockers, open_decisions, last_cp),
    }


def _compute_generic_recommendations(blockers, decisions, last_cp) -> List[str]:
    recs = []
    if decisions:
        recs.append("Resolve pending decisions to unblock the project flow.")
    if blockers:
        recs.append("Address active blockers before starting new work items.")
    if not last_cp:
        recs.append("Define your first major goal and create an initial checkpoint.")
    return recs


def render_brief_default(model: BriefModel, store=None) -> str:
    """Concise 10-second scan for humans and agents."""
    lines = [f"\U0001F4CB REKALL SESSION BRIEF \u2014 {model['project']}"]

    # Show project goal if set
    goal = model.get("goal")
    if goal:
        lines.append(f"Goal: {goal}")

    # Clean Slate Check
    if not any([model["summary"]["last_checkpoint"], model["warnings"], model["blockers"], model["open_decisions"]]):
        lines.append("\nFresh project. No history yet.")
        lines.append("\nQuick start:")
        lines.append("  1. Do your work normally")
        lines.append("  2. rekall checkpoint --summary \"what you did\"")
        lines.append("  3. If something fails: rekall attempts add <id> --title \"...\" --evidence \"...\"")
        lines.append("\nRekall will track your progress and warn future sessions about failed paths.")
        return "\n".join(lines)

    # Sections
    sections = [
        ("Current Focus", [model["summary"]["next_action"]]),
        ("Last checkpoint", [model["summary"]["last_checkpoint"]["summary"]] if model["summary"]["last_checkpoint"] else []),
        ("DO NOT RETRY", [w["message"] for w in model["warnings"]]),
        ("Needs decision", [d["title"] for d in model["open_decisions"]]),
        ("Blocked by", [b["title"] for b in model["blockers"]]),
        ("Constraints", model["constraints"])
    ]

    for title, items in sections:
        if not items:
            continue
        lines.append(f"\n{title}:")
        for item in items[:3]:
            lines.append(f"  {item}")

    # Stats line if store available
    if store:
        try:
            from rekall.core.stats import compute_stats, format_stats_line
            stats = compute_stats(store)
            stats_line = format_stats_line(stats)
            if stats_line:
                lines.append(f"\nValue: {stats_line}")
        except Exception:
            pass

    return "\n".join(lines)


def render_brief_full(model: BriefModel) -> str:
    """Expanded operator view."""
    lines = [f"\U0001F4CB Rekall Brief [FULL] \u2014 {model['project']}"]
    lines.append(f"Generated at: {model['generated_at']}")
    lines.append("-" * 40)

    lines.append("\n[ SUMMARY ]")
    lines.append(f"Next Action: {model['summary']['next_action']}")
    cp = model["summary"]["last_checkpoint"]
    if cp:
        lines.append(f"Last Checkpoint: {cp['summary']} ({cp['timestamp']})")
        if cp.get("git_sha"):
            lines.append(f"  SHA: {cp['git_sha']}")

    if model["warnings"]:
        lines.append("\n[ DO NOT REPEAT ]")
        for w in model["warnings"]:
            lines.append(f"  !! {w['message']}")

    if model["open_decisions"]:
        lines.append("\n[ PENDING DECISIONS ]")
        for d in model["open_decisions"]:
            lines.append(f"  ? {d['title']} (ID: {d['decision_id']})")

    if model["blockers"]:
        lines.append("\n[ BLOCKERS ]")
        for b in model["blockers"]:
            lines.append(f"  X {b['title']} (Severity: {b['severity']})")

    if model["constraints"]:
        lines.append("\n[ CONSTRAINTS ]")
        for c in model["constraints"]:
            lines.append(f"  * {c}")

    if model["recommended_actions"]:
        lines.append("\n[ RECOMMENDED NEXT ACTIONS ]")
        for a in model["recommended_actions"]:
            lines.append(f"  -> {a}")

    return "\n".join(lines)


def render_brief_json(model: BriefModel) -> str:
    """Stable structured JSON for agents."""
    return json.dumps(model, indent=2)


# Legacy/Compatibility Wrapper
def generate_session_brief(store: StateStore, mode: Optional[str] = None) -> Dict[str, Any]:
    """Old entry point, redirected to generate_brief_model with mapping for tests."""
    model = generate_brief_model(store)

    # Use mode from store if not provided
    if mode is None:
        mode = store.project_config.get("rekall_mode", "coordination")

    # Map new model to old test expectations
    legacy = {
        "project": model.get("project", "unknown"),
        "focus": [{"title": b["title"]} for b in model.get("blockers", []) if b.get("severity") == "high"], # Heuristic
        "blockers": [{"title": b["title"]} for b in model.get("blockers", [])],
        "failed_attempts": [{"title": w["message"]} for w in model.get("warnings", [])],
        "pending_decisions": [{"title": d["title"]} for d in model.get("open_decisions", [])],
        "next_actions": model.get("recommended_actions", ["Resolution pending"]),
        "recent_completions": [], # Not currently synthesized in new model
        "mode": mode,
        "generated_at": model.get("generated_at")
    }

    # Add focus heuristic if empty: first in-progress work item
    if not legacy["focus"]:
        in_prog = [w for w in store.work_items.values() if w.get("status") == "in_progress"]
        if in_prog:
            legacy["focus"] = [{"title": in_prog[0]["title"]}]

    # Add recent completions heuristic
    done = sorted([w for w in store.work_items.values() if w.get("status") == "done"],
                  key=lambda x: x.get("updated_at", ""), reverse=True)
    legacy["recent_completions"] = [{"title": w["title"]} for w in done[:3]]

    return legacy


def format_brief_human(brief: Dict[str, Any]) -> str:
    """Old entry point, redirected to render_brief_default."""
    # If it's the old dict format, we might need a dummy model or just use the old formatter
    if "summary" in brief:
        return render_brief_default(brief)  # type: ignore

    # Simple fallback for the legacy dict returned by generate_session_brief
    lines = ["=== SESSION BRIEF ==="]
    if brief.get("focus"):
        lines.append(f"Current Focus: {brief['focus'][0]['title']}")
    else:
        lines.append("nothing in progress")
    if brief.get("blockers"):
        lines.append(f"Blockers: {len(brief['blockers'])}")
    if brief.get("failed_attempts"):
        lines.append(f"DO NOT RETRY: {brief['failed_attempts'][0]['title']}")
    if brief.get("pending_decisions"):
        lines.append(f"Pending Decisions: {len(brief['pending_decisions'])}")
    return "\n".join(lines)

