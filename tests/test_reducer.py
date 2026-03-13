"""Tests for the deterministic state reducer."""
from datetime import datetime, timedelta, timezone

import pytest

from rekall.core.reducer import (
    ComputedState,
    ReducerError,
    apply_work_item_events,
    compute_snapshot_hash,
    determine_head,
    extract_failed_attempts,
    extract_last_checkpoint,
    extract_open_decisions,
    filter_events_up_to_head,
    reduce,
    state_to_snapshot,
)

# ── Helpers ──

def ts(minutes: int) -> str:
    """Generate a deterministic ISO timestamp offset by N minutes from epoch."""
    base = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(minutes=minutes)).isoformat()


def wi_event(wid: str, e_type: str, minutes: int, patch: dict = None) -> dict:
    """Create a work item event."""
    ev = {
        "work_item_id": wid,
        "type": e_type,
        "timestamp": ts(minutes),
        "event_id": f"ev-{wid}-{minutes}",
    }
    if patch:
        ev["patch"] = patch
    return ev


def timeline_event(eid: str, minutes: int, summary: str, etype: str = "milestone") -> dict:
    return {
        "event_id": eid,
        "type": etype,
        "summary": summary,
        "timestamp": ts(minutes),
    }


def decision_event(did: str, minutes: int, title: str, status: str = "proposed") -> dict:
    return {
        "decision_id": did,
        "title": title,
        "status": status,
        "timestamp": ts(minutes),
    }


def attempt_event(aid: str, minutes: int, title: str, outcome: str = "failed") -> dict:
    return {
        "attempt_id": aid,
        "title": title,
        "outcome": outcome,
        "timestamp": ts(minutes),
    }


def head_move(hm_id: str, to_event_id: str = None, to_timestamp: str = None,
              reason: str = "test") -> dict:
    return {
        "head_move_id": hm_id,
        "to_event_id": to_event_id,
        "to_timestamp": to_timestamp,
        "reason": reason,
        "created_by": {"actor_id": "test"},
        "created_at": ts(999),
    }


# ── determine_head tests ──

class TestDetermineHead:
    def test_no_events_returns_empty(self):
        eid, ets = determine_head([], {})
        assert eid is None
        assert ets == ""

    def test_latest_event_when_no_head_moves(self):
        streams = {
            "timeline": [
                timeline_event("t1", 10, "first"),
                timeline_event("t2", 20, "second"),
            ],
            "work_items": [
                wi_event("w1", "WORK_ITEM_CREATED", 5, {"title": "x", "status": "todo", "priority": "p2"}),
            ],
        }
        eid, ets = determine_head([], streams)
        assert eid == "t2"
        assert ets == ts(20)

    def test_head_move_by_event_id(self):
        streams = {
            "timeline": [
                timeline_event("t1", 10, "first"),
                timeline_event("t2", 20, "second"),
                timeline_event("t3", 30, "third"),
            ],
        }
        moves = [head_move("hm1", to_event_id="t2")]
        eid, ets = determine_head(moves, streams)
        assert eid == "t2"
        assert ets == ts(20)

    def test_head_move_by_timestamp(self):
        streams = {
            "timeline": [
                timeline_event("t1", 10, "first"),
                timeline_event("t2", 20, "second"),
                timeline_event("t3", 30, "third"),
            ],
        }
        moves = [head_move("hm1", to_timestamp=ts(25))]
        eid, ets = determine_head(moves, streams)
        assert eid == "t2"
        assert ets == ts(20)

    def test_last_head_move_wins(self):
        streams = {
            "timeline": [
                timeline_event("t1", 10, "first"),
                timeline_event("t2", 20, "second"),
                timeline_event("t3", 30, "third"),
            ],
        }
        moves = [
            head_move("hm1", to_event_id="t1"),
            head_move("hm2", to_event_id="t3"),
        ]
        eid, ets = determine_head(moves, streams)
        assert eid == "t3"
        assert ets == ts(30)

    def test_missing_target_raises(self):
        streams = {"timeline": [timeline_event("t1", 10, "first")]}
        moves = [head_move("hm1", to_event_id="nonexistent")]
        with pytest.raises(ReducerError, match="not found"):
            determine_head(moves, streams)


