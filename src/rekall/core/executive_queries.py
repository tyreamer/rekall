from typing import Any, Dict, List, Optional
from enum import Enum
from dataclasses import dataclass, field
import datetime

from rekall.core.state_store import StateStore


class ExecutiveQueryType(str, Enum):
    ON_TRACK = "ON_TRACK"
    BLOCKERS = "BLOCKERS"
    CHANGED_SINCE = "CHANGED_SINCE"
    NEXT_7_DAYS = "NEXT_7_DAYS"
    RECENT_DECISIONS = "RECENT_DECISIONS"
    FAILED_ATTEMPTS = "FAILED_ATTEMPTS"
    WHERE_RUNNING_ACCESS = "WHERE_RUNNING_ACCESS"
    RESUME_IN_30 = "RESUME_IN_30"


@dataclass
class ExecutiveResponse:
    target_project_id: str
    query_type: ExecutiveQueryType
    summary: List[str] = field(default_factory=list)
    confidence: str = "high"
    evidence: List[str] = field(default_factory=list)
    work_items: List[Dict[str, Any]] = field(default_factory=list)
    blockers: List[Dict[str, Any]] = field(default_factory=list)
    next_steps: List[Dict[str, Any]] = field(default_factory=list)


def is_stale(iso_str: str, days: int, now: datetime.datetime) -> bool:
    if not iso_str:
        return True
    try:
        dt = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return (now - dt).days >= days
    except ValueError:
        return True


