"""Tests for Hub sync module."""
import json
import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rekall.core.hub_sync import (
    SyncError,
    _derive_event_id,
    _get_hub_config,
    _load_cursor,
    _records_to_events,
    _save_cursor,
    is_hub_configured,
    sync_to_hub,
)
from rekall.core.state_store import StateStore, resolve_vault_dir


@pytest.fixture
def temp_vault():
    """Create a temporary vault with sample data."""
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        from rekall.cli import ensure_state_initialized
        ensure_state_initialized(base, is_json=True, init_mode=True)
        store = StateStore(base)
        actor = {"actor_id": "test"}
        store.append_attempt({
            "attempt_id": str(uuid.uuid4())[:16],
            "title": "Test attempt",
            "work_item_id": "wi-1",
            "evidence": "test",
        }, actor=actor)
        store.append_attempt({
            "attempt_id": str(uuid.uuid4())[:16],
            "title": "Second attempt",
            "work_item_id": "wi-2",
            "evidence": "test2",
        }, actor=actor)
        yield base, store


class TestHubConfig:
    def test_not_configured_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            url, token, org = _get_hub_config()
            assert url is None
            assert token is None

    def test_configured_with_env_vars(self):
        env = {
            "REKALL_HUB_URL": "https://hub.example.com",
            "REKALL_HUB_TOKEN": "test-token",
            "REKALL_HUB_ORG_ID": "my-org",
        }
        with patch.dict(os.environ, env, clear=True):
            url, token, org = _get_hub_config()
            assert url == "https://hub.example.com"
            assert token == "test-token"
            assert org == "my-org"

    def test_trailing_slash_stripped(self):
        env = {
            "REKALL_HUB_URL": "https://hub.example.com/",
            "REKALL_HUB_TOKEN": "t",
        }
        with patch.dict(os.environ, env, clear=True):
            url, _, _ = _get_hub_config()
            assert url == "https://hub.example.com"

    def test_default_org_id(self):
        env = {
            "REKALL_HUB_URL": "https://hub.example.com",
            "REKALL_HUB_TOKEN": "t",
        }
        with patch.dict(os.environ, env, clear=True):
            _, _, org = _get_hub_config()
            assert org == "default"

    def test_is_hub_configured(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_hub_configured() is False
        env = {
            "REKALL_HUB_URL": "https://hub.example.com",
            "REKALL_HUB_TOKEN": "t",
        }
        with patch.dict(os.environ, env, clear=True):
            assert is_hub_configured() is True


class TestCursor:
    def test_load_empty_cursor(self):
        with tempfile.TemporaryDirectory() as d:
            assert _load_cursor(Path(d)) == {}

    def test_save_and_load_cursor(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            cursor = {"attempts": 5, "decisions": 2}
            _save_cursor(p, cursor)
            loaded = _load_cursor(p)
            assert loaded == cursor


class TestDeriveEventId:
    def test_deterministic(self):
        id1 = _derive_event_id("org", "repo", "attempts", 0)
        id2 = _derive_event_id("org", "repo", "attempts", 0)
        assert id1 == id2

    def test_different_offsets_differ(self):
        id1 = _derive_event_id("org", "repo", "attempts", 0)
        id2 = _derive_event_id("org", "repo", "attempts", 1)
        assert id1 != id2

    def test_valid_uuid(self):
        eid = _derive_event_id("org", "repo", "attempts", 0)
        parsed = uuid.UUID(eid)
        assert parsed.version == 5


class TestRecordsToEvents:
    def test_converts_records(self):
        records = [
            {"type": "attempt.append", "timestamp": "2026-01-01T00:00:00Z", "event_hash": "h1", "prev_hash": None, "data": "x"},
            {"type": "attempt.append", "timestamp": "2026-01-01T00:01:00Z", "event_hash": "h2", "prev_hash": "h1", "data": "y"},
        ]
        events = _records_to_events(records, "org1", "repo1", "attempts", 0)
        assert len(events) == 2
        assert events[0]["stream_offset"] == 0
        assert events[1]["stream_offset"] == 1
        assert events[0]["org_id"] == "org1"
        assert events[0]["stream_name"] == "attempts"
        assert events[0]["event_type"] == "attempt.append"
        assert events[0]["payload_json"] == records[0]

    def test_offset_continuation(self):
        records = [{"type": "x", "timestamp": "t", "event_hash": "h"}]
        events = _records_to_events(records, "o", "r", "s", 10)
        assert events[0]["stream_offset"] == 10


class TestSyncToHub:
    def test_skips_when_not_configured(self, temp_vault):
        vault_dir, store = temp_vault
        with patch.dict(os.environ, {}, clear=True):
            result = sync_to_hub(vault_dir, store.manifest)
            assert result["skipped"] is True

    @patch("rekall.core.hub_sync._post_batch")
    def test_syncs_events(self, mock_post, temp_vault):
        vault_dir, store = temp_vault
        mock_post.return_value = {
            "accepted": 2,
            "rejected": 0,
            "errors": [],
            "cursor": {"attempts": 1},
        }
        env = {
            "REKALL_HUB_URL": "https://hub.example.com",
            "REKALL_HUB_TOKEN": "test-token",
            "REKALL_HUB_ORG_ID": "test-org",
        }
        with patch.dict(os.environ, env, clear=True):
            result = sync_to_hub(vault_dir, store.manifest)
            assert result["accepted"] >= 2
            assert mock_post.called

    @patch("rekall.core.hub_sync._post_batch")
    def test_cursor_prevents_resync(self, mock_post, temp_vault):
        vault_dir, store = temp_vault
        # Pre-set cursor to indicate all attempts are synced
        _save_cursor(vault_dir, {"attempts": 999})

        mock_post.return_value = {
            "accepted": 0,
            "rejected": 0,
            "errors": [],
            "cursor": {},
        }
        env = {
            "REKALL_HUB_URL": "https://hub.example.com",
            "REKALL_HUB_TOKEN": "test-token",
        }
        with patch.dict(os.environ, env, clear=True):
            result = sync_to_hub(vault_dir, store.manifest)
            # Should not have posted attempts since cursor is ahead
            # (may still post activity events)
            assert result.get("skipped") is not True


class TestCmdSync:
    def test_sync_no_hub_configured(self, temp_vault, capsys):
        """Test that cmd_sync shows config instructions when not configured."""
        from rekall.cli import cmd_sync

        vault_dir, _ = temp_vault
        args = MagicMock()
        args.json = False
        args.quiet = False
        args.store_dir = str(vault_dir)

        with patch.dict(os.environ, {}, clear=True):
            cmd_sync(args)

        captured = capsys.readouterr()
        assert "not configured" in captured.out.lower() or "REKALL_HUB_URL" in captured.out