# ── filter_events_up_to_head tests ──

class TestFilterEvents:
    def test_filters_future_events(self):
        events = [
            timeline_event("t1", 10, "a"),
            timeline_event("t2", 20, "b"),
            timeline_event("t3", 30, "c"),
        ]
        result = filter_events_up_to_head(events, ts(25))
        assert len(result) == 2
        assert result[-1]["event_id"] == "t2"

    def test_includes_exact_timestamp(self):
        events = [timeline_event("t1", 10, "a")]
        result = filter_events_up_to_head(events, ts(10))
        assert len(result) == 1

    def test_empty_when_head_before_all(self):
        events = [timeline_event("t1", 10, "a")]
        result = filter_events_up_to_head(events, ts(5))
        assert len(result) == 0


# ── apply_work_item_events tests ──

class TestWorkItemReplay:
    def test_create(self):
        events = [
            wi_event("w1", "WORK_ITEM_CREATED", 10,
                     {"title": "Task 1", "status": "todo", "priority": "p1"}),
        ]
        result = apply_work_item_events({}, events)
        assert "w1" in result
        assert result["w1"]["title"] == "Task 1"
        assert result["w1"]["version"] == 1

    def test_create_then_patch(self):
        events = [
            wi_event("w1", "WORK_ITEM_CREATED", 10,
                     {"title": "Task 1", "status": "todo", "priority": "p1"}),
            wi_event("w1", "WORK_ITEM_PATCHED", 20,
                     {"status": "in_progress"}),
        ]
        result = apply_work_item_events({}, events)
        assert result["w1"]["status"] == "in_progress"
        assert result["w1"]["version"] == 2

    def test_claim_and_release(self):
        events = [
            wi_event("w1", "WORK_ITEM_CREATED", 10,
                     {"title": "Task 1", "status": "todo", "priority": "p1"}),
            wi_event("w1", "WORK_ITEM_CLAIMED", 20,
                     {"claimed_by": "agent-1"}),
            wi_event("w1", "WORK_ITEM_RELEASED", 30, {}),
        ]
        result = apply_work_item_events({}, events)
        assert result["w1"]["claim"] is None
        assert result["w1"]["version"] == 3

    def test_incremental_from_base(self):
        base = {"w1": {"work_item_id": "w1", "title": "Existing", "status": "todo", "version": 2}}
        events = [
            wi_event("w1", "WORK_ITEM_PATCHED", 30, {"status": "done"}),
        ]
        result = apply_work_item_events(base, events)
        assert result["w1"]["status"] == "done"
        assert result["w1"]["version"] == 3

    def test_does_not_mutate_base(self):
        base = {"w1": {"work_item_id": "w1", "title": "X", "status": "todo", "version": 1}}
        events = [wi_event("w1", "WORK_ITEM_PATCHED", 10, {"status": "done"})]
        apply_work_item_events(base, events)
        assert base["w1"]["status"] == "todo"  # Original unchanged

    def test_duplicate_create_ignored(self):
        events = [
            wi_event("w1", "WORK_ITEM_CREATED", 10, {"title": "First", "status": "todo", "priority": "p1"}),
            wi_event("w1", "WORK_ITEM_CREATED", 20, {"title": "Duplicate", "status": "todo", "priority": "p1"}),
        ]
        result = apply_work_item_events({}, events)
        assert result["w1"]["title"] == "First"


# ── Extraction tests ──

