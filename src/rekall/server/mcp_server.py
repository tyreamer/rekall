import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from rekall.core.state_store import StateStore

logger = logging.getLogger(__name__)

_store: Optional[StateStore] = None


def get_store() -> StateStore:
    global _store
    if _store is None:
        default_artifact = (
            Path(__file__).parent.parent.parent.parent
            / "examples"
            / "sample_state_artifact"
        )
        artifact_path = os.getenv("REKALL_ARTIFACT_PATH", str(default_artifact))
        _store = StateStore(Path(artifact_path))
    return _store


def _paginate(
    items: List[Dict[str, Any]], limit: int, offset: int = 0
) -> Dict[str, Any]:
    paginated = items[offset : offset + limit]
    res: Dict[str, Any] = {"items": paginated}
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
        "updated_at": cfg.get("updated_at"),
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


def project_init(args: dict) -> list:
    store = get_store()
    import datetime

    from rekall.cli import build_guard_payload
    from rekall.core.executive_queries import ExecutiveQueryType, query_executive_status

    try:
        repo_name = store.project_config.get("project_id", store.base_dir.parent.name)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        last_updated = "Never"
        timeline_events = store._load_jsonl("timeline.jsonl")
        if timeline_events:
            last_event = max(timeline_events, key=lambda x: x.get("timestamp", ""))
            last_updated = last_event.get("timestamp", "Unknown")

        status_resp = query_executive_status(store, ExecutiveQueryType.ON_TRACK)
        blockers_resp = query_executive_status(store, ExecutiveQueryType.BLOCKERS)
        guard_payload = build_guard_payload(store)

        lines = []
        lines.append(f"# Onboarding Cheat Sheet: {repo_name}")
        lines.append(f"**Generated**: {timestamp}")
        lines.append(f"**execution ledger Last Updated**: {last_updated}")
        lines.append("")

        lines.append("## What is Rekall?")
        lines.append(
            "Rekall is a project state execution ledger for AI agents and human collaborators."
        )
        lines.append(
            "It tracks decisions, attempts, and work items as a machine-readable event stream."
        )
        lines.append("")

        lines.append("## Project Reality Snapshot")
        if status_resp.summary:
            for s in status_resp.summary:
                lines.append(f"- {s}")
        lines.append(f"- **Total Work Items**: {len(status_resp.work_items)}")
        lines.append("")

        lines.append("## Risks / Unknowns")
        risks = guard_payload.get("risks_blockers", [])
        if risks:
            for r in risks[:5]:
                lines.append(f"- [{r['work_item_id']}] {r['title']} ({r['status']})")
        else:
            lines.append("No critical risks identified by guard.")
        lines.append("")

        lines.append("## Blockers")
        if blockers_resp.blockers:
            for b in blockers_resp.blockers:
                wid = b.get("work_item_id")
                title = b.get("title", "Untitled")
                lines.append(f"- **{wid}**: {title}")
        else:
            lines.append("No blockers detected.")
        lines.append("")

        lines.append("## State Artifact Layout")
        lines.append("```text")
        lines.append(f"{store.base_dir.name}/")
        lines.append(
            "\u251c\u2500\u2500 project.yaml          # Project identity & goals"
        )
        lines.append(
            "\u251c\u2500\u2500 work-items.jsonl      # Mutable work state execution ledger"
        )
        lines.append("\u251c\u2500\u2500 decisions.jsonl       # Architectural choices")
        lines.append(
            "\u251c\u2500\u2500 attempts.jsonl        # History of what failed"
        )
        lines.append(
            "\u2514\u2500\u2500 artifacts/            # Generated summaries & briefs"
        )
        lines.append("```")
        lines.append("")

        lines.append("## How to update state")
        lines.append("If you try something and fail, add an attempt:")
        lines.append(
            '`rekall attempts add REQ-1 --title "Tried changing font size" --evidence "UI broke"`'
        )
        lines.append("If you make an architectural choice, propose a decision:")
        lines.append(
            '`rekall decisions propose --title "Use Postgres" --rationale "Need relational data" --tradeoffs "Heavier than SQLite"`'
        )
        lines.append("")

        lines.append("## Next Recommended Commands")
        lines.append("```bash")
        lines.append("rekall status")
        lines.append("rekall guard")
        lines.append("rekall blockers")
        lines.append(
            f"rekall handoff {store.project_config.get('project_id', repo_name)} -o ./handoff/"
        )
        lines.append("```")
        lines.append("")

        lines.append("## Links")
        lines.append(
            "- [Quickstart Guide](https://github.com/run-rekall/rekall#quick-start-for-humans--agents)"
        )
        lines.append(
            "- [BETA.md](https://github.com/run-rekall/rekall/blob/main/docs/BETA.md)"
        )
        lines.append(
            "- [GitHub Discussions](https://github.com/run-rekall/rekall/discussions)"
        )

        content = "\n".join(lines)

        artifacts_dir = store.base_dir / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)
        out_path = artifacts_dir / "init_cheatsheet.md"
        out_path.write_text(content, encoding="utf-8")

        return [{"status": "success", "path": str(out_path), "content": content}]
    except Exception as e:
        return [{"error": {"code": "INTERNAL_ERROR", "message": str(e)}}]


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
        if status and item.get("status") not in status:
            continue
        if type_filter and item.get("type") not in type_filter:
            continue
        if priority and item.get("priority") not in priority:
            continue
        if owner and item.get("owner") != owner:
            continue

        summary = {
            "work_item_id": item.get("work_item_id"),
            "type": item.get("type"),
            "title": item.get("title"),
            "status": item.get("status"),
            "priority": item.get("priority"),
            "owner": item.get("owner"),
            "claim": item.get("claim"),
            "version": item.get("version"),
            "updated_at": item.get("updated_at"),
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
        id_val = (
            r.get("attempt_id")
            or r.get("decision_id")
            or r.get("event_id")
            or r.get("activity_id")
            or ""
        )
        return (ts, id_val)

    records.sort(key=sort_key)
    return [_paginate(records, limit, offset)]


def attempt_list(args: dict) -> list:
    return _list_log("attempts.jsonl", args)


def decision_list(args: dict) -> list:
    return _list_log("decisions.jsonl", args)


def timeline_list(args: dict) -> list:
    return _list_log("timeline.jsonl", args)


def activity_list(args: dict) -> list:
    return _list_log("activity.jsonl", args)


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
        raise ValueError(
            "work_item_id, expected_version, patch, and actor are required"
        )
    store = get_store()
    try:
        updated = store.update_work_item(
            cast(str, work_item_id), cast(Dict[str, Any], patch), cast(int, expected_version), cast(Dict[str, Any], actor), force=bool(force), reason=cast(Optional[str], reason)
        )
        return [{"work_item": updated}]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        if "Version mismatch" in str(e):
            err_code = "CONFLICT"
        elif "claimed by" in str(e):
            err_code = "FORBIDDEN"
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
        updated = store.claim_work_item(
            cast(str, work_item_id), cast(int, expected_version), cast(Dict[str, Any], actor), cast(int, lease_seconds), bool(force), cast(Optional[str], reason)
        )
        return [{"work_item": updated}]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        if "Version mismatch" in str(e):
            err_code = "CONFLICT"
        elif "currently claimed" in str(e):
            err_code = "FORBIDDEN"
        return [{"error": {"code": err_code, "message": str(e)}}]


def work_renew_claim(args: dict) -> list:
    work_item_id = args.get("work_item_id")
    expected_version = args.get("expected_version")
    actor = args.get("actor")
    lease_seconds = args.get("lease_seconds", 1800)
    reason = args.get("reason")
    store = get_store()
    try:
        updated = store.renew_claim(
            cast(str, work_item_id), cast(int, expected_version), cast(Dict[str, Any], actor), cast(int, lease_seconds), cast(Optional[str], reason)
        )
        return [{"work_item": updated}]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        if "Version mismatch" in str(e):
            err_code = "CONFLICT"
        elif "do not hold" in str(e):
            err_code = "FORBIDDEN"
        return [{"error": {"code": err_code, "message": str(e)}}]


def work_release_claim(args: dict) -> list:
    work_item_id = args.get("work_item_id")
    expected_version = args.get("expected_version")
    actor = args.get("actor")
    force = args.get("force", False)
    reason = args.get("reason")
    store = get_store()
    try:
        updated = store.release_claim(
            cast(str, work_item_id), cast(int, expected_version), cast(Dict[str, Any], actor), bool(force), cast(Optional[str], reason)
        )
        return [{"work_item": updated}]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        if "Version mismatch" in str(e):
            err_code = "CONFLICT"
        elif "do not hold" in str(e):
            err_code = "FORBIDDEN"
        return [{"error": {"code": err_code, "message": str(e)}}]


def attempt_append(args: dict) -> list:
    project_id = args.get("project_id")
    attempt = args.get("attempt")
    actor = args.get("actor")
    reason = args.get("reason")
    idempotency_key = args.get("idempotency_key")
    if not project_id or not attempt or not actor:
        raise ValueError("project_id, attempt, and actor are required")
    store = get_store()
    try:
        updated = store.append_attempt(
            attempt, actor, reason=reason, idempotency_key=idempotency_key
        )
        return [{"attempt": updated}]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        if "Secret detected" in str(e):
            err_code = "SECRET_DETECTED"
        return [{"error": {"code": err_code, "message": str(e)}}]


def decision_propose(args: dict) -> list:
    project_id = args.get("project_id")
    decision = args.get("decision")
    actor = args.get("actor")
    reason = args.get("reason")
    idempotency_key = args.get("idempotency_key")
    if not project_id or not decision or not actor:
        raise ValueError("project_id, decision, and actor are required")
    store = get_store()
    try:
        updated = store.propose_decision(
            decision, actor, reason=reason, idempotency_key=idempotency_key
        )
        return [{"decision": updated}]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        if "Secret detected" in str(e):
            err_code = "SECRET_DETECTED"
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
        if "lacks" in str(e).lower() or "capability" in str(e).lower():
            err_code = "FORBIDDEN"
        return [{"error": {"code": err_code, "message": str(e)}}]


def timeline_append(args: dict) -> list:
    project_id = args.get("project_id")
    event = args.get("event")
    actor = args.get("actor")
    reason = args.get("reason")
    idempotency_key = args.get("idempotency_key")
    if not project_id or not event or not actor:
        raise ValueError("project_id, event, and actor are required")
    store = get_store()
    try:
        updated = store.append_timeline(
            event, actor, reason=reason, idempotency_key=idempotency_key
        )
        return [{"event": updated}]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        if "Secret detected" in str(e):
            err_code = "SECRET_DETECTED"
        return [{"error": {"code": err_code, "message": str(e)}}]


def exec_query(args: dict) -> list:
    project_id = args.get("project_id")
    query_type = args.get("query_type")
    since = args.get("since")

    if not project_id or not query_type:
        raise ValueError("project_id and query_type are required")

    store = get_store()
    # The original line `work_items = list(store.work_items.values())` was not used in the original exec_query logic.
    # The provided change redefines exec_query, so I'm using the new definition.
    import dataclasses

    from rekall.core.executive_queries import ExecutiveQueryType, query_executive_status

    try:
        q_type = ExecutiveQueryType(query_type)
        resp = query_executive_status(store, q_type, since)
        return [{"executive_response": dataclasses.asdict(resp)}]
    except ValueError as e:
        return [{"error": {"code": "VALIDATION_ERROR", "message": str(e)}}]


def artifact_append(args: dict) -> list:
    project_id = args.get("project_id")
    artifact = args.get("artifact")
    actor = args.get("actor")
    reason = args.get("reason")
    idempotency_key = args.get("idempotency_key")
    if not project_id or not artifact or not actor:
        raise ValueError("project_id, artifact, and actor are required")
    store = get_store()
    try:
        updated = store.append_artifact(
            artifact, actor, reason=reason, idempotency_key=idempotency_key
        )
        return [{"artifact": updated}]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        if "Secret detected" in str(e):
            err_code = "SECRET_DETECTED"
        return [{"error": {"code": err_code, "message": str(e)}}]


def research_append(args: dict) -> list:
    project_id = args.get("project_id")
    research = args.get("research")
    actor = args.get("actor")
    reason = args.get("reason")
    idempotency_key = args.get("idempotency_key")
    if not project_id or not research or not actor:
        raise ValueError("project_id, research, and actor are required")
    store = get_store()
    try:
        updated = store.append_research(
            research, actor, reason=reason, idempotency_key=idempotency_key
        )
        return [{"research": updated}]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        if "Secret detected" in str(e):
            err_code = "SECRET_DETECTED"
        return [{"error": {"code": err_code, "message": str(e)}}]


def link_append(args: dict) -> list:
    project_id = args.get("project_id")
    link = args.get("link")
    actor = args.get("actor")
    reason = args.get("reason")
    idempotency_key = args.get("idempotency_key")
    if not project_id or not link or not actor:
        raise ValueError("project_id, link, and actor are required")
    store = get_store()
    try:
        updated = store.append_link(
            link, actor, reason=reason, idempotency_key=idempotency_key
        )
        return [{"link": updated}]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        if "Secret detected" in str(e):
            err_code = "SECRET_DETECTED"
        return [{"error": {"code": err_code, "message": str(e)}}]


def anchor_save(args: dict) -> list:
    project_id = args.get("project_id")
    anchor = args.get("anchor")
    actor = args.get("actor")
    reason = args.get("reason")
    idempotency_key = args.get("idempotency_key")
    if not project_id or not anchor or not actor:
        raise ValueError("project_id, anchor, and actor are required")
    store = get_store()
    try:
        updated = store.save_anchor(
            anchor, actor, reason=reason, idempotency_key=idempotency_key
        )
        return [{"anchor": updated}]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        if "Secret detected" in str(e):
            err_code = "SECRET_DETECTED"
        return [{"error": {"code": err_code, "message": str(e)}}]


def anchor_resume(args: dict) -> list:
    project_id = args.get("project_id")
    anchor_id = args.get("anchor_id")
    if not project_id:
        raise ValueError("project_id is required")
    store = get_store()
    try:
        res = store.resume_anchor(anchor_id)
        if "error" in res:
            return [{"error": {"code": "NOT_FOUND", "message": res["error"]}}]
        return [res]
    except Exception as e:
        return [{"error": {"code": "VALIDATION_ERROR", "message": str(e)}}]


def digest_while_you_were_gone(args: dict) -> list:
    project_id = args.get("project_id")
    since = args.get("since")
    limit = args.get("limit", 25)
    if not project_id:
        raise ValueError("project_id is required")
    store = get_store()
    try:
        res = store.digest_while_you_were_gone(since=since, limit=limit)
        return [res]
    except Exception as e:
        return [{"error": {"code": "VALIDATION_ERROR", "message": str(e)}}]


def graph_trace(args: dict) -> list:
    project_id = args.get("project_id")
    root = args.get("root")
    depth = args.get("depth", 2)
    include_bundles = args.get("include_bundles", True)
    if not project_id or not root:
        raise ValueError("project_id and root are required")
    store = get_store()
    try:
        res = store.trace_graph(root=root, depth=depth, include_bundles=include_bundles)
        if "error" in res:
            return [{"error": {"code": "NOT_FOUND", "message": res["error"]}}]
        return [res]
    except Exception as e:
        return [{"error": {"code": "VALIDATION_ERROR", "message": str(e)}}]

def policy_preflight(args: dict) -> list:
    project_id = args.get("project_id")
    action_type = args.get("action_type")
    params = args.get("params", {})
    context = args.get("context", {})
    if not project_id or not action_type:
        raise ValueError("project_id and action_type are required")
    store = get_store()
    try:
        res = store.check_policy(action_type, params, context)
        return [res]
    except Exception as e:
        return [{"error": {"code": "VALIDATION_ERROR", "message": str(e)}}]

def exec_natural_query(args: dict) -> list:
    """Unified dispatcher for exec.query. Supports both canonical types and natural language."""
    project_id = args.get("project_id")
    query_type = args.get("query_type")
    query = args.get("query")
    since = args.get("since")

    if not project_id:
        raise ValueError("project_id is required")

    store = get_store()

    # 1. Dispatch to Canonical if query_type is provided
    if query_type:
        import dataclasses

        from rekall.core.executive_queries import (
            ExecutiveQueryType,
            query_executive_status,
        )
        try:
            q_type = ExecutiveQueryType(query_type)
            resp = query_executive_status(store, q_type, since)
            return [{"executive_response": dataclasses.asdict(resp)}]
        except Exception as e:
            return [{"error": {"code": "VALIDATION_ERROR", "message": f"Canonical query failed: {e}"}}]

    # 2. Natural Language context generation
    if query:
        try:
            # Load the critical ledger streams
            timeline = store._load_stream("timeline.jsonl") or []
            attempts = store._load_stream("attempts.jsonl") or []
            decisions = store._load_stream("decisions.jsonl") or []

            # Format the ledger for the LLM
            ledger_text = []
            ledger_text.append(f"====== PROJECT EXECUTION LEDGER for {project_id} ======")

            ledger_text.append("\n--- TIMELINE EVENTS ---")
            for t in timeline[-25:]:
                ledger_text.append(json.dumps(t))

            ledger_text.append("\n--- RECENT ATTEMPTS ---")
            for a in attempts[-25:]:
                ledger_text.append(json.dumps(a))

            ledger_text.append("\n--- RECENT DECISIONS ---")
            for d in decisions[-25:]:
                ledger_text.append(json.dumps(d))

            system_instruction = f"""
You are answering the user's query: "{query}"

Use the execution ledger provided above to formulate your answer.
RULES:
1. You MUST cite exact event IDs (e.g., attempt_id, decision_id, event_id) for every claim you make.
2. If the evidence is missing from the ledger, explicitly state: "Evidence missing. A log entry for X is required."
3. Do not invent or hallucinate events.
"""
            return [{"text": "\n".join(ledger_text) + "\n\n" + system_instruction}]
        except Exception as e:
            return [{"error": {"code": "VALIDATION_ERROR", "message": f"Natural query generation failed: {e}"}}]

    # 3. Default: Return project status if no type/query
    from rekall.cli import build_guard_payload
    payload = build_guard_payload(store)
    return [{"ok": True, "message": "Specify query_type or query for detailed info.", "status": payload.get("project", {}).get("status")}]


def propose_action(args: dict) -> list:
    project_id = args.get("project_id")
    action_type = args.get("action_type")
    params = args.get("params", {})
    risk_hint = args.get("risk_hint", "")
    context = args.get("context", {})
    actor = args.get("actor")
    reason = args.get("reason")
    idempotency_key = args.get("idempotency_key")
    if not project_id or not action_type or not actor:
        raise ValueError("project_id, action_type, and actor are required")
    store = get_store()
    try:
        updated = store.propose_action(
            action_type, params, risk_hint, context, actor, reason=reason, idempotency_key=idempotency_key
        )
        return [{"action_id": updated["action_id"], "action_hash": updated["action_hash"]}]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        if "Secret detected" in str(e):
            err_code = "SECRET_DETECTED"
        return [{"error": {"code": err_code, "message": str(e)}}]

def capture_approval(args: dict) -> list:
    project_id = args.get("project_id")
    decision_id = args.get("decision_id")
    action_id = args.get("action_id")
    decision = args.get("decision")
    note = args.get("note", "")
    actor_metadata = args.get("actor_metadata")
    actor = args.get("actor") or actor_metadata
    reason = args.get("reason")
    idempotency_key = args.get("idempotency_key")
    if not project_id or not decision_id or not decision or not actor:
        raise ValueError("project_id, decision_id, decision, and actor are required")
    store = get_store()
    try:
        updated = store.capture_approval(
            decision_id, decision, action_id=action_id, note=note, actor=actor, reason=reason, idempotency_key=idempotency_key
        )
        return [updated]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        return [{"error": {"code": err_code, "message": str(e)}}]

def wait_for_approval(args: dict) -> list:
    project_id = args.get("project_id")
    decision_id = args.get("decision_id")
    prompt = args.get("prompt", "Human approval required.")
    options = args.get("options", ["approve", "reject"])
    action_id = args.get("action_id")
    actor = args.get("actor")
    reason = args.get("reason")
    idempotency_key = args.get("idempotency_key")
    if not project_id or not decision_id or not actor:
        raise ValueError("project_id, decision_id, and actor are required")
    store = get_store()
    try:
        updated = store.wait_for_approval(
            decision_id, prompt, options, actor=actor, action_id=action_id, reason=reason, idempotency_key=idempotency_key
        )
        return [updated]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        return [{"error": {"code": err_code, "message": str(e)}}]

def capture_outcome(args: dict) -> list:
    project_id = args.get("project_id")
    action_id = args.get("action_id")
    outcome_metadata = args.get("outcome_metadata", {})
    actor = args.get("actor")
    reason = args.get("reason")
    idempotency_key = args.get("idempotency_key")
    if not project_id or not action_id or not actor:
        raise ValueError("project_id, action_id, and actor are required")
    store = get_store()
    try:
        updated = store.capture_outcome(
            action_id, outcome_metadata, actor, reason=reason, idempotency_key=idempotency_key
        )
        return [updated]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        if "Secret detected" in str(e):
            err_code = "SECRET_DETECTED"
        return [{"error": {"code": err_code, "message": str(e)}}]

def actuate_cli(args: dict) -> list:
    project_id = args.get("project_id")
    action_id = args.get("action_id")
    command = args.get("command")
    cwd = args.get("cwd", ".")
    actor = args.get("actor")

    if not project_id or not action_id or not command or not actor:
        raise ValueError("project_id, action_id, command, and actor are required")

    import subprocess
    import traceback

    store = get_store()
    try:
        result = subprocess.run(command, cwd=cwd, shell=True, capture_output=True, text=True, timeout=120)
        outcome_metadata = {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "success": result.returncode == 0
        }
    except Exception as e:
        outcome_metadata = {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "success": False
        }

    try:
        updated = store.capture_outcome(action_id, outcome_metadata, actor)
        return [{"status": "success" if outcome_metadata["success"] else "failed", "outcome": outcome_metadata, "record": updated}]
    except Exception as e:
        return [{"error": {"code": "VALIDATION_ERROR", "message": f"Failed to record outcome: {e}", "outcome": outcome_metadata}}]

def actuate_file_write(args: dict) -> list:
    project_id = args.get("project_id")
    action_id = args.get("action_id")
    file_path = args.get("file_path")
    content = args.get("content", "")
    actor = args.get("actor")

    if not project_id or not action_id or not file_path or not actor:
        raise ValueError("project_id, action_id, file_path, and actor are required")

    store = get_store()
    from pathlib import Path

    try:
        p = Path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        outcome_metadata = {
            "file_path": str(p),
            "bytes_written": len(content.encode("utf-8")),
            "success": True
        }
    except Exception as e:
        import traceback
        outcome_metadata = {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "success": False
        }

    try:
        updated = store.capture_outcome(action_id, outcome_metadata, actor)
        return [{"status": "success" if outcome_metadata["success"] else "failed", "outcome": outcome_metadata, "record": updated}]
    except Exception as e:
        return [{"error": {"code": "VALIDATION_ERROR", "message": f"Failed to record outcome: {e}", "outcome": outcome_metadata}}]

def guard_query(args: dict) -> list:
    """Read-only preflight guard query returning the same payload as `rekall guard --json`."""
    project_id = args.get(
        "project_id"
    )  # Added project_id for consistency with other tools
    if not project_id:
        raise ValueError("project_id is required")
    store = get_store()
    from rekall.cli import build_guard_payload

    payload = build_guard_payload(store)
    return [{"ok": True, "guard": "PASS", **payload}]


# --- MCP JSON-RPC Server Core ---

TOOLS_DEF = [
    {
        "name": "project.list",
        "description": "List projects visible to caller.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
                "cursor": {"type": "string"},
                "tag": {"type": "string"},
                "updated_since": {"type": "string"},
            },
        },
    },
    {
        "name": "project.get",
        "description": "Get a project's canonical metadata.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {
                "project_id": {"type": "string"},
                "include": {"type": "array"},
            },
        },
    },
    {
        "name": "project.init",
        "description": "Generate an initialization cheat sheet for the project and return it as markdown.",
        "inputSchema": {"type": "object", "properties": {}},
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
                "updated_since": {"type": "string"},
            },
        },
    },
    {
        "name": "work.get",
        "description": "Get a specific work item's details.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "work_item_id"],
            "properties": {
                "project_id": {"type": "string"},
                "work_item_id": {"type": "string"},
                "include": {"type": "array"},
            },
        },
    },
    {
        "name": "attempt.list",
        "description": "List attempts.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {
                "project_id": {"type": "string"},
                "limit": {"type": "integer"},
                "cursor": {"type": "string"},
                "since": {"type": "string"},
            },
        },
    },
    {
        "name": "decision.list",
        "description": "List decisions.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {
                "project_id": {"type": "string"},
                "limit": {"type": "integer"},
                "cursor": {"type": "string"},
                "status": {"type": "array"},
                "since": {"type": "string"},
            },
        },
    },
    {
        "name": "timeline.list",
        "description": "List timeline events.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {
                "project_id": {"type": "string"},
                "limit": {"type": "integer"},
                "cursor": {"type": "string"},
                "since": {"type": "string"},
            },
        },
    },
    {
        "name": "activity.list",
        "description": "List activity/audit events.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {
                "project_id": {"type": "string"},
                "limit": {"type": "integer"},
                "cursor": {"type": "string"},
                "since": {"type": "string"},
            },
        },
    },
    {
        "name": "env.list",
        "description": "List environments.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {
                "project_id": {"type": "string"},
                "limit": {"type": "integer"},
                "cursor": {"type": "string"},
            },
        },
    },
    {
        "name": "access.list",
        "description": "List access references.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {
                "project_id": {"type": "string"},
                "limit": {"type": "integer"},
                "cursor": {"type": "string"},
            },
        },
    },
    {
        "name": "work.create",
        "description": "Create a new work item.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "work_item", "actor"],
            "properties": {
                "project_id": {"type": "string"},
                "work_item": {"type": "object"},
                "actor": {"type": "object"},
                "reason": {"type": "string"},
            },
        },
    },
    {
        "name": "work.update",
        "description": "Update a work item.",
        "inputSchema": {
            "type": "object",
            "required": [
                "project_id",
                "work_item_id",
                "expected_version",
                "patch",
                "actor",
            ],
            "properties": {
                "project_id": {"type": "string"},
                "work_item_id": {"type": "string"},
                "expected_version": {"type": "integer"},
                "patch": {"type": "object"},
                "actor": {"type": "object"},
                "force": {"type": "boolean"},
                "reason": {"type": "string"},
            },
        },
    },
    {
        "name": "work.claim",
        "description": "Claim a work item with a lease.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "work_item_id", "expected_version", "actor"],
            "properties": {
                "project_id": {"type": "string"},
                "work_item_id": {"type": "string"},
                "expected_version": {"type": "integer"},
                "actor": {"type": "object"},
                "lease_seconds": {"type": "integer"},
                "force": {"type": "boolean"},
                "reason": {"type": "string"},
            },
        },
    },
    {
        "name": "work.renew_claim",
        "description": "Renew a claim.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "work_item_id", "expected_version", "actor"],
            "properties": {
                "project_id": {"type": "string"},
                "work_item_id": {"type": "string"},
                "expected_version": {"type": "integer"},
                "actor": {"type": "object"},
                "lease_seconds": {"type": "integer"},
                "reason": {"type": "string"},
            },
        },
    },
    {
        "name": "work.release_claim",
        "description": "Release a claim.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "work_item_id", "expected_version", "actor"],
            "properties": {
                "project_id": {"type": "string"},
                "work_item_id": {"type": "string"},
                "expected_version": {"type": "integer"},
                "actor": {"type": "object"},
                "force": {"type": "boolean"},
                "reason": {"type": "string"},
            },
        },
    },
    {
        "name": "attempt.append",
        "description": "Append an attempt note.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "attempt", "actor"],
            "properties": {
                "project_id": {"type": "string"},
                "attempt": {"type": "object"},
                "actor": {"type": "object"},
                "reason": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
        },
    },
    {
        "name": "decision.propose",
        "description": "Propose a decision log.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "decision", "actor"],
            "properties": {
                "project_id": {"type": "string"},
                "decision": {"type": "object"},
                "actor": {"type": "object"},
                "reason": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
        },
    },
    {
        "name": "decision.approve",
        "description": "Approve a decision.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "decision_id", "actor"],
            "properties": {
                "project_id": {"type": "string"},
                "decision_id": {"type": "string"},
                "actor": {"type": "object"},
                "reason": {"type": "string"},
            },
        },
    },
    {
        "name": "timeline.append",
        "description": "Append a timeline event.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "event", "actor"],
            "properties": {
                "project_id": {"type": "string"},
                "event": {"type": "object"},
                "actor": {"type": "object"},
                "reason": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
        },
    },
    {
        "name": "exec.query",
        "description": "DEPRECATED in favor of unified query tool below.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {"project_id": {"type": "string"}},
        },
    },
    {
        "name": "guard.query",
        "description": "Preflight drift guard. Returns project constraints, recent decisions, recent attempts, risks/blockers, and environment pointers. Read-only.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {"project_id": {"type": "string"}},
        },
    },
    {
        "name": "artifact.append",
        "description": "Append an artifact record.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "artifact", "actor"],
            "properties": {
                "project_id": {"type": "string"},
                "artifact": {"type": "object"},
                "actor": {"type": "object"},
                "reason": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
        },
    },
    {
        "name": "research.append",
        "description": "Append a research item record.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "research", "actor"],
            "properties": {
                "project_id": {"type": "string"},
                "research": {"type": "object"},
                "actor": {"type": "object"},
                "reason": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
        },
    },
    {
        "name": "link.append",
        "description": "Append a link edge record.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "link", "actor"],
            "properties": {
                "project_id": {"type": "string"},
                "link": {"type": "object"},
                "actor": {"type": "object"},
                "reason": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
        },
    },
    {
        "name": "anchor.save",
        "description": "Save an intent checkpoint anchor.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "anchor", "actor"],
            "properties": {
                "project_id": {"type": "string"},
                "anchor": {"type": "object"},
                "actor": {"type": "object"},
                "reason": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
        },
    },
    {
        "name": "anchor.resume",
        "description": "Resume an intent checkpoint anchor context.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {
                "project_id": {"type": "string"},
                "anchor_id": {"type": "string"},
            },
        },
    },
    {
        "name": "digest.while_you_were_gone",
        "description": "Get a digest of recent activity.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {
                "project_id": {"type": "string"},
                "since": {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "graph.trace",
        "description": "Trace a provenance graph from a root node.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "root"],
            "properties": {
                "project_id": {"type": "string"},
                "root": {"type": "object"},
                "depth": {"type": "integer"},
                "include_bundles": {"type": "boolean"},
            },
        },
    },
    {
        "name": "policy.preflight",
        "description": "Preflight check for an action against current policies (shadow mode).",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "action_type"],
            "properties": {
                "project_id": {"type": "string"},
                "action_type": {"type": "string"},
                "params": {"type": "object"},
                "context": {"type": "object"},
            },
        },
    },
    {
        "name": "propose_action",
        "description": "Propose an action before executing it to record intent and a deterministic action hash.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "action_type", "actor"],
            "properties": {
                "project_id": {"type": "string"},
                "action_type": {"type": "string"},
                "params": {"type": "object"},
                "risk_hint": {"type": "string"},
                "context": {"type": "object"},
                "actor": {"type": "object"},
                "reason": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
        },
    },
    {
        "name": "capture_approval",
        "description": "Capture human or agent approval/rejection for an action or decision.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "decision_id", "decision", "actor"],
            "properties": {
                "project_id": {"type": "string"},
                "decision_id": {"type": "string"},
                "action_id": {"type": "string"},
                "decision": {"type": "string"},
                "note": {"type": "string"},
                "actor": {"type": "object"},
                "actor_metadata": {"type": "object"},
                "reason": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
        },
    },
    {
        "name": "wait_for_approval",
        "description": "Signal that the agent is pausing and waiting for a human to approve an action or decision. Returns a PAUSE_AND_EXIT instruction.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "decision_id", "actor"],
            "properties": {
                "project_id": {"type": "string"},
                "decision_id": {"type": "string"},
                "action_id": {"type": "string"},
                "prompt": {"type": "string"},
                "options": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "actor": {"type": "object"},
                "reason": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
        },
    },
    {
        "name": "capture_outcome",
        "description": "Capture the result metadata of an executed action.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "action_id", "actor"],
            "properties": {
                "project_id": {"type": "string"},
                "action_id": {"type": "string"},
                "outcome_metadata": {"type": "object"},
                "actor": {"type": "object"},
                "reason": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
        },
    },
    {
        "name": "actuate_cli",
        "description": "A wrapped actuator to execute a shell command and capture its outcome automatically.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "action_id", "command", "actor"],
            "properties": {
                "project_id": {"type": "string"},
                "action_id": {"type": "string"},
                "command": {"type": "string"},
                "cwd": {"type": "string"},
                "actor": {"type": "object"},
            },
        },
    },
    {
        "name": "actuate_file_write",
        "description": "A wrapped actuator to write a file and capture its outcome automatically.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "action_id", "file_path", "actor"],
            "properties": {
                "project_id": {"type": "string"},
                "action_id": {"type": "string"},
                "file_path": {"type": "string"},
                "content": {"type": "string"},
                "actor": {"type": "object"},
            },
        },
    },
    {
        "name": "exec.query",
        "description": "Query the execution ledger. Returns canonical results if query_type is provided, or natural language insights if query is provided.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {
                "project_id": {"type": "string"},
                "query_type": {
                    "type": "string",
                    "enum": [
                        "ON_TRACK",
                        "BLOCKERS",
                        "CHANGED_SINCE",
                        "NEXT_7_DAYS",
                        "RECENT_DECISIONS",
                        "FAILED_ATTEMPTS",
                        "WHERE_RUNNING_ACCESS",
                        "RESUME_IN_30",
                    ],
                },
                "query": {"type": "string", "description": "Natural language question"},
                "since": {"type": "string", "description": "ISO timestamp for CHANGED_SINCE"},
            },
        },
    },
]

