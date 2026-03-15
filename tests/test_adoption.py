"""Tests for adoption improvements: stats, brief enhancements, MCP tools."""
import json

import pytest

from rekall.core.state_store import StateStore
from rekall.core.stats import compute_stats, format_stats_full, format_stats_line


@pytest.fixture
def vault(tmp_path):
    store_dir = tmp_path / "project-state"
    store_dir.mkdir()
    (store_dir / "schema-version.txt").write_text("0.1")
    (store_dir / "project.yaml").write_text(
        "project_id: test\ngoal: Build the best API\n"
    )
    (store_dir / "manifest.json").write_text(json.dumps({
        "schema_version": "0.1",
        "streams": {}
    }))
    return store_dir


@pytest.fixture
def store(vault):
    return StateStore(vault)


class TestStats:
    def test_empty_vault_stats(self, store):
        stats = compute_stats(store)
        assert stats["checkpoints"] == 0
        assert stats["sessions"] == 0
        assert stats["retries_prevented"] == 0
        assert stats["estimated_tokens_saved"] == 0
        assert stats["decisions_total"] == 0
        assert stats["attempts_total"] == 0

    def test_stats_with_activity(self, store):
        store.append_timeline(
            event={"type": "milestone", "summary": "First checkpoint"},
            actor={"actor_id": "test"},
        )
        store.append_attempt(
            {"title": "Try redis", "outcome": "failed", "evidence": "OOM"},
            {"actor_id": "test"},
        )
        store.append_decision(
            {"title": "Use Postgres", "status": "proposed", "rationale": "SQL"},
            {"actor_id": "test"},
        )
        stats = compute_stats(store)
        assert stats["checkpoints"] == 1
        assert stats["failed_attempts_recorded"] == 1
        assert stats["retries_prevented"] == 1
        assert stats["estimated_tokens_saved"] == 4000
        assert stats["attempts_total"] == 1
        assert stats["decisions_total"] == 1
        assert stats["decisions_open"] == 1

    def test_format_stats_line_empty(self):
        stats = {"checkpoints": 0, "retries_prevented": 0, "estimated_tokens_saved": 0, "decisions_total": 0}
        assert format_stats_line(stats) == ""

    def test_format_stats_line_with_data(self):
        stats = {"checkpoints": 5, "retries_prevented": 3, "estimated_tokens_saved": 12000, "decisions_total": 2}
        line = format_stats_line(stats)
        assert "5 checkpoints" in line
        assert "3 retries prevented" in line
        assert "2 decisions" in line
        assert "12,000 tokens saved" in line

    def test_format_stats_full(self, store):
        stats = compute_stats(store)
        output = format_stats_full(stats)
        assert "Rekall Usage Stats" in output
        assert "Checkpoints:" in output
        assert "Attempts:" in output
        assert "Decisions:" in output


class TestBriefGoal:
    def test_brief_shows_goal(self, store):
        from rekall.core.brief import generate_brief_model, render_brief_default
        store.append_timeline(
            event={"type": "milestone", "summary": "Started"},
            actor={"actor_id": "test"},
        )
        model = generate_brief_model(store)
        assert model.get("goal") == "Build the best API"
        output = render_brief_default(model)
        assert "Build the best API" in output

    def test_brief_no_goal_when_missing(self, tmp_path):
        store_dir = tmp_path / "no-goal"
        store_dir.mkdir()
        (store_dir / "schema-version.txt").write_text("0.1")
        (store_dir / "project.yaml").write_text("project_id: bare\n")
        (store_dir / "manifest.json").write_text(json.dumps({
            "schema_version": "0.1", "streams": {}
        }))
        st = StateStore(store_dir)
        from rekall.core.brief import generate_brief_model
        model = generate_brief_model(st)
        assert model.get("goal") is None


class TestBriefDoNotRetry:
    def test_do_not_retry_section(self, store):
        from rekall.core.brief import generate_brief_model, render_brief_default
        store.append_attempt(
            {"title": "Use SQLite for analytics", "outcome": "failed", "evidence": "Too slow"},
            {"actor_id": "test"},
        )
        store.append_timeline(
            event={"type": "milestone", "summary": "Checkpoint"},
            actor={"actor_id": "test"},
        )
        model = generate_brief_model(store)
        output = render_brief_default(model)
        assert "DO NOT RETRY" in output
        assert "SQLite" in output


class TestBriefStats:
    def test_brief_includes_stats(self, store):
        from rekall.core.brief import generate_brief_model, render_brief_default
        # Create enough activity for stats to show
        store.append_attempt(
            {"title": "Bad approach", "outcome": "failed", "evidence": "Crashed"},
            {"actor_id": "test"},
        )
        store.append_timeline(
            event={"type": "milestone", "summary": "Progress"},
            actor={"actor_id": "test"},
        )
        model = generate_brief_model(store)
        output = render_brief_default(model, store=store)
        assert "Value:" in output
        assert "retries prevented" in output
