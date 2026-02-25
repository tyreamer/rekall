import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from rekall.core.state_store import StateStore

logger = logging.getLogger(__name__)

_store: Optional[StateStore] = None

def get_store() -> StateStore:
    global _store
    if _store is None:
        default_artifact = Path(__file__).parent.parent.parent.parent / "examples" / "sample_state_artifact"
        artifact_path = os.getenv("REKALL_ARTIFACT_PATH", str(default_artifact))
        _store = StateStore(Path(artifact_path))
    return _store

def _paginate(items: List[Dict[str, Any]], limit: int, offset: int = 0) -> Dict[str, Any]:
    paginated = items[offset:offset + limit]
    res = {"items": paginated}
    if offset + limit < len(items):
        res["next_cursor"] = str(offset + limit)
    return res

# --- Tool Implementations ---

def project_list(args: dict) -> list:
    limit = args.get("limit", 50)
    cursor = str(args.get("cursor", "0"))
    offset = int(cursor) if cursor.isdigit() else 0
    tag = args.get("tag")
    
    store = get_store()
    cfg = store.project_config
    if not cfg:
        return [_paginate([], limit, offset)]
        
    if tag and tag not in cfg.get("tags", []):
         return [_paginate([], limit, offset)]

    summary = {
        "project_id": cfg.get("project_id"),
        "name": cfg.get("name"),
        "one_liner": cfg.get("one_liner"),
        "schema_version": cfg.get("schema_version"),
        "updated_at": cfg.get("updated_at")
    }
    return [_paginate([summary], limit, offset)]

def project_get(args: dict) -> list:
    project_id = args.get("project_id")
    if not project_id:
        raise ValueError("project_id is required")
        
    store = get_store()
    cfg = store.project_config
    if cfg.get("project_id") != project_id:
         return [{"error": "Project not found"}]
        
    return [{"project": cfg}]

def work_list(args: dict) -> list:
    limit = args.get("limit", 100)
    cursor = str(args.get("cursor", "0"))
    offset = int(cursor) if cursor.isdigit() else 0
    status = args.get("status")
    type_filter = args.get("type")
    priority = args.get("priority")
    owner = args.get("owner")
    
    store = get_store()
    items = list(store.work_items.values())
    
    filtered = []
    for item in items:
        if status and item.get("status") not in status: continue
        if type_filter and item.get("type") not in type_filter: continue
        if priority and item.get("priority") not in priority: continue
        if owner and item.get("owner") != owner: continue
        
        summary = {
            "work_item_id": item.get("work_item_id"),
            "type": item.get("type"),
            "title": item.get("title"),
            "status": item.get("status"),
            "priority": item.get("priority"),
            "owner": item.get("owner"),
            "claim": item.get("claim"),
            "version": item.get("version"),
            "updated_at": item.get("updated_at")
        }
        filtered.append(summary)
        
    filtered.sort(key=lambda x: (x.get("updated_at", ""), x.get("work_item_id", "")))
    return [_paginate(filtered, limit, offset)]

def work_get(args: dict) -> list:
    work_item_id = args.get("work_item_id")
    if not work_item_id:
        raise ValueError("work_item_id is required")
        
    store = get_store()
    item = store.work_items.get(work_item_id)
    if not item:
        return [{"error": "Work item not found"}]
        
    return [{"work_item": item}]

def _list_log(filename: str, args: dict) -> list:
    limit = args.get("limit", 100)
    cursor = str(args.get("cursor", "0"))
    offset = int(cursor) if cursor.isdigit() else 0
    
    store = get_store()
    records = store._load_jsonl(filename)
    
    def sort_key(r):
        ts = r.get("timestamp", "")
        id_val = r.get("attempt_id") or r.get("decision_id") or r.get("event_id") or r.get("activity_id") or ""
        return (ts, id_val)
        
    records.sort(key=sort_key)
    return [_paginate(records, limit, offset)]

def attempt_list(args: dict) -> list: return _list_log("attempts.jsonl", args)
def decision_list(args: dict) -> list: return _list_log("decisions.jsonl", args)
def timeline_list(args: dict) -> list: return _list_log("timeline.jsonl", args)
def activity_list(args: dict) -> list: return _list_log("activity.jsonl", args)

