import uuid
from pathlib import Path

import pytest

from rekall.server import mcp_server
from rekall.server.mcp_server import (
    get_store,
    project_get,
    timeline_list,
    work_get,
    work_list,
)

SAMPLE_DIR = Path(__file__).parent.parent / "examples" / "sample_state_artifact"


@pytest.fixture(autouse=True)
def setup_store(monkeypatch, tmp_path):
    # Use a real temporary directory for the store
    store_dir = tmp_path / "project-state"
    store_dir.mkdir()
    (store_dir / "manifest.json").write_text('{"project_id": "prj_646d63703ec5", "schema_version": "0.1"}')
    (store_dir / "schema-version.txt").write_text("0.1")

    # Copy sample data if needed, but for these tests we might just want a fresh store
    # or copy the sample one. Let's copy the sample one to be safe with existing test data.
    import shutil
    shutil.copytree(SAMPLE_DIR, store_dir, dirs_exist_ok=True)

    monkeypatch.setenv("REKALL_STATE_DIR", str(store_dir))
    # force reload so tests always use the fixture
    mcp_server._base_dir = store_dir
    mcp_server._store = None
    get_store()
    yield


def test_project_get():
    result = project_get({"project_id": "prj_646d63703ec5"})
    assert isinstance(result, list)
    assert len(result) == 1
    assert "project" in result[0]
    assert result[0]["project"]["name"] == "Sample Project State Layer POC"


def test_work_list():
    result = work_list({"project_id": "prj_646d63703ec5", "limit": 10, "offset": 0})
    assert isinstance(result, list)
    assert len(result) == 1
    payload = result[0]
    assert "items" in payload
    # Check deterministic ordering (fallback to IDs if needed)
    items = payload["items"]
    assert len(items) > 0
    # ensure basic shape
    assert "work_item_id" in items[0]
    assert "claim" in items[0]
    assert "version" in items[0]


def test_work_list_filters():
    # Only status="todo"
    result = work_list({"project_id": "prj_646d63703ec5", "status": ["todo"]})
    items = result[0]["items"]
    assert all(i["status"] == "todo" for i in items)


def test_work_get():
    # Get a known ID from sample
    store = get_store()
    wid = list(store.work_items.keys())[0]
    result = work_get({"project_id": "prj_646d63703ec5", "work_item_id": wid})

    assert "work_item" in result[0]
    item = result[0]["work_item"]
    assert item["work_item_id"] == wid
    assert "version" in item


def test_timeline_list():
    result = timeline_list({"project_id": "prj_646d63703ec5", "limit": 5})
    assert "items" in result[0]
    items = result[0]["items"]
    assert len(items) > 0

    # Check sorting: should be older timestamp first
    timestamps = [i.get("timestamp", "") for i in items]
    assert timestamps == sorted(timestamps)  # Deterministic ascending order


# --- Write Tests ---


def test_create_adds_new(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))

    mcp_server._store = None

    actor = {"actor_type": "human", "actor_id": "u-1"}
    args = {
        "project_id": "prj_646d63703ec5",
        "actor": actor,
        "work_item": {
            "title": "New Task",
            "type": "task",
            "status": "todo",
            "priority": "p2",
        },
    }

    from rekall.server.mcp_server import work_create

    res = work_create(args)[0]
    assert "work_item" in res
    wid = res["work_item"]["work_item_id"]

    # Verify it can be fetched
    get_res = work_get({"project_id": "prj_646d63703ec5", "work_item_id": wid})[0]
    assert get_res["work_item"]["title"] == "New Task"
    assert get_res["work_item"]["version"] == 1


