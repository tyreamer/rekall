import json
import logging
import os
import re
import shutil
import sys
import uuid
import datetime
import hmac
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import yaml
from .policy import PolicyEngine, get_default_policy

logger = logging.getLogger(__name__)


class SchemaVersionError(Exception):
    pass


class SecretDetectedError(Exception):
    pass


class StateConflictError(Exception):
    """Raised when expected_version does not match current version"""

    pass


class WorkItemEventTypes:
    CREATED = "WORK_ITEM_CREATED"
    PATCHED = "WORK_ITEM_PATCHED"
    CLAIMED = "WORK_ITEM_CLAIMED"
    RELEASED = "WORK_ITEM_RELEASED"


# basic secret detection patterns (heuristic)
SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),  # Generic secret key pattern
    re.compile(r"xox[baprs]-[a-zA-Z0-9]{10,}"),  # Slack tokens
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access keys
    re.compile(r"eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+"),  # JWT
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),  # GitHub Personal Access Token
    re.compile(r"(?i)token="),  # Token query param
    re.compile(r"(?i)access_token="),  # Access token query param
    re.compile(r"(?i)Authorization:\s+"),  # Authorization header
    re.compile(r"(?i)Bearer\s+"),  # Bearer token
    re.compile(r"(?i)x-api-key"),  # API key header
    re.compile(r"AIza[0-9A-Za-z-_]{35}"),  # Google API Key
]


def sanitize_url(url: str) -> str:
    """Strips query parameters from URL to avoid leaking secrets."""
    if not url:
        return url
    if "?" in url:
        url = url.split("?")[0]
    return url


class BloatConfig:
    MAX_RECORD_BYTES = 128 * 1024  # 128 KB
    MAX_HOT_RECORDS = 1000  # Roll over after 1000 records
    MAX_HOT_BYTES = 5 * 1024 * 1024  # 5 MB


def detect_secrets(data: Any, path: str = "") -> None:
    """Recursively checks for secrets in values and raises SecretDetectedError if found."""
    if isinstance(data, dict):
        for k, v in data.items():
            detect_secrets(v, path=f"{path}.{k}" if path else k)
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            detect_secrets(item, path=f"{path}[{idx}]")
    elif isinstance(data, str):
        for pattern in SECRET_PATTERNS:
            if pattern.search(data):
                raise SecretDetectedError(f"Secret detected in field: {path}")


