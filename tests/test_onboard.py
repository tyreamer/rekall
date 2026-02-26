import os
import tempfile
import json
import pytest
from pathlib import Path
from rekall.cli import cmd_onboard, ExitCode
from argparse import Namespace

@pytest.fixture
def temp_repo():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)

def test_onboard_auto_init(temp_repo, capfd):
    # In a temp repo with no project-state/, rekall onboard creates it and writes the file.
    store_dir = temp_repo / "project-state"
    args = Namespace(store_dir=str(store_dir), json=False, print=False, out=None, force=False, debug=False)
    
    cmd_onboard(args)
    
    assert store_dir.exists()
    assert (store_dir / "project.yaml").exists()
    cheat_sheet = store_dir / "artifacts" / "onboard_cheatsheet.md"
    assert cheat_sheet.exists()
    
    content = cheat_sheet.read_text()
    assert "# Onboarding Cheat Sheet" in content
    assert "What is Rekall?" in content
    
    captured = capfd.readouterr()
    assert f"Created: {cheat_sheet}" in captured.out

def test_onboard_existing_repo(temp_repo, capfd):
    # In a repo with project-state/, rekall onboard writes the file.
    store_dir = temp_repo / "project-state"
    store_dir.mkdir()
    (store_dir / "schema-version.txt").write_text("0.1")
    (store_dir / "project.yaml").write_text("project_id: existing_proj\n")
    
    args = Namespace(store_dir=str(store_dir), json=False, print=False, out=None, force=False, debug=False)
    cmd_onboard(args)
    
    cheat_sheet = store_dir / "artifacts" / "onboard_cheatsheet.md"
    assert cheat_sheet.exists()
    assert "existing_proj" in cheat_sheet.read_text()

def test_onboard_force_overwrite(temp_repo):
    # --force overwrites existing file.
    store_dir = temp_repo / "project-state"
    store_dir.mkdir()
    (store_dir / "schema-version.txt").write_text("0.1")
    (store_dir / "project.yaml").write_text("project_id: force_test\n")
    
    artifacts_dir = store_dir / "artifacts"
    artifacts_dir.mkdir()
    cheat_sheet = artifacts_dir / "onboard_cheatsheet.md"
    cheat_sheet.write_text("old content")
    
    # Without force should fail
    args = Namespace(store_dir=str(store_dir), json=False, print=False, out=None, force=False, debug=False)
    with pytest.raises(SystemExit) as excinfo:
        cmd_onboard(args)
    assert excinfo.value.code == ExitCode.CONFLICT.value
    
    # With force should succeed
    args.force = True
    cmd_onboard(args)
    assert "old content" not in cheat_sheet.read_text()
    assert "# Onboarding Cheat Sheet" in cheat_sheet.read_text()

def test_onboard_corrupted_jsonl(temp_repo, capfd):
    # Corrupted JSONL in state produces a friendly error (assert substring contains filename).
    store_dir = temp_repo / "project-state"
    store_dir.mkdir()
    (store_dir / "schema-version.txt").write_text("0.1")
    (store_dir / "project.yaml").write_text("project_id: corrupt_test\n")
    (store_dir / "work-items.jsonl").write_text("{bad json\n")
    
    args = Namespace(store_dir=str(store_dir), json=False, print=False, out=None, force=False, debug=False)
    with pytest.raises(SystemExit) as excinfo:
        cmd_onboard(args)
    assert excinfo.value.code == ExitCode.INTERNAL_ERROR.value
    
    captured = capfd.readouterr()
    assert "Onboarding failed" in captured.out
    assert "active.jsonl" in captured.out.lower()

def test_onboard_print_flag(temp_repo, capfd):
    # --print includes expected heading text on stdout.
    store_dir = temp_repo / "project-state"
    args = Namespace(store_dir=str(store_dir), json=False, print=True, out=None, force=False, debug=False)
    
    cmd_onboard(args)
    
    captured = capfd.readouterr()
    assert "--- ONBOARDING CHEAT SHEET ---" in captured.out
    assert "# Onboarding Cheat Sheet" in captured.out
