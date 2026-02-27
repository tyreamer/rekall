import tempfile
from argparse import Namespace
from pathlib import Path

import pytest

from rekall.cli import ExitCode, cmd_init


@pytest.fixture
def temp_repo():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def test_init_auto_init(temp_repo, capfd):
    # In a temp repo with no project-state/, rekall init creates it and writes the file.
    store_dir = temp_repo / "project-state"
    args = Namespace(
        store_dir=str(store_dir),
        state_dir=None,
        dotdir=False,
        json=False,
        print=False,
        out=None,
        force=False,
        debug=False,
    )

    cmd_init(args)

    assert store_dir.exists()
    assert (store_dir / "project.yaml").exists()
    cheat_sheet = store_dir / "artifacts" / "onboard_cheatsheet.md"
    assert cheat_sheet.exists()

    content = cheat_sheet.read_text()
    assert "# Onboarding Cheat Sheet" in content
    assert "What is Rekall?" in content

    captured = capfd.readouterr()
    assert f"Created: {cheat_sheet}" in captured.out


def test_init_existing_repo(temp_repo, capfd):
    # In a repo with project-state/, rekall init writes the file.
    store_dir = temp_repo / "project-state"
    store_dir.mkdir()
    (store_dir / "schema-version.txt").write_text("0.1")
    (store_dir / "project.yaml").write_text("project_id: existing_proj\n")

    args = Namespace(
        store_dir=str(store_dir),
        state_dir=None,
        dotdir=False,
        json=False,
        print=False,
        out=None,
        force=False,
        debug=False,
    )
    cmd_init(args)

    cheat_sheet = store_dir / "artifacts" / "onboard_cheatsheet.md"
    assert cheat_sheet.exists()
    assert "existing_proj" in cheat_sheet.read_text()


def test_init_force_overwrite(temp_repo):
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
    args = Namespace(
        store_dir=str(store_dir),
        state_dir=None,
        dotdir=False,
        json=False,
        print=False,
        out=None,
        force=False,
        debug=False,
    )
    with pytest.raises(SystemExit) as excinfo:
        cmd_init(args)
    assert excinfo.value.code == ExitCode.CONFLICT.value

    # With force should succeed
    args.force = True
    cmd_init(args)
    assert "old content" not in cheat_sheet.read_text()
    assert "# Onboarding Cheat Sheet" in cheat_sheet.read_text()


def test_init_corrupted_jsonl(temp_repo, capfd):
    # Corrupted JSONL in state produces a friendly error (assert substring contains filename).
    store_dir = temp_repo / "project-state"
    store_dir.mkdir()
    (store_dir / "schema-version.txt").write_text("0.1")
    (store_dir / "project.yaml").write_text("project_id: corrupt_test\n")
    (store_dir / "streams/work_items").mkdir(parents=True, exist_ok=True)
    (store_dir / "streams/work_items/active.jsonl").write_text("{bad json\n")

    args = Namespace(
        store_dir=str(store_dir),
        state_dir=None,
        dotdir=False,
        json=False,
        print=False,
        out=None,
        force=False,
        debug=True,
    )
    with pytest.raises(SystemExit) as excinfo:
        cmd_init(args)
    assert excinfo.value.code == ExitCode.INTERNAL_ERROR.value

    captured = capfd.readouterr()
    assert "Onboarding failed" in captured.out
    assert "active.jsonl" in captured.out.lower()


def test_init_print_flag(temp_repo, capfd):
    # --print includes expected heading text on stdout.
    store_dir = temp_repo / "project-state"
    args = Namespace(
        store_dir=str(store_dir),
        state_dir=None,
        dotdir=False,
        json=False,
        print=True,
        out=None,
        force=False,
        debug=False,
    )

    cmd_init(args)

    captured = capfd.readouterr()
    assert "--- ONBOARDING CHEAT SHEET ---" in captured.out
    assert "# Onboarding Cheat Sheet" in captured.out


def test_init_state_dir_flag(temp_repo):
    # --state-dir flag overrides default
    custom_dir = temp_repo / "custom-state"
    args = Namespace(
        store_dir="project-state",
        state_dir=str(custom_dir),
        dotdir=False,
        json=False,
        print=False,
        out=None,
        force=False,
        debug=False,
    )

    cmd_init(args)

    assert custom_dir.exists()
    assert (custom_dir / "artifacts" / "onboard_cheatsheet.md").exists()
    assert not (temp_repo / "project-state").exists()


def test_init_dotdir_flag(temp_repo, monkeypatch):
    # --dotdir flag uses .rekall/
    monkeypatch.chdir(temp_repo)
    args = Namespace(
        store_dir="project-state",
        state_dir=None,
        dotdir=True,
        json=False,
        print=False,
        out=None,
        force=False,
        debug=False,
    )

    cmd_init(args)

    assert (temp_repo / ".rekall").exists()
    assert (temp_repo / ".rekall" / "artifacts" / "onboard_cheatsheet.md").exists()
