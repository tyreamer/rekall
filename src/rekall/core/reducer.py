"""
Deterministic state reducer for Rekall.

Computes the active project state from:
  1. An optional snapshot (base state)
  2. Raw event streams replayed up to HEAD
  3. HeadMove events that control where HEAD points

This module contains only pure functions and data structures.
No I/O is performed here — loading/saving is the caller's responsibility.
"""
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ── Event ID extraction helper ──

def _event_id(ev: Dict[str, Any]) -> Optional[str]:
    """Extract the canonical ID from any event record."""
    for key in ("event_id", "activity_id", "decision_id", "attempt_id",
                "work_item_id", "revert_id", "head_move_id", "check_id",
                "action_id"):
        val = ev.get(key)
        if val:
            return val
    return None


def _event_ts(ev: Dict[str, Any]) -> str:
    """Extract timestamp from any event record."""
    return ev.get("timestamp") or ev.get("created_at") or ""


# ── ComputedState ──

@dataclass
class ComputedState:
    """Fully materialized project state at a point in time."""
    head_event_id: str = ""
    head_timestamp: str = ""
    work_items: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    open_decisions: List[Dict[str, Any]] = field(default_factory=list)
    failed_attempts: List[Dict[str, Any]] = field(default_factory=list)
    last_checkpoint: Optional[Dict[str, Any]] = None
    timeline_events: List[Dict[str, Any]] = field(default_factory=list)
    stream_cursors: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @property
    def blockers(self) -> List[Dict[str, Any]]:
        return [w for w in self.work_items.values() if w.get("status") == "blocked"]

    @property
    def in_progress(self) -> List[Dict[str, Any]]:
        return [w for w in self.work_items.values() if w.get("status") == "in_progress"]

    @property
    def recent_completions(self) -> List[Dict[str, Any]]:
        done = [w for w in self.work_items.values() if w.get("status") == "done"]
        return sorted(done, key=lambda x: x.get("updated_at", ""), reverse=True)[:3]


# ── HEAD determination ──

class ReducerError(Exception):
    pass


def determine_head(
    head_moves: List[Dict[str, Any]],
    all_events_by_stream: Dict[str, List[Dict[str, Any]]],
) -> Tuple[Optional[str], Optional[str]]:
    """
    Determine the current HEAD position.

    Returns (head_event_id, head_timestamp).

    Rules:
    1. If head_moves exist, use the LAST one (by append order).
    2. Otherwise, HEAD is the latest event across all streams.
    """
    if head_moves:
        latest_hm = head_moves[-1]

        if latest_hm.get("to_event_id"):
            target_id = latest_hm["to_event_id"]
            for events in all_events_by_stream.values():
                for ev in events:
                    if _event_id(ev) == target_id:
                        return (target_id, _event_ts(ev))
            raise ReducerError(
                f"HeadMove target event {target_id} not found in any stream"
            )

        elif latest_hm.get("to_timestamp"):
            cutoff = latest_hm["to_timestamp"]
            best_id: Optional[str] = None
            best_ts = ""
            for events in all_events_by_stream.values():
                for ev in events:
                    ts = _event_ts(ev)
                    if ts <= cutoff and ts > best_ts:
                        best_ts = ts
                        best_id = _event_id(ev)
            return (best_id, best_ts or cutoff)

    # Fallback: latest event across all streams
    best_id = None
    best_ts = ""
    for events in all_events_by_stream.values():
        for ev in events:
            ts = _event_ts(ev)
            if ts > best_ts:
                best_ts = ts
                best_id = _event_id(ev)
    return (best_id, best_ts)


# ── Stream filtering ──

def filter_events_up_to_head(
    events: List[Dict[str, Any]],
    head_timestamp: str,
) -> List[Dict[str, Any]]:
    """Return events with timestamp <= head_timestamp, preserving order."""
    return [ev for ev in events if _event_ts(ev) <= head_timestamp]


# ── Work item replay ──

_WI_CREATED = "WORK_ITEM_CREATED"
_WI_PATCHED = "WORK_ITEM_PATCHED"
_WI_CLAIMED = "WORK_ITEM_CLAIMED"
_WI_RELEASED = "WORK_ITEM_RELEASED"


