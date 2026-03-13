import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from rekall.core.state_store import StateStore

logger = logging.getLogger(__name__)

_base_dir: Optional[Path] = None
_store: Optional[StateStore] = None
_session_briefed: bool = False  # Session gate: has the agent seen the brief?


def get_store() -> StateStore:
    global _store, _base_dir
    if _store is None:
        if _base_dir is None:
            # Fallback for direct import/test
            from rekall.core.state_store import resolve_vault_dir
            _base_dir = resolve_vault_dir()

        if not (_base_dir / "manifest.json").exists():
             raise ValueError("Rekall vault not initialized. Call project.bootstrap first.")

        _store = StateStore(_base_dir)
    return _store


def project_bootstrap(args: dict) -> list:
    """Zero-setup path: ensures vault exists and metadata is set."""
    global _base_dir, _store
    if _base_dir is None:
        from rekall.core.state_store import resolve_vault_dir
        _base_dir = resolve_vault_dir()

    from rekall.cli import ensure_state_initialized
    ensure_state_initialized(_base_dir, is_json=True, init_mode=True)

    # Now we can safely create the store
    _store = StateStore(_base_dir)

    # Optionally set metadata
    patch = {}
    if "goal" in args:
        patch["goal"] = args["goal"]
    if "phase" in args:
        patch["phase"] = args["phase"]
    if "status" in args:
        patch["status"] = args["status"]
    if "confidence" in args:
        patch["confidence"] = args["confidence"]

    actor = args.get("actor", {"actor_id": "agent_bootstrap"})
    if patch:
        _store.patch_project_meta(patch, actor=actor)

    meta = _store.get_project_meta()

    # Include full session brief so agents get immediate working context
    from rekall.core.brief import generate_session_brief
    brief = generate_session_brief(_store)

    out = {
        "status": "success",
        "message": "Project bootstrapped successfully.",
        "vault_path": str(_base_dir),
        "metadata": meta,
        "session_brief": brief,
    }

    if brief.get("drift_warning"):
        out["drift_warning"] = brief["drift_warning"]

    return [out]

def project_meta_get(args: dict) -> list:
    store = get_store()
    return [{"metadata": store.get_project_meta()}]


def project_meta_patch(args: dict) -> list:
    store = get_store()
    patch = args.get("patch", {})
    actor = args.get("actor", {"actor_id": "agent_meta_patch"})
    idemp = args.get("idempotency_key")

    res = store.patch_project_meta(patch, actor=actor, idempotency_key=idemp)
    return [{"metadata": res}]


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
        drift = store.check_drift()
        if drift:
            updated["drift_warning"] = drift

        import subprocess
        timeline = store._load_stream_raw("timeline.jsonl", hot_only=False)
        checkpointed_shas = {t.get("git_sha") for t in timeline if t.get("git_sha")}
        res = subprocess.run(["git", "log", "-n", "50", "--format=%h"], capture_output=True, text=True)
        uncheckpointed = 0
        if res.returncode == 0:
            for sha in res.stdout.strip().split("\n"):
                if not sha:
                    continue
                if sha in checkpointed_shas:
                    break
                uncheckpointed += 1

        updated["session_summary"] = {
            "uncheckpointed_commits": uncheckpointed,
            "backfill_recommendation": "Run 'rekall checkpoint --commit <sha>' to backfill missing commits." if uncheckpointed > 0 else "All commits are checkpointed."
        }

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
        drift = store.check_drift()
        res = store.resume_anchor(anchor_id)
        if "error" in res:
            return [{"error": {"code": "NOT_FOUND", "message": res["error"]}}]
        store.start_session()
        if drift:
            res["drift_warning"] = drift
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


def session_brief(args: dict) -> list:
    """One-call session brief: returns everything an agent needs to continue work."""
    store = get_store()
    try:
        from rekall.core.brief import generate_session_brief
        brief = generate_session_brief(store)
        return [brief]
    except Exception as e:
        return [{"error": {"code": "INTERNAL_ERROR", "message": str(e)}}]


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



def rekall_verify_mcp(args: dict) -> list:
    """Verifies cryptographic integrity and schema of the Rekall ledger."""
    store = get_store()
    try:
        streams = ["timeline.jsonl", "actions.jsonl", "decisions.jsonl", "attempts.jsonl"]
        hash_results = {}
        for stream in streams:
            res = store.verify_stream_integrity(stream)
            hash_results[stream] = res

        val_res = store.validate_all(strict=True)
        ok = val_res.get("summary", {}).get("status") != "❌"
        for res in hash_results.values():
            if not res["valid"]:
                ok = False

        if ok:
            return [{
                "ok": True,
                "message": "Cryptographic integrity and schema verified",
                "hash_chain": hash_results,
                "schema_validation": val_res
            }]
        else:
            return [{
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Ledger verification failed",
                    "hash_chain": hash_results,
                    "schema_validation": val_res
                }
            }]
    except Exception as e:
        return [{"error": {"code": "INTERNAL_ERROR", "message": str(e)}}]

