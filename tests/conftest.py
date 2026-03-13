import pytest


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Ensure tests don't inherit local or global state configuration."""
    monkeypatch.delenv("REKALL_STATE_DIR", raising=False)
    monkeypatch.delenv("REKALL_ARTIFACT_PATH", raising=False)
