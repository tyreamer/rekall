import pytest
from pathlib import Path
from rekall.core.state_store import StateStore, SecretDetectedError, StateConflictError

SAMPLE_DIR = Path(__file__).parent.parent / "examples" / "sample_state_artifact"


def test_load_sample_artifact(tmp_path):
    # Copy sample to tmp so migration doesn't mess with repo
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)

    StateStore(tmp_path)

    # Check that it migrated
    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "streams" / "work_items" / "active.jsonl").exists()
    # Legacy file should be gone
    assert not (tmp_path / "work-items.jsonl").exists()


def test_work_items_replayed(tmp_path):
    import shutil

    shutil.copytree(SAMPLE_DIR, tmp_path, dirs_exist_ok=True)
    store = StateStore(tmp_path)
    assert len(store.work_items) > 0

    # Check that at least one item has a computed version and claim status
    for wid, item in store.work_items.items():
        assert "version" in item
        assert isinstance(item["version"], int)
        assert "claim" in item


def test_secret_detection(tmp_path):
    store = StateStore(SAMPLE_DIR)

    malicious_records = [
        {"notes": "Here is my key sk-A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0"},
        {"url": "https://example.com?token=12345"},
        {"url": "https://example.com?access_token=abcdef"},
        {"url": "https://example.com?Authorization: Bearer xyz"},
        {"url": "https://github.com/repo?ghp_1234567890abcdef1234567890abcdef1234"},
        {"header": "x-api-key: 12345"},
        {"key": "AIzaSyB-abcdefghijklmnopqrstuvwxyz12345"},
    ]

    for record in malicious_records:
        with pytest.raises(SecretDetectedError):
            store.append_jsonl_idempotent("activity", record, id_field="event_id")


def test_sanitize_url():
    from rekall.core.state_store import sanitize_url

    # Should strip query params
    assert sanitize_url("https://example.com?foo=bar") == "https://example.com"
    assert (
        sanitize_url("https://github.com/org/repo/pull/1?access_token=secret")
        == "https://github.com/org/repo/pull/1"
    )

    # Should leave url without query params alone
    assert sanitize_url("https://example.com/path") == "https://example.com/path"

    # Should handle empty/none
    assert sanitize_url("") == ""
    assert sanitize_url(None) is None


def test_append_idempotent_dedupes(tmp_path):
    store = StateStore(SAMPLE_DIR)
    store.base_dir = tmp_path  # Override base_dir for testing writes

    record = {"log_id": "123", "data": "hello"}

    # First append
    store.append_jsonl_idempotent("test_stream", record, "log_id")

    # Second append (should be ignored)
    store.append_jsonl_idempotent(
        "test_stream", {"log_id": "123", "data": "world"}, "log_id"
    )

    # Verify file only has one line
    active_path = tmp_path / "streams" / "test_stream" / "active.jsonl"
    lines = active_path.read_text().splitlines()
    assert len(lines) == 1
    assert '"hello"' in lines[0]


def test_optimistic_concurrency(tmp_path):
    (tmp_path / "schema-version.txt").write_text("0.1")
    store = StateStore(tmp_path)

    # Add a mock work item via the API if possible, or just mock memory for this specific test
    # But since initialize() replays work_items, we should at least have a manifest entry
    store.append_jsonl_idempotent("work_items", {"event_id": "dummy"}, "event_id")
    store.work_items["WI-test"] = {
        "work_item_id": "WI-test",
        "version": 2,
        "title": "Initial",
    }

    actor = {"actor_type": "human", "actor_id": "user"}

    # Valid update
    updated = store.update_work_item(
        "WI-test", {"title": "Updated"}, expected_version=2, actor=actor
    )
    assert updated["version"] == 3
    assert updated["title"] == "Updated"

    # Invalid update (conflict)
    with pytest.raises(StateConflictError):
        store.update_work_item(
            "WI-test", {"title": "Conflict"}, expected_version=2, actor=actor
        )