def env_list(args: dict) -> list:
    limit = args.get("limit", 100)
    cursor = str(args.get("cursor", "0"))
    offset = int(cursor) if cursor.isdigit() else 0
    store = get_store()
    envs = store.envs_config.get("environments", [])
    envs.sort(key=lambda x: x.get("env_id", ""))
    return [_paginate(envs, limit, offset)]

def access_list(args: dict) -> list:
    limit = args.get("limit", 100)
    cursor = str(args.get("cursor", "0"))
    offset = int(cursor) if cursor.isdigit() else 0
    store = get_store()
    refs = store.access_config.get("access_refs", [])
    refs.sort(key=lambda x: x.get("access_ref_id", ""))
    return [_paginate(refs, limit, offset)]

# --- Write Tools ---
def work_create(args: dict) -> list:
    project_id = args.get("project_id")
    work_item = args.get("work_item")
    actor = args.get("actor")
    reason = args.get("reason")
    if not project_id or not work_item or not actor:
        raise ValueError("project_id, work_item, and actor are required")
    store = get_store()
    try:
        updated = store.create_work_item(work_item, actor, reason=reason)
        return [{"work_item": updated}]
    except Exception as e:
        return [{"error": {"code": "VALIDATION_ERROR", "message": str(e)}}]

def work_update(args: dict) -> list:
    work_item_id = args.get("work_item_id")
    expected_version = args.get("expected_version")
    patch = args.get("patch")
    actor = args.get("actor")
    force = args.get("force", False)
    reason = args.get("reason")
    if not all([work_item_id, expected_version is not None, patch, actor]):
        raise ValueError("work_item_id, expected_version, patch, and actor are required")
    store = get_store()
    try:
        updated = store.update_work_item(work_item_id, patch, expected_version, actor, force=force, reason=reason)
        return [{"work_item": updated}]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        if "Version mismatch" in str(e): err_code = "CONFLICT"
        elif "claimed by" in str(e): err_code = "FORBIDDEN"
        return [{"error": {"code": err_code, "message": str(e)}}]

def work_claim(args: dict) -> list:
    work_item_id = args.get("work_item_id")
    expected_version = args.get("expected_version")
    actor = args.get("actor")
    lease_seconds = args.get("lease_seconds", 1800)
    force = args.get("force", False)
    reason = args.get("reason")
    store = get_store()
    try:
        updated = store.claim_work_item(work_item_id, expected_version, actor, lease_seconds, force, reason)
        return [{"work_item": updated}]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        if "Version mismatch" in str(e): err_code = "CONFLICT"
        elif "currently claimed" in str(e): err_code = "FORBIDDEN"
        return [{"error": {"code": err_code, "message": str(e)}}]

def work_renew_claim(args: dict) -> list:
    work_item_id = args.get("work_item_id")
    expected_version = args.get("expected_version")
    actor = args.get("actor")
    lease_seconds = args.get("lease_seconds", 1800)
    reason = args.get("reason")
    store = get_store()
    try:
        updated = store.renew_claim(work_item_id, expected_version, actor, lease_seconds, reason)
        return [{"work_item": updated}]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        if "Version mismatch" in str(e): err_code = "CONFLICT"
        elif "do not hold" in str(e): err_code = "FORBIDDEN"
        return [{"error": {"code": err_code, "message": str(e)}}]

def work_release_claim(args: dict) -> list:
    work_item_id = args.get("work_item_id")
    expected_version = args.get("expected_version")
    actor = args.get("actor")
    force = args.get("force", False)
    reason = args.get("reason")
    store = get_store()
    try:
        updated = store.release_claim(work_item_id, expected_version, actor, force, reason)
        return [{"work_item": updated}]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        if "Version mismatch" in str(e): err_code = "CONFLICT"
        elif "do not hold" in str(e): err_code = "FORBIDDEN"
        return [{"error": {"code": err_code, "message": str(e)}}]

def attempt_append(args: dict) -> list:
    project_id = args.get("project_id")
    attempt = args.get("attempt")
    actor = args.get("actor")
    reason = args.get("reason")
    if not project_id or not attempt or not actor:
        raise ValueError("project_id, attempt, and actor are required")
    store = get_store()
    try:
        updated = store.append_attempt(attempt, actor, reason=reason)
        return [{"attempt": updated}]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        if "Secret detected" in str(e): err_code = "SECRET_DETECTED"
        return [{"error": {"code": err_code, "message": str(e)}}]