TOOL_REGISTRY = {
    "project.list": project_list,
    "project.get": project_get,
    "project.init": project_init,
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
    "exec.query": exec_natural_query,  # Prefer natural query if possible, or dispatcher
    "guard.query": guard_query,
    "artifact.append": artifact_append,
    "research.append": research_append,
    "link.append": link_append,
    "anchor.save": anchor_save,
    "anchor.resume": anchor_resume,
    "digest.while_you_were_gone": digest_while_you_were_gone,
    "graph.trace": graph_trace,
    "policy.preflight": policy_preflight,
    "propose_action": propose_action,
    "wait_for_approval": wait_for_approval,
    "capture_approval": capture_approval,
    "capture_outcome": capture_outcome,
    "actuate_cli": actuate_cli,
    "actuate_file_write": actuate_file_write,
}


def send_response(response: dict):
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


def handle_request(req: dict):
    method = req.get("method")
    req_id = req.get("id")

    try:
        if method == "initialize":
            send_response(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",  # MCP standard version
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "rekall-mcp", "version": "0.1.0"},
                    },
                }
            )
        elif method == "tools/list":
            send_response(
                {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS_DEF}}
            )
        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})

            if name in TOOL_REGISTRY:
                try:
                    result_data = TOOL_REGISTRY[name](args)
                    is_error = False

                    # 1. Check if the tool returned an error object
                    if (
                        len(result_data) == 1
                        and isinstance(result_data[0], dict)
                        and "error" in result_data[0]
                    ):
                        is_error = True
                        err_obj = result_data[0]["error"]
                        response_text = json.dumps(err_obj, indent=2)
                    else:
                        # 2. Extract text if present, otherwise dump JSON
                        first = result_data[0] if result_data else {}
                        if isinstance(first, dict) and "text" in first:
                            response_text = str(first["text"])
                        elif isinstance(first, dict) and "executive_response" in first:
                            # Special handling for executive responses to make them readable
                            response_text = json.dumps(first["executive_response"], indent=2)
                        else:
                            response_text = json.dumps(first, indent=2)

                    send_response(
                        {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {
                                "content": [{"type": "text", "text": response_text}],
                                "isError": is_error,
                            },
                        }
                    )
                except Exception as e:
                    import traceback
                    tb = traceback.format_exc()
                    logger.error(f"Tool execution failed: {tb}")
                    # Print to stderr for visibility in Claude dashboard
                    print(f"ERROR: {tb}", file=sys.stderr)

                    send_response(
                        {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {
                                "content": [
                                    {
                                        "type": "text",
                                        "text": f"Error executing tool '{name}': {str(e)}\n\n{tb}"
                                    }
                                ],
                                "isError": True,
                            },
                        }
                    )
            else:
                send_response(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32601, "message": f"Tool not found: {name}"},
                    }
                )
        else:
            if req_id is not None:
                send_response(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32601, "message": "Method not found"},
                    }
                )
    except Exception as e:
        if req_id is not None:
            send_response(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32603, "message": str(e)},
                }
            )


def main():
    logger.setLevel(logging.ERROR)  # Prevent logging to stdout which breaks JSON-RPC
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            handle_request(req)
        except json.JSONDecodeError:
            send_response(
                {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}}
            )


if __name__ == "__main__":
    main()
