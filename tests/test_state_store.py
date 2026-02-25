import pytest
from pathlib import Path
from rekall.core.state_store import StateStore, SchemaVersionError, SecretDetectedError, StateConflictError

SAMPLE_DIR = Path(__file__).parent.parent / "examples" / "sample_state_artifact"

def test_load_sample_artifact():
    # Should load without errors
    store = StateStore(SAMPLE_DIR)
    
    assert store.project_config["schema_version"] == "0.1"
    assert "environments" in store.envs_config
    assert "access_refs" in store.access_config

def test_work_items_replayed():
    store = StateStore(SAMPLE_DIR)
    assert len(store.work_items) > 0
    
    # Check that at least one item has a computed version and claim status
    for wid, item in store.work_items.items():
        assert "version" in item
        assert isinstance(item["version"], int)
        assert "claim" in item

def test_secret_detection(tmp_path):
    store = StateStore(SAMPLE_DIR)
    
    malicious_record = {
        "event_id": "evt-malicious",
        "actor": {"actor_type": "human", "actor_id": "h-1"},
        "patch": {
            "notes": "Here is my key sk-A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0"
        }
    }
    
    with pytest.raises(SecretDetectedError):
        store.append_jsonl_idempotent("activity.jsonl", malicious_record, id_field="event_id")

def test_append_idempotent_dedupes(tmp_path):
    store = StateStore(SAMPLE_DIR)
    store.base_dir = tmp_path # Override base_dir for testing writes
    
    record = {"log_id": "123", "data": "hello"}
    
    # First append
    store.append_jsonl_idempotent("test.jsonl", record, "log_id")
    
    # Second append (should be ignored)
    store.append_jsonl_idempotent("test.jsonl", {"log_id": "123", "data": "world"}, "log_id")
    
    # Verify file only has one line
    lines = (tmp_path / "test.jsonl").read_text().splitlines()
    assert len(lines) == 1
    assert '"hello"' in lines[0]

def test_optimistic_concurrency(tmp_path):
    store = StateStore(SAMPLE_DIR)
    store.base_dir = tmp_path
    
    # Add a mock work item
    store.work_items["WI-test"] = {
        "work_item_id": "WI-test",
        "version": 2,
        "title": "Initial"
    }
    
    actor = {"actor_type": "human", "actor_id": "user"}
    
    # Valid update
    updated = store.update_work_item("WI-test", {"title": "Updated"}, expected_version=2, actor=actor)
    assert updated["version"] == 3
    assert updated["title"] == "Updated"
    
    # Invalid update (conflict)
    with pytest.raises(StateConflictError):
        store.update_work_item("WI-test", {"title": "Conflict"}, expected_version=2, actor=actor)

