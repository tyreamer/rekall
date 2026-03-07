"""Tests for the session brief, session lifecycle, bypass detection, modes, and AGENTS.md generation."""
import json
import tempfile
from argparse import Namespace
from pathlib import Path

import pytest

from rekall.cli import (
    cmd_agents_md,
    cmd_brief,
    cmd_mode,
    cmd_session,
    ensure_state_initialized,
)
from rekall.core.brief import format_brief_human, generate_session_brief
from rekall.core.state_store import StateStore


@pytest.fixture
def temp_store():
    """Create an initialized vault with sample data for testing."""
    with tempfile.TemporaryDirectory() as d:
        base_dir = Path(d)
        ensure_state_initialized(base_dir, is_json=True, init_mode=True)
        store = StateStore(base_dir)

        actor = {"actor_id": "test_user"}

        # Create work items in various states
        store.create_work_item(
            {"title": "Implement auth", "status": "in_progress", "priority": "p0"},
            actor,
        )
        store.create_work_item(
            {"title": "Fix DB migration", "status": "blocked", "priority": "p1"},
            actor,
        )
        store.create_work_item(
            {"title": "Write docs", "status": "todo", "priority": "p2"},
            actor,
        )
        store.create_work_item(
            {"title": "Setup CI", "status": "done", "priority": "p1"},
            actor,
        )

        # Log a failed attempt
        store.append_attempt(
            {
                "work_item_id": "wi_auth",
                "title": "Tried OAuth2 with Google",
                "outcome": "failed",
                "result": "CORS errors on redirect, not viable for SPA",
            },
            actor,
        )

        # Propose a pending decision
        store.propose_decision(
            {
                "title": "Use JWT vs session cookies",
                "context": "Need auth strategy",
                "options_considered": ["JWT", "session cookies"],
                "status": "proposed",
            },
            actor,
        )

        yield base_dir


@pytest.fixture
def empty_store():
    """Create a minimal empty vault."""
    with tempfile.TemporaryDirectory() as d:
        base_dir = Path(d)
        ensure_state_initialized(base_dir, is_json=True, init_mode=True)
        yield base_dir


# --- generate_session_brief tests ---


class TestGenerateSessionBrief:
    def test_returns_all_sections(self, temp_store):
        store = StateStore(temp_store)
        brief = generate_session_brief(store)

        assert "project" in brief
        assert "focus" in brief
        assert "blockers" in brief
        assert "failed_attempts" in brief
        assert "pending_decisions" in brief
        assert "next_actions" in brief
        assert "recent_completions" in brief
        assert "mode" in brief

    def test_focus_shows_in_progress(self, temp_store):
        store = StateStore(temp_store)
        brief = generate_session_brief(store)

        assert len(brief["focus"]) >= 1
        titles = [w["title"] for w in brief["focus"]]
        assert "Implement auth" in titles

    def test_blockers_shows_blocked(self, temp_store):
        store = StateStore(temp_store)
        brief = generate_session_brief(store)

        assert len(brief["blockers"]) >= 1
        titles = [w["title"] for w in brief["blockers"]]
        assert "Fix DB migration" in titles

    def test_failed_attempts_populated(self, temp_store):
        store = StateStore(temp_store)
        brief = generate_session_brief(store)

        assert len(brief["failed_attempts"]) >= 1
        assert "OAuth2" in brief["failed_attempts"][0]["title"]

    def test_pending_decisions_populated(self, temp_store):
        store = StateStore(temp_store)
        brief = generate_session_brief(store)

        assert len(brief["pending_decisions"]) >= 1
        assert "JWT" in brief["pending_decisions"][0]["title"]

    def test_next_actions_not_empty(self, temp_store):
        store = StateStore(temp_store)
        brief = generate_session_brief(store)

        assert len(brief["next_actions"]) >= 1

    def test_recent_completions(self, temp_store):
        store = StateStore(temp_store)
        brief = generate_session_brief(store)

        assert len(brief["recent_completions"]) >= 1
        titles = [w["title"] for w in brief["recent_completions"]]
        assert "Setup CI" in titles

    def test_empty_vault_returns_valid_brief(self, empty_store):
        store = StateStore(empty_store)
        brief = generate_session_brief(store)

        assert brief["focus"] == []
        assert brief["blockers"] == []
        assert brief["failed_attempts"] == []
        assert brief["pending_decisions"] == []
        assert len(brief["next_actions"]) >= 1  # Always has a default recommendation

    def test_mode_defaults_to_coordination(self, temp_store):
        store = StateStore(temp_store)
        brief = generate_session_brief(store)
        assert brief["mode"] == "coordination"

    def test_mode_override(self, temp_store):
        store = StateStore(temp_store)
        brief = generate_session_brief(store, mode="lite")
        assert brief["mode"] == "lite"


