import json

import pytest

from rekall.core.brief import (
    generate_brief_model,
    render_brief_default,
    render_brief_full,
    render_brief_json,
)
from rekall.core.state_store import StateStore


@pytest.fixture
def empty_store(tmp_path):
    (tmp_path / "schema-version.txt").write_text("0.2")
    store = StateStore(tmp_path)
    # Note: StateStore.initialize() is called in __init__
    return store

@pytest.fixture
def active_store(tmp_path):
    (tmp_path / "schema-version.txt").write_text("0.2")
    store = StateStore(tmp_path)
    actor = {"actor_id": "u1"}

    # 1. Add a checkpoint
    store.append_timeline(
        {"type": "milestone", "title": "Set up database schema", "git_sha": "a1b2c3d"},
        actor=actor
    )

    # 2. Add a blocked item
    store.create_work_item(
        {
            "work_item_id": "item_1",
            "title": "API Integration",
            "status": "blocked",
            "priority": "high"
        },
        actor=actor
    )

    # 3. Add a failed attempt
    store.append_attempt(
        {
            "attempt_id": "att_1",
            "title": "Use SQLite",
            "outcome": "failed",
            "timestamp": "2026-03-12T10:00:00Z"
        },
        actor=actor
    )

    # 4. Add a pending decision
    store.propose_decision(
        {
            "decision_id": "dec_1",
            "title": "Postgres vs MySQL",
            "status": "proposed",
            "timestamp": "2026-03-12T11:00:00Z"
        },
        actor=actor
    )

    return store


def test_brief_empty_state(empty_store):
    model = generate_brief_model(empty_store)
    output = render_brief_default(model)

    assert "clean slate" in output
    assert "No checkpoints" in output
    assert "Start working" in output

def test_brief_active_state_default(active_store):
    model = generate_brief_model(active_store)
    output = render_brief_default(model)

    assert "Current Focus:" in output
    assert "Resolve pending decision: Postgres vs MySQL" in output
    assert "Last checkpoint:" in output
    assert "Set up database schema" in output
    assert "Do not repeat:" in output
    assert "Failed: Use SQLite" in output
    assert "Blocked by:" in output
    assert "API Integration" in output

def test_brief_active_state_full(active_store):
    model = generate_brief_model(active_store)
    output = render_brief_full(model)

    assert "[FULL]" in output
    assert "[ SUMMARY ]" in output
    assert "[ DO NOT REPEAT ]" in output
    assert "[ PENDING DECISIONS ]" in output
    assert "[ BLOCKERS ]" in output
    assert "SHA: a1b2c3d" in output

def test_brief_active_state_json(active_store):
    model = generate_brief_model(active_store)
    output = render_brief_json(model)
    data = json.loads(output)

    assert data["project"] is not None
    assert data["summary"]["next_action"] == "Resolve pending decision: Postgres vs MySQL"
    assert data["summary"]["last_checkpoint"]["git_sha"] == "a1b2c3d"
    assert len(data["blockers"]) == 1
    assert data["blockers"][0]["severity"] == "high"