def test_claim_increments_version(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    mcp_server._store = None

    store = get_store()
    wid = list(store.work_items.keys())[0]
    item = store.work_items[wid]
    ver = item["version"]

    actor = {"actor_type": "agent", "actor_id": "ag-1"}

    from rekall.server.mcp_server import work_claim

    res = work_claim(
        {
            "project_id": "prj_646d63703ec5",
            "work_item_id": wid,
            "expected_version": ver,
            "actor": actor,
            "force": True,  # Break any existing claim in sample
        }
    )[0]

    assert "work_item" in res
    new_ver = res["work_item"]["version"]
    assert new_ver == ver + 1
    assert res["work_item"]["claim"]["claimed_by"] == "ag-1"


def test_version_mismatch_conflict(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    mcp_server._store = None

    store = get_store()
    wid = list(store.work_items.keys())[0]

    from rekall.server.mcp_server import work_update

    res = work_update(
        {
            "project_id": "prj_646d63703ec5",
            "work_item_id": wid,
            "expected_version": 9999,  # wrong
            "actor": {"actor_type": "human", "actor_id": "u-1"},
            "patch": {"title": "conflict"},
        }
    )[0]

    assert "error" in res
    assert res["error"]["code"] == "CONFLICT"


def test_non_claimant_rejected(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    mcp_server._store = None

    store = get_store()
    wid = list(store.work_items.keys())[0]
    ver = store.work_items[wid]["version"]

    from rekall.server.mcp_server import work_claim, work_update

    # Claim for ag-1
    work_claim(
        {
            "project_id": "prj_646d63703ec5",
            "work_item_id": wid,
            "expected_version": ver,
            "actor": {"actor_type": "agent", "actor_id": "ag-1"},
            "force": True,
        }
    )

    new_ver = store.work_items[wid]["version"]

    # Try to update as ag-2
    res = work_update(
        {
            "project_id": "prj_646d63703ec5",
            "work_item_id": wid,
            "expected_version": new_ver,
            "actor": {"actor_type": "agent", "actor_id": "ag-2"},
            "patch": {"title": "hacked"},
        }
    )[0]

    assert "error" in res
    assert res["error"]["code"] in ["FORBIDDEN", "LEASE_EXPIRED"]


def test_renew_extends_lease(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    mcp_server._store = None

    store = get_store()
    wid = list(store.work_items.keys())[0]
    ver = store.work_items[wid]["version"]

    from rekall.server.mcp_server import work_claim, work_renew_claim

    res1 = work_claim(
        {
            "project_id": "prj_646d63703ec5",
            "work_item_id": wid,
            "expected_version": ver,
            "actor": {"actor_type": "agent", "actor_id": "ag-3"},
            "force": True,
        }
    )[0]
    lease_1 = res1["work_item"]["claim"]["lease_until"]
    v2 = res1["work_item"]["version"]

    import time

    time.sleep(0.1)

    res2 = work_renew_claim(
        {
            "project_id": "prj_646d63703ec5",
            "work_item_id": wid,
            "expected_version": v2,
            "actor": {"actor_type": "agent", "actor_id": "ag-3"},
        }
    )[0]

    lease_2 = res2["work_item"]["claim"]["lease_until"]
    assert lease_2 > lease_1


def test_release_clears_claim(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    mcp_server._store = None

    store = get_store()
    wid = list(store.work_items.keys())[0]
    ver = store.work_items[wid]["version"]

    from rekall.server.mcp_server import work_claim, work_release_claim

    res1 = work_claim(
        {
            "project_id": "prj_646d63703ec5",
            "work_item_id": wid,
            "expected_version": ver,
            "actor": {"actor_type": "agent", "actor_id": "ag-4"},
            "force": True,
        }
    )[0]
    v2 = res1["work_item"]["version"]

    res2 = work_release_claim(
        {
            "project_id": "prj_646d63703ec5",
            "work_item_id": wid,
            "expected_version": v2,
            "actor": {"actor_type": "agent", "actor_id": "ag-4"},
        }
    )[0]

    assert res2["work_item"]["claim"] is None


def test_attempt_append_idempotency(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    mcp_server._store = None

    from rekall.server.mcp_server import attempt_append

    actor = {"actor_type": "agent", "actor_id": "ag-1"}
    attempt = {"attempt_id": "att-123", "notes": "first try"}

    res1 = attempt_append(
        {"project_id": "prj_646d63703ec5", "attempt": attempt, "actor": actor}
    )[0]
    assert "attempt" in res1

    # Append identical attempt_id
    attempt2 = {"attempt_id": "att-123", "notes": "different notes ignored"}
    res2 = attempt_append(
        {"project_id": "prj_646d63703ec5", "attempt": attempt2, "actor": actor}
    )[0]

    assert res2["attempt"]["notes"] == "first try"  # Return original


def test_decision_propose_idempotency(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    mcp_server._store = None

    from rekall.server.mcp_server import decision_propose

    actor = {"actor_type": "human", "actor_id": "h-1"}

    d1 = {"decision_id": "dec-999", "title": "Move to Postgres"}
    res1 = decision_propose(
        {"project_id": "prj_646d63703ec5", "decision": d1, "actor": actor}
    )[0]
    assert res1["decision"]["status"] == "proposed"

    d2 = {"decision_id": "dec-999", "title": "Change to MySQL"}
    res2 = decision_propose(
        {"project_id": "prj_646d63703ec5", "decision": d2, "actor": actor}
    )[0]
    assert res2["decision"]["title"] == "Move to Postgres"


def test_timeline_append_idempotency(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    mcp_server._store = None

    from rekall.server.mcp_server import timeline_append

    actor = {"actor_type": "system", "actor_id": "sys"}

    ev = {"event_id": "evt-777", "message": "Deployment completed"}
    res1 = timeline_append(
        {"project_id": "prj_646d63703ec5", "event": ev, "actor": actor}
    )[0]
    assert "event" in res1

    res2 = timeline_append(
        {"project_id": "prj_646d63703ec5", "event": ev, "actor": actor}
    )[0]
    assert res2["event"]["message"] == "Deployment completed"


def test_decision_approve_forbidden_without_capability(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    mcp_server._store = None

    from rekall.server.mcp_server import decision_approve, decision_propose

    actor1 = {"actor_type": "agent", "actor_id": "ag-1"}
    d1 = {"decision_id": "dec-001", "title": "Add Redis"}
    decision_propose(
        {"project_id": "prj_646d63703ec5", "decision": d1, "actor": actor1}
    )

    # Approve without cap
    res = decision_approve(
        {"project_id": "prj_646d63703ec5", "decision_id": "dec-001", "actor": actor1}
    )[0]
    assert "error" in res
    assert res["error"]["code"] == "FORBIDDEN"


def test_decision_approve_success_with_capability(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    mcp_server._store = None

    from rekall.server.mcp_server import decision_approve, decision_propose

    actor1 = {"actor_type": "agent", "actor_id": "ag-1"}
    actor_admin = {
        "actor_type": "human",
        "actor_id": "admin",
        "capabilities": ["approve_decisions"],
    }

    d1 = {"decision_id": "dec-002", "title": "Change architecture"}
    decision_propose(
        {"project_id": "prj_646d63703ec5", "decision": d1, "actor": actor1}
    )

    res = decision_approve(
        {
            "project_id": "prj_646d63703ec5",
            "decision_id": "dec-002",
            "actor": actor_admin,
        }
    )[0]
    assert "decision" in res
    assert res["decision"]["status"] == "approved"
    assert res["decision"]["supersedes"] == "dec-002"


def test_activity_event_emitted(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    mcp_server._store = None

    from rekall.server.mcp_server import activity_list, attempt_append

    actor = {"actor_type": "agent", "actor_id": "ag-1"}
    attempt = {"attempt_id": "att-100", "notes": "does it log?"}

    attempt_append(
        {"project_id": "prj_646d63703ec5", "attempt": attempt, "actor": actor}
    )

    # Read activity
    res = activity_list({"project_id": "prj_646d63703ec5"})[0]
    items = res["items"]

    # Check if there's an activity record for attempt att-100
    found = False
    for item in items:
        if item.get("target_id") == "att-100" and item.get("action") == "append":
            found = True
            break

    assert found


def test_exec_query_on_track(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    mcp_server._store = None

    from rekall.server.mcp_server import exec_query, get_store, work_update

    store = get_store()

    # 1. By default, sample artifact actually has 2 blocked items
    res = exec_query({"project_id": "prj_646d63703ec5", "query_type": "ON_TRACK"})[0]
    er = res.get("executive_response")
    assert er is not None
    assert er["confidence"] == "high"
    assert any("AT_RISK" in s for s in er["summary"])  # 2 active blockers
    assert len(er["evidence"]) > 0

    # 2. To test ON_TRACK, we must unblock them
    blockers = [w for w in store.work_items.values() if w.get("status") == "blocked"]
    for w in blockers:
        work_update(
            {
                "project_id": "prj_646d63703ec5",
                "work_item_id": w["work_item_id"],
                "expected_version": w["version"],
                "actor": {"actor_type": "human", "actor_id": "u-1"},
                "patch": {"status": "in_progress"},
                "force": True,
            }
        )

    res2 = exec_query({"project_id": "prj_646d63703ec5", "query_type": "ON_TRACK"})[0]
    er2 = res2["executive_response"]
    assert any("ON_TRACK" in s for s in er2["summary"])
    assert any(
        "in_progress" in getattr(ev, "status", "in_progress")
        for ev in er2.get("evidence", [])
    )  # heuristic check


def test_exec_query_blockers(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    mcp_server._store = None

    from rekall.server.mcp_server import exec_query, get_store, work_update

    store = get_store()

    wid = list(store.work_items.keys())[0]
    ver = store.work_items[wid]["version"]
    work_update(
        {
            "project_id": "prj_646d63703ec5",
            "work_item_id": wid,
            "expected_version": ver,
            "actor": {"actor_type": "human", "actor_id": "u-2"},
            "patch": {"status": "blocked"},
            "force": True,
        }
    )

    res = exec_query({"project_id": "prj_646d63703ec5", "query_type": "BLOCKERS"})[0]
    er = res["executive_response"]
    assert er["confidence"] in ["medium", "high"]
    assert any("blocked" in s for s in er["summary"])
    assert len(er["evidence"]) > 0
    assert any(wid in ev for ev in er["evidence"])


def test_exec_query_changed_since(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    mcp_server._store = None

    from rekall.server.mcp_server import exec_query, timeline_append

    # Add an event
    eid = f"evt-new-{uuid.uuid4().hex[:8]}"
    timeline_append(
        {
            "project_id": "prj_646d63703ec5",
            "event": {"event_id": eid, "message": "hello"},
            "actor": {"actor_type": "human", "actor_id": "u-1"},
        }
    )

    import datetime

    yesterday = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    ).isoformat()

    res = exec_query(
        {
            "project_id": "prj_646d63703ec5",
            "query_type": "CHANGED_SINCE",
            "since": yesterday,
        }
    )[0]
    er = res["executive_response"]
    assert any("activities since" in s for s in er["summary"])
    assert len(er["evidence"]) >= 1


def test_exec_query_resume_in_30(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    mcp_server._store = None

    from rekall.server.mcp_server import exec_query

    res = exec_query({"project_id": "prj_646d63703ec5", "query_type": "RESUME_IN_30"})[
        0
    ]
    er = res["executive_response"]

    # Should include goal, items, envs
    summary_text = " ".join(er["summary"])
    assert "Goal:" in summary_text

    evidence_text = " ".join(er["evidence"])
    assert "work_item:" in evidence_text
    assert "env:" in evidence_text


def test_artifact_append_idempotency(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    from rekall.server.mcp_server import artifact_append

    mcp_server._store = None
    actor = {"actor_type": "agent", "actor_id": "ag-1"}
    art = {"artifact_id": "art-1", "title": "PR"}

    res1 = artifact_append({"project_id": "prj_1", "artifact": art, "actor": actor})[0]
    assert "artifact" in res1

    art2 = {"artifact_id": "art-1", "title": "different"}
    res2 = artifact_append({"project_id": "prj_1", "artifact": art2, "actor": actor})[0]
    assert res2["artifact"]["title"] == "PR"


def test_research_append(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    from rekall.server.mcp_server import research_append

    mcp_server._store = None
    actor = {"actor_type": "agent", "actor_id": "ag-1"}
    res_item = {"research_id": "res-1", "title": "Notes"}

    r = research_append({"project_id": "prj_1", "research": res_item, "actor": actor})[
        0
    ]
    assert "research" in r


def test_link_append(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    from rekall.server.mcp_server import link_append

    mcp_server._store = None
    actor = {"actor_type": "agent", "actor_id": "ag-1"}
    link = {"edge_id": "edge-1", "from": {"node_type": "attempt", "id": "att-1"}}

    r = link_append({"project_id": "prj_1", "link": link, "actor": actor})[0]
    assert "link" in r


def test_anchor_save_resume(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    from rekall.server.mcp_server import anchor_resume, anchor_save

    mcp_server._store = None
    actor = {"actor_type": "agent", "actor_id": "ag-1"}
    anchor = {"anchor_id": "anch-1", "note": "Saving state"}

    anchor_save({"project_id": "prj_1", "anchor": anchor, "actor": actor})

    res = anchor_resume({"project_id": "prj_1", "anchor_id": "anch-1"})[0]
    assert "anchor" in res
    assert res["note"] == "Saving state"


def test_digest_while_you_were_gone(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    from rekall.server.mcp_server import digest_while_you_were_gone

    mcp_server._store = None

    res = digest_while_you_were_gone({"project_id": "prj_1"})[0]
    assert "summary" in res


def test_graph_trace(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    from rekall.server.mcp_server import (
        attempt_append,
        decision_propose,
        graph_trace,
        link_append,
    )

    mcp_server._store = None
    actor = {"actor_type": "agent", "actor_id": "ag-1"}

    attempt = {"attempt_id": "att-1", "notes": "test"}
    attempt_append({"project_id": "prj_1", "attempt": attempt, "actor": actor})

    decision = {"decision_id": "dec-1", "title": "test decision"}
    decision_propose({"project_id": "prj_1", "decision": decision, "actor": actor})

    link = {
        "edge_id": "edge-1",
        "from": {"node_type": "attempt", "id": "att-1"},
        "to": {"node_type": "decision", "id": "dec-1"},
    }
    link_append({"project_id": "prj_1", "link": link, "actor": actor})

    res = graph_trace(
        {"project_id": "prj_1", "root": {"node_type": "attempt", "id": "att-1"}}
    )[0]
    assert "nodes" in res
    assert "edges" in res


def test_propose_and_approve_capture_contract(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    from rekall.server.mcp_server import (
        capture_approval,
        capture_outcome,
        get_store,
        propose_action,
    )

    mcp_server._store = None
    actor = {"actor_type": "agent", "actor_id": "ag-1"}

    # 1. Propose action
    res1 = propose_action(
        {
            "project_id": "prj_1",
            "action_type": "run_command",
            "params": {"cmd": "npm install"},
            "risk_hint": "modifies node_modules",
            "context": {"cwd": "/app"},
            "actor": actor,
        }
    )[0]
    assert "action_id" in res1
    assert "action_hash" in res1
    action_id = res1["action_id"]

    # 2. Capture approval
    decision_id = f"dec-{uuid.uuid4().hex[:8]}"
    human_actor = {"actor_type": "human", "actor_id": "u-1"}
    res2 = capture_approval(
        {
            "project_id": "prj_1",
            "decision_id": decision_id,
            "action_id": action_id,
            "decision": "approve",
            "note": "Looks safe to me",
            "actor": human_actor,
        }
    )[0]
    assert res2["status"] == "success"
    assert "decision_id" in res2
    assert "anchor_id" in res2

    # 3. Capture outcome
    res3 = capture_outcome(
        {
            "project_id": "prj_1",
            "action_id": action_id,
            "outcome_metadata": {"exit_code": 0, "stdout": "installed 5 packages"},
            "actor": actor,
        }
    )[0]
    assert res3["status"] == "success"
    assert "attempt_id" in res3

    # Check store streams
    store = get_store()
    actions = store._load_jsonl("actions.jsonl")
    assert any(a["action_id"] == action_id for a in actions)

    decisions = store._load_jsonl("decisions.jsonl")
    assert any(d["decision_id"] == res2["decision_id"] for d in decisions)

    anchors = store._load_jsonl("anchors.jsonl")
    assert any(a["anchor_id"] == res2["anchor_id"] for a in anchors)

    attempts = store._load_jsonl("attempts.jsonl")
    assert any(a["attempt_id"] == res3["attempt_id"] for a in attempts)


def test_wait_for_approval_contract(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    from rekall.server.mcp_server import (
        get_store,
        propose_action,
        wait_for_approval,
    )

    mcp_server._store = None
    actor = {"actor_type": "agent", "actor_id": "ag-1"}

    # 1. Propose action
    res1 = propose_action(
        {
            "project_id": "prj_1",
            "action_type": "delete_db",
            "params": {"force": True},
            "risk_hint": "destructive",
            "context": {"cwd": "/"},
            "actor": actor,
        }
    )[0]
    action_id = res1["action_id"]

    # 2. Agent waits
    decision_id = f"dec-{uuid.uuid4().hex[:8]}"
    res2 = wait_for_approval(
        {
            "project_id": "prj_1",
            "decision_id": decision_id,
            "action_id": action_id,
            "prompt": "Waiting for human to verify delete_db",
            "actor": actor,
        }
    )[0]

    assert res2["status"] == "PAUSE_AND_EXIT"
    assert "exit your loop" in res2["message"]
    assert res2["decision_id"] == decision_id
    assert res2["action_id"] == action_id

    # Verify StateStore contains WaitingOnHuman event
    store = get_store()
    actions = store._load_stream("actions.jsonl")

    wait_events = [e for e in actions if e.get("type") == "WaitingOnHuman" and e.get("decision_id") == decision_id]
    assert len(wait_events) == 1
    assert wait_events[0]["prompt"] == "Waiting for human to verify delete_db"
    assert wait_events[0]["options"] == ["approve", "reject"]
    assert wait_events[0]["created_by"]["actor_id"] == "ag-1"

def test_actuator_cli(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    from rekall.server.mcp_server import (
        actuate_cli,
        propose_action,
    )

    mcp_server._store = None
    actor = {"actor_type": "agent", "actor_id": "ag-1"}

    # 1. Propose action
    res1 = propose_action(
        {
            "project_id": "prj_1",
            "action_type": "test_cmd",
            "params": {"cmd": "echo hello"},
            "risk_hint": "safe",
            "context": {"cwd": "/"},
            "actor": actor,
        }
    )[0]
    action_id = res1["action_id"]

    # 2. Actuate CLI (Linux/Mac/Win compat: echo usually works on all)
    res2 = actuate_cli(
        {
            "project_id": "prj_1",
            "action_id": action_id,
            "command": "echo hello_actuator",
            "actor": actor,
        }
    )[0]

    assert res2["status"] == "success"
    assert "hello_actuator" in res2["outcome"]["stdout"]

    # Verify outcome metadata was captured
    outcome = res2["record"]
    assert outcome["action_id"] == action_id
    assert res2["outcome"]["success"] is True

def test_actuator_file_write(monkeypatch, tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    from rekall.server.mcp_server import (
        actuate_file_write,
        propose_action,
    )

    mcp_server._store = None
    actor = {"actor_type": "agent", "actor_id": "ag-1"}

    res1 = propose_action(
        {
            "project_id": "prj_1",
            "action_type": "write_file",
            "params": {"file": "test.txt"},
            "risk_hint": "safe",
            "context": {"cwd": "/"},
            "actor": actor,
        }
    )[0]
    action_id = res1["action_id"]

    target_file = tmp_path / "test.txt"

    res2 = actuate_file_write(
        {
            "project_id": "prj_1",
            "action_id": action_id,
            "file_path": str(target_file),
            "content": "hello file write",
            "actor": actor,
        }
    )[0]

    assert res2["status"] == "success"
    assert target_file.exists()
    assert target_file.read_text(encoding="utf-8") == "hello file write"

    outcome = res2["record"]
    assert outcome["action_id"] == action_id
    assert res2["outcome"]["success"] is True
    assert res2["outcome"]["bytes_written"] > 0

def test_policy_preflight(tmp_path, monkeypatch):
    import shutil
    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_ARTIFACT_PATH", str(tmp_path))
    from rekall.server.mcp_server import policy_preflight

    mcp_server._store = None

    # 1. Test safe action
    res = policy_preflight({
        "project_id": "prj_1",
        "action_type": "ls",
        "params": {"args": "-l"}
    })[0]
    assert res["effect"] == "allow"

    # 2. Test destructive action (should match default policy)
    res = policy_preflight({
        "project_id": "prj_1",
        "action_type": "actuate_cli",
        "params": {"command": "rm -rf /"}
    })[0]
    assert res["effect"] == "deny"
    assert "Destructive" in res["reason"]

def test_guard_query():
    from rekall.server.mcp_server import guard_query
    result = guard_query({"project_id": "prj_646d63703ec5"})
    assert isinstance(result, list)
    assert len(result) == 1
    payload = result[0]
    assert payload["ok"] is True
    assert "guard" in payload
    assert "project" in payload
    assert "recent_decisions" in payload
    assert "recent_attempts" in payload


def test_guard_query_missing_project_id():
    from rekall.server.mcp_server import guard_query
    with pytest.raises(ValueError, match="project_id is required"):
        guard_query({})
def test_exec_query_dispatcher(monkeypatch):
    from rekall.server.mcp_server import exec_natural_query
    # 1. Test canonical fallback
    args = {"project_id": "prj_646d63703ec5", "query_type": "ON_TRACK"}
    res = exec_natural_query(args)[0]
    assert "executive_response" in res
    assert res["executive_response"]["confidence"] == "high"


def test_exec_query_dispatcher_natural():
    from rekall.server.mcp_server import exec_natural_query
    # 2. Test natural language path
    args = {"project_id": "prj_646d63703ec5", "query": "What is the status?"}
    res = exec_natural_query(args)[0]
    assert "text" in res
    assert "PROJECT EXECUTION LEDGER" in res["text"]
    assert "TIMELINE EVENTS" in res["text"]


def test_stale_lock_cleanup(monkeypatch, tmp_path):
    import json
    import time

    from rekall.core.state_store import StateStore

    # 1. Setup store with required files
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    (store_dir / "schema-version.txt").write_text("0.1", encoding="utf-8")
    (store_dir / "project.yaml").write_text("project_id: prj_1", encoding="utf-8")
    (store_dir / "envs.yaml").write_text("environments: {}", encoding="utf-8")
    (store_dir / "access.yaml").write_text("roles: {}", encoding="utf-8")

    # Create manifest to prevent initialization errors
    manifest = {
        "streams": {},
        "last_checkpoint": None,
        "schema_version": "0.1",
    }
    (store_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    store = StateStore(store_dir)

    # 2. Create a "stale" lock file (31s old)
    stream_name = "activity"
    stream_dir = store_dir / "streams" / stream_name
    stream_dir.mkdir(parents=True)
    active_file = stream_dir / "active.jsonl"
    active_file.touch()
    lock_file = active_file.with_suffix(".lock")
    lock_file.touch()

    # Backdate the lock file
    old_time = time.time() - 60
    import os
    os.utime(lock_file, (old_time, old_time))

    # 3. Running an append should cleanup the lock and succeed
    store.append_jsonl_idempotent(stream_name, {"type": "TestEvent", "id": "1"}, "id")

    assert not lock_file.exists()
    assert len(store._load_stream(stream_name)) == 1


def test_mcp_handle_request_tool_crash(monkeypatch):
    import json
    import sys
    from io import StringIO

    from rekall.server import mcp_server

    # Mock send_response to capture output
    output = StringIO()
    monkeypatch.setattr(mcp_server, "send_response", lambda x: output.write(json.dumps(x) + "\n"))

    # Mock a tool to crash
    def crashing_tool(args):
        raise RuntimeError("BOOM")

    monkeypatch.setitem(mcp_server.TOOL_REGISTRY, "crash.tool", crashing_tool)

    # Simulate tool call
    req = {
        "jsonrpc": "2.0",
        "id": "123",
        "method": "tools/call",
        "params": {
            "name": "crash.tool",
            "arguments": {}
        }
    }

    # Suppress stderr print during test
    monkeypatch.setattr(sys, "stderr", StringIO())

    mcp_server.handle_request(req)

    res = json.loads(output.getvalue())
    assert res["id"] == "123"
    assert "isError" in res["result"]
    assert res["result"]["isError"] is True
    assert "Error executing tool 'crash.tool': BOOM" in res["result"]["content"][0]["text"]

def test_project_bootstrap(monkeypatch, tmp_path):
    # Start with an empty directory (no project-state)
    monkeypatch.setenv("REKALL_STATE_DIR", str(tmp_path / "project-state"))
    mcp_server._store = None
    mcp_server._base_dir = tmp_path / "project-state"

    from rekall.server.mcp_server import project_bootstrap

    args = {
        "goal": "Test Goal",
        "phase": "Alpha",
        "status": "STARTED"
    }

    res = project_bootstrap(args)[0]
    assert res["status"] == "success"
    assert res["metadata"]["goal"] == "Test Goal"
    assert res["metadata"]["phase"] == "Alpha"
    assert (tmp_path / "project-state" / "manifest.json").exists()


def test_project_meta_get_patch(monkeypatch, tmp_path):
    import shutil
    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("REKALL_STATE_DIR", str(tmp_path))
    mcp_server._store = None
    mcp_server._base_dir = tmp_path

    from rekall.server.mcp_server import project_meta_get, project_meta_patch

    # Get initial
    res1 = project_meta_get({})[0]
    assert "metadata" in res1

    # Patch
    patch_args = {
        "patch": {"goal": "Updated Goal", "confidence": "0.99"},
        "actor": {"actor_id": "test_agent"}
    }
    res2 = project_meta_patch(patch_args)[0]
    assert res2["metadata"]["goal"] == "Updated Goal"
    assert res2["metadata"]["confidence"] == "0.99"

    # Verify persistence
    mcp_server._store = None
    res3 = project_meta_get({})[0]
    assert res3["metadata"]["goal"] == "Updated Goal"