def rekall_log_mcp(args: dict) -> list:
    """Returns a concatenated log of recent timeline events and activity."""
    limit = args.get("limit", 20)
    store = get_store()
    try:
        timeline = store._load_stream("timeline.jsonl") or []
        activity = store._load_stream("activity.jsonl") or []
        combined = sorted(timeline + activity, key=lambda x: x.get("timestamp", ""), reverse=True)
        return [{"items": combined[:limit]}]
    except Exception as e:
        return [{"error": {"code": "INTERNAL_ERROR", "message": str(e)}}]

def guard_query(args: dict) -> list:
    """Read-only preflight guard query returning the same payload as `rekall guard --json`."""
    project_id = args.get(
        "project_id"
    )  # Added project_id for consistency with other tools
    if not project_id:
        raise ValueError("project_id is required")
    store = get_store()
    from rekall.cli import build_guard_payload

    drift = store.check_drift()
    store.start_session()

    payload = build_guard_payload(store)
    out = {"ok": True, "guard": "PASS", **payload}
    if drift:
        out["drift_warning"] = drift
    return [out]


def rekall_checkpoint(args: dict) -> list:
    project_id = args.get("project_id")
    if not project_id:
        raise ValueError("project_id is required")

    ctype = args.get("type", "milestone")
    title = args.get("title", "checkpoint")
    summary = args.get("summary", "")
    tags = args.get("tags", [])
    commit_arg = args.get("git_commit")
    actor = args.get("actor")
    if not actor:
        actor = {"actor_id": "mcp_assistant"}

    store = get_store()

    import logging
    import subprocess
    import uuid
    logger = logging.getLogger(__name__)

    git_sha = None
    git_subject = None
    if commit_arg:
        try:
            if commit_arg.lower() == "auto":
                res = subprocess.run(["git", "log", "-1", "--format=%h|%s"], capture_output=True, text=True, check=True)
                parts = res.stdout.strip().split("|", 1)
                if len(parts) == 2:
                    git_sha, git_subject = parts
            else:
                git_sha = commit_arg
                res = subprocess.run(["git", "log", "-1", "--format=%s", commit_arg], capture_output=True, text=True, check=True)
                git_subject = res.stdout.strip()
        except Exception as e:
            logger.warning(f"Failed to resolve git commit {commit_arg}: {e}")

    record_id = str(uuid.uuid4())
    record = {
        "title": title,
        "summary": summary,
        "tags": tags,
    }

    if ctype == "milestone":
        record["type"] = "milestone"
        record["event_id"] = record_id
    elif ctype == "task_done":
        record["type"] = "task"
        record["work_item_id"] = record_id
        record["status"] = "done"
        record["intent"] = summary
    elif ctype == "attempt_failed":
        record["type"] = "attempt_failed"
        record["attempt_id"] = record_id
        record["outcome"] = "failure"
    elif ctype == "decision":
        record["type"] = "decision"
        record["decision_id"] = record_id
        record["status"] = "approved"
    elif ctype == "artifact":
        record["type"] = "artifact"
        record["artifact_id"] = record_id

    if git_sha:
        record["git_sha"] = git_sha
        record["git_subject"] = git_subject

    try:
        if ctype == "task_done":
            store.create_work_item(record, actor=actor)
            store.append_timeline({
                "type": "milestone",
                "summary": f"Task completed: {title}",
                "work_item_id": record_id
            }, actor=actor)
            tid = record_id
        elif ctype == "decision":
            store.append_decision(record, actor=actor)
            tid = record_id
        elif ctype == "attempt_failed":
            store.append_attempt(record, actor=actor)
            tid = record_id
        elif ctype == "artifact":
            store.append_artifact(record, actor=actor)
            tid = record_id
        else:
            record["details"] = summary
            res_tl = store.append_timeline(record, actor=actor)
            tid = res_tl.get("event_id", record_id)

        out = {"ok": True, "type": ctype, "id": tid}
        if git_sha:
            out["git_sha"] = git_sha
        return [out]
    except Exception as e:
        err_code = "VALIDATION_ERROR"
        if "Secret detected" in str(e):
            err_code = "SECRET_DETECTED"
        return [{"error": {"code": err_code, "message": str(e)}}]