# --- format_brief_human tests ---


class TestFormatBriefHuman:
    def test_human_format_contains_key_sections(self, temp_store):
        store = StateStore(temp_store)
        brief = generate_session_brief(store)
        text = format_brief_human(brief)

        assert "SESSION BRIEF" in text
        assert "Current Focus" in text
        assert "Implement auth" in text

    def test_human_format_shows_failed_attempts(self, temp_store):
        store = StateStore(temp_store)
        brief = generate_session_brief(store)
        text = format_brief_human(brief)

        assert "DO NOT RETRY" in text
        assert "OAuth2" in text

    def test_human_format_shows_pending_decisions(self, temp_store):
        store = StateStore(temp_store)
        brief = generate_session_brief(store)
        text = format_brief_human(brief)

        assert "Pending Decisions" in text

    def test_empty_vault_format(self, empty_store):
        store = StateStore(empty_store)
        brief = generate_session_brief(store)
        text = format_brief_human(brief)

        assert "SESSION BRIEF" in text
        assert "nothing in progress" in text


# --- CLI cmd_brief tests ---


class TestCmdBrief:
    def test_brief_json_output(self, temp_store, capfd):
        args = Namespace(store_dir=str(temp_store), json=True, debug=False)
        cmd_brief(args)
        captured = capfd.readouterr()
        data = json.loads(captured.out)
        assert "focus" in data
        assert "blockers" in data
        assert "failed_attempts" in data

    def test_brief_human_output(self, temp_store, capfd):
        args = Namespace(store_dir=str(temp_store), json=False, debug=False)
        cmd_brief(args)
        captured = capfd.readouterr()
        assert "SESSION BRIEF" in captured.out


# --- CLI cmd_session tests ---


class TestCmdSession:
    def test_session_start_prints_brief(self, empty_store, capfd):
        args = Namespace(
            store_dir=str(empty_store), json=False, debug=False, subcommand="start"
        )
        cmd_session(args)
        captured = capfd.readouterr()
        assert "SESSION BRIEF" in captured.out

    def test_session_start_json(self, empty_store, capfd):
        args = Namespace(
            store_dir=str(empty_store), json=True, debug=False, subcommand="start"
        )
        cmd_session(args)
        captured = capfd.readouterr()
        data = json.loads(captured.out)
        assert data["status"] == "session_started"
        assert "brief" in data

    def test_session_end_records_summary(self, temp_store, capfd):
        args = Namespace(
            store_dir=str(temp_store),
            json=False,
            debug=False,
            subcommand="end",
            summary="Stopped at auth implementation, JWT approach next",
            actor="test_user",
        )
        cmd_session(args)
        captured = capfd.readouterr()
        assert "Session ended" in captured.out

        # Verify timeline event was recorded
        store = StateStore(temp_store)
        timeline = store._load_stream("timeline")
        session_ends = [e for e in timeline if e.get("type") == "session_end"]
        assert len(session_ends) >= 1
        assert "JWT" in session_ends[-1]["summary"]

    def test_session_end_without_summary(self, temp_store, capfd):
        args = Namespace(
            store_dir=str(temp_store),
            json=False,
            debug=False,
            subcommand="end",
            summary="",
            actor="test_user",
        )
        cmd_session(args)
        captured = capfd.readouterr()
        assert "Session ended" in captured.out
        assert "Tip" in captured.out


# --- CLI cmd_mode tests ---


class TestCmdMode:
    def test_set_mode_lite(self, temp_store, capfd):
        args = Namespace(
            store_dir=str(temp_store),
            json=False,
            debug=False,
            mode="lite",
            actor="test_user",
        )
        cmd_mode(args)
        captured = capfd.readouterr()
        assert "lite" in captured.out

        # Verify mode is persisted
        store = StateStore(temp_store)
        meta = store.get_project_meta()
        assert meta.get("rekall_mode") == "lite"

    def test_set_mode_governed(self, temp_store, capfd):
        args = Namespace(
            store_dir=str(temp_store),
            json=True,
            debug=False,
            mode="governed",
            actor="test_user",
        )
        cmd_mode(args)
        captured = capfd.readouterr()
        data = json.loads(captured.out)
        assert data["mode"] == "governed"

    def test_mode_reflected_in_brief(self, temp_store):
        store = StateStore(temp_store)
        actor = {"actor_id": "test_user"}
        store.patch_project_meta({"rekall_mode": "governed"}, actor=actor)

        store2 = StateStore(temp_store)
        brief = generate_session_brief(store2)
        assert brief["mode"] == "governed"


