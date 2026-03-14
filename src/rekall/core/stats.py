"""
Local usage stats computed from the vault.
No telemetry, no network — everything derived from existing event streams.
"""
from typing import Any, Dict, Optional


def compute_stats(store) -> Dict[str, Any]:
    """Compute local value metrics from vault streams."""
    timeline = store._load_stream_raw("timeline", hot_only=False)
    attempts = store._load_stream_raw("attempts", hot_only=False)
    decisions = store._load_stream_raw("decisions", hot_only=False)
    activity = store._load_stream_raw("activity", hot_only=False)

    # Core counts
    checkpoints = [e for e in timeline if e.get("type") == "milestone" or e.get("event") == "checkpoint"]
    sessions = [e for e in timeline if e.get("type") == "session_end"]
    failed_attempts = [a for a in attempts if str(a.get("outcome", "")).lower() == "failed"]
    open_decisions = [d for d in decisions if d.get("status") in ("proposed", "pending")]

    # Session gate injections (counted from activity stream)
    policy_evals = [e for e in activity if e.get("type") == "PolicyEvaluation"]

    # Staleness check
    last_ts = ""
    for e in timeline:
        ts = e.get("timestamp", "")
        if ts > last_ts:
            last_ts = ts

    stale_days: Optional[float] = None
    if last_ts:
        try:
            from datetime import datetime, timezone
            last_dt = datetime.fromisoformat(last_ts)
            now = datetime.now(timezone.utc)
            stale_days = (now - last_dt).total_seconds() / 86400
        except Exception:
            pass

    # Estimated retries prevented = failed attempts that were recorded
    # (each one is a path an agent won't retry if it reads the brief)
    retries_prevented = len(failed_attempts)

    # Conservative token savings estimate:
    # ~4000 tokens per avoided retry attempt (context load + failed execution)
    estimated_tokens_saved = retries_prevented * 4000

    return {
        "checkpoints": len(checkpoints),
        "sessions": len(sessions),
        "failed_attempts_recorded": len(failed_attempts),
        "retries_prevented": retries_prevented,
        "estimated_tokens_saved": estimated_tokens_saved,
        "open_decisions": len(open_decisions),
        "work_items_total": len(store.work_items),
        "work_items_done": sum(1 for w in store.work_items.values() if w.get("status") == "done"),
        "policy_evaluations": len(policy_evals),
        "last_activity": last_ts or None,
        "stale_days": round(stale_days, 1) if stale_days is not None else None,
    }


def format_stats_line(stats: Dict[str, Any]) -> str:
    """One-line summary for embedding in brief output."""
    parts = []
    if stats["checkpoints"]:
        parts.append(f"{stats['checkpoints']} checkpoints")
    if stats["retries_prevented"]:
        parts.append(f"{stats['retries_prevented']} retries prevented")
    if stats["estimated_tokens_saved"]:
        parts.append(f"~{stats['estimated_tokens_saved']:,} tokens saved")
    if not parts:
        return ""
    return " | ".join(parts)


def format_stats_full(stats: Dict[str, Any]) -> str:
    """Multi-line stats for the stats command."""
    lines = ["Rekall Usage Stats (local vault):", ""]
    lines.append(f"  Checkpoints recorded:    {stats['checkpoints']}")
    lines.append(f"  Sessions completed:      {stats['sessions']}")
    lines.append(f"  Failed attempts logged:  {stats['failed_attempts_recorded']}")
    lines.append(f"  Retries prevented:       {stats['retries_prevented']}")
    lines.append(f"  Est. tokens saved:       ~{stats['estimated_tokens_saved']:,}")
    lines.append(f"  Open decisions:          {stats['open_decisions']}")
    lines.append(f"  Work items (done/total): {stats['work_items_done']}/{stats['work_items_total']}")

    if stats.get("stale_days") is not None:
        if stats["stale_days"] > 7:
            lines.append(f"\n  Stale project: {stats['stale_days']} days since last activity")
        elif stats["stale_days"] > 1:
            lines.append(f"\n  Last activity: {stats['stale_days']} days ago")

    return "\n".join(lines)
