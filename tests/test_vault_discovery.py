import tempfile
from pathlib import Path

from rekall.core.state_store import resolve_vault_dir


def test_resolve_vault_dir_basic():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # Fallback to current / project-state
        res = resolve_vault_dir(tmp_path)
        assert res == tmp_path / "project-state"

def test_resolve_vault_dir_project_state_exists():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ps = tmp_path / "project-state"
        ps.mkdir()
        (ps / "manifest.json").write_text("{}")

        res = resolve_vault_dir(tmp_path)
        assert res == ps

def test_resolve_vault_dir_parent():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ps = root / "project-state"
        ps.mkdir()
        (ps / "manifest.json").write_text("{}")

        child = root / "subdir" / "deep"
        child.mkdir(parents=True)

        res = resolve_vault_dir(child)
        assert res == ps

def test_resolve_vault_dir_dotdir():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ps = root / ".rekall" / "project-state"
        ps.mkdir(parents=True)
        (ps / "manifest.json").write_text("{}")

        res = resolve_vault_dir(root)
        assert res == ps
