"""Tests for idempotency_key on Attempt, Timeline, and Decision records."""

import json
import tempfile
import pytest
from pathlib import Path

from rekall.core.state_store import StateStore


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as d:
        base_dir = Path(d)
        (base_dir / "schema-version.txt").write_text("0.1")
        (base_dir / "project.yaml").write_text(
            "project_id: test_proj\ndescription: Test\nrepo_url: https://github.com/test"
        )
        (base_dir / "envs.yaml").write_text("dev: {}")
        (base_dir / "access.yaml").write_text("roles: {}")
        event = {
            "event_id": "e1",
            "type": "WORK_ITEM_CREATED",
            "work_item_id": "wi_1",
            "patch": {"title": "Test Item", "status": "todo", "priority": "p1"},
        }
        (base_dir / "work-items.jsonl").write_text(json.dumps(event) + "\n")
        for f in ["activity.jsonl", "attempts.jsonl", "decisions.jsonl", "timeline.jsonl"]:
            (base_dir / f).touch()
        yield StateStore(base_dir)


# ── Attempt idempotency_key ─────────────────────────────────────────────


class TestAttemptIdempotencyKey:
    def test_duplicate_idemp_key_no_op(self, store):
        """Same idempotency_key with different attempt_ids → only one record stored."""
        actor = {"actor_id": "agent_a"}
        attempt1 = {"work_item_id": "wi_1", "title": "First try", "outcome": "fail"}
        attempt2 = {"work_item_id": "wi_1", "title": "Retry same action", "outcome": "fail"}

        r1 = store.append_attempt(attempt1, actor, idempotency_key="send-email-v1")
        r2 = store.append_attempt(attempt2, actor, idempotency_key="send-email-v1")

        # Returns the first record (no-op)
        assert r1["attempt_id"] == r2["attempt_id"]

        with open(store.base_dir / "attempts.jsonl") as f:
            lines = [l for l in f if l.strip()]
        assert len(lines) == 1

    def test_different_idemp_keys_appended(self, store):
        """Different idempotency_keys result in two records."""
        actor = {"actor_id": "agent_a"}
        store.append_attempt({"work_item_id": "wi_1", "title": "A"}, actor, idempotency_key="key-1")
        store.append_attempt({"work_item_id": "wi_1", "title": "B"}, actor, idempotency_key="key-2")

        with open(store.base_dir / "attempts.jsonl") as f:
            lines = [l for l in f if l.strip()]
        assert len(lines) == 2

    def test_idemp_key_stored_in_record(self, store):
        """idempotency_key is persisted in the record."""
        actor = {"actor_id": "agent_a"}
        r = store.append_attempt(
            {"work_item_id": "wi_1", "title": "X"}, actor, idempotency_key="migrate-db-001"
        )
        assert r["idempotency_key"] == "migrate-db-001"

    def test_no_idemp_key_backward_compatible(self, store):
        """Records without idempotency_key still work fine."""
        actor = {"actor_id": "agent_a"}
        r = store.append_attempt({"work_item_id": "wi_1", "title": "Normal"}, actor)
        assert "idempotency_key" not in r

    def test_same_id_still_idempotent(self, store):
        """Primary ID-based idempotency still works (unchanged behavior)."""
        actor = {"actor_id": "agent_a"}
        fixed = {"attempt_id": "fixed-001", "work_item_id": "wi_1", "title": "Fixed"}
        r1 = store.append_attempt(fixed, actor)
        r2 = store.append_attempt(fixed, actor)
        assert r1["attempt_id"] == r2["attempt_id"]


# ── Timeline idempotency_key ────────────────────────────────────────────


class TestTimelineIdempotencyKey:
    def test_duplicate_idemp_key_no_op(self, store):
        actor = {"actor_id": "agent_a"}
        e1 = {"type": "note", "summary": "Migration started"}
        e2 = {"type": "note", "summary": "Migration started again"}

        r1 = store.append_timeline(e1, actor, idempotency_key="run-migration-2026")
        r2 = store.append_timeline(e2, actor, idempotency_key="run-migration-2026")

        assert r1["event_id"] == r2["event_id"]

        with open(store.base_dir / "timeline.jsonl") as f:
            lines = [l for l in f if l.strip()]
        assert len(lines) == 1

    def test_idemp_key_stored(self, store):
        actor = {"actor_id": "agent_a"}
        r = store.append_timeline(
            {"type": "note", "summary": "Deploy"}, actor, idempotency_key="deploy-prod-v3"
        )
        assert r["idempotency_key"] == "deploy-prod-v3"

    def test_no_idemp_key_backward_compatible(self, store):
        actor = {"actor_id": "agent_a"}
        r = store.append_timeline({"type": "note", "summary": "Normal event"}, actor)
        assert "idempotency_key" not in r


# ── Decision idempotency_key ────────────────────────────────────────────


class TestDecisionIdempotencyKey:
    def test_duplicate_idemp_key_no_op(self, store):
        actor = {"actor_id": "agent_a"}
        d1 = {"title": "Use Postgres", "rationale": "ACID", "tradeoffs": "ops cost"}
        d2 = {"title": "Use Postgres (duplicate)", "rationale": "still ACID", "tradeoffs": "same"}

        r1 = store.propose_decision(d1, actor, idempotency_key="db-choice-2026")
        r2 = store.propose_decision(d2, actor, idempotency_key="db-choice-2026")

        assert r1["decision_id"] == r2["decision_id"]

        with open(store.base_dir / "decisions.jsonl") as f:
            lines = [l for l in f if l.strip()]
        assert len(lines) == 1


# ── Backward compatibility: existing artifact without idempotency_key ───


class TestBackwardCompatibility:
    def test_existing_artifact_validates(self, store):
        """StateStore artifacts without idempotency_key pass validate_all."""
        report = store.validate_all(strict=False)
        assert report["summary"]["errors"] == 0

    def test_validate_detects_duplicate_idemp_keys_as_warning(self, store):
        """validate_all warns about duplicate idempotency_keys in strict mode."""
        actor = {"actor_id": "agent_a"}
        # Write two records with the same idempotency_key directly (bypass dedupe to set up test)
        r1 = {"attempt_id": "a1", "idempotency_key": "dup-key", "work_item_id": "wi_1",
              "title": "A", "performed_by": actor, "timestamp": "2026-01-01T00:00:00Z"}
        r2 = {"attempt_id": "a2", "idempotency_key": "dup-key", "work_item_id": "wi_1",
              "title": "B", "performed_by": actor, "timestamp": "2026-01-01T00:01:00Z"}
        with open(store.base_dir / "attempts.jsonl", "a") as f:
            f.write(json.dumps(r1) + "\n")
            f.write(json.dumps(r2) + "\n")

        report = store.validate_all(strict=False)
        all_dupes = report["id_uniqueness"]["duplicates"]
        assert any("dup-key" in d for d in all_dupes)
