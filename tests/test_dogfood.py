import tempfile
from argparse import Namespace
from pathlib import Path

import pytest

from rekall.cli import cmd_timeline_add, ensure_state_initialized


@pytest.fixture
def temp_repo():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def test_ensure_state_initialized(temp_repo):
    store_dir = temp_repo / "project-state"
    ensure_state_initialized(store_dir, is_json=False)

    assert store_dir.exists()
    assert (store_dir / "schema-version.txt").read_text() == "0.1"
    assert (store_dir / "project.yaml").exists()
    assert (store_dir / "envs.yaml").exists()
    assert (store_dir / "access.yaml").exists()
    assert (store_dir / "streams/work_items/active.jsonl").exists()
    assert (store_dir / "streams/activity/active.jsonl").exists()
    assert (store_dir / "streams/attempts/active.jsonl").exists()
    assert (store_dir / "streams/decisions/active.jsonl").exists()
    assert (store_dir / "streams/timeline/active.jsonl").exists()


def test_timeline_add_auto_inits(temp_repo, capfd):
    store_dir = temp_repo / "project-state"
    args = Namespace(
        store_dir=str(store_dir),
        json=False,
        summary="Test CI Dogfooding",
        idempotency_key="ci-run-1",
        actor="ci_bot",
    )

    # Store dir does not exist yet. cmd_timeline_add should intercept and create it.
    cmd_timeline_add(args)

    assert store_dir.exists()
    assert (store_dir / "streams/timeline/active.jsonl").exists()

    timeline_content = (store_dir / "streams/timeline/active.jsonl").read_text()
    assert "Test CI Dogfooding" in timeline_content
    assert "ci-run-1" in timeline_content
