import os
import tempfile
import json
import pytest
from pathlib import Path
from rekall.cli import cmd_validate, cmd_export, cmd_import, cmd_handoff
from argparse import Namespace

@pytest.fixture
def temp_store():
    with tempfile.TemporaryDirectory() as d:
        base_dir = Path(d)
        (base_dir / "schema-version.txt").write_text("0.1")
        (base_dir / "project.yaml").write_text("project_id: test_proj\ndescription: Test\nrepo_url: https://github.com/test")
        (base_dir / "envs.yaml").write_text("dev: {}")
        (base_dir / "access.yaml").write_text("roles: {}")
        
        # Valid work item
        event = {
            "event_id": "e1",
            "type": "WORK_ITEM_CREATED",
            "work_item_id": "wi_1",
            "patch": {
                "title": "Test Item",
                "status": "todo",
                "priority": "p1"
            }
        }
        (base_dir / "work-items.jsonl").write_text(json.dumps(event) + "\n")
        yield base_dir

def test_cmd_validate_success(temp_store, caplog):
    import logging
    caplog.set_level(logging.INFO)
    args = Namespace(store_dir=str(temp_store))
    try:
        cmd_validate(args)
    except SystemExit as e:
        # Should not exit on success, or exit 0
        assert e.code == 0
    assert "Validation successful: 1 work" in caplog.text

def test_cmd_validate_failure():
    with tempfile.TemporaryDirectory() as d:
        base_dir = Path(d)
        (base_dir / "schema-version.txt").write_text("0.1")
        # Missing title and status
        event = {
            "event_id": "e1",
            "type": "WORK_ITEM_CREATED",
            "work_item_id": "wi_1",
            "patch": {}
        }
        (base_dir / "work-items.jsonl").write_text(json.dumps(event) + "\n")
        
        args = Namespace(store_dir=d)
        with pytest.raises(SystemExit) as excinfo:
            cmd_validate(args)
        assert excinfo.value.code == 1

def test_cmd_export(temp_store):
    out_dir = temp_store / "output_dir"
    args = Namespace(store_dir=str(temp_store), out=str(out_dir), json=False)
    
    cmd_export(args)
    
    assert out_dir.exists()
    assert (out_dir / "project.yaml").exists()
    assert (out_dir / "schema-version.txt").exists()
    assert (out_dir / "work-items.jsonl").exists()

def test_cmd_import(temp_store):
    out_dir = temp_store / "output_dir"
    args = Namespace(store_dir=str(temp_store), out=str(out_dir), json=False)
    cmd_export(args)
    
    # Import into a new dir
    with tempfile.TemporaryDirectory() as import_d:
        import_args = Namespace(source=str(out_dir), store_dir=import_d, json=False)
        cmd_import(import_args)
        
        imported_dir = Path(import_d)
        assert (imported_dir / "schema-version.txt").exists()
        assert (imported_dir / "project.yaml").exists()
        assert (imported_dir / "work-items.jsonl").exists()

def test_cmd_handoff(temp_store):
    out_dir = temp_store / "handoff_out"
    args = Namespace(store_dir=str(temp_store), project_id="test_proj", out=str(out_dir))
    
    cmd_handoff(args)
    
    assert out_dir.exists()
    assert (out_dir / "snapshot.json").exists()
    brief = out_dir / "boot_brief.md"
    assert brief.exists()
    
    content = brief.read_text()
    assert "Project Goal" in content
    assert "Status" in content
    assert "Blockers" in content
    assert "wi_1" in content
    assert "test_proj" in content
