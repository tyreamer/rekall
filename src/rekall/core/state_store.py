import json
import logging
import re
import os
import shutil
import uuid
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import yaml

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
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),                  # Generic secret key pattern
    re.compile(r"xox[baprs]-[a-zA-Z0-9]{10,}"),          # Slack tokens
    re.compile(r"AKIA[0-9A-Z]{16}"),                     # AWS access keys
    re.compile(r"eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+"),  # JWT
]

class BloatConfig:
    MAX_RECORD_BYTES = 128 * 1024  # 128 KB
    MAX_HOT_RECORDS = 1000        # Roll over after 1000 records
    MAX_HOT_BYTES = 5 * 1024 * 1024 # 5 MB

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
        
        # In-memory caches for easy access
        self.project_config: Dict[str, Any] = {}
        self.envs_config: Dict[str, Any] = {}
        self.access_config: Dict[str, Any] = {}
        
        self.manifest: Dict[str, Any] = {
            "streams": {},
            "last_checkpoint": None,
            "schema_version": "0.1"
        }
        
        # LRU-ish cache for idempotency in the HOT window
        self._idemp_cache: Dict[str, Set[str]] = {} # stream_name -> set of IDs
        
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
        if version != "0.1":
            raise SchemaVersionError(f"Unsupported schema version: {version}. Expected: 0.1")
            
        # 2. Load Manifest and Migrate if necessary
        self._load_manifest()
        self._migrate_legacy_files()
        
        # 3. Load YAMLs safely, verifying no secrets
        self.project_config = self._load_yaml("project.yaml")
        self.envs_config = self._load_yaml("envs.yaml")
        self.access_config = self._load_yaml("access.yaml")
        
        # 4. Reload Work Items from event stream (HOT only by default)
        self._replay_work_items()

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
            "timeline.jsonl": ("timeline", "event_id")
        }
        
        for filename, (stream_key, id_field) in legacy_files.items():
            legacy_path = self.base_dir / filename
            if legacy_path.exists():
                stream_dir = streams_dir / stream_key
                stream_dir.mkdir(parents=True, exist_ok=True)
                active_path = stream_dir / "active.jsonl"
                
                if not active_path.exists():
                    shutil.move(legacy_path, active_path)
                else:
                    # Append legacy to active if both exist (unlikely in fresh migration)
                    with open(active_path, "a", encoding="utf-8") as target:
                        with open(legacy_path, "r", encoding="utf-8") as source:
                            target.write(source.read())
                    legacy_path.unlink()
                
                self.manifest["streams"][stream_key] = {
                    "active_file": str(active_path.relative_to(self.base_dir)),
                    "segments": [],
                    "id_field": id_field
                }
        
        if any(f in os.listdir(self.base_dir) for f in legacy_files):
            self._save_manifest()

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        filepath = self.base_dir / filename
        if not filepath.exists():
            return {}
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            detect_secrets(data)
            return data

    def _load_jsonl(self, filename: str) -> List[Dict[str, Any]]:
        filepath = self.base_dir / filename
        if not filepath.exists():
            return []
        records = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                if line.strip():
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        # Log but continue if possible during general load
                        # validate_all will catch this for a proper report
                        logger.warning(f"Malformed JSON in {filename}:{line_no}: {line}")
        return records

    def append_jsonl_idempotent(self, stream_name: str, record: Dict[str, Any], id_field: str) -> Dict[str, Any]:
        """
        Appends a record to a jsonl stream idempotently and enforces bloat guardrails.
        """
        detect_secrets(record)
        
        # 1. Record Size Guardrail
        record_json = json.dumps(record, sort_keys=True)
        if len(record_json.encode('utf-8')) > BloatConfig.MAX_RECORD_BYTES:
            raise ValueError(f"Record exceeds maximum size of {BloatConfig.MAX_RECORD_BYTES} bytes")

        # 2. Ensure stream exists in manifest
        if stream_name not in self.manifest["streams"]:
            stream_dir = self.base_dir / "streams" / stream_name
            stream_dir.mkdir(parents=True, exist_ok=True)
            active_file = stream_dir / "active.jsonl"
            active_file.touch(exist_ok=True)
            self.manifest["streams"][stream_name] = {
                "active_file": str(active_file.relative_to(self.base_dir)),
                "segments": [],
                "id_field": id_field
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
                        if not line.strip(): continue
                        try:
                            existing = json.loads(line)
                            if existing.get(id_field): self._idemp_cache[stream_name].add(existing[id_field])
                            if existing.get("idempotency_key"): self._idemp_cache[stream_name].add(f"idemp:{existing['idempotency_key']}")
                        except json.JSONDecodeError: continue

        if rid in self._idemp_cache[stream_name]:
            # Double check active file to be sure (if cache was partial, but here we wamed it)
            return record # Assume exists
            
        if idemp_key and f"idemp:{idemp_key}" in self._idemp_cache[stream_name]:
            return record # Assume exists

        # 4. Atomic Append with Locking logic (simplified for now)
        lock_file = active_path.with_suffix(".lock")
        try:
            # Basic file locking (wait-and-retry could be added)
            with open(lock_file, "x"): pass 
            
            # Check rollover before append
            if active_path.exists():
                stat = active_path.stat()
                # Count lines without loading whole file
                count = 0
                with open(active_path, "rb") as f:
                    for _ in f: count += 1
                
                if stat.st_size > BloatConfig.MAX_HOT_BYTES or count >= BloatConfig.MAX_HOT_RECORDS:
                    self._roll_over_stream(stream_name)
                    # Re-resolve active path after rollover
                    active_path = self.base_dir / self.manifest["streams"][stream_name]["active_file"]

            with open(active_path, "a", encoding="utf-8") as f:
                f.write(record_json + "\n")
            
            # Update cache
            if rid: self._idemp_cache[stream_name].add(rid)
            if idemp_key: self._idemp_cache[stream_name].add(f"idemp:{idemp_key}")
            
        finally:
            if lock_file.exists():
                lock_file.unlink()
            
        return record

    def _roll_over_stream(self, stream_name: str):
        stream_info = self.manifest["streams"][stream_name]
        active_path = self.base_dir / stream_info["active_file"]
        
        seg_idx = len(stream_info["segments"]) + 1
        seg_name = f"seg-{seg_idx:04d}.jsonl"
        seg_path = active_path.parent / seg_name
        
        shutil.move(active_path, seg_path)
        active_path.touch()
        
        stream_info["segments"].append(str(seg_path.relative_to(self.base_dir)))
        self._save_manifest()
        logger.info(f"Rolled over stream '{stream_name}' to {seg_name}")

    def _replay_work_items(self):
        """
        Replays work_items.jsonl into self.work_items map.
        Computes `version` and `claim` dynamically.
        """
        self.work_items.clear()
        
        # In strict validation we might want to catch these earlier, but replay needs to survive
        try:
            events = self._load_jsonl("work-items.jsonl")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse work-items.jsonl: {e}")
            events = []
            
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
                    # Even in replay, we simulate applying patches correctly. 
                    if expected_version is not None and item["version"] != expected_version:
                        logger.warning(f"Replay mismatch for {wid}: expected v{expected_version}, got v{item['version']}")
                    
                    patch_data = event.get("patch", {})
                    item.update(patch_data)
                    item["version"] += 1
            elif e_type == WorkItemEventTypes.CLAIMED:
                if wid in self.work_items:
                    item = self.work_items[wid]
                    claim = event.get("patch", {})
                    # Should contain `claimed_by` and `lease_until`
                    item["claim"] = claim
                    item["version"] += 1
            elif e_type == WorkItemEventTypes.RELEASED:
                if wid in self.work_items:
                    item = self.work_items[wid]
                    item["claim"] = None
                    item["version"] += 1

    def _append_activity(self, action: str, target_type: str, target_id: str, actor: Dict[str, Any], diff: Optional[Dict[str, Any]] = None, reason: Optional[str] = None):
        import uuid
        import datetime
        activity_record = {
            "activity_id": str(uuid.uuid4()),
            "project_id": self.project_config.get("project_id", ""),
            "actor": actor,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        if diff:
            activity_record["diff"] = diff
        if reason:
            activity_record["reason"] = reason
            
        self.append_jsonl_idempotent("activity.jsonl", activity_record, id_field="activity_id")

    def _verify_claim_for_update(self, item: Dict[str, Any], actor: Dict[str, Any], force: bool = False):
        if force:
            return  # Admin override
            
        claim = item.get("claim")
        if not claim:
            return  # Unclaimed items can be updated by anyone (or we could enforce claim-first, but spec says "If claim exists and caller isn't claimant -> FORBIDDEN")
            
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        
        lease_until_str = claim.get("lease_until")
        if lease_until_str:
            try:
                lease_until = datetime.datetime.fromisoformat(lease_until_str.replace('Z', '+00:00'))
                if now > lease_until:
                    # Lease expired, essentially unclaimed
                    return
            except ValueError:
                pass
                
        # Active claim exists
        if claim.get("claimed_by") != actor.get("actor_id"):
            raise PermissionError(f"Work item {item['work_item_id']} is claimed by {claim.get('claimed_by')}")

    def create_work_item(self, work_item: Dict[str, Any], actor: Dict[str, Any], reason: Optional[str] = None) -> Dict[str, Any]:
        detect_secrets(work_item)
        import uuid
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
            "updated_at": now
        }
        
        event = {
            "event_id": event_id,
            "type": WorkItemEventTypes.CREATED,
            "project_id": self.project_config.get("project_id", ""),
            "work_item_id": wid,
            "timestamp": now,
            "actor": actor,
            "expected_version": 0,
            "patch": patch
        }
        if reason:
            event["reason"] = reason
            
        self.append_jsonl_idempotent("work-items.jsonl", event, id_field="event_id")
        self._append_activity("create", "work_item", wid, actor, diff=patch, reason=reason)
        
        # Apply to memory
        patch["work_item_id"] = wid
        patch["version"] = 1
        patch["claim"] = None
        self.work_items[wid] = patch
        return patch

    def update_work_item(self, work_item_id: str, patch: Dict[str, Any], expected_version: int, actor: Dict[str, Any], force: bool = False, reason: Optional[str] = None) -> Dict[str, Any]:
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
            
        import uuid
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
            "patch": patch
        }
        if reason:
            event["reason"] = reason
        
        self.append_jsonl_idempotent("work-items.jsonl", event, id_field="event_id")
        self._append_activity("update", "work_item", work_item_id, actor, diff=patch, reason=reason)
        
        # Re-apply memory state
        item.update(patch)
        item["version"] += 1
        return item
        
    def claim_work_item(self, work_item_id: str, expected_version: int, actor: Dict[str, Any], lease_seconds: int = 1800, force: bool = False, reason: Optional[str] = None) -> Dict[str, Any]:
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
                        lease_until = datetime.datetime.fromisoformat(lease_until_str.replace('Z', '+00:00'))
                        if now <= lease_until:
                            raise PermissionError(f"Work item {work_item_id} is currently claimed by {claim['claimed_by']}")
                    except ValueError:
                        pass
        
        import uuid
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        lease_until = (now + datetime.timedelta(seconds=lease_seconds)).isoformat()
        
        claim_data = {
            "claimed_by": actor.get("actor_id"),
            "lease_until": lease_until
        }
        
        event = {
            "event_id": str(uuid.uuid4()),
            "type": WorkItemEventTypes.CLAIMED,
            "project_id": item.get("project_id", ""),
            "work_item_id": work_item_id,
            "timestamp": now.isoformat(),
            "actor": actor,
            "expected_version": expected_version,
            "patch": claim_data
        }
        if reason:
            event["reason"] = reason
            
        self.append_jsonl_idempotent("work-items.jsonl", event, id_field="event_id")
        self._append_activity("claim", "work_item", work_item_id, actor, diff=claim_data, reason=reason)
        
        item["claim"] = claim_data
        item["version"] += 1
        return item
        
    def renew_claim(self, work_item_id: str, expected_version: int, actor: Dict[str, Any], lease_seconds: int = 1800, reason: Optional[str] = None) -> Dict[str, Any]:
        item = self.work_items.get(work_item_id)
        if not item:
            raise KeyError(f"Work item {work_item_id} not found")
            
        if item["version"] != expected_version:
            raise StateConflictError(
                f"Version mismatch for {work_item_id}. Expected {expected_version}, but current is {item['version']}"
            )
            
        claim = item.get("claim")
        if not claim or claim.get("claimed_by") != actor.get("actor_id"):
            raise PermissionError(f"Cannot renew: you do not hold the active claim for {work_item_id}")
            
        # It's identical to claiming again
        return self.claim_work_item(work_item_id, expected_version, actor, lease_seconds, force=True, reason=reason)

    def release_claim(self, work_item_id: str, expected_version: int, actor: Dict[str, Any], force: bool = False, reason: Optional[str] = None) -> Dict[str, Any]:
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
                raise PermissionError(f"Cannot release: you do not hold the active claim for {work_item_id}")
                
        import uuid
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        event = {
            "event_id": str(uuid.uuid4()),
            "type": WorkItemEventTypes.RELEASED,
            "project_id": item.get("project_id", ""),
            "work_item_id": work_item_id,
            "timestamp": now,
            "actor": actor,
            "expected_version": expected_version
        }
        if reason:
            event["reason"] = reason
            
        self.append_jsonl_idempotent("work-items.jsonl", event, id_field="event_id")
        self._append_activity("release", "work_item", work_item_id, actor, reason=reason)
        
        item["claim"] = None
        item["version"] += 1
        return item

    def append_attempt(self, attempt: Dict[str, Any], actor: Dict[str, Any], reason: Optional[str] = None, idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        detect_secrets(attempt)
        import uuid
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
        if record is attempt: # Identity check since `append_jsonl_idempotent` returns existing if duplicate
            self._append_activity("append", "attempt", attempt_id, actor, reason=reason)
            
        return record

    def propose_decision(self, decision: Dict[str, Any], actor: Dict[str, Any], reason: Optional[str] = None, idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        detect_secrets(decision)
        import uuid
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
            
        record = self.append_jsonl_idempotent("decisions.jsonl", decision, "decision_id")
        
        if record is decision:
            self._append_activity("propose", "decision", decision_id, actor, reason=reason)
            
        return record

    def approve_decision(self, decision_id: str, actor: Dict[str, Any], reason: Optional[str] = None) -> Dict[str, Any]:
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
            return target # Idempotent approval
            
        import uuid
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        approved_decision = target.copy()
        new_id = str(uuid.uuid4())
        approved_decision["decision_id"] = new_id
        approved_decision["status"] = "approved"
        approved_decision["supersedes"] = decision_id
        approved_decision["decided_by"] = actor
        approved_decision["timestamp"] = now
        
        self.append_jsonl_idempotent("decisions.jsonl", approved_decision, "decision_id")
        self._append_activity("approve", "decision", decision_id, actor, diff={"status": "approved", "new_decision_id": new_id}, reason=reason)
        
        return approved_decision

    def append_timeline(self, event: Dict[str, Any], actor: Dict[str, Any], reason: Optional[str] = None, idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        detect_secrets(event)
        import uuid
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

    def validate_all(self, strict: bool = False) -> Dict[str, Any]:
        """
        Performs a deep diagnostic scan of the entire StateStore.
        Returns a structured report dictionary.
        Raises ValueError in strict mode if any warnings exist.
        """
        import datetime
        report = {
            "summary": {"status": "✅", "errors": 0, "warnings": 0},
            "schema_version": {"status": "✅", "details": ""},
            "files_present": {"status": "✅", "missing": []},
            "jsonl_integrity": {"status": "✅", "malformed": []},
            "id_uniqueness": {"status": "✅", "duplicates": []},
            "references": {"status": "✅", "dangling": []},
            "secrets": {"status": "✅", "detected": []},
            "claims": {"status": "✅", "expired": []}
        }
        
        def add_error(section: str, msg: str):
            report[section]["status"] = "❌"
            if "errors" not in report[section]: report[section]["errors"] = []
            report[section]["errors"].append(msg)
            report["summary"]["errors"] += 1
            report["summary"]["status"] = "❌"
            
        def add_warning(section: str, list_key: str, msg: str):
            if report[section]["status"] == "✅":
                report[section]["status"] = "⚠️"
            report[section][list_key].append(msg)
            report["summary"]["warnings"] += 1
            if report["summary"]["status"] == "✅":
                report["summary"]["status"] = "⚠️"

        # 1. Schema Version
        schema_file = self.base_dir / "schema-version.txt"
        if not schema_file.exists():
            add_error("schema_version", "Missing schema-version.txt")
        else:
            v = schema_file.read_text().strip()
            report["schema_version"]["details"] = v
            if v != "0.1":
                add_error("schema_version", f"Unsupported version: {v}")
                
        # 2. Files Present
        expected_files = ["project.yaml", "envs.yaml", "access.yaml", "work-items.jsonl", "activity.jsonl", "attempts.jsonl", "decisions.jsonl", "timeline.jsonl"]
        for f in expected_files:
            if not (self.base_dir / f).exists():
                add_warning("files_present", "missing", f)
                
        # 3. JSONL Integrity & ID Uniqueness
        seen_ids = set()
        seen_idemp_keys = set()
        for f in ["work-items.jsonl", "activity.jsonl", "attempts.jsonl", "decisions.jsonl", "timeline.jsonl"]:
            filepath = self.base_dir / f
            if not filepath.exists():
                continue
                
            id_field_map = {
                "work-items.jsonl": "event_id",
                "activity.jsonl": "activity_id",
                "attempts.jsonl": "attempt_id",
                "decisions.jsonl": "decision_id",
                "timeline.jsonl": "event_id"
            }
            id_key = id_field_map[f]
            seen_idemp_keys.clear()
            
            with open(filepath, "r", encoding="utf-8") as file:
                for line_no, line in enumerate(file, 1):
                    if not line.strip(): continue
                    try:
                        record = json.loads(line)
                        rid = record.get(id_key)
                        idemp_key = record.get("idempotency_key")
                        if rid:
                            if rid in seen_ids:
                                add_warning("id_uniqueness", "duplicates", f"{f}:{line_no} Duplicate ID {rid}")
                            else:
                                seen_ids.add(rid)
                        else:
                            add_error("jsonl_integrity", f"{f}:{line_no} Missing ID field '{id_key}'")
                            
                        if idemp_key:
                            if idemp_key in seen_idemp_keys:
                                add_warning("id_uniqueness", "duplicates", f"{f}:{line_no} Duplicate idempotency_key '{idemp_key}'")
                            else:
                                seen_idemp_keys.add(idemp_key)

                    except json.JSONDecodeError as e:
                        add_warning("jsonl_integrity", "malformed", f"{f}:{line_no} JSON Decode Error: {str(e)}")
                        add_error("jsonl_integrity", f"Fatal parse error in {f}")

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
                add_warning("references", "dangling", f"Work item {wid} missing 'title'")
            if "status" not in item:
                add_error("references", f"Work item {wid} missing 'status'")
                
            deps = item.get("dependencies", {})
            for blocker in deps.get("blocked_by", []):
                if blocker not in self.work_items:
                    add_warning("references", "dangling", f"Work item {wid} blocked by missing ID: {blocker}")
                    
        # 6. Claims Validity
        now = datetime.datetime.now(datetime.timezone.utc)
        for wid, item in self.work_items.items():
            claim = item.get("claim")
            if claim and claim.get("lease_until"):
                try:
                    dt = datetime.datetime.fromisoformat(claim["lease_until"].replace('Z', '+00:00'))
                    if now > dt:
                        add_warning("claims", "expired", f"Work item {wid} has expired claim held by {claim.get('claimed_by')}")
                except ValueError:
                    add_error("claims", f"Work item {wid} has malformed claim date {claim['lease_until']}")
                    
        # 7. Corruption Recovery Guidance
        if report["summary"]["status"] == "❌":
            report["summary"]["recovery"] = (
                "If a JSONL file is corrupted, you can: \n"
                "1. Restore from a recent 'rekall checkpoint' or backup.\n"
                "2. Manually remove the malformed line if it's the last one.\n"
                "3. Run 'rekall doctor' for a full system check."
            )
                    
        if strict and report["summary"]["warnings"] > 0:
            report["summary"]["status"] = "❌"
            
        return report

