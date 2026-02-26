import pytest
import json
from rekall.core.state_store import StateStore, BloatConfig


@pytest.fixture
def clean_store(tmp_path):
    (tmp_path / "schema-version.txt").write_text("0.1")
    return StateStore(tmp_path)


def test_record_size_enforcement(clean_store):
    """Verify that records exceeding MAX_RECORD_BYTES are rejected."""
    large_record = {
        "event_id": "large_evt",
        "data": "x" * (BloatConfig.MAX_RECORD_BYTES + 1),
    }
    with pytest.raises(ValueError, match="Record exceeds maximum size"):
        clean_store.append_jsonl_idempotent("timeline", large_record, "event_id")


def test_rollover_at_count_threshold(tmp_path):
    """Verify stream rolls over to a segment file when record count exceeds limit."""
    # Temporarily lower threshold for fast test
    original_max = BloatConfig.MAX_HOT_RECORDS
    BloatConfig.MAX_HOT_RECORDS = 5
    try:
        (tmp_path / "schema-version.txt").write_text("0.1")
        store = StateStore(tmp_path)

        for i in range(7):
            store.append_jsonl_idempotent(
                "timeline", {"event_id": f"evt-{i}", "note": "test"}, "event_id"
            )

        # Should have seg-0001.jsonl and active.jsonl
        timeline_dir = tmp_path / "streams" / "timeline"
        assert (timeline_dir / "seg-0001.jsonl").exists()
        assert (timeline_dir / "active.jsonl").exists()

        # Manifest should track it
        assert (
            "streams/timeline/seg-0001.jsonl"
            in store.manifest["streams"]["timeline"]["segments"]
        )

        # Seg-0001 should have 5 records, active should have 2
        with open(timeline_dir / "seg-0001.jsonl") as f:
            assert len(f.readlines()) == 5
        with open(timeline_dir / "active.jsonl") as f:
            assert len(f.readlines()) == 2

    finally:
        BloatConfig.MAX_HOT_RECORDS = original_max


def test_rollover_at_size_threshold(tmp_path):
    """Verify stream rolls over to a segment file when byte size exceeds limit."""
    original_bytes = BloatConfig.MAX_HOT_BYTES
    BloatConfig.MAX_HOT_BYTES = 1024  # 1 KB
    try:
        (tmp_path / "schema-version.txt").write_text("0.1")
        store = StateStore(tmp_path)

        large_record = {"event_id": "large", "data": "x" * 1200}
        # First append -> active
        store.append_jsonl_idempotent("timeline", large_record, "event_id")
        # Second append -> still active (size is 600+)
        store.append_jsonl_idempotent(
            "timeline", {"event_id": "next", "data": "short"}, "event_id"
        )

        # Third append should trigger rollover if previous size > 1024?
        # Actually my logic checks size *before* append.
        # So 600 + 600 = 1200 > 1024. Next write should roll.
        store.append_jsonl_idempotent(
            "timeline", {"event_id": "trigger", "data": "trigger"}, "event_id"
        )

        timeline_dir = tmp_path / "streams" / "timeline"
        assert (timeline_dir / "seg-0001.jsonl").exists()
    finally:
        BloatConfig.MAX_HOT_BYTES = original_bytes


def test_idempotency_across_segments(tmp_path):
    """Verify that duplicates are detected even if stored in an older segment."""
    original_max = BloatConfig.MAX_HOT_RECORDS
    BloatConfig.MAX_HOT_RECORDS = 2
    try:
        (tmp_path / "schema-version.txt").write_text("0.1")
        store = StateStore(tmp_path)

        store.append_jsonl_idempotent(
            "timeline", {"event_id": "target", "val": 1}, "event_id"
        )
        store.append_jsonl_idempotent(
            "timeline", {"event_id": "other", "val": 2}, "event_id"
        )
        # Rollover triggers on next write
        store.append_jsonl_idempotent(
            "timeline", {"event_id": "trigger", "val": 3}, "event_id"
        )

        # Now 'target' is in seg-0001.jsonl
        # Append 'target' again
        store.append_jsonl_idempotent(
            "timeline", {"event_id": "target", "val": 99}, "event_id"
        )

        # Load stream and verify no duplicates
        records = store._load_stream("timeline", hot_only=False)
        ids = [r["event_id"] for r in records]
        assert ids.count("target") == 1

    finally:
        BloatConfig.MAX_HOT_RECORDS = original_max


def test_corruption_recovery(tmp_path):
    """Verify that truncated or malformed JSONL lines are skipped safely."""
    (tmp_path / "schema-version.txt").write_text("0.1")
    store = StateStore(tmp_path)

    # First, let StateStore initialize the stream in the manifest
    store.append_jsonl_idempotent("timeline", {"event_id": "init"}, "event_id")

    stream_info = store.manifest["streams"]["timeline"]
    active_path = tmp_path / stream_info["active_file"]

    with open(active_path, "w") as f:
        f.write(json.dumps({"event_id": "good1"}) + "\n")
        f.write('{"event_id": "bad", "truncated": \n')  # Malformed
        f.write(json.dumps({"event_id": "good2"}) + "\n")

    records = store._load_stream("timeline", hot_only=True)
    assert len(records) == 2
    assert records[0]["event_id"] == "good1"
    assert records[1]["event_id"] == "good2"