class TestExtractors:
    def test_open_decisions_max_five(self):
        events = [decision_event(f"d{i}", i * 10, f"Decision {i}") for i in range(10)]
        result = extract_open_decisions(events)
        assert len(result) == 5
        # Newest first
        assert result[0]["decision_id"] == "d9"

    def test_closed_decisions_excluded(self):
        events = [
            decision_event("d1", 10, "Open", "proposed"),
            decision_event("d2", 20, "Closed", "decided"),
        ]
        result = extract_open_decisions(events)
        assert len(result) == 1
        assert result[0]["decision_id"] == "d1"

    def test_failed_attempts(self):
        events = [
            attempt_event("a1", 10, "Try A", "failed"),
            attempt_event("a2", 20, "Try B", "succeeded"),
            attempt_event("a3", 30, "Try C", "failed"),
        ]
        result = extract_failed_attempts(events)
        assert len(result) == 2
        assert result[0]["attempt_id"] == "a3"

    def test_last_checkpoint(self):
        events = [
            timeline_event("t1", 10, "First milestone"),
            timeline_event("t2", 20, "Second milestone"),
            {"event_id": "t3", "type": "session_end", "summary": "ended", "timestamp": ts(30)},
        ]
        result = extract_last_checkpoint(events)
        assert result is not None
        assert result["summary"] == "Second milestone"

    def test_no_checkpoints(self):
        events = [
            {"event_id": "t1", "type": "session_end", "summary": "end", "timestamp": ts(10)},
        ]
        result = extract_last_checkpoint(events)
        assert result is None


# ── Full reduce() tests ──