def query_executive_status(
    store: StateStore, query_type: ExecutiveQueryType, since: Optional[str] = None
) -> ExecutiveResponse:
    """Executes a canonical executive status query against the state store."""
    work_items = list(store.work_items.values())
    project_id = store.project_config.get("project_id", "unknown")

    now = datetime.datetime.now(datetime.timezone.utc)
    res = ExecutiveResponse(target_project_id=project_id, query_type=query_type)

    # Consensus Primitives (The Evidence) - MUST LEAD EVERY RESPONSE
    timeline = store._load_stream("timeline.jsonl")
    activity = store._load_stream("activity.jsonl")
    anchors = store._load_stream("anchors.jsonl")
    
    head_prefix = "[VERIFIABLE RECORD] "
    if timeline:
        last = max(timeline, key=lambda x: x.get("timestamp", ""))
        l_hash = last.get("event_hash", "N/A")[:12]
        head_prefix += f"HEAD: {l_hash}... "
    else:
        head_prefix += "Empty stream. "

    policy_checks = [e for e in activity if e.get("type") == "PolicyCheck"]
    if policy_checks:
        effect = policy_checks[-1].get("effect", "unknown")
        head_prefix += f"Policy: {effect.upper()}. "
    
    if anchors:
        sig_s = "SIGNED" if anchors[-1].get("signature") else "UNSIGNED"
        head_prefix += f"Anchor: {sig_s}."
    
    res.summary.append(head_prefix)

    if query_type == ExecutiveQueryType.ON_TRACK:
        blockers = [w for w in work_items if w.get("status") == "blocked"]
        stale_blockers = [
            w for w in blockers if is_stale(w.get("updated_at", ""), 7, now)
        ]

        if stale_blockers:
            res.summary.append(
                f"Status computed as AT_RISK or OFF_TRACK due to {len(stale_blockers)} stale blockers."
            )
            res.confidence = "medium"
            res.evidence.extend(
                [f"work_item: {w['work_item_id']}" for w in stale_blockers[:5]]
            )
        elif blockers:
            res.summary.append(
                f"Status computed as AT_RISK due to {len(blockers)} active blockers."
            )
            res.confidence = "high"
            res.evidence.extend(
                [f"work_item: {w['work_item_id']}" for w in blockers[:5]]
            )
        else:
            in_prog = [w for w in work_items if w.get("status") == "in_progress"]
            if not in_prog:
                res.summary.append(
                    "Status computed as PAUSED or LOW ACTIVITY (no active work)."
                )
                res.confidence = "low"
            else:
                res.summary.append(
                    "Status computed as ON_TRACK. Work is progressing with no recorded blockers."
                )
                res.evidence.extend(
                    [f"work_item: {w['work_item_id']}" for w in in_prog[:3]]
                )

        res.work_items = work_items
        res.blockers = [w for w in work_items if w.get("status") == "blocked"]
        res.next_steps = [
            w for w in work_items if w.get("status") in ["todo", "in_progress"]
        ]

    elif query_type == ExecutiveQueryType.BLOCKERS:
        blockers = [w for w in work_items if w.get("status") == "blocked"]
        if not blockers:
            res.summary.append("No active blockers recorded.")
            res.confidence = "high"
        else:
            res.summary.append(f"Found {len(blockers)} blocked work items.")
            # Sort by priority, then age
            blockers.sort(
                key=lambda x: (x.get("priority", "p9"), x.get("updated_at", ""))
            )
            res.evidence.extend(
                [f"work_item: {w['work_item_id']}" for w in blockers[:10]]
            )
            if any(is_stale(w.get("updated_at", ""), 7, now) for w in blockers):
                res.confidence = "medium"
                res.summary.append("Warning: Some blockers are stale (>7 days).")

        res.work_items = work_items
        res.blockers = blockers

    elif query_type == ExecutiveQueryType.CHANGED_SINCE:
        if not since:
            raise ValueError("CHANGED_SINCE requires 'since' timestamp")

        acts = store._load_jsonl("activity.jsonl")
        recent = [a for a in acts if a.get("timestamp", "") >= since]
        recent.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        if not recent:
            res.summary.append(f"No activity recorded since {since}.")
            res.confidence = "high"
        else:
            res.summary.append(f"Found {len(recent)} activities since {since}.")
            res.evidence.extend(
                [
                    f"activity: {a['activity_id']} (target_type: {a.get('target_type')})"
                    for a in recent[:10]
                ]
            )

    elif query_type == ExecutiveQueryType.NEXT_7_DAYS:
        priorities = [
            w
            for w in work_items
            if w.get("status") in ["todo", "in_progress"]
            and w.get("priority") in ["p0", "p1"]
        ]
        if priorities:
            res.summary.append(
                f"Focusing on {len(priorities)} high-priority (p0/p1) work items."
            )
            res.evidence.extend(
                [f"work_item: {w['work_item_id']}" for w in priorities[:5]]
            )
        else:
            res.summary.append(
                "No high-priority work items found. Execution plan unclear."
            )
            res.confidence = "low"

    elif query_type == ExecutiveQueryType.RECENT_DECISIONS:
        decs = store._load_jsonl("decisions.jsonl")
        decs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        if not decs:
            res.summary.append("No decisions recorded.")
        else:
            res.summary.append(f"Found {len(decs)} total decisions.")
            res.evidence.extend(
                [
                    f"decision: {d['decision_id']} ({d.get('title', 'untitled')}) [hash: {d.get('event_hash', 'N/A')[:8]}...]"
                    for d in decs[:5]
                ]
            )

    elif query_type == ExecutiveQueryType.FAILED_ATTEMPTS:
        atts = store._load_jsonl("attempts.jsonl")
        failed = [a for a in atts if str(a.get("outcome", "")).lower() == "failed"]
        failed.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        if not failed:
            res.summary.append("No failed attempts recorded.")
        else:
            res.summary.append(f"Found {len(failed)} failed attempts.")
            res.evidence.extend([f"attempt: {a['attempt_id']}" for a in failed[:5]])

    elif query_type == ExecutiveQueryType.WHERE_RUNNING_ACCESS:
        envs = store.envs_config.get("environments", [])
        refs = store.access_config.get("access_refs", [])
        res.summary.append(
            f"Project defines {len(envs)} environments and {len(refs)} access references."
        )
        res.evidence.extend([f"env: {e.get('env_id')}" for e in envs[:3]])
        res.evidence.extend([f"access_ref: {r.get('access_ref_id')}" for r in refs[:3]])

    elif query_type == ExecutiveQueryType.RESUME_IN_30:
        # Synthesize multiple things
        in_prog = [w for w in work_items if w.get("status") == "in_progress"]
        blockers = [w for w in work_items if w.get("status") == "blocked"]

        res.summary.append(
            f"Project has {len(in_prog)} items in-progress and {len(blockers)} active blockers."
        )
        res.summary.append(f"Goal: {store.project_config.get('one_liner', 'Unknown')}.")

        # Check for WaitingOnHuman vs Decisions
        actions = store._load_stream("actions.jsonl")
        decisions = store._load_stream("decisions.jsonl")
        
        waits = [a for a in actions if a.get("type") == "WaitingOnHuman"]
        decision_by_action = {d.get("action_id"): d for d in decisions if d.get("action_id")}
        
        unresolved = []
        resolved = []
        for w in waits:
            aid = w.get("action_id")
            w_hash = w.get("event_hash", "N/A")[:8]
            if aid in decision_by_action:
                resolved.append((w, decision_by_action[aid]))
            else:
                unresolved.append(w)
                
        if unresolved:
            res.summary.append(f"WARNING: There are {len(unresolved)} UNRESOLVED breakpoints. Human must rekall decide.")
            for w in unresolved[:3]:
                w_hash = w.get("event_hash", "N/A")[:8]
                res.evidence.append(f"unresolved_breakpoint: action_id={w.get('action_id')} reason={w.get('reason')} [hash: {w_hash}...]")
        if resolved:
            res.summary.append(f"There are {len(resolved)} RESOLVED breakpoints ready for agent pickup.")
            for w, d in resolved[-3:]:
                d_hash = d.get("event_hash", "N/A")[:8]
                res.evidence.append(f"resolved_breakpoint: action_id={w.get('action_id')} decision={d.get('status')} [hash: {d_hash}...]")
        
        # Policy Check Evidence
        acts = store._load_jsonl("activity.jsonl")
        policy_checks = [a for a in acts if a.get("type") == "PolicyCheck"]
        if policy_checks:
            last_p = policy_checks[-1]
            res.summary.append(f"Evidence: Shadow policy guardrail active. Last check: {last_p.get('effect')} ({last_p.get('rule_id')}).")
            res.evidence.append(f"policy_check: status={last_p.get('effect')} rule={last_p.get('rule_id')} [hash: {last_p.get('event_hash', 'N/A')[:8]}...]")

        # Human Anchor Evidence
        anchors = [a for a in acts if a.get("type") == "HumanAnchor"]
        if anchors:
            last_a = anchors[-1]
            sig_s = "SIGNED" if last_a.get("signature") else "UNSIGNED"
            res.evidence.append(f"provenance_anchor: {last_a.get('activity_id')} [{sig_s}]")

        res.evidence.extend([f"work_item: {w['work_item_id']}" for w in in_prog[:2]])
        res.evidence.extend([f"work_item: {w['work_item_id']}" for w in blockers[:2]])

        envs = store.envs_config.get("environments", [])
        if envs:
            res.evidence.append(f"env: {envs[0].get('env_id')}")

        res.work_items = work_items
        res.next_steps = in_prog
        res.blockers = blockers

    else:
        raise ValueError(f"Unsupported query_type: {query_type}")

    return res