def decision_propose(args: dict) -> list:
    project_id = args.get("project_id")
    decision = args.get("decision")
    actor = args.get("actor")
    reason = args.get("reason")
    if not project_id or not decision or not actor:
        raise ValueError("project_id, decision, and actor are required")
    store = get_store()
    try:
        updated = store.propose_decision(decision, actor, reason=reason)
        return [{"decision": updated}]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        if "Secret detected" in str(e): err_code = "SECRET_DETECTED"
        return [{"error": {"code": err_code, "message": str(e)}}]

def decision_approve(args: dict) -> list:
    project_id = args.get("project_id")
    decision_id = args.get("decision_id")
    actor = args.get("actor")
    reason = args.get("reason")
    if not project_id or not decision_id or not actor:
        raise ValueError("project_id, decision_id, and actor are required")
    store = get_store()
    try:
        updated = store.approve_decision(decision_id, actor, reason=reason)
        return [{"decision": updated}]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        if "lacks" in str(e).lower() or "capability" in str(e).lower(): err_code = "FORBIDDEN"
        return [{"error": {"code": err_code, "message": str(e)}}]

def timeline_append(args: dict) -> list:
    project_id = args.get("project_id")
    event = args.get("event")
    actor = args.get("actor")
    reason = args.get("reason")
    if not project_id or not event or not actor:
        raise ValueError("project_id, event, and actor are required")
    store = get_store()
    try:
        updated = store.append_timeline(event, actor, reason=reason)
        return [{"event": updated}]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        if "Secret detected" in str(e): err_code = "SECRET_DETECTED"
        return [{"error": {"code": err_code, "message": str(e)}}]