# --- CLI cmd_agents_md tests ---


class TestCmdAgentsMd:
    def test_generates_agents_md(self, temp_store, capfd):
        out_path = temp_store / "AGENTS.md"
        args = Namespace(
            store_dir=str(temp_store),
            json=False,
            debug=False,
            out=str(out_path),
            force=False,
        )
        cmd_agents_md(args)

        assert out_path.exists()
        content = out_path.read_text(encoding="utf-8")
        assert "AGENTS.md" in content
        assert "Where things live" in content
        assert "Session protocol" in content
        assert "rekall brief" in content
        assert "session.brief" in content or "project.bootstrap" in content
        assert "Live execution state" in content

    def test_agents_md_contains_mode(self, temp_store, capfd):
        out_path = temp_store / "AGENTS.md"

        # Set mode first
        store = StateStore(temp_store)
        store.patch_project_meta({"rekall_mode": "governed"}, actor={"actor_id": "test"})

        args = Namespace(
            store_dir=str(temp_store),
            json=False,
            debug=False,
            out=str(out_path),
            force=False,
        )
        cmd_agents_md(args)

        content = out_path.read_text(encoding="utf-8")
        assert "governed" in content

    def test_agents_md_no_overwrite_without_force(self, temp_store, capfd):
        out_path = temp_store / "AGENTS.md"
        out_path.write_text("existing content", encoding="utf-8")

        args = Namespace(
            store_dir=str(temp_store),
            json=False,
            debug=False,
            out=str(out_path),
            force=False,
        )

        with pytest.raises(SystemExit):
            cmd_agents_md(args)

    def test_agents_md_overwrite_with_force(self, temp_store, capfd):
        out_path = temp_store / "AGENTS.md"
        out_path.write_text("existing content", encoding="utf-8")

        args = Namespace(
            store_dir=str(temp_store),
            json=False,
            debug=False,
            out=str(out_path),
            force=True,
        )
        cmd_agents_md(args)

        content = out_path.read_text(encoding="utf-8")
        assert "AGENTS.md" in content
        assert "existing content" not in content


# --- MCP session.brief tests ---


class TestMCPSessionBrief:
    def test_session_brief_via_mcp(self, temp_store, monkeypatch):
        from rekall.server import mcp_server

        monkeypatch.setenv("REKALL_STATE_DIR", str(temp_store))
        mcp_server._base_dir = temp_store
        mcp_server._store = None

        result = mcp_server.session_brief({})
        assert isinstance(result, list)
        brief = result[0]
        assert "focus" in brief
        assert "blockers" in brief
        assert "failed_attempts" in brief
        assert "pending_decisions" in brief
        assert "next_actions" in brief

    def test_bootstrap_includes_brief(self, temp_store, monkeypatch):
        from rekall.server import mcp_server

        monkeypatch.setenv("REKALL_STATE_DIR", str(temp_store))
        mcp_server._base_dir = temp_store
        mcp_server._store = None

        result = mcp_server.project_bootstrap({})
        assert isinstance(result, list)
        out = result[0]
        assert "session_brief" in out
        assert "focus" in out["session_brief"]
        assert "failed_attempts" in out["session_brief"]


# --- Bypass detection tests ---


class TestBypassDetection:
    def test_detects_pending_decisions(self, temp_store):
        from rekall.cli import _detect_bypass

        store = StateStore(temp_store)
        warnings = _detect_bypass(store, temp_store)

        # Should warn about the pending decision we created
        decision_warnings = [w for w in warnings if "pending decision" in w]
        assert len(decision_warnings) >= 1

    def test_no_false_positives_on_empty_vault(self, empty_store):
        from rekall.cli import _detect_bypass

        store = StateStore(empty_store)
        warnings = _detect_bypass(store, empty_store)

        # Empty vault should not produce warnings about pending decisions or attempts
        assert not any("pending decision" in w for w in warnings)
