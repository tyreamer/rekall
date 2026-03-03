"""Tests for rekall checkpoint command."""

import json
import tempfile
from argparse import Namespace
from pathlib import Path

import pytest

from rekall.cli import ExitCode, cmd_checkpoint, cmd_validate


@pytest.fixture
def temp_store():
    with tempfile.TemporaryDirectory() as d:
        base_dir = Path(d)
        from rekall.cli import ensure_state_initialized
        ensure_state_initialized(base_dir, is_json=True, init_mode=True)

        event = {
            "event_id": "e1",
            "type": "WORK_ITEM_CREATED",
            "work_item_id": "wi_1",
            "patch": {"title": "Test Item", "status": "todo", "priority": "p1"},
        }
        # Add a work item to ensure some state exists if needed
        from rekall.core.state_store import StateStore
        store = StateStore(base_dir)
        store.append_jsonl_idempotent("work_items", event, "event_id")
        yield base_dir


class TestCheckpointExport:
    def test_creates_valid_export(self, temp_store):
        """Checkpoint creates an export folder that passes rekall validate."""
        out_dir = temp_store / "checkpoint_out"
        args = Namespace(
            store_dir=str(temp_store),
            out=str(out_dir),
            json=False,
            type="milestone",
            title="pre-deploy",
            summary="test summary",
            actor="cli_user",
            event_id=None,
            project_id="test_proj",
        )
        cmd_checkpoint(args)

        # Export folder must exist with required files
        assert out_dir.exists()
        assert (out_dir / "schema-version.txt").exists()
        assert (out_dir / "project.yaml").exists()
        assert (out_dir / "streams/work_items/active.jsonl").exists()

        # Exported folder must pass validation
        validate_args = Namespace(
            store_dir=str(out_dir),
            json=False,
            strict=False,
            mcp=False,
            server_cmd=None,
            quiet=True,
        )
        # Should not raise (or exit 0)
        try:
            cmd_validate(validate_args)
        except SystemExit as e:
            # Allow exit 0 or warnings (3) but not errors (2)
            assert e.code != ExitCode.VALIDATION_FAILED.value


class TestCheckpointTimeline:
    def test_appends_one_timeline_event(self, temp_store):
        """Checkpoint appends exactly one timeline event per run."""
        out_dir = temp_store / "ckpt1"
        args = Namespace(
            store_dir=str(temp_store),
            out=str(out_dir),
            json=False,
            type="milestone",
            title="v1",
            summary="test summary",
            actor="cli_user",
            event_id=None,
            project_id="test_proj",
        )
        cmd_checkpoint(args)

        with open(temp_store / "streams/timeline/active.jsonl") as f:
            lines = [line for line in f.readlines() if line.strip()]
        assert len(lines) == 1

        evt = json.loads(lines[0])
        assert evt["type"] == "milestone"
        assert "test summary" in evt["summary"]

    def test_checkpoint_task_done(self, temp_store):
        args = Namespace(
            store_dir=str(temp_store),
            out=None,
            json=False,
            type="task_done",
            title="Completed feature X",
            summary="Did some work",
            actor="cli_user",
            event_id=None,
            project_id="test_proj",
        )
        cmd_checkpoint(args)

        with open(temp_store / "streams/work_items/active.jsonl") as f:
            lines = [line for line in f.readlines() if line.strip()]
        assert len(lines) == 2
        evt = json.loads(lines[-1])
        assert evt["type"] == "WORK_ITEM_CREATED"

        with open(temp_store / "streams/timeline/active.jsonl") as f:
            lines = [line for line in f.readlines() if line.strip()]
        assert len(lines) == 1
        evt = json.loads(lines[0])
        assert evt["type"] == "milestone"
        assert "Task completed: Completed feature X" in evt["summary"]

    def test_idempotent_with_event_id(self, temp_store):
        """If event_id is provided and command runs twice, only one timeline event."""
        out_dir = temp_store / "ckpt_idem"
        args = Namespace(
            store_dir=str(temp_store),
            out=str(out_dir),
            json=False,
            type="milestone",
            title="idempotent-test",
            summary="test summary",
            actor="cli_user",
            event_id="fixed_checkpoint_001",
            project_id="test_proj",
        )

        cmd_checkpoint(args)
        cmd_checkpoint(args)

        with open(temp_store / "streams/timeline/active.jsonl") as f:
            lines = [line for line in f.readlines() if line.strip()]
        assert len(lines) == 1
        evt = json.loads(lines[0])
        assert evt["event_id"] == "fixed_checkpoint_001"

    def test_two_runs_without_event_id_create_two_events(self, temp_store):
        """Without explicit event_id, each run creates a new event."""
        args1 = Namespace(
            store_dir=str(temp_store),
            out=str(temp_store / "ckpt_a"),
            json=False,
            type="milestone",
            title="run1",
            summary="test run1",
            actor="cli_user",
            event_id=None,
            project_id="test_proj",
        )
        args2 = Namespace(
            store_dir=str(temp_store),
            out=str(temp_store / "ckpt_b"),
            json=False,
            type="milestone",
            title="run2",
            summary="test run2",
            actor="cli_user",
            event_id=None,
            project_id="test_proj",
        )

        cmd_checkpoint(args1)
        cmd_checkpoint(args2)

        with open(temp_store / "streams/timeline/active.jsonl") as f:
            lines = [line for line in f.readlines() if line.strip()]
        assert len(lines) == 2


class TestCheckpointJSON:
    def test_json_output_valid(self, temp_store, capfd):
        """--json output is valid JSON with required keys."""
        out_dir = temp_store / "ckpt_json"
        args = Namespace(
            store_dir=str(temp_store),
            out=str(out_dir),
            json=True,
            type="milestone",
            title="json-test",
            summary="test json output",
            actor="cli_user",
            event_id=None,
            project_id="test_proj",
        )
        cmd_checkpoint(args)

        captured = capfd.readouterr()
        data = json.loads(captured.out)

        assert data["ok"] is True
        assert "id" in data
        assert data["type"] == "milestone"

    def test_json_with_event_id(self, temp_store, capfd):
        out_dir = temp_store / "ckpt_json2"
        args = Namespace(
            store_dir=str(temp_store),
            out=str(out_dir),
            json=True,
            type="milestone",
            title="json-eid",
            summary="test eid",
            actor="tester",
            event_id="custom_evt_42",
            project_id="test_proj",
        )
        cmd_checkpoint(args)

        captured = capfd.readouterr()
        data = json.loads(captured.out)
        assert data["id"] == "custom_evt_42"


class TestCheckpointEdgeCases:
    def test_missing_store_dir(self):
        args = Namespace(
            store_dir="/nonexistent/path",
            out="/tmp/out",
            json=False,
            type="milestone",
            title="x",
            summary="x",
            actor="x",
            event_id=None,
            project_id="test_proj",
        )
        with pytest.raises(SystemExit) as excinfo:
            cmd_checkpoint(args)
        assert excinfo.value.code == ExitCode.NOT_FOUND.value