def exec_query(args: dict) -> list:
    project_id = args.get("project_id")
    query_type = args.get("query_type")
    since = args.get("since")
    
    if not project_id or not query_type:
        raise ValueError("project_id and query_type are required")
        
    store = get_store()
    work_items = list(store.work_items.values())
    
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    
    # Helper to check if an iso string is older than X days
    def is_stale(iso_str: str, days: int) -> bool:
        if not iso_str: return True
        try:
            dt = datetime.datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
            return (now - dt).days >= days
        except ValueError:
            return True

    res = {
        "summary": [],
        "confidence": "high",
        "evidence": []
    }
    
    if query_type == "ON_TRACK":
        blockers = [w for w in work_items if w.get("status") == "blocked"]
        stale_blockers = [w for w in blockers if is_stale(w.get("updated_at", ""), 7)]
        
        if stale_blockers:
            res["summary"].append(f"Status computed as AT_RISK or OFF_TRACK due to {len(stale_blockers)} stale blockers.")
            res["confidence"] = "medium"
            res["evidence"].extend([f"work_item: {w['work_item_id']}" for w in stale_blockers[:5]])
        elif blockers:
            res["summary"].append(f"Status computed as AT_RISK due to {len(blockers)} active blockers.")
            res["confidence"] = "high"
            res["evidence"].extend([f"work_item: {w['work_item_id']}" for w in blockers[:5]])
        else:
            in_prog = [w for w in work_items if w.get("status") == "in_progress"]
            if not in_prog:
                res["summary"].append("Status computed as PAUSED or LOW ACTIVITY (no active work).")
                res["confidence"] = "low"
            else:
                res["summary"].append("Status computed as ON_TRACK. Work is progressing with no recorded blockers.")
                res["evidence"].extend([f"work_item: {w['work_item_id']}" for w in in_prog[:3]])
                
    elif query_type == "BLOCKERS":
        blockers = [w for w in work_items if w.get("status") == "blocked"]
        if not blockers:
            res["summary"].append("No active blockers recorded.")
            res["confidence"] = "high"
        else:
            res["summary"].append(f"Found {len(blockers)} blocked work items.")
            # Sort by priority, then age
            blockers.sort(key=lambda x: (x.get("priority", "p9"), x.get("updated_at", "")))
            res["evidence"].extend([f"work_item: {w['work_item_id']}" for w in blockers[:10]])
            if any(is_stale(w.get("updated_at", ""), 7) for w in blockers):
                res["confidence"] = "medium"
                res["summary"].append("Warning: Some blockers are stale (>7 days).")
                
    elif query_type == "CHANGED_SINCE":
        if not since:
            return [{"error": {"code": "VALIDATION_ERROR", "message": "CHANGED_SINCE requires 'since' timestamp"}}]
            
        acts = store._load_jsonl("activity.jsonl")
        recent = [a for a in acts if a.get("timestamp", "") >= since]
        recent.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        if not recent:
            res["summary"].append(f"No activity recorded since {since}.")
            res["confidence"] = "high"
        else:
            res["summary"].append(f"Found {len(recent)} activities since {since}.")
            res["evidence"].extend([f"activity: {a['activity_id']} (target_type: {a.get('target_type')})" for a in recent[:10]])
            
    elif query_type == "NEXT_7_DAYS":
        priorities = [w for w in work_items if w.get("status") in ["todo", "in_progress"] and w.get("priority") in ["p0", "p1"]]
        if priorities:
            res["summary"].append(f"Focusing on {len(priorities)} high-priority (p0/p1) work items.")
            res["evidence"].extend([f"work_item: {w['work_item_id']}" for w in priorities[:5]])
        else:
            res["summary"].append("No high-priority work items found. Execution plan unclear.")
            res["confidence"] = "low"
            
    elif query_type == "RECENT_DECISIONS":
        decs = store._load_jsonl("decisions.jsonl")
        decs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        if not decs:
            res["summary"].append("No decisions recorded.")
        else:
            res["summary"].append(f"Found {len(decs)} total decisions.")
            res["evidence"].extend([f"decision: {d['decision_id']} ({d.get('title', 'untitled')})" for d in decs[:5]])

    elif query_type == "FAILED_ATTEMPTS":
        atts = store._load_jsonl("attempts.jsonl")
        failed = [a for a in atts if str(a.get("outcome", "")).lower() == "failed"]
        failed.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        if not failed:
            res["summary"].append("No failed attempts recorded.")
        else:
            res["summary"].append(f"Found {len(failed)} failed attempts.")
            res["evidence"].extend([f"attempt: {a['attempt_id']}" for a in failed[:5]])

    elif query_type == "WHERE_RUNNING_ACCESS":
        envs = store.envs_config.get("environments", [])
        refs = store.access_config.get("access_refs", [])
        res["summary"].append(f"Project defines {len(envs)} environments and {len(refs)} access references.")
        res["evidence"].extend([f"env: {e.get('env_id')}" for e in envs[:3]])
        res["evidence"].extend([f"access_ref: {r.get('access_ref_id')}" for r in refs[:3]])

    elif query_type == "RESUME_IN_30":
        # Synthesize multiple things
        in_prog = [w for w in work_items if w.get("status") == "in_progress"]
        blockers = [w for w in work_items if w.get("status") == "blocked"]
        
        res["summary"].append(f"Project has {len(in_prog)} items in-progress and {len(blockers)} active blockers.")
        res["summary"].append(f"Goal: {store.project_config.get('one_liner', 'Unknown')}.")
        
        res["evidence"].extend([f"work_item: {w['work_item_id']}" for w in in_prog[:2]])
        res["evidence"].extend([f"work_item: {w['work_item_id']}" for w in blockers[:2]])
        
        envs = store.envs_config.get("environments", [])
        if envs:
            res["evidence"].append(f"env: {envs[0].get('env_id')}")
            
    else:
        return [{"error": {"code": "VALIDATION_ERROR", "message": f"Unsupported query_type: {query_type}"}}]

    return [{"executive_response": res}]

# --- MCP JSON-RPC Server Core ---

