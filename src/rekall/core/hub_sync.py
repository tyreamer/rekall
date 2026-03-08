"""Rekall Hub sync — sends unsynced append-only events to a remote Rekall Hub.

This module is additive and optional. If no Hub URL is configured, all
functions are no-ops. The local vault remains the source of truth.

Integration contract: see RekallHub/docs/integration_contract.md (v1.0).
"""
import hashlib
import json
import logging
import os
import platform
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)

# Streams to sync (append-only ledgers)
SYNCABLE_STREAMS = [
    "work_items", "attempts", "decisions", "timeline",
    "activity", "artifacts", "research", "anchors",
]

MAX_BATCH_SIZE = 500
MAX_RETRIES = 5
BACKOFF_BASE = 1  # seconds


def _get_hub_config() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Read Hub config from environment variables.

    Returns (hub_url, token, org_id) or (None, None, None) if not configured.
    """
    hub_url = os.environ.get("REKALL_HUB_URL", "").rstrip("/")
    token = os.environ.get("REKALL_HUB_TOKEN", "")
    org_id = os.environ.get("REKALL_HUB_ORG_ID", "")
    if not hub_url or not token:
        return None, None, None
    return hub_url, token, org_id or "default"


def _cursor_path(vault_dir: Path) -> Path:
    """Path to the local cursor file tracking what has been synced."""
    return vault_dir / ".hub_cursor.json"


def _load_cursor(vault_dir: Path) -> Dict[str, int]:
    """Load the sync cursor. Returns {stream_name: last_synced_offset}."""
    cp = _cursor_path(vault_dir)
    if cp.exists():
        try:
            with open(cp, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning("Corrupt cursor file, starting from 0")
    return {}


def _save_cursor(vault_dir: Path, cursor: Dict[str, int]) -> None:
    """Persist the sync cursor."""
    cp = _cursor_path(vault_dir)
    with open(cp, "w", encoding="utf-8") as f:
        json.dump(cursor, f, indent=2)


def _derive_event_id(org_id: str, repo_id: str, stream_name: str, offset: int) -> str:
    """Deterministic UUID v5 from stream coordinates — stable across retries."""
    namespace = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    key = f"{org_id}:{repo_id}:{stream_name}:{offset}"
    return str(uuid.uuid5(namespace, key))


def _derive_repo_id(vault_dir: Path) -> str:
    """Derive a repo_id from the vault directory path."""
    # Use the parent directory name (project root) as repo_id
    project_root = vault_dir.parent
    return project_root.name


def _load_stream_records(
    vault_dir: Path, manifest: Dict[str, Any], stream_name: str
) -> List[Dict[str, Any]]:
    """Load all raw records from a stream (all segments + active file)."""
    if stream_name not in manifest.get("streams", {}):
        return []

    stream_info = manifest["streams"][stream_name]
    files_to_load = []

    # Segments first (oldest to newest)
    for seg in stream_info.get("segments", []):
        files_to_load.append(vault_dir / seg)

    # Then active file
    active = stream_info.get("active_file", "")
    if active:
        files_to_load.append(vault_dir / active)

    records = []
    for filepath in files_to_load:
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
    return records


def _records_to_events(
    records: List[Dict[str, Any]],
    org_id: str,
    repo_id: str,
    stream_name: str,
    start_offset: int,
) -> List[Dict[str, Any]]:
    """Convert raw vault records to Hub event envelopes."""
    host_id = platform.node() or "unknown"
    events = []

    for i, record in enumerate(records):
        offset = start_offset + i
        events.append({
            "org_id": org_id,
            "repo_id": repo_id,
            "host_id": host_id,
            "session_id": record.get("session_id", "unknown"),
            "stream_name": stream_name,
            "stream_offset": offset,
            "event_id": _derive_event_id(org_id, repo_id, stream_name, offset),
            "event_type": record.get("type", f"{stream_name}.append"),
            "timestamp": record.get("timestamp", record.get("created_at", "")),
            "event_hash": record.get("event_hash", ""),
            "prev_hash": record.get("prev_hash", None),
            "payload_json": record,
        })

    return events


def _post_batch(
    hub_url: str, token: str, events: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """POST a batch of events to the Hub with retries and backoff."""
    url = f"{hub_url}/v1/ingest/events"
    payload = json.dumps({"events": events}).encode("utf-8")

    for attempt in range(MAX_RETRIES):
        try:
            req = Request(url, data=payload, method="POST")
            req.add_header("Authorization", f"Bearer {token}")
            req.add_header("Content-Type", "application/json")

            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))

        except HTTPError as e:
            if e.code == 401:
                raise SyncError("Authentication failed. Check REKALL_HUB_TOKEN.") from e
            if e.code == 422:
                # Validation error — log and skip
                body = e.read().decode("utf-8", errors="replace")
                logger.warning("Hub rejected batch (422): %s", body)
                return {"accepted": 0, "rejected": len(events), "errors": [body], "cursor": {}}
            if e.code == 429:
                retry_after = int(e.headers.get("Retry-After", BACKOFF_BASE * (2 ** attempt)))
                logger.info("Rate limited, waiting %ds", retry_after)
                time.sleep(retry_after)
                continue
            if e.code >= 500:
                wait = BACKOFF_BASE * (2 ** attempt)
                logger.warning("Hub returned %d, retrying in %ds", e.code, wait)
                time.sleep(wait)
                continue
            raise SyncError(f"Hub returned HTTP {e.code}") from e

        except (URLError, OSError) as e:
            wait = BACKOFF_BASE * (2 ** attempt)
            if attempt < MAX_RETRIES - 1:
                logger.warning("Connection error, retrying in %ds: %s", wait, e)
                time.sleep(wait)
            else:
                raise SyncError(f"Hub unreachable after {MAX_RETRIES} attempts: {e}") from e

    return {"accepted": 0, "rejected": len(events), "errors": ["max retries exceeded"], "cursor": {}}


class SyncError(Exception):
    """Raised when sync fails in a non-recoverable way."""
    pass


def sync_to_hub(
    vault_dir: Path,
    manifest: Dict[str, Any],
    quiet: bool = False,
) -> Dict[str, Any]:
    """Sync unsynced vault events to the Hub.

    Returns a summary dict with accepted/rejected/errors counts.
    """
    hub_url, token, org_id = _get_hub_config()
    if not hub_url:
        return {"skipped": True, "reason": "Hub not configured"}

    repo_id = _derive_repo_id(vault_dir)
    cursor = _load_cursor(vault_dir)

    total_accepted = 0
    total_rejected = 0
    all_errors: List[str] = []
    streams_synced: List[str] = []

    for stream_name in SYNCABLE_STREAMS:
        records = _load_stream_records(vault_dir, manifest, stream_name)
        if not records:
            continue

        # Determine what's already been synced
        last_synced = cursor.get(stream_name, -1)
        unsynced = records[last_synced + 1:]

        if not unsynced:
            continue

        start_offset = last_synced + 1
        events = _records_to_events(unsynced, org_id, repo_id, stream_name, start_offset)

        # Send in batches
        for batch_start in range(0, len(events), MAX_BATCH_SIZE):
            batch = events[batch_start:batch_start + MAX_BATCH_SIZE]

            try:
                result = _post_batch(hub_url, token, batch)
                total_accepted += result.get("accepted", 0)
                total_rejected += result.get("rejected", 0)
                all_errors.extend(result.get("errors", []))

                # Update cursor from server response
                server_cursor = result.get("cursor", {})
                if stream_name in server_cursor:
                    cursor[stream_name] = server_cursor[stream_name]
                elif result.get("accepted", 0) > 0:
                    # Fallback: use our local knowledge
                    cursor[stream_name] = start_offset + len(batch) - 1

            except SyncError as e:
                all_errors.append(str(e))
                if not quiet:
                    logger.error("Sync failed for %s: %s", stream_name, e)
                break

        if not all_errors or all_errors[-1] != str(all_errors):
            streams_synced.append(stream_name)

    _save_cursor(vault_dir, cursor)

    return {
        "accepted": total_accepted,
        "rejected": total_rejected,
        "errors": all_errors,
        "streams_synced": streams_synced,
    }


def is_hub_configured() -> bool:
    """Check if Hub sync is configured."""
    hub_url, token, _ = _get_hub_config()
    return bool(hub_url and token)