def actuate_commit(args: dict) -> list:
    project_id = args.get("project_id")
    message = args.get("message")
    actor = args.get("actor")
    if not project_id:
        raise ValueError("project_id is required")
    if not message:
        raise ValueError("message is required")
    if not actor:
        actor = {"actor_id": "mcp_assistant"}

    store = get_store()
    import logging
    import subprocess
    import uuid
    logging.getLogger(__name__)

    try:
        res = subprocess.run(["git", "commit", "-m", message], capture_output=True, text=True)
        if res.returncode != 0:
            return [{"error": {"code": "VALIDATION_ERROR", "message": f"Git commit failed: {res.stderr or res.stdout}"}}]

        git_sha = subprocess.run(["git", "log", "-1", "--format=%h"], capture_output=True, text=True).stdout.strip()
        git_subject = subprocess.run(["git", "log", "-1", "--format=%s"], capture_output=True, text=True).stdout.strip()

        record_id = str(uuid.uuid4())
        record = {
            "type": "task",
            "title": git_subject,
            "summary": "Auto-checkpointed via actuate_commit",
            "work_item_id": record_id,
            "status": "done",
            "intent": "Auto-checkpointed git commit",
            "git_sha": git_sha,
            "git_subject": git_subject,
        }

        store.create_work_item(record, actor=actor)
        store.append_timeline({
            "type": "milestone",
            "summary": f"Task completed: {git_subject}",
            "work_item_id": record_id,
            "git_sha": git_sha,
            "git_subject": git_subject,
        }, actor=actor)

        store.start_session()
        store.record_write()

        out = {
            "ok": True,
            "git_sha": git_sha,
            "work_item_id": record_id,
            "message": "Commit and checkpoint successful."
        }
        return [out]
    except Exception as e:
        return [{"error": {"code": "INTERNAL_ERROR", "message": str(e)}}]


# --- MCP JSON-RPC Server Core ---

TOOLS_DEF = [
    {
        "name": "rekall.init",
        "description": "Initialize or repair a Rekall vault. Ensures project identity and goals are set. Call this at the very beginning of a project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "High-level project objective"},
                "phase": {"type": "string", "description": "Current development phase (e.g., alpha, beta)"},
                "status": {"type": "string", "description": "Project status (e.g., on_track, at_risk)"},
                "confidence": {"type": "string", "description": "Confidence level (0.0 to 1.0)"},
                "actor": {"type": "object", "description": "Actor identity metadata"}
            }
        }
    },
    {
        "name": "rekall.brief",
        "description": "One-call session brief. Returns focus, blockers, failed attempts (do not retry), and pending decisions. Call this at the start of every session.",
        "inputSchema": {"type": "object", "properties": {}}
    },

    {
        "name": "rekall.checkpoint",
        "description": "Create a durable checkpoint of current progress. Optionally attaches a git commit.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "title"],
            "properties": {
                "project_id": {"type": "string"},
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "type": {"type": "string", "description": "task_done | milestone | decision | attempt_failed"},
                "git_commit": {"type": "string", "description": "'auto' or specific SHA"},
                "tags": {"type": "array", "items": {"type": "string"}}
            }
        }
    },
    {
        "name": "rekall.log",
        "description": "View recent history of the project ledger.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20}
            }
        }
    },
    {
        "name": "rekall.verify",
        "description": "Verify cryptographic integrity and hash chain (tamper evidence) of the project ledger.",
        "inputSchema": {"type": "object", "properties": {}}
    },
]

TOOL_REGISTRY = {
    "rekall.init": project_bootstrap,
    "rekall.brief": session_brief,
    "rekall.checkpoint": rekall_checkpoint,
    "rekall.log": rekall_log_mcp,
    "rekall.verify": rekall_verify_mcp,
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
            global _session_briefed
            params = req.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})

            # Session gate: track when the agent has seen the brief
            if name in ("rekall.brief", "rekall.init"):
                _session_briefed = True

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

                    # --- Session gate: auto-inject brief on first non-brief tool call ---
                    if not _session_briefed and not is_error:
                        _session_briefed = True
                        try:
                            brief_data = session_brief({})
                            first_brief = brief_data[0] if brief_data else {}
                            if isinstance(first_brief, dict) and "error" not in first_brief:
                                brief_text = first_brief.get("text", json.dumps(first_brief, indent=2)) if isinstance(first_brief, dict) else str(first_brief)
                                response_text = (
                                    "=== REKALL SESSION CONTEXT (auto-injected) ===\n"
                                    + brief_text
                                    + "\n=== END SESSION CONTEXT ===\n\n"
                                    + response_text
                                )
                        except Exception:
                            pass  # Don't break the actual tool call if brief fails

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