TOOLS_DEF = [
    {
        "name": "project.list",
        "description": "List projects visible to caller.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer"}, "cursor": {"type": "string"}, "tag": {"type": "string"}, "updated_since": {"type": "string"}}
        }
    },
    {
        "name": "project.get",
        "description": "Get a project's canonical metadata.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {"project_id": {"type": "string"}, "include": {"type": "array"}}
        }
    },
    {
        "name": "work.list",
        "description": "List work items with filters.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {
                "project_id": {"type": "string"},
                "limit": {"type": "integer"},
                "cursor": {"type": "string"},
                "status": {"type": "array"},
                "type": {"type": "array"},
                "priority": {"type": "array"},
                "tag": {"type": "string"},
                "owner": {"type": "string"},
                "claimed_by": {"type": "string"},
                "blocked_only": {"type": "boolean"},
                "updated_since": {"type": "string"}
            }
        }
    },
    {
        "name": "work.get",
        "description": "Get a specific work item's details.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "work_item_id"],
            "properties": {"project_id": {"type": "string"}, "work_item_id": {"type": "string"}, "include": {"type": "array"}}
        }
    },
    {
        "name": "attempt.list",
        "description": "List attempts.",
        "inputSchema": {"type": "object", "required": ["project_id"], "properties": {"project_id": {"type": "string"}, "limit": {"type": "integer"}, "cursor": {"type": "string"}, "since": {"type": "string"}}}
    },
    {
        "name": "decision.list",
        "description": "List decisions.",
        "inputSchema": {"type": "object", "required": ["project_id"], "properties": {"project_id": {"type": "string"}, "limit": {"type": "integer"}, "cursor": {"type": "string"}, "status": {"type": "array"}, "since": {"type": "string"}}}
    },
    {
        "name": "timeline.list",
        "description": "List timeline events.",
        "inputSchema": {"type": "object", "required": ["project_id"], "properties": {"project_id": {"type": "string"}, "limit": {"type": "integer"}, "cursor": {"type": "string"}, "since": {"type": "string"}}}
    },
    {
        "name": "activity.list",
        "description": "List activity/audit events.",
        "inputSchema": {"type": "object", "required": ["project_id"], "properties": {"project_id": {"type": "string"}, "limit": {"type": "integer"}, "cursor": {"type": "string"}, "since": {"type": "string"}}}
    },
    {
        "name": "env.list",
        "description": "List environments.",
        "inputSchema": {"type": "object", "required": ["project_id"], "properties": {"project_id": {"type": "string"}, "limit": {"type": "integer"}, "cursor": {"type": "string"}}}
    },
    {
        "name": "access.list",
        "description": "List access references.",
        "inputSchema": {"type": "object", "required": ["project_id"], "properties": {"project_id": {"type": "string"}, "limit": {"type": "integer"}, "cursor": {"type": "string"}}}
    },
    {
        "name": "work.create",
        "description": "Create a new work item.",
        "inputSchema": {"type": "object", "required": ["project_id", "work_item", "actor"], "properties": {"project_id": {"type": "string"}, "work_item": {"type": "object"}, "actor": {"type": "object"}, "reason": {"type": "string"}}}
    },
    {
        "name": "work.update",
        "description": "Update a work item.",
        "inputSchema": {"type": "object", "required": ["project_id", "work_item_id", "expected_version", "patch", "actor"], "properties": {"project_id": {"type": "string"}, "work_item_id": {"type": "string"}, "expected_version": {"type": "integer"}, "patch": {"type": "object"}, "actor": {"type": "object"}, "force": {"type": "boolean"}, "reason": {"type": "string"}}}
    },
    {
        "name": "work.claim",
        "description": "Claim a work item with a lease.",
        "inputSchema": {"type": "object", "required": ["project_id", "work_item_id", "expected_version", "actor"], "properties": {"project_id": {"type": "string"}, "work_item_id": {"type": "string"}, "expected_version": {"type": "integer"}, "actor": {"type": "object"}, "lease_seconds": {"type": "integer"}, "force": {"type": "boolean"}, "reason": {"type": "string"}}}
    },
    {
        "name": "work.renew_claim",
        "description": "Renew a claim.",
        "inputSchema": {"type": "object", "required": ["project_id", "work_item_id", "expected_version", "actor"], "properties": {"project_id": {"type": "string"}, "work_item_id": {"type": "string"}, "expected_version": {"type": "integer"}, "actor": {"type": "object"}, "lease_seconds": {"type": "integer"}, "reason": {"type": "string"}}}
    },
    {
        "name": "work.release_claim",
        "description": "Release a claim.",
        "inputSchema": {"type": "object", "required": ["project_id", "work_item_id", "expected_version", "actor"], "properties": {"project_id": {"type": "string"}, "work_item_id": {"type": "string"}, "expected_version": {"type": "integer"}, "actor": {"type": "object"}, "force": {"type": "boolean"}, "reason": {"type": "string"}}}
    },
    {
        "name": "attempt.append",
        "description": "Append an attempt note.",
        "inputSchema": {"type": "object", "required": ["project_id", "attempt", "actor"], "properties": {"project_id": {"type": "string"}, "attempt": {"type": "object"}, "actor": {"type": "object"}, "reason": {"type": "string"}}}
    },
    {
        "name": "decision.propose",
        "description": "Propose a decision log.",
        "inputSchema": {"type": "object", "required": ["project_id", "decision", "actor"], "properties": {"project_id": {"type": "string"}, "decision": {"type": "object"}, "actor": {"type": "object"}, "reason": {"type": "string"}}}
    },
    {
        "name": "decision.approve",
        "description": "Approve a decision.",
        "inputSchema": {"type": "object", "required": ["project_id", "decision_id", "actor"], "properties": {"project_id": {"type": "string"}, "decision_id": {"type": "string"}, "actor": {"type": "object"}, "reason": {"type": "string"}}}
    },
    {
        "name": "timeline.append",
        "description": "Append a timeline event.",
        "inputSchema": {"type": "object", "required": ["project_id", "event", "actor"], "properties": {"project_id": {"type": "string"}, "event": {"type": "object"}, "actor": {"type": "object"}, "reason": {"type": "string"}}}
    },
    {
        "name": "exec.query",
        "description": "Execute a canonical executive status query.",
        "inputSchema": {
            "type": "object", 
            "required": ["project_id", "query_type"], 
            "properties": {
                "project_id": {"type": "string"}, 
                "query_type": {"type": "string", "enum": ["ON_TRACK", "BLOCKERS", "CHANGED_SINCE", "NEXT_7_DAYS", "RECENT_DECISIONS", "FAILED_ATTEMPTS", "WHERE_RUNNING_ACCESS", "RESUME_IN_30"]},
                "since": {"type": "string", "description": "ISO timestamp for CHANGED_SINCE queries"}
            }
        }
    }
]

