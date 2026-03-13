"""Tests for provenance hardening: verification of new event types and signatures."""
import json

import pytest

from rekall.core.reducer import ComputedState, compute_snapshot_hash, state_to_snapshot
from rekall.core.state_store import StateStore


@pytest.fixture
def vault(tmp_path):
    store_dir = tmp_path / "project-state"
    store_dir.mkdir()
    (store_dir / "schema-version.txt").write_text("0.1")
    (store_dir / "project.yaml").write_text("project_id: provenance_test\n")
    (store_dir / "manifest.json").write_text(json.dumps({
        "schema_version": "0.1",
        "streams": {}
    }))
    return store_dir


@pytest.fixture
def store(vault):
    return StateStore(vault)


class TestHeadMoveIntegrity:
    def test_head_move_has_hash_chain(self, store):
        hm1 = store.append_head_move(
            actor={"actor_id": "test"},
            reason="First rewind",
            to_timestamp="2026-01-01T00:00:00+00:00",
        )
        assert "event_hash" in hm1
        assert hm1["prev_hash"] is None  # First in stream

        hm2 = store.append_head_move(
            actor={"actor_id": "test"},
            reason="Second rewind",
            to_timestamp="2026-01-02T00:00:00+00:00",
        )
        assert hm2["prev_hash"] == hm1["event_hash"]

    def test_head_move_verify_stream(self, store):
        store.append_head_move(
            actor={"actor_id": "test"},
            reason="Test",
            to_timestamp="2026-01-01T00:00:00+00:00",
        )
        result = store.verify_stream_integrity("head_moves")
        assert result["status"] == "\u2705"
        assert result["count"] == 1

    def test_head_move_requires_target(self, store):
        with pytest.raises(ValueError, match="requires to_event_id or to_timestamp"):
            store.append_head_move(
                actor={"actor_id": "test"},
                reason="No target",
            )


class TestPolicyEvaluationIntegrity:
    def test_policy_eval_in_hash_chain(self, store):
        store.evaluate_policy(
            "test_action", {"key": "val"}, {"actor_id": "agent-1"}
        )
        result = store.verify_stream_integrity("activity")
        assert result["status"] == "\u2705"

    def test_multiple_evals_chain_correctly(self, store):
        store.evaluate_policy("a1", {}, {"actor_id": "x"})
        store.evaluate_policy("a2", {}, {"actor_id": "x"})
        store.evaluate_policy("a3", {}, {"actor_id": "x"})

        result = store.verify_stream_integrity("activity")
        assert result["status"] == "\u2705"
        assert result["count"] == 3


class TestApprovalSignatures:
    def test_approval_is_signed(self, store):
        grant = store.grant_approval(
            "test-approval-123",
            {"actor_id": "admin"},
            note="Approved",
        )
        assert "signature" in grant
        assert len(grant["signature"]) == 64  # SHA-256 hex

    def test_approval_in_hash_chain(self, store):
        store.grant_approval("ap1", {"actor_id": "admin"})
        result = store.verify_stream_integrity("activity")
        assert result["status"] == "\u2705"


class TestSnapshotIntegrity:
    def test_snapshot_hash_is_deterministic(self):
        state = ComputedState(
            head_event_id="t1",
            head_timestamp="2026-01-01T00:00:00+00:00",
            work_items={"w1": {"title": "Test", "status": "done"}},
        )
        snap1 = state_to_snapshot(state, "2026-01-01T00:00:00+00:00")
        snap2 = state_to_snapshot(state, "2026-01-01T00:00:00+00:00")
        assert snap1["snapshot_hash"] == snap2["snapshot_hash"]

    def test_snapshot_tamper_detection(self):
        state = ComputedState(head_event_id="t1", head_timestamp="2026-01-01T00:00:00+00:00")
        snap = state_to_snapshot(state, "2026-01-01T00:00:00+00:00")
        original_hash = snap["snapshot_hash"]

        snap["work_items"]["injected"] = {"bad": True}
        assert compute_snapshot_hash(snap) != original_hash

    def test_save_and_load_snapshot(self, store):
        # Create some state first
        store.create_work_item(
            work_item={"title": "Test Task", "status": "done", "priority": "p1"},
            actor={"actor_id": "test"},
        )
        store.append_timeline(
            event={"type": "milestone", "summary": "Test checkpoint"},
            actor={"actor_id": "test"},
        )

        # Save snapshot
        snap = store.save_snapshot()
        assert snap["snapshot_hash"] != ""
        assert snap["head_event_id"] != ""

        # Load it back
        loaded = store._load_global_snapshot()
        assert loaded is not None
        assert loaded["snapshot_hash"] == snap["snapshot_hash"]

        # Verify hash
        assert compute_snapshot_hash(loaded) == loaded["snapshot_hash"]


