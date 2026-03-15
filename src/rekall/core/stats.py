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
    succeeded_attempts = [a for a in attempts if str(a.get("outcome", "")).lower() == "succeeded"]
    open_decisions = [d for d in decisions if d.get("status") in ("proposed", "pending")]
    decided = [d for d in decisions if d.get("status") in ("decided", "approved", "rejected")]
    policy_evals = [e for e in activity if e.get("type") == "PolicyEvaluation"]

    # Staleness: check across ALL streams for latest timestamp
    last_ts = ""
    for stream in [timeline, attempts, decisions, activity]:
        for e in stream:
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

    # Retries prevented = failed attempts recorded (each is a path agents won't retry)
    retries_prevented = len(failed_attempts)

    # Conservative token savings: ~4000 tokens per avoided retry
    estimated_tokens_saved = retries_prevented * 4000

    return {
        "checkpoints": len(checkpoints),
        "sessions": len(sessions),
        "attempts_total": len(attempts),
        "failed_attempts_recorded": len(failed_attempts),
        "succeeded_attempts": len(succeeded_attempts),
        "retries_prevented": retries_prevented,
        "estimated_tokens_saved": estimated_tokens_saved,
        "decisions_total": len(decisions),
        "decisions_open": len(open_decisions),
        "decisions_resolved": len(decided),
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
    if stats["decisions_total"]:
        parts.append(f"{stats['decisions_total']} decisions")
    if stats["estimated_tokens_saved"]:
        parts.append(f"~{stats['estimated_tokens_saved']:,} tokens saved")
    if not parts:
        return ""
    return " | ".join(parts)


def format_stats_full(stats: Dict[str, Any]) -> str:
    """Multi-line stats for the stats command."""
    lines = ["Rekall Usage Stats (local vault):", ""]
    lines.append(f"  Checkpoints:       {stats['checkpoints']}")
    lines.append(f"  Sessions:          {stats['sessions']}")
    lines.append(f"  Attempts:          {stats['attempts_total']} ({stats['failed_attempts_recorded']} failed, {stats['succeeded_attempts']} succeeded)")
    lines.append(f"  Decisions:         {stats['decisions_total']} ({stats['decisions_open']} open, {stats['decisions_resolved']} resolved)")
    lines.append(f"  Work items:        {stats['work_items_done']}/{stats['work_items_total']} done")

    if stats["retries_prevented"]:
        lines.append(f"\n  Retries prevented: {stats['retries_prevented']}")
        lines.append(f"  Est. tokens saved: ~{stats['estimated_tokens_saved']:,}")

    if stats.get("stale_days") is not None:
        if stats["stale_days"] > 7:
            lines.append(f"\n  WARNING: Stale project — {stats['stale_days']} days since last activity")
        elif stats["stale_days"] > 1:
            lines.append(f"\n  Last activity: {stats['stale_days']} days ago")

    return "\n".join(lines)