TOOL_REGISTRY = {
    "project.list": project_list,
    "project.get": project_get,
    "work.list": work_list,
    "work.get": work_get,
    "attempt.list": attempt_list,
    "decision.list": decision_list,
    "timeline.list": timeline_list,
    "activity.list": activity_list,
    "env.list": env_list,
    "access.list": access_list,
    "work.create": work_create,
    "work.update": work_update,
    "work.claim": work_claim,
    "work.renew_claim": work_renew_claim,
    "work.release_claim": work_release_claim,
    "attempt.append": attempt_append,
    "decision.propose": decision_propose,
    "decision.approve": decision_approve,
    "timeline.append": timeline_append,
    "exec.query": exec_query
}

def send_response(response: dict):
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()

def handle_request(req: dict):
    method = req.get("method")
    req_id = req.get("id")
    
    try:
        if method == "initialize":
            send_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05", # MCP standard version
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "rekall-mcp", "version": "0.1.0"}
                }
            })
        elif method == "tools/list":
            send_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": TOOLS_DEF
                }
            })
        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})
            
            if name in TOOL_REGISTRY:
                try:
                    result_data = TOOL_REGISTRY[name](args)
                    is_error = False
                    if len(result_data) == 1 and isinstance(result_data[0], dict) and "error" in result_data[0]:
                        is_error = True
                        err_obj = result_data[0]["error"]
                        response_content = json.dumps(err_obj)
                    else:
                        response_content = json.dumps(result_data[0]) if result_data else "{}"
                        
                    send_response({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": response_content}],
                            "isError": is_error
                        }
                    })
                except Exception as e:
                    send_response({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": json.dumps({"code": "UNKNOWN", "message": str(e)})}],
                            "isError": True
                        }
                    })
            else:
                send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Tool not found: {name}"}
                })
        else:
            if req_id is not None:
                send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": "Method not found"}
                })
    except Exception as e:
        if req_id is not None:
            send_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(e)}
            })

def main():
    logger.setLevel(logging.ERROR) # Prevent logging to stdout which breaks JSON-RPC
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            handle_request(req)
        except json.JSONDecodeError:
            send_response({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}})

if __name__ == "__main__":
    main()