class TestRewindProvenance:
    def test_rewind_creates_auditable_head_move(self, store):
        store.append_timeline(
            event={"type": "milestone", "summary": "Checkpoint A"},
            actor={"actor_id": "test"},
        )

        hm = store.rewind(
            actor={"actor_id": "human"},
            reason="Bad run, rewinding",
            to_timestamp="2026-01-01T00:00:00+00:00",
        )
        assert hm["type"] == "HeadMove"
        assert hm["reason"] == "Bad run, rewinding"
        assert "event_hash" in hm

        # Verify the head_moves stream has integrity
        result = store.verify_stream_integrity("head_moves")
        assert result["status"] == "\u2705"

    def test_rewind_invalidates_snapshot(self, store):
        store.append_timeline(event={"type": "milestone", "summary": "A"}, actor={"actor_id": "test"})
        store.save_snapshot()
        assert (store.base_dir / "snapshot.json").exists()

        store.rewind(
            actor={"actor_id": "test"},
            reason="Going back",
            to_timestamp="2025-01-01T00:00:00+00:00",
        )
        assert not (store.base_dir / "snapshot.json").exists()


class TestComputeStateIntegration:
    def test_compute_state_from_live_vault(self, store):
        """Full integration: write events then compute state."""
        store.create_work_item(
            work_item={"title": "Task 1", "status": "in_progress", "priority": "p1"},
            actor={"actor_id": "agent"},
        )
        store.append_timeline(
            event={"type": "milestone", "summary": "Started work"},
            actor={"actor_id": "agent"},
        )

        state = store.compute_state()
        assert len(state.work_items) == 1
        assert state.last_checkpoint is not None
        assert state.last_checkpoint["summary"] == "Started work"

    def test_rewind_then_compute(self, store):
        """Rewind excludes future events from computed state."""
        store.append_timeline(
            event={"type": "milestone", "summary": "Early"},
            actor={"actor_id": "test"},
        )
        early_events = store._load_stream_raw("timeline")
        early_ts = early_events[0]["timestamp"]

        store.append_timeline(
            event={"type": "milestone", "summary": "Late"},
            actor={"actor_id": "test"},
        )

        # Before rewind: both visible
        state = store.compute_state()
        assert state.last_checkpoint["summary"] == "Late"

        # Rewind to before "Late"
        store.rewind(
            actor={"actor_id": "human"},
            reason="Undo late work",
            to_timestamp=early_ts,
        )

        state = store.compute_state()
        assert state.last_checkpoint["summary"] == "Early"

    def test_full_flow_store_to_brief(self, store):
        """Integration: StateStore → compute_state() → generate_brief_model()."""
        from rekall.core.brief import generate_brief_model

        store.create_work_item(
            work_item={"title": "Build API", "status": "in_progress", "priority": "p1"},
            actor={"actor_id": "agent"},
        )
        store.append_timeline(
            event={"type": "milestone", "summary": "API scaffolding done"},
            actor={"actor_id": "agent"},
        )

        brief = generate_brief_model(store)
        assert brief["project"] is not None
        assert "API scaffolding done" in brief["summary"]["last_checkpoint"]["summary"]
        assert brief["summary"]["next_action"].startswith("Continue after")

    def test_brief_after_rewind_reflects_computed_state(self, store):
        """Brief uses reducer output, so rewind changes what brief shows."""
        from rekall.core.brief import generate_brief_model

        store.append_timeline(
            event={"type": "milestone", "summary": "Good checkpoint"},
            actor={"actor_id": "test"},
        )
        early_ts = store._load_stream_raw("timeline")[0]["timestamp"]

        store.append_timeline(
            event={"type": "milestone", "summary": "Bad checkpoint"},
            actor={"actor_id": "test"},
        )

        # Before rewind
        brief = generate_brief_model(store)
        assert "Bad checkpoint" in brief["summary"]["last_checkpoint"]["summary"]

        # After rewind
        store.rewind(
            actor={"actor_id": "human"},
            reason="bad run",
            to_timestamp=early_ts,
        )
        brief = generate_brief_model(store)
        assert "Good checkpoint" in brief["summary"]["last_checkpoint"]["summary"]