class TestReduce:
    def test_empty_state(self):
        state = reduce(None, {}, [])
        assert state.head_event_id == ""
        assert state.work_items == {}
        assert state.open_decisions == []

    def test_basic_replay(self):
        streams = {
            "work_items": [
                wi_event("w1", "WORK_ITEM_CREATED", 10,
                         {"title": "Task", "status": "todo", "priority": "p1"}),
                wi_event("w1", "WORK_ITEM_PATCHED", 20, {"status": "done"}),
            ],
            "timeline": [
                timeline_event("t1", 15, "Checkpoint 1"),
            ],
            "decisions": [
                decision_event("d1", 12, "Use postgres"),
            ],
            "attempts": [
                attempt_event("a1", 11, "Try redis", "failed"),
            ],
        }
        state = reduce(None, streams, [])
        assert state.work_items["w1"]["status"] == "done"
        assert state.last_checkpoint["summary"] == "Checkpoint 1"
        assert len(state.open_decisions) == 1
        assert len(state.failed_attempts) == 1
        assert state.head_timestamp == ts(20)

    def test_head_move_excludes_future(self):
        """Events after a HeadMove target are excluded."""
        streams = {
            "work_items": [
                wi_event("w1", "WORK_ITEM_CREATED", 10,
                         {"title": "Task", "status": "todo", "priority": "p1"}),
                wi_event("w1", "WORK_ITEM_PATCHED", 20, {"status": "done"}),
            ],
            "timeline": [
                timeline_event("t1", 10, "Early"),
                timeline_event("t2", 20, "Late"),
            ],
        }
        moves = [head_move("hm1", to_event_id="t1")]
        state = reduce(None, streams, moves)
        # Work item was created at t=10, patched at t=20.
        # HEAD is at t=10, so only the CREATE is visible.
        assert state.work_items["w1"]["status"] == "todo"
        assert state.last_checkpoint["summary"] == "Early"
        assert state.head_event_id == "t1"

    def test_rewind_then_advance(self):
        """Multiple HeadMoves: last one wins."""
        streams = {
            "timeline": [
                timeline_event("t1", 10, "A"),
                timeline_event("t2", 20, "B"),
                timeline_event("t3", 30, "C"),
            ],
        }
        moves = [
            head_move("hm1", to_event_id="t1"),  # rewind
            head_move("hm2", to_event_id="t3"),  # advance back
        ]
        state = reduce(None, streams, moves)
        assert state.head_event_id == "t3"
        assert state.last_checkpoint["summary"] == "C"

    def test_legacy_revert_compat(self):
        """Legacy StateRevert events are treated as synthetic HeadMoves."""
        streams = {
            "timeline": [
                timeline_event("t1", 10, "Good"),
                timeline_event("t2", 20, "Bad"),
            ],
        }
        reverts = [{
            "revert_id": "rev-1",
            "type": "StateRevert",
            "to_timestamp": ts(15),
            "timestamp": ts(25),
            "created_by": {"actor_id": "human"},
            "reason": "bad run",
        }]
        state = reduce(None, streams, [], legacy_reverts=reverts)
        assert state.head_event_id == "t1"
        assert state.last_checkpoint["summary"] == "Good"

    def test_snapshot_exact_match(self):
        """Snapshot at HEAD returns immediately without replay."""
        snapshot = {
            "head_event_id": "t2",
            "work_items": {"w1": {"title": "Cached", "status": "done"}},
            "open_decisions": [],
            "failed_attempts": [],
            "last_checkpoint": {"summary": "From snapshot", "timestamp": ts(20), "git_sha": None},
            "stream_cursors": {},
        }
        streams = {
            "timeline": [
                timeline_event("t1", 10, "A"),
                timeline_event("t2", 20, "B"),
            ],
        }
        state = reduce(snapshot, streams, [])
        assert state.work_items["w1"]["title"] == "Cached"
        assert state.last_checkpoint["summary"] == "From snapshot"

    def test_snapshot_incremental_replay(self):
        """Snapshot behind HEAD: replay only events after snapshot."""
        snapshot = {
            "head_event_id": "t1",
            "work_items": {"w1": {"work_item_id": "w1", "title": "Base", "status": "todo", "version": 1}},
            "open_decisions": [],
            "failed_attempts": [],
            "last_checkpoint": None,
            "stream_cursors": {},
        }
        streams = {
            "work_items": [
                wi_event("w1", "WORK_ITEM_CREATED", 10,
                         {"title": "Base", "status": "todo", "priority": "p1"}),
                wi_event("w1", "WORK_ITEM_PATCHED", 20, {"status": "done"}),
            ],
            "timeline": [
                timeline_event("t1", 10, "First"),
                timeline_event("t2", 20, "Second"),
            ],
        }
        state = reduce(snapshot, streams, [])
        assert state.work_items["w1"]["status"] == "done"
        assert state.last_checkpoint["summary"] == "Second"

    def test_snapshot_ahead_of_head_replays_from_scratch(self):
        """If HEAD moved backward past the snapshot, replay from genesis."""
        snapshot = {
            "head_event_id": "t3",
            "work_items": {"w1": {"work_item_id": "w1", "title": "Future", "status": "done", "version": 3}},
            "open_decisions": [],
            "failed_attempts": [],
            "last_checkpoint": None,
            "stream_cursors": {},
        }
        streams = {
            "work_items": [
                wi_event("w1", "WORK_ITEM_CREATED", 10,
                         {"title": "Task", "status": "todo", "priority": "p1"}),
            ],
            "timeline": [
                timeline_event("t1", 10, "A"),
                timeline_event("t2", 20, "B"),
                timeline_event("t3", 30, "C"),
            ],
        }
        # Rewind to t1 (before snapshot's t3)
        moves = [head_move("hm1", to_event_id="t1")]
        state = reduce(snapshot, streams, moves)
        assert state.work_items["w1"]["status"] == "todo"
        assert state.head_event_id == "t1"


# ── Determinism: genesis vs snapshot+tail produce same state ──

