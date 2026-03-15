"""Tests for the Forensic Explorer server and data layer."""
import json

import pytest

from rekall.core.state_store import StateStore


@pytest.fixture
def vault(tmp_path):
    store_dir = tmp_path / "project-state"
    store_dir.mkdir()
    (store_dir / "schema-version.txt").write_text("0.1")
    (store_dir / "project.yaml").write_text("project_id: explorer_test\n")
    (store_dir / "manifest.json").write_text(json.dumps({
        "schema_version": "0.1", "streams": {}
    }))
    return store_dir


@pytest.fixture
def store(vault):
    return StateStore(vault)


@pytest.fixture
def populated_store(store):
    """Store with events across all stream types."""
    store.append_timeline(
        event={"type": "milestone", "summary": "Initial setup"},
        actor={"actor_id": "human"},
    )
    store.append_attempt(
        {"title": "Try approach A", "outcome": "failed", "evidence": "OOM error"},
        {"actor_id": "agent-1"},
    )
    store.append_attempt(
        {"title": "Try approach B", "outcome": "succeeded", "evidence": "Worked"},
        {"actor_id": "agent-1"},
    )
    store.append_decision(
        {"title": "Use PostgreSQL", "status": "proposed", "rationale": "ACID compliance"},
        {"actor_id": "agent-1"},
    )
    store.create_work_item(
        work_item={"title": "Build API", "status": "in_progress", "priority": "p1"},
        actor={"actor_id": "human"},
    )
    store.append_head_move(
        actor={"actor_id": "human"},
        reason="Rewind past bad approach",
        to_timestamp="2099-01-01T00:00:00+00:00",
    )
    return store


class TestUnifiedEvents:
    def test_loads_all_streams(self, populated_store, monkeypatch):
        from rekall.explorer import server
        monkeypatch.setattr(server, "_store", populated_store)

        events = server._unified_events()
        types = {e["type"] for e in events}

        assert "checkpoint" in types
        assert "attempt_failed" in types
        assert "attempt_succeeded" in types
        assert "decision_proposed" in types
        assert "head_move" in types

    def test_event_schema(self, populated_store, monkeypatch):
        from rekall.explorer import server
        monkeypatch.setattr(server, "_store", populated_store)

        events = server._unified_events()
        for e in events:
            assert "id" in e
            assert "stream" in e
            assert "type" in e
            assert "timestamp" in e
            assert "summary" in e
            assert "actor" in e
            assert "raw" in e

    def test_sorted_by_timestamp_descending(self, populated_store, monkeypatch):
        from rekall.explorer import server
        monkeypatch.setattr(server, "_store", populated_store)

        events = server._unified_events()
        timestamps = [e["timestamp"] for e in events if e["timestamp"]]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_related_ids_extracted(self, populated_store, monkeypatch):
        from rekall.explorer import server
        monkeypatch.setattr(server, "_store", populated_store)

        events = server._unified_events()
        # Work item events should have work_item_id in related
        wi_events = [e for e in events if e["stream"] == "work_items"]
        for e in wi_events:
            if e["raw"].get("work_item_id"):
                assert len(e["related_ids"]) > 0

    def test_verification_status(self, populated_store, monkeypatch):
        from rekall.explorer import server
        monkeypatch.setattr(server, "_store", populated_store)

        events = server._unified_events()
        # Events that went through append_jsonl_idempotent should have hashes
        hashed = [e for e in events if e["verified"]]
        assert len(hashed) > 0


class TestHTMLServing:
    def test_index_html_exists(self):
        from pathlib import Path
        html_path = Path(__file__).parent.parent / "src" / "rekall" / "explorer" / "index.html"
        assert html_path.exists()
        content = html_path.read_text(encoding="utf-8")
        assert "Forensic Explorer" in content
        assert "Ledger" in content
        assert "Lineage" in content
