import json

import pytest

from rekall.server import mcp_server
from rekall.server.mcp_server import (
    get_store,
    project_get,
    timeline_list,
    work_get,
    work_list,
)


@pytest.fixture(autouse=True)
def setup_store(monkeypatch, tmp_path):
    store_dir = tmp_path / "project-state"
    store_dir.mkdir()
    (store_dir / "schema-version.txt").write_text("0.1")
    (store_dir / "project.yaml").write_text("project_id: test_proj\ndescription: Test\n")
    (store_dir / "manifest.json").write_text(json.dumps({
        "schema_version": "0.1",
        "streams": {}
    }))

    monkeypatch.setenv("REKALL_STATE_DIR", str(store_dir))
    mcp_server._base_dir = store_dir
    mcp_server._store = None
    get_store()
    yield


def test_project_get():
    result = project_get({"project_id": "test_proj"})
    assert isinstance(result, list)
    assert len(result) == 1
    assert "project" in result[0]
    assert result[0]["project"]["project_id"] == "test_proj"


def test_work_list_empty():
    result = work_list({"project_id": "test_proj", "limit": 10})
    assert isinstance(result, list)
    payload = result[0]
    assert "items" in payload
    assert len(payload["items"]) == 0


def test_work_create_and_get():
    store = get_store()
    store.create_work_item(
        {"title": "Test task", "status": "todo", "priority": "p1"},
        {"actor_id": "test"},
    )

    result = work_list({"project_id": "test_proj", "limit": 10})
    items = result[0]["items"]
    assert len(items) == 1
    wid = items[0]["work_item_id"]

    result = work_get({"project_id": "test_proj", "work_item_id": wid})
    assert "work_item" in result[0]
    assert result[0]["work_item"]["title"] == "Test task"


def test_timeline_list():
    store = get_store()
    store.append_timeline(
        {"type": "milestone", "summary": "Test event"},
        {"actor_id": "test"},
    )

    result = timeline_list({"project_id": "test_proj", "limit": 5})
    assert "items" in result[0]
    assert len(result[0]["items"]) > 0