class TestDeterminism:
    def _build_streams(self):
        return {
            "work_items": [
                wi_event("w1", "WORK_ITEM_CREATED", 10,
                         {"title": "T1", "status": "todo", "priority": "p1"}),
                wi_event("w2", "WORK_ITEM_CREATED", 15,
                         {"title": "T2", "status": "todo", "priority": "p2"}),
                wi_event("w1", "WORK_ITEM_PATCHED", 20, {"status": "in_progress"}),
                wi_event("w2", "WORK_ITEM_PATCHED", 25, {"status": "done"}),
                wi_event("w1", "WORK_ITEM_PATCHED", 30, {"status": "done"}),
            ],
            "timeline": [
                timeline_event("t1", 12, "Started"),
                timeline_event("t2", 22, "Progress"),
                timeline_event("t3", 32, "Done"),
            ],
            "decisions": [
                decision_event("d1", 18, "Use postgres", "proposed"),
                decision_event("d2", 28, "Add cache", "decided"),
            ],
            "attempts": [
                attempt_event("a1", 14, "Try redis", "failed"),
                attempt_event("a2", 24, "Try memcached", "succeeded"),
            ],
        }

    def test_genesis_equals_snapshot_plus_tail(self):
        """Full replay from genesis == snapshot at midpoint + tail replay."""
        streams = self._build_streams()

        # Full replay from genesis
        state_genesis = reduce(None, streams, [])

        # Create snapshot at midpoint (t=20)
        midpoint_state = reduce(
            None, streams,
            [head_move("hm-mid", to_timestamp=ts(20))]
        )
        snapshot = state_to_snapshot(midpoint_state, ts(20))

        # Replay from snapshot to end (no head moves = latest event)
        state_incremental = reduce(snapshot, streams, [])

        # Both must produce identical work items
        assert state_genesis.work_items == state_incremental.work_items
        assert state_genesis.head_event_id == state_incremental.head_event_id
        assert state_genesis.last_checkpoint == state_incremental.last_checkpoint

    def test_rewind_is_auditable_and_deterministic(self):
        """Rewind produces consistent state and doesn't delete events."""
        streams = self._build_streams()

        # Full state
        full = reduce(None, streams, [])
        assert full.work_items["w1"]["status"] == "done"

        # Rewind to t=20
        rewound = reduce(None, streams, [head_move("hm1", to_timestamp=ts(20))])
        assert rewound.work_items["w1"]["status"] == "in_progress"
        assert "w2" in rewound.work_items
        assert rewound.work_items["w2"]["status"] == "todo"

        # Original streams unchanged (rewind is non-destructive)
        assert len(streams["work_items"]) == 5
        assert len(streams["timeline"]) == 3

    def test_reduce_is_pure(self):
        """Calling reduce twice with same inputs produces same output."""
        streams = self._build_streams()
        s1 = reduce(None, streams, [])
        s2 = reduce(None, streams, [])
        assert s1.work_items == s2.work_items
        assert s1.head_event_id == s2.head_event_id
        assert s1.open_decisions == s2.open_decisions
        assert s1.failed_attempts == s2.failed_attempts
        assert s1.last_checkpoint == s2.last_checkpoint


# ── Snapshot tests ──

class TestSnapshot:
    def test_snapshot_roundtrip(self):
        state = ComputedState(
            head_event_id="t1",
            head_timestamp=ts(10),
            work_items={"w1": {"title": "X", "status": "done"}},
        )
        snap = state_to_snapshot(state, ts(10))
        assert snap["head_event_id"] == "t1"
        assert snap["snapshot_hash"] != ""

        # Verify hash
        expected = compute_snapshot_hash(snap)
        assert snap["snapshot_hash"] == expected

    def test_snapshot_tamper_detected(self):
        state = ComputedState(head_event_id="t1", head_timestamp=ts(10))
        snap = state_to_snapshot(state, ts(10))
        original_hash = snap["snapshot_hash"]

        # Tamper
        snap["work_items"]["injected"] = {"bad": True}
        assert compute_snapshot_hash(snap) != original_hash


# ── ComputedState properties ──

class TestComputedStateProperties:
    def test_blockers(self):
        state = ComputedState(work_items={
            "w1": {"status": "blocked", "title": "A"},
            "w2": {"status": "in_progress", "title": "B"},
        })
        assert len(state.blockers) == 1
        assert state.blockers[0]["title"] == "A"

    def test_in_progress(self):
        state = ComputedState(work_items={
            "w1": {"status": "in_progress", "title": "A"},
            "w2": {"status": "done", "title": "B"},
        })
        assert len(state.in_progress) == 1

    def test_recent_completions_sorted_and_limited(self):
        items = {f"w{i}": {"status": "done", "updated_at": ts(i * 10), "title": f"T{i}"}
                 for i in range(5)}
        state = ComputedState(work_items=items)
        assert len(state.recent_completions) == 3
        assert state.recent_completions[0]["title"] == "T4"