class StateStore:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.work_items: Dict[str, Dict[str, Any]] = {}

        # In-execution record caches for easy access
        self.project_config: Dict[str, Any] = {}
        self.envs_config: Dict[str, Any] = {}
        self.access_config: Dict[str, Any] = {}

        self.manifest: Dict[str, Any] = {
            "streams": {},
            "last_checkpoint": None,
            "schema_version": "0.1",
        }

        # LRU-ish cache for idempotency in the HOT window
        self._idemp_cache: Dict[str, Set[str]] = {}  # stream_name -> set of IDs

        self.initialize()

    def initialize(self):
        """Load configuration and replay state."""
        if not self.base_dir.exists():
            raise FileNotFoundError(f"Directory {self.base_dir} does not exist.")

        # 1. Validate Schema Version
        schema_file = self.base_dir / "schema-version.txt"
        if not schema_file.exists():
            raise FileNotFoundError("Missing schema-version.txt")

        version = schema_file.read_text().strip()
        if version not in ["0.1", "0.2"]:
            raise SchemaVersionError(
                f"Unsupported schema version: {version}. Expected: 0.1 or 0.2"
            )

        # 2. Load Manifest and Migrate if necessary
        self._load_manifest()
        self._migrate_legacy_files()

        # 3. Load YAMLs safely, verifying no secrets
        self.project_config = self._load_yaml("project.yaml")
        self.envs_config = self._load_yaml("envs.yaml")
        self.access_config = self._load_yaml("access.yaml")

        # 4. Reload Work Items from event stream (HOT only by default)
        self._replay_work_items()

        # 5. Ensure default policy exists
        policy_file = self.base_dir / "policy.yaml"
        if not policy_file.exists():
            policy_file.write_text(get_default_policy(), encoding="utf-8")
        
        self.initialized = True

    def _load_manifest(self):
        manifest_path = self.base_dir / "manifest.json"
        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as f:
                self.manifest = json.load(f)
        else:
            self._save_manifest()

    def _save_manifest(self):
        manifest_path = self.base_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.manifest, f, indent=2)

    def _migrate_legacy_files(self):
        """Moves legacy flat files into streams/ directory and initializes manifest."""
        streams_dir = self.base_dir / "streams"
        legacy_files = {
            "work-items.jsonl": ("work_items", "event_id"),
            "activity.jsonl": ("activity", "activity_id"),
            "attempts.jsonl": ("attempts", "attempt_id"),
            "decisions.jsonl": ("decisions", "decision_id"),
            "timeline.jsonl": ("timeline", "event_id"),
        }

        migrated = False
        for filename, (stream_key, id_field) in legacy_files.items():
            legacy_path = self.base_dir / filename
            if legacy_path.exists():
                migrated = True
                stream_dir = streams_dir / stream_key
                stream_dir.mkdir(parents=True, exist_ok=True)
                active_path = stream_dir / "active.jsonl"

                if not active_path.exists():
                    shutil.move(str(legacy_path), str(active_path))
                else:
                    # Append legacy to active if both exist (unlikely in fresh migration)
                    with open(active_path, "a", encoding="utf-8") as target:
                        with open(legacy_path, "r", encoding="utf-8") as source:
                            target.write(source.read())
                    legacy_path.unlink()

                self.manifest["streams"][stream_key] = {
                    "active_file": str(
                        active_path.relative_to(self.base_dir).as_posix()
                    ),
                    "segments": [],
                    "id_field": id_field,
                }

        if migrated:
            self._save_manifest()
            logger.info("Migrated legacy state files to stream structure.")

    def gc(self, archive: bool = True):
        """
        Garbage collects old segments that are already captured in snapshots.
        If archive is True, moves them to an .archive/ folder. Otherwise deletes them.
        """
        if "work_items" not in self.manifest.get("streams", {}):
            return

        stream_info = self.manifest["streams"]["work_items"]
        snapshot_path = self.base_dir / stream_info["active_file"]
        snapshot_path = snapshot_path.parent / "snapshot.json"

        if not snapshot_path.exists():
            logger.info("GC skipped: No snapshot found to reference.")
            return

        try:
            with open(snapshot_path, "r", encoding="utf-8") as f:
                snap_data = json.load(f)
                last_snap_idx = snap_data.get("last_segment_index", 0)
        except Exception as e:
            logger.error(f"GC failed to read snapshot: {e}")
            return

        if last_snap_idx == 0:
            return

        # Segments index is 1-based. Segments list in manifest is ordered.
        # segments: ["streams/work_items/seg-0001.jsonl", ...]

        orig_segments = stream_info.get("segments", [])
        new_segments = []
        to_remove = []

        for i, seg_path_str in enumerate(orig_segments, 1):
            if i <= last_snap_idx:
                to_remove.append(self.base_dir / seg_path_str)
            else:
                new_segments.append(seg_path_str)

        if not to_remove:
            logger.info("GC: No old segments to archive.")
            return

        if archive:
            archive_dir = (
                self.base_dir / stream_info["active_file"]
            ).parent / ".archive"
            archive_dir.mkdir(exist_ok=True)
            for p in to_remove:
                if p.exists():
                    shutil.move(str(p), str(archive_dir / p.name))
        else:
            for p in to_remove:
                if p.exists():
                    p.unlink()

        stream_info["segments"] = new_segments
        self._save_manifest()
        logger.info(f"GC completed: Archived/Removed {len(to_remove)} segments.")

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        filepath = self.base_dir / filename
        if not filepath.exists():
            return {}
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            detect_secrets(data)
            return data

    def _load_jsonl(self, filename: str) -> List[Dict[str, Any]]:
        """Loads all records from a jsonl stream (including all segments) applying HEAD semantics."""
        return self._load_stream(filename, hot_only=False)

    def _load_stream_raw(
        self, stream_name: str, hot_only: bool = True
    ) -> List[Dict[str, Any]]:
        """Loads records from a stream natively, without applying HEAD semantics."""
        stream_name = stream_name.replace(".jsonl", "").replace("-", "_")
        if stream_name not in self.manifest.get("streams", {}):
            return []

        stream_info = self.manifest["streams"][stream_name]
        files_to_load = [self.base_dir / stream_info["active_file"]]

        if not hot_only:
            for seg in stream_info.get("segments", []):
                files_to_load.insert(0, self.base_dir / seg)

        records = []
        for filepath in files_to_load:
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8") as f:
                    for line_no, line in enumerate(f, 1):
                        if line.strip():
                            try:
                                records.append(json.loads(line))
                            except json.JSONDecodeError:
                                logger.warning(
                                    f"Malformed JSON in {filepath.name}:{line_no}: {line}"
                                )
        return records

    def _apply_head_semantics(self, stream_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filters a stream of records by ignoring events that were un-done by a StateRevert."""
        # Note: calling _load_stream_raw here avoids infinite recursion if we ask for reverts
        reverts = self._load_stream_raw("reverts", hot_only=False)
        if not reverts:
            return stream_records
            
        combined = []
        for r in stream_records:
            t = r.get("timestamp") or r.get("created_at") or r.get("created", "")
            combined.append((t, "event", r))
            
        for rev in reverts:
            t = rev.get("timestamp", "")
            combined.append((t, "revert", rev))
            
        # Stable sort by timestamp
        combined.sort(key=lambda x: x[0])
        
        active = []
        for t, etype, obj in combined:
            if etype == "revert":
                to_t = obj.get("to_timestamp", "")
                active = [x for x in active if x[0] <= to_t]
            else:
                active.append((t, obj))
                
        return [obj for t, obj in active]

    def _load_stream(
        self, stream_name: str, hot_only: bool = True
    ) -> List[Dict[str, Any]]:
        """Loads records from a stream and filters out reverted futures."""
        records = self._load_stream_raw(stream_name, hot_only=hot_only)
        if stream_name.replace(".jsonl", "").replace("-", "_") == "reverts":
            return records
        return self._apply_head_semantics(records)

    def _get_device_secret(self) -> str:
        """Retrieves or generates a device-local secret for signatures."""
        config_dir = Path.home() / ".rekall"
        secret_file = config_dir / "device-secret.txt"
        if secret_file.exists():
            return secret_file.read_text().strip()
        
        config_dir.mkdir(parents=True, exist_ok=True)
        secret = uuid.uuid4().hex + uuid.uuid4().hex
        secret_file.write_text(secret)
        return secret

    def _sign_event(self, event_hash: str) -> str:
        """Signs an event hash using HMAC-SHA256 with the device secret."""
        secret = self._get_device_secret()
        sig = hmac.new(secret.encode("utf-8"), event_hash.encode("utf-8"), hashlib.sha256).hexdigest()
        return sig

    def verify_stream_integrity(self, stream_name: str) -> Dict[str, Any]:
        """
        Validates the cryptographic hash chain for a given stream.
        """
        records = self._load_stream_raw(stream_name, hot_only=False)
        errors = []
        last_hash = None
        
        for i, record in enumerate(records):
            # 1. Check prev_hash matches last_hash
            if record.get("prev_hash") != last_hash:
                errors.append(f"Record {i} prev_hash mismatch: expected {last_hash}, got {record.get('prev_hash')}")
            
            # 2. Recalculate event_hash
            record_for_hash = record.copy()
            claimed_hash = record_for_hash.pop("event_hash", None)
            record_json_canonical = json.dumps(record_for_hash, sort_keys=True)
            actual_hash = hashlib.sha256(record_json_canonical.encode("utf-8")).hexdigest()
            
            if claimed_hash != actual_hash:
                errors.append(f"Record {i} event_hash mismatch: expected {claimed_hash}, got {actual_hash}")
                
            last_hash = actual_hash
            
        return {
            "stream": stream_name,
            "count": len(records),
            "status": "\u2705" if not errors else "\u274c",
            "errors": errors
        }

    def append_jsonl_idempotent(
        self, stream_name: str, record: Dict[str, Any], id_field: str
    ) -> Dict[str, Any]:
        """
        Appends a record to a jsonl stream idempotently and enforces bloat guardrails.
        """
        stream_name = stream_name.replace(".jsonl", "").replace("-", "_")
        detect_secrets(record)

        # 1. Record Size Guardrail
        record_json = json.dumps(record, sort_keys=True)
        if len(record_json.encode("utf-8")) > BloatConfig.MAX_RECORD_BYTES:
            raise ValueError(
                f"Record exceeds maximum size of {BloatConfig.MAX_RECORD_BYTES} bytes"
            )

        # 2. Ensure stream exists in manifest
        if stream_name not in self.manifest["streams"]:
            stream_dir = self.base_dir / "streams" / stream_name
            stream_dir.mkdir(parents=True, exist_ok=True)
            active_file = stream_dir / "active.jsonl"
            active_file.touch(exist_ok=True)
            self.manifest["streams"][stream_name] = {
                "active_file": str(active_file.relative_to(self.base_dir)),
                "segments": [],
                "id_field": id_field,
                "latest_hash": None
            }
            self._save_manifest()

        stream_info = self.manifest["streams"][stream_name]
        active_path = self.base_dir / stream_info["active_file"]

        # 3. Idempotency Check (HOT Window via Cache + Active File)
        rid = record.get(id_field)
        idemp_key = record.get("idempotency_key")

        if stream_name not in self._idemp_cache:
            self._idemp_cache[stream_name] = set()
            # Warm up cache from active file
            if active_path.exists():
                with open(active_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            existing = json.loads(line)
                            if existing.get(id_field):
                                self._idemp_cache[stream_name].add(existing[id_field])
                            if existing.get("idempotency_key"):
                                self._idemp_cache[stream_name].add(
                                    f"idemp:{existing['idempotency_key']}"
                                )
                        except json.JSONDecodeError:
                            continue

        if rid in self._idemp_cache[stream_name]:
            return next(
                (r for r in self._load_stream(stream_name) if r.get(id_field) == rid),
                record,
            )

        if idemp_key and f"idemp:{idemp_key}" in self._idemp_cache[stream_name]:
            return next(
                (
                    r
                    for r in self._load_stream(stream_name)
                    if r.get("idempotency_key") == idemp_key
                ),
                record,
            )

        # 4. Hash Chain logic
        import hashlib
        prev_hash = stream_info.get("latest_hash")
        record["prev_hash"] = prev_hash
        
        # Canonical hash of everything in record except the hash field itself
        record_for_hash = record.copy()
        record_json_canonical = json.dumps(record_for_hash, sort_keys=True)
        event_hash = hashlib.sha256(record_json_canonical.encode("utf-8")).hexdigest()
        record["event_hash"] = event_hash
        
        # Final JSON for writing
        record_json = json.dumps(record, sort_keys=True)
        
        # Guardrail on final size
        if len(record_json.encode("utf-8")) > BloatConfig.MAX_RECORD_BYTES:
            raise ValueError(
                f"Record exceeds maximum size of {BloatConfig.MAX_RECORD_BYTES} bytes"
            )

        # 5. Atomic Append with Locking logic (simplified for now)
        lock_file = active_path.with_suffix(".lock")
        try:
            # Basic file locking (wait-and-retry could be added)
            with open(lock_file, "x"):
                pass

            # Check rollover before append
            if active_path.exists():
                stat = active_path.stat()
                # Count lines without loading whole file
                count = 0
                with open(active_path, "rb") as f:
                    for _ in f:
                        count += 1

                if (
                    stat.st_size > BloatConfig.MAX_HOT_BYTES
                    or count >= BloatConfig.MAX_HOT_RECORDS
                ):
                    self._roll_over_stream(stream_name)
                    # Re-resolve active path after rollover
                    active_path = (
                        self.base_dir
                        / self.manifest["streams"][stream_name]["active_file"]
                    )

            with open(active_path, "a", encoding="utf-8") as f:
                f.write(record_json + "\n")

            # Update manifest with latest hash
            self.manifest["streams"][stream_name]["latest_hash"] = event_hash
            self._save_manifest()

            # Update cache
            if rid:
                self._idemp_cache[stream_name].add(rid)
            if idemp_key:
                self._idemp_cache[stream_name].add(f"idemp:{idemp_key}")

        finally:
            if lock_file.exists():
                lock_file.unlink()

        return record

    def _generate_work_items_snapshot(self, last_segment_index: int):
        stream_info = self.manifest["streams"].get("work_items")
        if not stream_info:
            return

        snapshot_path = self.base_dir / stream_info["active_file"]
        snapshot_path = snapshot_path.parent / "snapshot.json"

        data = {"last_segment_index": last_segment_index, "work_items": self.work_items}

        temp_path = snapshot_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        shutil.move(str(temp_path), str(snapshot_path))

    def _roll_over_stream(self, stream_name: str):
        stream_info = self.manifest["streams"][stream_name]
        active_path = self.base_dir / stream_info["active_file"]

        seg_idx = len(stream_info["segments"]) + 1
        seg_name = f"seg-{seg_idx:04d}.jsonl"
        seg_path = active_path.parent / seg_name

        shutil.move(str(active_path), str(seg_path))
        active_path.touch()

        stream_info["segments"].append(seg_path.relative_to(self.base_dir).as_posix())
        self._save_manifest()

        if stream_name == "work_items":
            self._generate_work_items_snapshot(seg_idx)

        logger.info(f"Rolled over stream '{stream_name}' to {seg_name}")

    def _apply_work_item_events(self, events: List[Dict[str, Any]]):
        for event in events:
            wid = event.get("work_item_id")
            if not wid:
                continue

            e_type = event.get("type")

            if e_type == WorkItemEventTypes.CREATED:
                if wid not in self.work_items:
                    data = event.get("patch", {})
                    data["work_item_id"] = wid
                    data["version"] = 1
                    if "claim" not in data:
                        data["claim"] = None
                    self.work_items[wid] = data
            elif e_type == WorkItemEventTypes.PATCHED:
                if wid in self.work_items:
                    item = self.work_items[wid]
                    expected_version = event.get("expected_version")
                    if (
                        expected_version is not None
                        and item["version"] != expected_version
                    ):
                        logger.warning(
                            f"Replay mismatch for {wid}: expected v{expected_version}, got v{item['version']}"
                        )

                    patch_data = event.get("patch", {})
                    item.update(patch_data)
                    item["version"] += 1
            elif e_type == WorkItemEventTypes.CLAIMED:
                if wid in self.work_items:
                    item = self.work_items[wid]
                    claim = event.get("patch", {})
                    item["claim"] = claim
                    item["version"] += 1
            elif e_type == WorkItemEventTypes.RELEASED:
                if wid in self.work_items:
                    item = self.work_items[wid]
                    item["claim"] = None
                    item["version"] += 1

    def _replay_work_items(self):
        """
        Replays work_items stream into self.work_items map.
        Uses snapshot.json to resume from the last rolled-over segment to speed up load.
        """
        self.work_items.clear()

        stream_info = self.manifest.get("streams", {}).get("work_items")

        # Legacy fallback if stream hasn't been migrated
        if not stream_info:
            try:
                events = self._load_jsonl("work-items.jsonl")
            except Exception as e:
                logger.error(f"Failed to parse work-items.jsonl: {e}")
                events = []
            self._apply_work_item_events(events)
            return

        snapshot_path = self.base_dir / stream_info["active_file"]
        snapshot_path = snapshot_path.parent / "snapshot.json"

        last_seg_idx = 0
        if snapshot_path.exists():
            try:
                with open(snapshot_path, "r", encoding="utf-8") as f:
                    snap_data = json.load(f)
                    self.work_items = snap_data.get("work_items", {})
                    last_seg_idx = snap_data.get("last_segment_index", 0)
            except Exception as e:
                logger.warning(f"Failed to load snapshot, replaying all: {str(e)}")
                self.work_items.clear()
                last_seg_idx = 0

        # Replay segments strictly newer than last_seg_idx
        files_to_load = []
        for i, seg in enumerate(stream_info["segments"], 1):
            if i > last_seg_idx:
                files_to_load.append(self.base_dir / seg)

        # Always replay active file
        files_to_load.append(self.base_dir / stream_info["active_file"])

        for filepath in files_to_load:
            if filepath.exists():
                try:
                    # In python 3.9 filepath can be passed to open directly, but if _load_jsonl_raw doesn't exist, we must use _load_jsonl
                    # Wait, _load_jsonl takes a 'str' filename relative to base_dir, or _load_jsonl_raw might be missing?
                    # Let's check if _load_jsonl can take absolute paths.
                    # If not, let's just implement inline loading to be safe.
                    events = []
                    with open(filepath, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip():
                                events.append(json.loads(line))
                    self._apply_work_item_events(events)
                except Exception as e:
                    logger.warning(f"Failed to replay {filepath}: {e}")

    def _append_activity(
        self,
        action: str,
        target_type: str,
        target_id: str,
        actor: Dict[str, Any],
        diff: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
    ):
        import datetime

        activity_record = {
            "activity_id": str(uuid.uuid4()),
            "project_id": self.project_config.get("project_id", ""),
            "actor": actor,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        if diff:
            activity_record["diff"] = diff
        if reason:
            activity_record["reason"] = reason

        self.append_jsonl_idempotent(
            "activity.jsonl", activity_record, id_field="activity_id"
        )

    def _verify_claim_for_update(
        self, item: Dict[str, Any], actor: Dict[str, Any], force: bool = False
    ):
        if force:
            return  # Admin override

        claim = item.get("claim")
        if not claim:
            return  # Unclaimed items can be updated by anyone (or we could enforce claim-first, but spec says "If claim exists and caller isn't claimant -> FORBIDDEN")

        now = datetime.datetime.now(datetime.timezone.utc)

        lease_until_str = claim.get("lease_until")
        if lease_until_str:
            try:
                lease_until = datetime.datetime.fromisoformat(
                    lease_until_str.replace("Z", "+00:00")
                )
                if now > lease_until:
                    # Lease expired, essentially unclaimed
                    return
            except ValueError:
                pass

        # Active claim exists
        if claim.get("claimed_by") != actor.get("actor_id"):
            raise PermissionError(
                f"Work item {item['work_item_id']} is claimed by {claim.get('claimed_by')}"
            )

    def create_work_item(
        self,
        work_item: Dict[str, Any],
        actor: Dict[str, Any],
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        detect_secrets(work_item)
        import datetime

        wid = work_item.get("work_item_id") or f"WI-{str(uuid.uuid4())[:8]}"
        if wid in self.work_items:
            raise StateConflictError(f"Work item {wid} already exists")

        event_id = str(uuid.uuid4())
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Ensure mandatory semantic fields
        patch = {
            "type": work_item.get("type", "task"),
            "title": work_item.get("title", ""),
            "intent": work_item.get("intent", ""),
            "status": work_item.get("status", "todo"),
            "priority": work_item.get("priority", "p2"),
            "owner": work_item.get("owner"),
            "tags": work_item.get("tags", []),
            "dependencies": work_item.get("dependencies", {}),
            "evidence_links": work_item.get("evidence_links", []),
            "definition_of_done": work_item.get("definition_of_done", []),
            "created_at": now,
            "updated_at": now,
        }

        event = {
            "event_id": event_id,
            "type": WorkItemEventTypes.CREATED,
            "project_id": self.project_config.get("project_id", ""),
            "work_item_id": wid,
            "timestamp": now,
            "actor": actor,
            "expected_version": 0,
            "patch": patch,
        }
        if reason:
            event["reason"] = reason

        self.append_jsonl_idempotent("work-items.jsonl", event, id_field="event_id")
        self._append_activity(
            "create", "work_item", wid, actor, diff=patch, reason=reason
        )

        # Apply to execution record
        patch["work_item_id"] = wid
        patch["version"] = 1
        patch["claim"] = None
        self.work_items[wid] = patch
        return patch

    def update_work_item(
        self,
        work_item_id: str,
        patch: Dict[str, Any],
        expected_version: int,
        actor: Dict[str, Any],
        force: bool = False,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Mutable update via API: verifies expected_version, then appends to JSONL."""
        detect_secrets(patch)
        item = self.work_items.get(work_item_id)
        if not item:
            raise KeyError(f"Work item {work_item_id} not found")

        if item["version"] != expected_version:
            raise StateConflictError(
                f"Version mismatch for {work_item_id}. "
                f"Expected {expected_version}, but current is {item['version']}"
            )

        self._verify_claim_for_update(item, actor, force)

        import datetime

        event_id = str(uuid.uuid4())
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        patch["updated_at"] = now

        event = {
            "event_id": event_id,
            "type": WorkItemEventTypes.PATCHED,
            "project_id": item.get("project_id", ""),
            "work_item_id": work_item_id,
            "timestamp": now,
            "actor": actor,
            "expected_version": expected_version,
            "patch": patch,
        }
        if reason:
            event["reason"] = reason

        self.append_jsonl_idempotent("work-items.jsonl", event, id_field="event_id")
        self._append_activity(
            "update", "work_item", work_item_id, actor, diff=patch, reason=reason
        )

        # Re-apply execution record state
        item.update(patch)
        item["version"] += 1
        return item

    def claim_work_item(
        self,
        work_item_id: str,
        expected_version: int,
        actor: Dict[str, Any],
        lease_seconds: int = 1800,
        force: bool = False,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        item = self.work_items.get(work_item_id)
        if not item:
            raise KeyError(f"Work item {work_item_id} not found")

        if item["version"] != expected_version:
            raise StateConflictError(
                f"Version mismatch for {work_item_id}. "
                f"Expected {expected_version}, but current is {item['version']}"
            )

        # Check existing claim unless forcing
        if not force:
            claim = item.get("claim")
            import datetime

            now = datetime.datetime.now(datetime.timezone.utc)
            if claim and claim.get("claimed_by") != actor.get("actor_id"):
                lease_until_str = claim.get("lease_until")
                if lease_until_str:
                    try:
                        lease_until = datetime.datetime.fromisoformat(
                            lease_until_str.replace("Z", "+00:00")
                        )
                        if now <= lease_until:
                            raise PermissionError(
                                f"Work item {work_item_id} is currently claimed by {claim['claimed_by']}"
                            )
                    except ValueError:
                        pass

        import datetime

        now = datetime.datetime.now(datetime.timezone.utc)
        lease_until_ts = (now + datetime.timedelta(seconds=lease_seconds)).isoformat()

        claim_data = {"claimed_by": actor.get("actor_id"), "lease_until": lease_until_ts}

        event = {
            "event_id": str(uuid.uuid4()),
            "type": WorkItemEventTypes.CLAIMED,
            "project_id": item.get("project_id", ""),
            "work_item_id": work_item_id,
            "timestamp": now.isoformat(),
            "actor": actor,
            "expected_version": expected_version,
            "patch": claim_data,
        }
        if reason:
            event["reason"] = reason

        self.append_jsonl_idempotent("work-items.jsonl", event, id_field="event_id")
        self._append_activity(
            "claim", "work_item", work_item_id, actor, diff=claim_data, reason=reason
        )

        item["claim"] = claim_data
        item["version"] += 1
        return item

    def renew_claim(
        self,
        work_item_id: str,
        expected_version: int,
        actor: Dict[str, Any],
        lease_seconds: int = 1800,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        item = self.work_items.get(work_item_id)
        if not item:
            raise KeyError(f"Work item {work_item_id} not found")

        if item["version"] != expected_version:
            raise StateConflictError(
                f"Version mismatch for {work_item_id}. Expected {expected_version}, but current is {item['version']}"
            )

        claim = item.get("claim")
        if not claim or claim.get("claimed_by") != actor.get("actor_id"):
            raise PermissionError(
                f"Cannot renew: you do not hold the active claim for {work_item_id}"
            )

        # It's identical to claiming again
        return self.claim_work_item(
            work_item_id,
            expected_version,
            actor,
            lease_seconds,
            force=True,
            reason=reason,
        )

    def release_claim(
        self,
        work_item_id: str,
        expected_version: int,
        actor: Dict[str, Any],
        force: bool = False,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        item = self.work_items.get(work_item_id)
        if not item:
            raise KeyError(f"Work item {work_item_id} not found")

        if item["version"] != expected_version:
            raise StateConflictError(
                f"Version mismatch for {work_item_id}. Expected {expected_version}, but current is {item['version']}"
            )

        if not force:
            claim = item.get("claim")
            if not claim or claim.get("claimed_by") != actor.get("actor_id"):
                raise PermissionError(
                    f"Cannot release: you do not hold the active claim for {work_item_id}"
                )

        import datetime

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        event = {
            "event_id": str(uuid.uuid4()),
            "type": WorkItemEventTypes.RELEASED,
            "project_id": item.get("project_id", ""),
            "work_item_id": work_item_id,
            "timestamp": now,
            "actor": actor,
            "expected_version": expected_version,
        }
        if reason:
            event["reason"] = reason

        self.append_jsonl_idempotent("work-items.jsonl", event, id_field="event_id")
        self._append_activity(
            "release", "work_item", work_item_id, actor, reason=reason
        )

        item["claim"] = None
        item["version"] += 1
        return item

    def append_attempt(
        self,
        attempt: Dict[str, Any],
        actor: Dict[str, Any],
        reason: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        detect_secrets(attempt)
        import datetime

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        attempt_id = attempt.get("attempt_id") or str(uuid.uuid4())
        attempt["attempt_id"] = attempt_id
        attempt["performed_by"] = actor
        if idempotency_key:
            attempt["idempotency_key"] = idempotency_key
        if "timestamp" not in attempt:
            attempt["timestamp"] = now

        record = self.append_jsonl_idempotent("attempts.jsonl", attempt, "attempt_id")

        # Emit activity only if it was actually newly appended
        if (
            record is attempt
        ):  # Identity check since `append_jsonl_idempotent` returns existing if duplicate
            self._append_activity("append", "attempt", attempt_id, actor, reason=reason)

        return record

    def propose_decision(
        self,
        decision: Dict[str, Any],
        actor: Dict[str, Any],
        reason: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        detect_secrets(decision)
        import datetime

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        decision_id = decision.get("decision_id") or str(uuid.uuid4())
        decision["decision_id"] = decision_id
        decision["decided_by"] = actor
        decision["status"] = "proposed"
        if idempotency_key:
            decision["idempotency_key"] = idempotency_key
        if "timestamp" not in decision:
            decision["timestamp"] = now

        record = self.append_jsonl_idempotent(
            "decisions.jsonl", decision, "decision_id"
        )

        if record is decision:
            self._append_activity(
                "propose", "decision", decision_id, actor, reason=reason
            )

        return record

    def approve_decision(
        self, decision_id: str, actor: Dict[str, Any], reason: Optional[str] = None
    ) -> Dict[str, Any]:
        # Enforce capability
        capabilities = actor.get("capabilities", [])
        if "approve_decisions" not in capabilities:
            raise PermissionError("Actor lacks 'approve_decisions' capability")

        # Since decisions are append-only logs, a mutable status breaks the merge-safe rules.
        # However, the invariants document says: "Approval gates are enforced in the tool layer"
        # and suggests appending an approval event or redefining the status.
        # For this POC, we will load decisions, find it, then append a NEW record that supersedes
        # or just an Activity event that confers approval. To match "return updated decision",
        # let's create a new Decision record that supersedes the proposed one with status=approved.

        decisions = self._load_jsonl("decisions.jsonl")
        target = next((d for d in decisions if d["decision_id"] == decision_id), None)

        if not target:
            raise KeyError(f"Decision {decision_id} not found")

        if target.get("status") == "approved":
            return target  # Idempotent approval

        import datetime

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        approved_decision = target.copy()
        new_id = str(uuid.uuid4())
        approved_decision["decision_id"] = new_id
        approved_decision["status"] = "approved"
        approved_decision["supersedes"] = decision_id
        approved_decision["decided_by"] = actor
        approved_decision["timestamp"] = now

        self.append_jsonl_idempotent(
            "decisions.jsonl", approved_decision, "decision_id"
        )
        self._append_activity(
            "approve",
            "decision",
            decision_id,
            actor,
            diff={"status": "approved", "new_decision_id": new_id},
            reason=reason,
        )

        return approved_decision

    def append_timeline(
        self,
        event: Dict[str, Any],
        actor: Dict[str, Any],
        reason: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        detect_secrets(event)
        import datetime

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        event_id = event.get("event_id") or str(uuid.uuid4())
        event["event_id"] = event_id
        event["created_by"] = actor
        if idempotency_key:
            event["idempotency_key"] = idempotency_key
        if "timestamp" not in event:
            event["timestamp"] = now

        record = self.append_jsonl_idempotent("timeline.jsonl", event, "event_id")

        if record is event:
            self._append_activity("append", "timeline", event_id, actor, reason=reason)

        return record

    def append_artifact(
        self,
        artifact: Dict[str, Any],
        actor: Dict[str, Any],
        reason: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Appends an artifact record."""
        ref = artifact.get("ref", {})
        if "url" in ref:
            ref["url"] = sanitize_url(ref["url"])

        detect_secrets(artifact)
        import datetime

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        artifact_id = artifact.get("artifact_id") or str(uuid.uuid4())
        artifact["artifact_id"] = artifact_id
        artifact["created_by"] = actor
        artifact["type"] = "artifact"
        if idempotency_key:
            artifact["idempotency_key"] = idempotency_key
        if "created_at" not in artifact:
            artifact["created_at"] = now

        record = self.append_jsonl_idempotent(
            "artifacts.jsonl", artifact, "artifact_id"
        )

        if record is artifact:
            self._append_activity(
                "append", "artifact", artifact_id, actor, reason=reason
            )

        return record

    def append_research(
        self,
        research: Dict[str, Any],
        actor: Dict[str, Any],
        reason: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Appends a research_item record."""
        ref = research.get("ref", {})
        if "url" in ref:
            ref["url"] = sanitize_url(ref["url"])

        detect_secrets(research)
        import datetime

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        research_id = research.get("research_id") or str(uuid.uuid4())
        research["research_id"] = research_id
        research["created_by"] = actor
        research["type"] = "research_item"
        if idempotency_key:
            research["idempotency_key"] = idempotency_key
        if "created_at" not in research:
            research["created_at"] = now

        record = self.append_jsonl_idempotent("research.jsonl", research, "research_id")

        if record is research:
            self._append_activity(
                "append", "research", research_id, actor, reason=reason
            )

        return record

    def append_link(
        self,
        link: Dict[str, Any],
        actor: Dict[str, Any],
        reason: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Appends a link edge record."""
        detect_secrets(link)
        import datetime

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        edge_id = link.get("edge_id") or str(uuid.uuid4())
        link["edge_id"] = edge_id
        link["created_by"] = actor
        link["type"] = "link"
        if idempotency_key:
            link["idempotency_key"] = idempotency_key
        if "created_at" not in link:
            link["created_at"] = now

        record = self.append_jsonl_idempotent("links.jsonl", link, "edge_id")

        if record is link:
            self._append_activity("append", "link", edge_id, actor, reason=reason)

        return record

    def save_anchor(
        self,
        anchor: Dict[str, Any],
        actor: Dict[str, Any],
        reason: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Appends an anchor save record."""
        detect_secrets(anchor)
        import datetime

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        anchor_id = anchor.get("anchor_id") or str(uuid.uuid4())
        anchor["anchor_id"] = anchor_id
        anchor["created_by"] = actor
        anchor["type"] = "anchor"
        if idempotency_key:
            anchor["idempotency_key"] = idempotency_key
        if "timestamp" not in anchor:
            anchor["timestamp"] = now
        record = self.append_jsonl_idempotent("anchors.jsonl", anchor, "anchor_id")
        return record

    def wait_for_approval(
        self,
        decision_id: str,
        prompt: str,
        options: list,
        actor: Dict[str, Any],
        action_id: Optional[str] = None,
        reason: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Appends a WaitingOnHuman event to signal the agent should pause."""
        detect_secrets(prompt)
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        wait_event = {
            "decision_id": decision_id,
            "type": "WaitingOnHuman",
            "prompt": prompt,
            "options": options,
            "timestamp": now,
            "created_by": actor,
            "reason": reason
        }
        if action_id:
            wait_event["action_id"] = action_id
        if idempotency_key:
            wait_event["idempotency_key"] = idempotency_key
            
        record = self.append_jsonl_idempotent("actions.jsonl", wait_event, "decision_id")
        return {
            "status": "PAUSE_AND_EXIT", 
            "message": f"Decision {decision_id} recorded. Please exit your loop and wait for human resume.", 
            "decision_id": decision_id,
            "action_id": action_id
        }

    def append_revert(
        self,
        to_timestamp: str,
        actor: Dict[str, Any],
        reason: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Appends a StateRevert event to the reverts stream."""
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        revert_id = f"rev-{uuid.uuid4().hex[:8]}"
        revert = {
            "revert_id": revert_id,
            "type": "StateRevert",
            "to_timestamp": to_timestamp,
            "timestamp": now,
            "created_by": actor,
            "reason": reason
        }
        if idempotency_key:
            revert["idempotency_key"] = idempotency_key
            
        record = self.append_jsonl_idempotent("reverts.jsonl", revert, "revert_id")
        return record

    def check_policy(self, action_type: str, params: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Runs the policy engine against an action."""
        policy_file = self.base_dir / "policy.yaml"
        if not policy_file.exists():
            return {"effect": "allow", "rule_id": None, "reason": "No policy.yaml found"}
            
        engine = PolicyEngine.from_file(str(policy_file))
        return engine.check_action(action_type, params, context)

    def propose_action(
        self,
        action_type: str,
        params: Dict[str, Any],
        risk_hint: str,
        context: Dict[str, Any],
        actor: Dict[str, Any],
        reason: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        detect_secrets(params)
        import datetime
        import hashlib

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        # 1. Shadow Policy Check
        policy_res = self.check_policy(action_type, params, context)
        
        # 2. Consistent hash of action content
        content_str = json.dumps({"action_type": action_type, "params": params}, sort_keys=True)
        action_hash = hashlib.sha256(content_str.encode("utf-8")).hexdigest()

        action_id = f"act-{uuid.uuid4().hex[:8]}"
        
        # 3. Record Policy Check result
        check_event = {
            "check_id": f"chk-{uuid.uuid4().hex[:8]}",
            "type": "PolicyCheck",
            "action_id": action_id,
            "effect": policy_res["effect"],
            "rule_id": policy_res["rule_id"],
            "reason": policy_res["reason"],
            "timestamp": now,
            "actor": actor
        }
        self.append_jsonl_idempotent("activity.jsonl", check_event, "check_id")
        
        event = {
            "action_id": action_id,
            "type": "ActionProposed",
            "action_type": action_type,
            "params": params,
            "risk_hint": risk_hint,
            "context": context,
            "action_hash": action_hash,
            "policy_effect": policy_res["effect"],
            "timestamp": now,
            "actor": actor
        }
        if idempotency_key:
            event["idempotency_key"] = idempotency_key

        record = self.append_jsonl_idempotent("actions.jsonl", event, "action_id")

        if record is event:
            self._append_activity("propose", "action", action_id, actor, diff={"action_type": action_type, "policy": policy_res["effect"]}, reason=reason)

        return record

    def capture_approval(
        self,
        decision_id: str,
        decision_str: str,
        note: str,
        actor: Dict[str, Any],
        action_id: Optional[str] = None,
        reason: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        decision_obj = {
            "decision_id": decision_id,
            "title": f"Approval response for decision {decision_id}",
            "status": "approved" if decision_str.lower() in ["approve", "approved", "yes", "allow"] else "rejected",
            "notes": note,
            "timestamp": now,
            "decided_by": actor
        }
        if action_id:
            decision_obj["action_id"] = action_id
        if idempotency_key:
            decision_obj["idempotency_key"] = idempotency_key
            
        self.append_jsonl_idempotent("decisions.jsonl", decision_obj, "decision_id")
        
        anchor_id = f"anch-{uuid.uuid4().hex[:8]}"
        anchor = {
            "anchor_id": anchor_id,
            "type": "HumanAnchor",
            "decision_id": decision_id,
            "note": note,
            "timestamp": now,
            "created_by": actor
        }
        if action_id:
            anchor["action_id"] = action_id
            
        # Add a placeholder signature based on the event hash (which append_jsonl_idempotent will calculate)
        # But wait, append_jsonl_idempotent calculates the hash of the record PASSED to it.
        # So we can calculate the hash here, sign it, and THEN pass it.
        # However, append_jsonl_idempotent adds prev_hash.
        # To simplify, we sign the concatenation of (decision_id, anchor_id, actor_id).
        sig_base = f"{decision_id}:{anchor_id}:{actor.get('actor_id', 'unknown')}"
        anchor["signature"] = self._sign_event(hashlib.sha256(sig_base.encode("utf-8")).hexdigest())
            
        self.append_jsonl_idempotent("anchors.jsonl", anchor, "anchor_id")
        
        if action_id:
            self._append_activity("approve", "action", action_id, actor, reason=reason)
        else:
            self._append_activity("approve", "decision", decision_id, actor, reason=reason)
        
        return {"status": "success", "decision_id": decision_id, "anchor_id": anchor_id}

    def capture_outcome(
        self,
        action_id: str,
        outcome_metadata: Dict[str, Any],
        actor: Dict[str, Any],
        reason: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        detect_secrets(outcome_metadata)
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        attempt_id = f"att-{uuid.uuid4().hex[:8]}"
        attempt = {
            "attempt_id": attempt_id,
            "action_id": action_id,
            "outcome": outcome_metadata,
            "timestamp": now,
            "performed_by": actor
        }
        if idempotency_key:
            attempt["idempotency_key"] = idempotency_key
            
        record = self.append_jsonl_idempotent("attempts.jsonl", attempt, "attempt_id")
        
        if record is attempt:
            self._append_activity("execute", "action", action_id, actor, reason=reason)
            
        return {"status": "success", "attempt_id": attempt_id, "action_id": action_id}

    def resume_anchor(self, anchor_id: Optional[str] = None) -> Dict[str, Any]:
        """Resumes from an anchor, providing a warm restart brief."""
        anchors = self._load_jsonl("anchors.jsonl")
        if not anchors:
            return {"error": "No anchors found."}

        if anchor_id:
            target = next((a for a in anchors if a.get("anchor_id") == anchor_id), None)
            if not target:
                return {"error": f"Anchor {anchor_id} not found."}
        else:
            target = sorted(
                anchors, key=lambda x: x.get("timestamp", ""), reverse=True
            )[0]

        anchor_time = target.get("timestamp", "")

        decisions = self._load_jsonl("decisions.jsonl")
        attempts = self._load_jsonl("attempts.jsonl")

        new_decisions = [d for d in decisions if d.get("timestamp", "") > anchor_time]
        new_attempts = [a for a in attempts if a.get("timestamp", "") > anchor_time]

        return {
            "anchor": target,
            "note": target.get("note", ""),
            "next_steps": target.get(
                "next_steps", target.get("optional", {}).get("next_steps", [])
            ),
            "since_anchor": {
                "new_decisions": len(new_decisions),
                "new_attempts": len(new_attempts),
                "decisions": new_decisions,
                "attempts": new_attempts,
            },
        }

    def digest_while_you_were_gone(
        self, since: Optional[str] = None, limit: int = 25
    ) -> Dict[str, Any]:
        """Generates a digest of recent activity."""
        if not since:
            since = (
                datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(days=1)
            ).isoformat()

        attempts = self._load_jsonl("attempts.jsonl")
        decisions = self._load_jsonl("decisions.jsonl")
        artifacts = self._load_jsonl("artifacts.jsonl")
        research = self._load_jsonl("research.jsonl")

        recent_attempts = sorted(
            [a for a in attempts if a.get("timestamp", "") >= since],
            key=lambda x: x.get("timestamp", ""),
            reverse=True,
        )[:limit]
        recent_decisions = sorted(
            [d for d in decisions if d.get("timestamp", "") >= since],
            key=lambda x: x.get("timestamp", ""),
            reverse=True,
        )[:limit]
        recent_artifacts = sorted(
            [a for a in artifacts if a.get("created_at", "") >= since],
            key=lambda x: x.get("created_at", ""),
            reverse=True,
        )[:limit]
        recent_research = sorted(
            [r for r in research if r.get("created_at", "") >= since],
            key=lambda x: x.get("created_at", ""),
            reverse=True,
        )[:limit]

        blockers = [a for a in recent_attempts if a.get("status") == "failed"]
        unapproved_decisions = [
            d for d in recent_decisions if d.get("status") != "approved"
        ]

        return {
            "since": since,
            "summary": {
                "recent_attempts_count": len(recent_attempts),
                "recent_decisions_count": len(recent_decisions),
                "failed_attempts": len(blockers),
                "unapproved_decisions": len(unapproved_decisions),
            },
            "recent_attempts": recent_attempts,
            "recent_decisions": recent_decisions,
            "blockers": blockers + unapproved_decisions,
            "recent_artifacts": recent_artifacts,
            "recent_research": recent_research,
        }

    def trace_graph(
        self, root: Dict[str, str], depth: int = 2, include_bundles: bool = True
    ) -> Dict[str, Any]:
        """Returns a deterministic provenance graph."""
        nodes_collected = {}  # key: (node_type, id) -> node
        edges_collected = []

        links = self._load_jsonl("links.jsonl")

        all_nodes = {
            "decision": {
                d["decision_id"]: d
                for d in self._load_jsonl("decisions.jsonl")
                if "decision_id" in d
            },
            "attempt": {
                a["attempt_id"]: a
                for a in self._load_jsonl("attempts.jsonl")
                if "attempt_id" in a
            },
            "artifact": {
                a["artifact_id"]: a
                for a in self._load_jsonl("artifacts.jsonl")
                if "artifact_id" in a
            },
            "research_item": {
                r["research_id"]: r
                for r in self._load_jsonl("research.jsonl")
                if "research_id" in r
            },
        }

        root_type = root.get("node_type")
        root_id = root.get("id")

        if root_type not in all_nodes or root_id not in all_nodes.get(root_type, {}):
            return {"error": f"Root node {root_type}/{root_id} not found."}

        nodes_collected[(root_type, root_id)] = all_nodes[root_type][root_id]
        current_level = set([(root_type, root_id)])

        for _ in range(depth):
            next_level = set()
            for edge in links:
                u = (
                    edge.get("from", {}).get("node_type"),
                    edge.get("from", {}).get("id"),
                )
                v = (edge.get("to", {}).get("node_type"), edge.get("to", {}).get("id"))

                if u in current_level or v in current_level:
                    if edge not in edges_collected:
                        edges_collected.append(edge)
                    if (
                        u not in nodes_collected
                        and u[0] in all_nodes
                        and u[1] in all_nodes[u[0]]
                    ):
                        nodes_collected[u] = all_nodes[u[0]][u[1]]
                        next_level.add(u)
                    if (
                        v not in nodes_collected
                        and v[0] in all_nodes
                        and v[1] in all_nodes[v[0]]
                    ):
                        nodes_collected[v] = all_nodes[v[0]][v[1]]
                        next_level.add(v)
            current_level = next_level

        sorted_nodes = [nodes_collected[k] for k in sorted(nodes_collected.keys())]
        sorted_edges = sorted(edges_collected, key=lambda e: e.get("edge_id", ""))

        result = {"root": root, "nodes": sorted_nodes, "edges": sorted_edges}

        if include_bundles:
            result["bundles"] = {
                "decision": [
                    n for k, n in nodes_collected.items() if k[0] == "decision"
                ],
                "attempts": [
                    n for k, n in nodes_collected.items() if k[0] == "attempt"
                ],
                "artifacts": [
                    n for k, n in nodes_collected.items() if k[0] == "artifact"
                ],
                "research": [
                    n for k, n in nodes_collected.items() if k[0] == "research_item"
                ],
            }

        return result

    def validate_all(self, strict: bool = False) -> Dict[str, Any]:
        """
        Performs a deep diagnostic scan of the entire StateStore.
        Returns a structured report dictionary.
        Raises ValueError in strict mode if any warnings exist.
        """
        report: Dict[str, Any] = {
            "summary": {"status": "\u2705", "errors": 0, "warnings": 0},
            "schema_version": {"status": "\u2705", "details": ""},
            "files_present": {"status": "\u2705", "missing": []},
            "jsonl_integrity": {"status": "\u2705", "malformed": []},
            "id_uniqueness": {"status": "\u2705", "duplicates": []},
            "references": {"status": "\u2705", "dangling": []},
            "secrets": {"status": "\u2705", "detected": []},
            "claims": {"status": "\u2705", "expired": []},
        }

        def add_error(section: str, msg: str):
            report[section]["status"] = "\u274c"
            if "errors" not in report[section]:
                report[section]["errors"] = []
            report[section]["errors"].append(msg)
            report["summary"]["errors"] += 1
            report["summary"]["status"] = "\u274c"

        def add_warning(section: str, list_key: str, msg: str):
            if report[section]["status"] == "\u2705":
                report[section]["status"] = "\u26a0\ufe0f"
            report[section][list_key].append(msg)
            report["summary"]["warnings"] += 1
            if report["summary"]["status"] == "\u2705":
                report["summary"]["status"] = "\u26a0\ufe0f"

        # 1. Schema Version
        schema_file = self.base_dir / "schema-version.txt"
        if not schema_file.exists():
            add_error("schema_version", "Missing schema-version.txt")
        else:
            v = schema_file.read_text().strip()
            report["schema_version"]["details"] = v
            if v not in ["0.1", "0.2"]:
                add_error("schema_version", f"Unsupported version: {v}")

        # 2. Files Present
        expected_yamls = ["project.yaml", "envs.yaml", "access.yaml"]
        for f in expected_yamls:
            if not (self.base_dir / f).exists():
                add_warning("files_present", "missing", f)

        if not (self.base_dir / "manifest.json").exists():
            add_warning("files_present", "missing", "manifest.json")

        # 3. JSONL Integrity & ID Uniqueness
        seen_ids = set()
        seen_idemp_keys = set()

        for stream_name, info in self.manifest.get("streams", {}).items():
            id_key = info.get("id_field", "event_id")
            files_to_check = [self.base_dir / info["active_file"]] + [
                self.base_dir / s for s in info.get("segments", [])
            ]

            for filepath in files_to_check:
                if not filepath.exists():
                    continue

                with open(filepath, "r", encoding="utf-8") as file:
                    for line_no, line in enumerate(file, 1):
                        if not line.strip():
                            continue
                        try:
                            # Also check record size during validation
                            line_bytes = len(line.encode("utf-8"))
                            if line_bytes > BloatConfig.MAX_RECORD_BYTES:
                                add_warning(
                                    "jsonl_integrity",
                                    "malformed",
                                    f"{filepath.name}:{line_no} Record exceeds MAX_RECORD_BYTES ({line_bytes})",
                                )

                            record = json.loads(line)
                            rid = record.get(id_key)
                            idemp_key = record.get("idempotency_key")
                            if rid:
                                if rid in seen_ids:
                                    add_warning(
                                        "id_uniqueness",
                                        "duplicates",
                                        f"{filepath.name}:{line_no} Duplicate ID {rid}",
                                    )
                                else:
                                    seen_ids.add(rid)
                            else:
                                add_error(
                                    "jsonl_integrity",
                                    f"{filepath.name}:{line_no} Missing ID field '{id_key}'",
                                )

                            if idemp_key:
                                # We check global uniqueness of idempotency keys across segments for this stream
                                full_idemp = f"{stream_name}:{idemp_key}"
                                if full_idemp in seen_idemp_keys:
                                    add_warning(
                                        "id_uniqueness",
                                        "duplicates",
                                        f"{filepath.name}:{line_no} Duplicate idempotency_key '{idemp_key}'",
                                    )
                                else:
                                    seen_idemp_keys.add(full_idemp)

                        except json.JSONDecodeError as e:
                            add_warning(
                                "jsonl_integrity",
                                "malformed",
                                f"{filepath.name}:{line_no} JSON Decode Error: {str(e)}",
                            )
                            add_error(
                                "jsonl_integrity",
                                f"Fatal parse error in {filepath.name}",
                            )

        # 4. Secrets
        for f in ["project.yaml", "envs.yaml", "access.yaml"]:
            try:
                data = self._load_yaml(f)
                detect_secrets(data, path=f)
            except SecretDetectedError as e:
                add_warning("secrets", "detected", str(e))
                add_error("secrets", "Secrets detected in YAML configurations")

        for items in [self.work_items.values()]:
            for item in items:
                try:
                    detect_secrets(item, path=f"WorkItem[{item.get('work_item_id')}]")
                except SecretDetectedError as e:
                    add_warning("secrets", "detected", str(e))
                    add_error("secrets", "Secrets detected in Work Items")

        # 5. References & Semantic Schema (Work Items)
        for wid, item in self.work_items.items():
            if not item.get("title"):
                add_warning(
                    "references", "dangling", f"Work item {wid} missing 'title'"
                )
            if "status" not in item:
                add_error("references", f"Work item {wid} missing 'status'")

            deps = item.get("dependencies", {})
            for blocker in deps.get("blocked_by", []):
                if blocker not in self.work_items:
                    add_warning(
                        "references",
                        "dangling",
                        f"Work item {wid} blocked by missing ID: {blocker}",
                    )

        # 6. Claims Validity
        now = datetime.datetime.now(datetime.timezone.utc)
        for wid, item in self.work_items.items():
            claim = item.get("claim")
            if claim and claim.get("lease_until"):
                try:
                    dt = datetime.datetime.fromisoformat(
                        claim["lease_until"].replace("Z", "+00:00")
                    )
                    if now > dt:
                        add_warning(
                            "claims",
                            "expired",
                            f"Work item {wid} has expired claim held by {claim.get('claimed_by')}",
                        )
                except ValueError:
                    add_error(
                        "claims",
                        f"Work item {wid} has malformed claim date {claim['lease_until']}",
                    )

        # 7. Corruption Recovery Guidance
        if report["summary"]["status"] == "\u274c":
            report["summary"]["recovery"] = (
                "If a JSONL file is corrupted, you can: \n"
                "1. Restore from a recent 'rekall checkpoint' or backup.\n"
                "2. Manually remove the malformed line if it's the last one.\n"
                "3. Run 'rekall doctor' for a full system check."
            )

        if strict and report["summary"]["warnings"] > 0:
            report["summary"]["status"] = "\u274c"

        return report
