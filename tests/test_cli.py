import os
import tempfile
import json
import pytest
from pathlib import Path
from rekall.cli import cmd_validate, cmd_export, cmd_import, cmd_handoff, ExitCode
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

def test_cmd_validate_success(temp_store, capfd):
    import logging
    args = Namespace(store_dir=str(temp_store), json=False, strict=False)
    try:
        cmd_validate(args)
    except SystemExit as e:
        # Should not exit on success, or exit 0
        assert e.code == 0
    captured = capfd.readouterr()
    assert "Status: ⚠️" in captured.out  # the mock has dangling refs so it's a warning, not a perfect check

def test_cmd_validate_missing_dir(capfd):
    # Test validation when store_dir does not exist
    args = Namespace(store_dir="/nonexistent/path", json=False, strict=False)
    with pytest.raises(SystemExit) as excinfo:
        cmd_validate(args)
    assert excinfo.value.code == ExitCode.NOT_FOUND.value

def test_cmd_validate_failure():
    with tempfile.TemporaryDirectory() as d:
        base_dir = Path(d)
        (base_dir / "schema-version.txt").write_text("0.1")
        # Missing title and status so validation will flag it
        event = {
            "event_id": "e1",
            "type": "WORK_ITEM_CREATED",
            "work_item_id": "wi_1",
            "patch": {}
        }
        (base_dir / "work-items.jsonl").write_text(json.dumps(event) + "\n")
        
        args = Namespace(store_dir=d, json=False, strict=False)
        with pytest.raises(SystemExit) as excinfo:
            cmd_validate(args)
        assert excinfo.value.code == ExitCode.VALIDATION_FAILED.value

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
def test_validate_regression_missing_files(temp_store, capfd):
    import os
    os.remove(temp_store / "envs.yaml")
    args = Namespace(store_dir=str(temp_store), json=False, strict=True)
    with pytest.raises(SystemExit) as excinfo:
        cmd_validate(args)
    assert excinfo.value.code == ExitCode.VALIDATION_FAILED.value
    captured = capfd.readouterr()
    assert "missing" in captured.out.lower()
    
def test_validate_regression_malformed_jsonl():
    with tempfile.TemporaryDirectory() as d:
        base_dir = Path(d)
        (base_dir / "schema-version.txt").write_text("0.1")
        (base_dir / "project.yaml").write_text("project_id: test_proj\n")
        (base_dir / "envs.yaml").write_text("dev: {}")
        (base_dir / "access.yaml").write_text("roles: {}")
        
        # Malformed jsonl
        (base_dir / "work-items.jsonl").write_text("{bad json\n")
        
        args = Namespace(store_dir=d, json=False, strict=False)
        with pytest.raises(SystemExit) as excinfo:
            cmd_validate(args)
        assert excinfo.value.code == ExitCode.VALIDATION_FAILED.value

def test_validate_regression_duplicate_ids():
    with tempfile.TemporaryDirectory() as d:
        base_dir = Path(d)
        (base_dir / "schema-version.txt").write_text("0.1")
        (base_dir / "project.yaml").write_text("project_id: test_proj\n")
        (base_dir / "envs.yaml").write_text("dev: {}")
        (base_dir / "access.yaml").write_text("roles: {}")
        
        event = {
            "event_id": "duplicate_1",
            "type": "WORK_ITEM_CREATED",
            "work_item_id": "wi_1",
            "patch": {"title": "Test", "status": "todo"}
        }
        content = json.dumps(event) + "\n" + json.dumps(event) + "\n"
        (base_dir / "work-items.jsonl").write_text(content)
        
        args = Namespace(store_dir=d, json=False, strict=True)
        with pytest.raises(SystemExit) as excinfo:
            cmd_validate(args)
        assert excinfo.value.code == ExitCode.VALIDATION_FAILED.value

def test_validate_regression_expired_claim(temp_store, capfd):
    import datetime
    store = temp_store
    
    # Manually inject an expired claim into work-items.jsonl
    event = {
        "event_id": "e_claim",
        "type": "WORK_ITEM_CLAIMED",
        "work_item_id": "wi_1",
        "patch": {
            "claimed_by": "test_user",
            "lease_until": (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)).isoformat()
        }
    }
    with open(store / "work-items.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
        
    args = Namespace(store_dir=str(store), json=False, strict=True)
    with pytest.raises(SystemExit) as excinfo:
        cmd_validate(args)
    assert excinfo.value.code == ExitCode.VALIDATION_FAILED.value
    captured = capfd.readouterr()
    assert "expired" in captured.out.lower()

def test_validate_json_schema(temp_store, capfd):
    args = Namespace(store_dir=str(temp_store), json=True, strict=False)
    # Should not raise
    cmd_validate(args)
    captured = capfd.readouterr()
    report = json.loads(captured.out)
    
    assert "summary" in report
    assert "schema_version" in report
    assert "files_present" in report
    assert "jsonl_integrity" in report
    assert "id_uniqueness" in report
    assert "references" in report
    assert "secrets" in report
    assert "claims" in report