def apply_work_item_events(
    base_items: Dict[str, Dict[str, Any]],
    events: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Pure function: applies work item events to a base state dict."""
    items = {k: dict(v) for k, v in base_items.items()}

    for event in events:
        wid = event.get("work_item_id")
        if not wid:
            continue
        e_type = event.get("type")

        if e_type == _WI_CREATED:
            if wid not in items:
                data = dict(event.get("patch", {}))
                data["work_item_id"] = wid
                data["version"] = 1
                if "claim" not in data:
                    data["claim"] = None
                items[wid] = data

        elif e_type == _WI_PATCHED:
            if wid in items:
                item = dict(items[wid])
                item.update(event.get("patch", {}))
                item["version"] = item.get("version", 0) + 1
                items[wid] = item

        elif e_type == _WI_CLAIMED:
            if wid in items:
                item = dict(items[wid])
                item["claim"] = event.get("patch", {})
                item["version"] = item.get("version", 0) + 1
                items[wid] = item

        elif e_type == _WI_RELEASED:
            if wid in items:
                item = dict(items[wid])
                item["claim"] = None
                item["version"] = item.get("version", 0) + 1
                items[wid] = item

    return items


# ── Stream extraction helpers ──

def extract_open_decisions(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Open decisions sorted newest-first, max 5."""
    result = []
    for d in sorted(events, key=lambda x: x.get("timestamp", ""), reverse=True):
        if d.get("status") in ("proposed", "pending"):
            result.append({
                "decision_id": d.get("decision_id", ""),
                "title": d.get("title", ""),
                "status": d.get("status", ""),
                "timestamp": d.get("timestamp", ""),
            })
            if len(result) >= 5:
                break
    return result


def extract_failed_attempts(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Failed attempts sorted newest-first."""
    result = []
    for a in sorted(events, key=lambda x: x.get("timestamp", ""), reverse=True):
        if str(a.get("outcome", "")).lower() == "failed":
            result.append({
                "attempt_id": a.get("attempt_id", ""),
                "title": a.get("title") or a.get("hypothesis", ""),
                "outcome": "failed",
                "timestamp": a.get("timestamp", ""),
            })
    return result


def extract_last_checkpoint(
    timeline_events: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Most recent checkpoint/milestone from timeline."""
    checkpoints = [
        e for e in timeline_events
        if e.get("type") == "milestone" or e.get("event") == "checkpoint"
    ]
    if not checkpoints:
        return None
    cp = max(checkpoints, key=lambda x: x.get("timestamp", ""))
    return {
        "summary": cp.get("summary", cp.get("title", "No summary")),
        "timestamp": cp.get("timestamp", ""),
        "git_sha": cp.get("git_sha"),
    }


# ── Snapshot helpers ──

def compute_snapshot_hash(snapshot_data: dict) -> str:
    """Deterministic hash of snapshot contents (excluding snapshot_hash)."""
    data = {k: v for k, v in snapshot_data.items() if k != "snapshot_hash"}
    canonical = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def state_to_snapshot(state: ComputedState, created_at: str) -> Dict[str, Any]:
    """Convert a ComputedState into a persistable snapshot dict."""
    snap: Dict[str, Any] = {
        "schema_version": "0.2",
        "snapshot_event_id": state.head_event_id,
        "head_event_id": state.head_event_id,
        "created_at": created_at,
        "work_items": state.work_items,
        "open_decisions": state.open_decisions,
        "failed_attempts": state.failed_attempts,
        "last_checkpoint": state.last_checkpoint,
        "stream_cursors": state.stream_cursors,
        "snapshot_hash": "",
    }
    snap["snapshot_hash"] = compute_snapshot_hash(snap)
    return snap


def snapshot_to_base_state(snapshot: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], str]:
    """Extract base work_items and snapshot head_event_id from a snapshot."""
    return (snapshot.get("work_items", {}), snapshot.get("head_event_id", ""))


# ── Main Reducer ──

def reduce(
    snapshot: Optional[Dict[str, Any]],
    raw_streams: Dict[str, List[Dict[str, Any]]],
    head_moves: List[Dict[str, Any]],
    legacy_reverts: Optional[List[Dict[str, Any]]] = None,
) -> ComputedState:
    """
    Deterministic state reducer. Pure function.

    Given a snapshot (optional), raw event streams, and head moves,
    computes the fully materialized project state at the current HEAD.
    """
    legacy_reverts = legacy_reverts or []

    # Step 1: Convert legacy reverts to synthetic head_moves if needed
    effective_head_moves = list(head_moves)
    if not effective_head_moves and legacy_reverts:
        last_revert = legacy_reverts[-1]
        effective_head_moves.append({
            "head_move_id": f"synthetic-{last_revert.get('revert_id', 'unknown')}",
            "to_event_id": None,
            "to_timestamp": last_revert.get("to_timestamp"),
            "reason": f"Legacy StateRevert: {last_revert.get('reason', '')}",
            "created_by": last_revert.get("created_by", {}),
            "created_at": last_revert.get("timestamp", ""),
        })

    # Step 2: Determine HEAD
    head_event_id, head_timestamp = determine_head(
        effective_head_moves, raw_streams
    )

    if not head_timestamp:
        return ComputedState()

    # Step 3: Determine replay base from snapshot
    snapshot_timestamp = ""
    base_work_items: Dict[str, Dict[str, Any]] = {}

    if snapshot:
        snap_head_id = snapshot.get("head_event_id", "")
        # Find the timestamp for the snapshot's head event
        snap_ts = ""
        for events in raw_streams.values():
            for ev in events:
                if _event_id(ev) == snap_head_id:
                    snap_ts = _event_ts(ev)
                    break
            if snap_ts:
                break

        if snap_head_id == head_event_id:
            # Snapshot is exactly at HEAD
            return ComputedState(
                head_event_id=head_event_id or "",
                head_timestamp=head_timestamp,
                work_items=snapshot.get("work_items", {}),
                open_decisions=snapshot.get("open_decisions", []),
                failed_attempts=snapshot.get("failed_attempts", []),
                last_checkpoint=snapshot.get("last_checkpoint"),
                stream_cursors=snapshot.get("stream_cursors", {}),
            )

        if snap_ts and snap_ts <= head_timestamp:
            # Snapshot is behind HEAD — use as base
            snapshot_timestamp = snap_ts
            base_work_items = snapshot.get("work_items", {})
        # else: snapshot is ahead of HEAD (rewind) — replay from scratch

    # Step 4: Filter all streams up to HEAD
    filtered: Dict[str, List[Dict[str, Any]]] = {}
    for stream_name, events in raw_streams.items():
        filtered[stream_name] = filter_events_up_to_head(events, head_timestamp)

    # Step 5: Work item replay (incremental from snapshot if available)
    wi_events = filtered.get("work_items", [])
    if snapshot_timestamp:
        wi_events = [
            ev for ev in wi_events
            if _event_ts(ev) > snapshot_timestamp
        ]
    work_items = apply_work_item_events(base_work_items, wi_events)

    # Step 6: Extract derived state
    open_decisions = extract_open_decisions(filtered.get("decisions", []))
    failed_attempts = extract_failed_attempts(filtered.get("attempts", []))
    timeline_events = filtered.get("timeline", [])
    last_checkpoint = extract_last_checkpoint(timeline_events)

    # Step 7: Build stream cursors
    cursors: Dict[str, Dict[str, Any]] = {}
    for stream_name, events in filtered.items():
        if events:
            last_ev = events[-1]
            cursors[stream_name] = {
                "stream_name": stream_name,
                "last_event_hash": last_ev.get("event_hash"),
                "last_timestamp": _event_ts(last_ev),
                "event_count": len(events),
            }

    return ComputedState(
        head_event_id=head_event_id or "",
        head_timestamp=head_timestamp,
        work_items=work_items,
        open_decisions=open_decisions,
        failed_attempts=failed_attempts,
        last_checkpoint=last_checkpoint,
        timeline_events=timeline_events,
        stream_cursors=cursors,
    )
