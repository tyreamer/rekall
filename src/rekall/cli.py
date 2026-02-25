import argparse
import sys
import json
from pathlib import Path
import logging
from enum import IntEnum

from rekall.core.state_store import StateStore
from rekall.core.handoff_generator import generate_boot_brief
from rekall.core.executive_queries import query_executive_status, ExecutiveQueryType

logger = logging.getLogger(__name__)

class ExitCode(IntEnum):
    SUCCESS = 0
    INTERNAL_ERROR = 1
    VALIDATION_FAILED = 2
    STRICT_WARNINGS = 3
    NOT_FOUND = 4
    FORBIDDEN = 5
    CONFLICT = 6
    SECRET_DETECTED = 7
    
def die(code: ExitCode, message: str, is_json: bool, details: dict = None):
    """Standardized exit formatter."""
    if is_json:
        payload = {"ok": False, "code": code.name, "message": message}
        if details:
            payload["details"] = details
        print(json.dumps(payload))
    else:
        logger.error(f"[{code.name}] {message}")
        if details:
            print(f"Details: {details}")
    sys.exit(code.value)

def setup_logging(json_mode: bool = False, quiet_mode: bool = False):
    if json_mode or quiet_mode:
        logging.basicConfig(level=logging.ERROR, format="%(message)s", force=True)
    else:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s", force=True)

def cmd_init(args):
    """Initializes a new Rekall project state directory."""
    base_dir = Path(args.store_dir)
    
    if base_dir.exists() and any(base_dir.iterdir()):
        die(ExitCode.CONFLICT, f"Directory {base_dir} is not empty.", args.json)
        
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
        (base_dir / "schema-version.txt").write_text("0.1")
        
        import yaml
        with open(base_dir / "project.yaml", "w", encoding="utf-8") as f:
            yaml.dump({
                "project_id": "new_project_123",
                "description": "A new Rekall project",
                "repo_url": "https://github.com/your-org/repo",
                "links": []
            }, f, sort_keys=False)
            
        with open(base_dir / "envs.yaml", "w", encoding="utf-8") as f:
            yaml.dump({"dev": {"type": "local"}}, f)
            
        with open(base_dir / "access.yaml", "w", encoding="utf-8") as f:
            yaml.dump({"roles": {}}, f)
            
        for name in ["work-items.jsonl", "activity.jsonl", "attempts.jsonl", "decisions.jsonl", "timeline.jsonl"]:
            (base_dir / name).touch()
            
        if args.json:
            print(json.dumps({"status": "success", "store_dir": str(base_dir)}))
        else:
            logger.info(f"Initialized empty Rekall state at {base_dir}/")
            
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Init failed: {str(e)}", args.json)

def cmd_demo(args):
    """One-click experience that sets up a temporary project, validates it, and generates handoff."""
    import tempfile
    import shutil
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        args.store_dir = temp_dir
        
        if not args.json:
            logger.info(f"Setting up demo in temporary directory: {temp_dir}")
            
        # Re-use init logic to stage the directory
        cmd_init(args)
        
        # Mock some events for the demo
        store = StateStore(temp_path)
        actor = {"actor_id": "demo_user"}
        wi_1 = store.create_work_item({"title": "Design Demo Project", "status": "todo"}, actor)
        wi_2 = store.create_work_item({"title": "Fix Onboarding Issue", "status": "in_progress"}, actor)
        store.claim_work_item(wi_2["work_item_id"], 1, actor)
        
        if not args.json:
            logger.info("Created sample work items. Running validation...")
            
        # Re-use validate
        args.strict = False
        cmd_validate(args)
        
        if not args.json:
            logger.info("Validation passed. Running handoff...")
            
        # Re-use handoff
        out_dir = temp_path / "handoff"
        args.out = str(out_dir)
        args.project_id = store.project_config.get("project_id")
        cmd_handoff(args)
        
        if args.json:
            print(json.dumps({"status": "success", "demo_dir": temp_dir}))
        else:
            import platform
            system = platform.system()
            brief_file = (out_dir / "boot_brief.md").resolve()
            state_dir = temp_path.resolve()
            
            if system == "Windows":
                view_cmd = f'notepad "{brief_file}"\n  (or) Get-Content "{brief_file}"'
            elif system == "Darwin":
                view_cmd = f'open "{brief_file}"'
            else:
                view_cmd = f'xdg-open "{brief_file}"'

            print("\n" + "="*50)
            print("✅ DEMO COMPLETE — OPEN THIS NOW:")
            print("="*50)
            print(f"\nYour boot brief is ready: {brief_file}")
            print(f"Your state artifact is dumped at: {state_dir}")
            print("\nView it now:")
            print(f"  {view_cmd}\n")
            print("-" * 50)
            print("Next, initialize your own project:")
            print("  rekall init ./project-state")
            print("  rekall guard --store-dir ./project-state   # preflight check")
            print("  rekall validate ./project-state --strict")
            print("-" * 50 + "\n")

def cmd_validate(args):
    """Validate StateStore schema and invariants."""
    base_dir = Path(args.store_dir)
    if not base_dir.exists():
        die(ExitCode.NOT_FOUND, f"Directory {base_dir} does not exist.", args.json)
        
    try:
        # We instantiate StateStore but don't want it to crash if schema-version is missing during init,
        # so we might need a raw validate. Actually, StateStore.initialize() raises exceptions. 
        # Let's bypass full init for validate so it can report *all* errors instead of crashing on the first.
        # But for now, let's wrap the init:
        try:
            store = StateStore(base_dir)
        except Exception as e:
            die(ExitCode.INTERNAL_ERROR, f"Validation failed during initialization: {str(e)}", args.json)
            
        report = store.validate_all(strict=args.strict)
        
        if args.json:
            print(json.dumps(report, indent=2))
        elif not getattr(args, "quiet", False):
            print("\n=== Rekall Validation Report ===")
            print(f"Status: {report['summary']['status']} ({report['summary']['errors']} errors, {report['summary']['warnings']} warnings)")
            
            for section, data in report.items():
                if section == "summary": continue
                status = data.get("status", "✅")
                print(f"\n{status} {section.replace('_', ' ').title()}")
                
                if status != "✅":
                    for k, v in data.items():
                        if k == "status": continue
                        if isinstance(v, list) and v:
                            for item in v:
                                print(f"  - [{k}] {item}")
                        elif v:
                             print(f"  - {v}")
                             
            print("================================\n")
            
        if report["summary"]["status"] == "❌":
            sys.exit(ExitCode.VALIDATION_FAILED.value)
        elif args.strict and report["summary"]["warnings"] > 0:
            sys.exit(ExitCode.STRICT_WARNINGS.value)
            
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Validation failed with exception: {str(e)}", args.json)

def cmd_snapshot(args):
    """Compile the state store into a single standalone snapshot.json (compact format)."""
    base_dir = Path(args.store_dir)
    try:
        store = StateStore(base_dir)
        
        # Compile snapshot with deterministic ordering
        activity = sorted(store._load_jsonl("activity.jsonl"), key=lambda x: (x.get("timestamp", ""), x.get("activity_id", "")))
        attempts = sorted(store._load_jsonl("attempts.jsonl"), key=lambda x: (x.get("timestamp", ""), x.get("attempt_id", "")))
        decisions = sorted(store._load_jsonl("decisions.jsonl"), key=lambda x: (x.get("timestamp", ""), x.get("decision_id", "")))
        timeline = sorted(store._load_jsonl("timeline.jsonl"), key=lambda x: (x.get("timestamp", ""), x.get("event_id", "")))
        events = sorted(store._load_jsonl("work-items.jsonl"), key=lambda x: (x.get("timestamp", ""), x.get("event_id", "")))
        
        # Sort work_items keys deterministically
        work_items_sorted = {k: store.work_items[k] for k in sorted(store.work_items.keys())}
        
        snapshot = {
            "project": store.project_config,
            "envs": store.envs_config,
            "access": store.access_config,
            "work_items": work_items_sorted,
            "events": events,
            "activity": activity,
            "attempts": attempts,
            "decisions": decisions,
            "timeline": timeline,
            "schema_version": "0.1" # Standardized version
        }
        
        # Write to requested output or stdout
        if args.out:
            out_file = Path(args.out)
            out_file.write_text(json.dumps(snapshot, indent=2))
            logger.info(f"Snapshot exported to {out_file}")
            if args.json: print(json.dumps({"status": "success", "snapshot_file": str(out_file)}))
        else:
            print(json.dumps(snapshot, indent=2))
            
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Snapshot failed: {str(e)}", args.json)

def cmd_export(args):
    """Copies the StateStore entirely to a requested output directory matching v0.1 Spec."""
    import shutil
    base_dir = Path(args.store_dir)
    out_dir = Path(args.out)
    
    try:
        store = StateStore(base_dir) # validates implicitly
        
        # If valid, just copy files over
        out_dir.mkdir(parents=True, exist_ok=True)
        
        files_to_copy = [
            "schema-version.txt", "project.yaml", "envs.yaml", "access.yaml",
            "work-items.jsonl", "activity.jsonl", "attempts.jsonl", "decisions.jsonl", "timeline.jsonl"
        ]
        
        for f in files_to_copy:
            src = base_dir / f
            if src.exists():
                shutil.copy2(src, out_dir / f)
                
        if args.json:
            print(json.dumps({"status": "success", "export_dir": str(out_dir)}))
        else:
            logger.info(f"Exported project state to {out_dir}")
            
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Export failed: {str(e)}", args.json)

def cmd_import(args):
    """Reads from a state store folder and imports events idempotently to the target directory."""
    target_dir = Path(args.store_dir)
    source_dir = Path(args.source)
    
    if not source_dir.exists() or not (source_dir / "schema-version.txt").exists():
        die(ExitCode.NOT_FOUND, f"Source directory {source_dir} is not a valid state store.", args.json)
        
    try:
        # Initialize target if it doesn't exist
        if not target_dir.exists() or not any(target_dir.iterdir()):
            fake_args = argparse.Namespace(store_dir=args.store_dir, json=False)
            cmd_init(fake_args)
            
        target_store = StateStore(target_dir)
        source_store = StateStore(source_dir)
        
        # Merge YAMLs (in a real scenario we'd do smart merge, but let's replace for now if source has content)
        import shutil
        for yaml_file in ["project.yaml", "envs.yaml", "access.yaml"]:
            if (source_dir / yaml_file).exists():
                shutil.copy2(source_dir / yaml_file, target_dir / yaml_file)
                
        # Idempotent JSONL event injection
        events_lists = [
            ("work-items.jsonl", "event_id"),
            ("activity.jsonl", "activity_id"),
            ("attempts.jsonl", "attempt_id"),
            ("decisions.jsonl", "decision_id"),
            ("timeline.jsonl", "event_id")
        ]
        
        for file_name, id_field in events_lists:
            if (source_dir / file_name).exists():
                records = source_store._load_jsonl(file_name)
                for record in records:
                    target_store.append_jsonl_idempotent(file_name, record, id_field)
                    
        if args.json:
            print(json.dumps({"status": "success", "imported_to": str(target_dir)}))
        else:
            logger.info(f"Import from folder {source_dir} to {target_dir} successful.")
            
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Import failed: {str(e)}", args.json)

def cmd_handoff(args):
    """Synthesizes project state to create boot_brief.md and exports snapshot.json."""
    base_dir = Path(args.store_dir)
    out_dir = Path(args.out)
    project_id = args.project_id
    
    try:
        store = StateStore(base_dir)
        
        # Verify project_id matches
        config_pid = store.project_config.get("project_id")
        if config_pid and config_pid != project_id:
            logger.warning(f"Warning: Requested project_id '{project_id}' does not match StateStore project_id '{config_pid}'. Proceeding anyway.")
            
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # Compile snapshot with deterministic ordering
        events = sorted(store._load_jsonl("work-items.jsonl"), key=lambda x: (x.get("timestamp", ""), x.get("event_id", "")))
        activity = sorted(store._load_jsonl("activity.jsonl"), key=lambda x: (x.get("timestamp", ""), x.get("activity_id", "")))
        attempts = sorted(store._load_jsonl("attempts.jsonl"), key=lambda x: (x.get("timestamp", ""), x.get("attempt_id", "")))
        decisions = sorted(store._load_jsonl("decisions.jsonl"), key=lambda x: (x.get("timestamp", ""), x.get("decision_id", "")))
        timeline = sorted(store._load_jsonl("timeline.jsonl"), key=lambda x: (x.get("timestamp", ""), x.get("event_id", "")))
        
        work_items_sorted = {k: store.work_items[k] for k in sorted(store.work_items.keys())}
        
        snapshot = {
            "project": store.project_config,
            "envs": store.envs_config,
            "access": store.access_config,
            "work_items": work_items_sorted,
            "events": events,
            "activity": activity,
            "attempts": attempts,
            "decisions": decisions,
            "timeline": timeline,
            "schema_version": "0.1"
        }
        
        snapshot_file = out_dir / "snapshot.json"
        snapshot_file.write_text(json.dumps(snapshot, indent=2))
        
        # Generate boot_brief.md
        brief_content = generate_boot_brief(store)
        brief_file = out_dir / "boot_brief.md"
        brief_file.write_text(brief_content, encoding="utf-8")
        
        logger.info(f"Handoff pack generated at {out_dir}")
        logger.info(f" - {brief_file}")
        logger.info(f" - {snapshot_file}")
        
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Handoff failed: {str(e)}", False)

def cmd_features(args):
    """Print the capability map and positioning."""
    print("\nRekall: The Project Reality Blackboard + Ledger (Not Kanban)")
    print("-" * 60)
    print("FEATURES:")
    print("  * Typed Link Matrix       : Bridges Jira, Notion, Figma into a single machine-readable layer.")
    print("  * Immutable Ledgers       : JSONL ledgers for decisions, attempts, and work-item state.")
    print("  * Agent Context injection : `handoff` pack aggregates blocks, history, and goals into a boot brief.")
    print("  * MCP Server Native       : Direct read/write bindings for Claude Desktop.")
    print("\nWHY NOT KANBAN?")
    print("  Kanban boards track what humans are assigned to.")
    print("  Rekall tracks what the project IS, what was TRIED, and WHY decisions were made.")
    print("  See: docs/WHY_NOT_KANBAN.md\n")

def execute_alias_query(args, qtype: ExecutiveQueryType):
    """Wrapper to run existing ExecutiveQueries directly from CLI."""
    base_dir = Path(args.store_dir)
    if not base_dir.exists():
        die(ExitCode.NOT_FOUND, f"Directory {base_dir} does not exist.", args.json)
        
    try:
        store = StateStore(base_dir)
        resp = query_executive_status(store, qtype)
        
        if args.json:
            import dataclasses
            print(json.dumps(dataclasses.asdict(resp), indent=2))
        else:
            print(f"\n[{qtype.name}] Target: {resp.target_project_id}")
            print(f"Items Match: {len(resp.work_items)}")
            if resp.blockers:
                print("BLOCKERS:")
                for b in resp.blockers:
                    print(f" - {b}")
            if resp.next_steps:
                print("NEXT STEPS:")
                for s in resp.next_steps:
                    print(f" - {s}")
            print("")
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Query failed: {str(e)}", args.json)

def cmd_alias_status(args): execute_alias_query(args, ExecutiveQueryType.ON_TRACK)
def cmd_alias_blockers(args): execute_alias_query(args, ExecutiveQueryType.BLOCKERS)
def cmd_alias_resume(args): execute_alias_query(args, ExecutiveQueryType.RESUME_IN_30)


def build_guard_payload(store: StateStore) -> dict:
    """Build the structured preflight guard payload from a StateStore."""
    import datetime
    
    # Project identity
    proj = store.project_config or {}
    project_info = {
        "name": proj.get("project_id", "unknown"),
        "description": proj.get("description", ""),
        "repo_url": proj.get("repo_url", ""),
        "phase": proj.get("phase", "not set"),
        "current_goal": proj.get("current_goal", "not set"),
        "status": proj.get("status", "unknown"),
        "confidence": proj.get("confidence", "not set"),
    }
    
    # Constraints / invariants
    constraints = proj.get("constraints", proj.get("invariants", []))
    if isinstance(constraints, dict):
        constraints = [f"{k}: {v}" for k, v in constraints.items()]
    constraints = constraints[:10] if constraints else []
    
    # Recent approved decisions (last 3)
    all_decisions = sorted(
        store._load_jsonl("decisions.jsonl"),
        key=lambda d: d.get("timestamp", ""),
        reverse=True
    )
    approved = [d for d in all_decisions if d.get("status") == "approved"][:3]
    proposed_if_none = [d for d in all_decisions if d.get("status") == "proposed"][:3] if not approved else []
    recent_decisions = approved or proposed_if_none
    decisions_out = []
    for d in recent_decisions:
        decisions_out.append({
            "decision_id": d.get("decision_id"),
            "title": d.get("title", ""),
            "status": d.get("status", ""),
            "tradeoffs": d.get("tradeoffs", ""),
            "rationale": d.get("rationale", ""),
            "evidence_refs": d.get("evidence_links", d.get("evidence", [])),
        })
    
    # Recent failed attempts (last 3)
    all_attempts = sorted(
        store._load_jsonl("attempts.jsonl"),
        key=lambda a: a.get("timestamp", ""),
        reverse=True
    )
    # Filter for outcome == "failed" or just show last 3 if no outcome field
    failed = [a for a in all_attempts if a.get("outcome") == "failed"][:3]
    recent_attempts = failed if failed else all_attempts[:3]
    attempts_out = []
    for a in recent_attempts:
        attempts_out.append({
            "attempt_id": a.get("attempt_id"),
            "title": a.get("title", ""),
            "work_item_id": a.get("work_item_id", ""),
            "hypothesis": a.get("hypothesis", a.get("title", "")),
            "outcome": a.get("outcome", "recorded"),
            "evidence_refs": a.get("evidence_links", a.get("evidence", [])),
        })
    
    # Top risks / blockers from work items
    now = datetime.datetime.now(datetime.timezone.utc)
    risks = []
    for wid, item in store.work_items.items():
        status = item.get("status", "")
        deps = item.get("dependencies", {})
        blocked_by = deps.get("blocked_by", [])
        if blocked_by or status in ("blocked", "at_risk"):
            risks.append({
                "work_item_id": wid,
                "title": item.get("title", ""),
                "status": status,
                "blocked_by": blocked_by,
                "evidence_refs": item.get("evidence_links", []),
            })
        elif status == "in_progress":
            claim = item.get("claim")
            if claim:
                lease_str = claim.get("lease_until", "")
                try:
                    lease_dt = datetime.datetime.fromisoformat(lease_str.replace('Z', '+00:00'))
                    if now > lease_dt:
                        risks.append({
                            "work_item_id": wid,
                            "title": item.get("title", ""),
                            "status": "in_progress (lease expired)",
                            "blocked_by": [],
                            "evidence_refs": item.get("evidence_links", []),
                        })
                except (ValueError, AttributeError):
                    pass
    
    # Environments + access (no secrets)
    envs = store.envs_config or {}
    access = store.access_config or {}
    operate = {
        "environments": {k: {kk: vv for kk, vv in (v if isinstance(v, dict) else {}).items() if "secret" not in kk.lower() and "key" not in kk.lower() and "token" not in kk.lower()} for k, v in envs.items()},
        "access_roles": list(access.get("roles", {}).keys()) if isinstance(access.get("roles"), dict) else [],
    }
    
    return {
        "project": project_info,
        "constraints": constraints,
        "recent_decisions": decisions_out,
        "recent_attempts": attempts_out,
        "risks_blockers": risks,
        "operate": operate,
    }


def cmd_guard(args):
    """Drift guard / invariant preflight check."""
    base_dir = Path(args.store_dir)
    if not base_dir.exists():
        die(ExitCode.NOT_FOUND, f"Directory {base_dir} does not exist.", args.json)
    
    try:
        store = StateStore(base_dir)
        payload = build_guard_payload(store)
        
        # Strict checks
        if args.strict:
            problems = []
            if not payload["constraints"]:
                problems.append("No constraints/invariants defined in project.yaml")
            if not payload["recent_decisions"]:
                problems.append("No decisions found in decisions.jsonl")
            if problems:
                if args.json:
                    print(json.dumps({"ok": False, "guard": "FAIL", "problems": problems, **payload}))
                else:
                    print("\n❌ GUARD PREFLIGHT FAILED")
                    for p in problems:
                        print(f"  ✗ {p}")
                sys.exit(ExitCode.VALIDATION_FAILED.value)
        
        # Emit timeline
        if getattr(args, "emit_timeline", False):
            import hashlib
            actor = {"actor_id": getattr(args, "actor", "cli_user")}
            event_id = hashlib.sha256(f"guard-preflight-{base_dir.resolve()}".encode()).hexdigest()[:16]
            store.append_timeline(
                {"event_id": event_id, "type": "note", "summary": "Preflight guard run"},
                actor=actor
            )
        
        # Output
        if args.json:
            print(json.dumps({"ok": True, "guard": "PASS", **payload}, indent=2, default=str))
        else:
            p = payload["project"]
            print("\n" + "="*55)
            print("🛡  REKALL PREFLIGHT GUARD")
            print("="*55)
            print(f"  Project   : {p['name']}")
            print(f"  Goal      : {p['current_goal']}")
            print(f"  Phase     : {p['phase']}")
            print(f"  Status    : {p['status']}")
            print(f"  Confidence: {p['confidence']}")
            
            # Constraints
            cs = payload["constraints"]
            print(f"\n📌 Constraints/Invariants ({len(cs)}):")
            if cs:
                for c in cs:
                    print(f"  • {c}")
            else:
                print("  (none defined — add 'constraints' to project.yaml)")
            
            # Decisions
            ds = payload["recent_decisions"]
            print(f"\n📜 Most Recent Decisions ({len(ds)}):")
            for d in ds:
                print(f"  [{d['decision_id'][:8]}] {d['title']}")
                print(f"    status: {d['status']}  tradeoffs: {d['tradeoffs']}")
                if d['evidence_refs']:
                    print(f"    evidence: {d['evidence_refs']}")
            if not ds:
                print("  (no decisions recorded yet)")
            
            # Attempts
            ats = payload["recent_attempts"]
            print(f"\n🧪 Most Recent Attempts ({len(ats)}):")
            for a in ats:
                print(f"  [{a['attempt_id'][:8]}] {a['title']}")
                print(f"    outcome: {a['outcome']}  item: {a['work_item_id']}")
                if a['evidence_refs']:
                    print(f"    evidence: {a['evidence_refs']}")
            if not ats:
                print("  (no attempts recorded yet)")
            
            # Risks
            rs = payload["risks_blockers"]
            print(f"\n⚠️  Top Risks/Blockers ({len(rs)}):")
            for r in rs:
                print(f"  [{r['work_item_id']}] {r['title']} ({r['status']})")
                if r['blocked_by']:
                    print(f"    blocked_by: {r['blocked_by']}")
            if not rs:
                print("  (none)")
            
            # Operate
            op = payload["operate"]
            print(f"\n🔧 Operate:")
            print(f"  Environments: {list(op['environments'].keys())}")
            print(f"  Access roles: {op['access_roles']}")
            
            print("\n" + "="*55 + "\n")
    
    except SystemExit:
        raise
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Guard failed: {str(e)}", args.json)

def cmd_attempts_add(args):
    base_dir = Path(args.store_dir)
    try:
        store = StateStore(base_dir)
        attempt = {
            "work_item_id": args.work_item_id,
            "title": args.title,
            "evidence": args.evidence
        }
        res = store.append_attempt(attempt, actor={"actor_id": args.actor})
        if args.json:
            print(json.dumps({"status": "success", "attempt": res}))
        else:
            logger.info(f"Attempt added: {res['attempt_id']}")
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Failed to add attempt: {str(e)}", args.json)

def cmd_decisions_propose(args):
    base_dir = Path(args.store_dir)
    try:
        store = StateStore(base_dir)
        decision = {
            "title": args.title,
            "rationale": args.rationale,
            "tradeoffs": args.tradeoffs
        }
        res = store.propose_decision(decision, actor={"actor_id": args.actor})
        if args.json:
            print(json.dumps({"status": "success", "decision": res}))
        else:
            logger.info(f"Decision proposed: {res['decision_id']}")
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Failed to propose decision: {str(e)}", args.json)

def cmd_lock(args):
    base_dir = Path(args.store_dir)
    try:
        store = StateStore(base_dir)
        
        # Parse ttl like "5m" or just "300"
        ttl_str = args.ttl
        if ttl_str.endswith("m"):
            lease_seconds = int(ttl_str[:-1]) * 60
        elif ttl_str.endswith("h"):
            lease_seconds = int(ttl_str[:-1]) * 3600
        elif ttl_str.endswith("s"):
            lease_seconds = int(ttl_str[:-1])
        else:
            lease_seconds = int(ttl_str) * 60 # default to minutes if no suffix
            
        res = store.claim_work_item(
            args.work_item_id, 
            expected_version=args.expected_version, 
            actor={"actor_id": args.actor}, 
            lease_seconds=lease_seconds,
            force=args.force
        )
        if args.json:
            print(json.dumps({"status": "success", "work_item": res}))
        else:
            claim = res.get("claim", {})
            logger.info(f"Lock acquired for {args.work_item_id} by {claim.get('claimed_by')} until {claim.get('lease_until')}")
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Failed to acquire lock: {str(e)}", args.json)

def main():
    setup_logging()
    
    desc = """Rekall: project reality blackboard + ledger (not Kanban)
    
EXAMPLES:
  # Try it out
  rekall demo
  
  # Check status & what's blocking you
  rekall status
  rekall blockers
  
  # Validate system state before AI integration
  rekall validate --strict
  
  # Dump standalone snapshots
  rekall export -o ./backup-state/
  
  # Generate AI context prompts
  rekall handoff my_project -o ./handoff_test/
"""
    
    parser = argparse.ArgumentParser(
        description=desc,
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress internal logs")
    subparsers = parser.add_subparsers(dest="command", required=True, title="Commands", metavar="")
    
    # Try It
    parser_demo = subparsers.add_parser("demo", help="[Try] Run a 1-click demo to see Rekall in action.")
    parser_demo.add_argument("--quiet", "-q", action="store_true", help="Suppress internal logs")
    parser_demo.set_defaults(func=cmd_demo)
    
    parser_features = subparsers.add_parser("features", help="[Try] Print capability map and 'Not Kanban' explainer.")
    parser_features.set_defaults(func=cmd_features)
    
    # Init
    parser_init = subparsers.add_parser("init", help="[Portability] Initialize a new Rekall directory.")
    parser_init.add_argument("store_dir", nargs="?", default="project-state", help="Directory to initialize")
    parser_init.set_defaults(func=cmd_init)
    
    # Validate
    parser_validate = subparsers.add_parser("validate", help="[Status] Validate the StateStore invariants.")
    parser_validate.add_argument("--store-dir", default=".", help="Directory of the StateStore")
    parser_validate.add_argument("--strict", action="store_true", help="Fail with ExitCode 3 on warnings")
    parser_validate.set_defaults(func=cmd_validate)
    
    # Portability
    parser_export = subparsers.add_parser("export", help="[Portability] Export to a new directory.")
    parser_export.add_argument("--store-dir", default=".", help="Directory of the StateStore")
    parser_export.add_argument("--out", "-o", required=True, help="Output directory path")
    parser_export.set_defaults(func=cmd_export)
    
    parser_snapshot = subparsers.add_parser("snapshot", help="[Portability] Export to a single snapshot.json blob.")
    parser_snapshot.add_argument("--store-dir", default=".", help="Directory of the StateStore")
    parser_snapshot.add_argument("--out", "-o", help="Output JSON file path")
    parser_snapshot.set_defaults(func=cmd_snapshot)
    
    parser_import = subparsers.add_parser("import", help="[Portability] Import events from a source folder.")
    parser_import.add_argument("source", help="Path to source state store folder")
    parser_import.add_argument("--store-dir", default=".", help="Target Directory of the StateStore")
    parser_import.set_defaults(func=cmd_import)
    
    # Handoff
    parser_handoff = subparsers.add_parser("handoff", help="[Handoff] Create a boot_brief.md context pack.")
    parser_handoff.add_argument("project_id", help="The Project ID being handed off")
    parser_handoff.add_argument("--store-dir", default=".", help="Directory of the current StateStore")
    parser_handoff.add_argument("--out", "-o", required=True, help="Output directory")
    parser_handoff.set_defaults(func=cmd_handoff)
    
    # Aliases
    parser_status = subparsers.add_parser("status", help="[Status] Query items ON_TRACK.")
    parser_status.add_argument("--store-dir", default=".", help="Directory of the current StateStore")
    parser_status.set_defaults(func=cmd_alias_status)
    
    parser_blockers = subparsers.add_parser("blockers", help="[Status] Query items BLOCKERS.")
    parser_blockers.add_argument("--store-dir", default=".", help="Directory of the current StateStore")
    parser_blockers.set_defaults(func=cmd_alias_blockers)
    
    parser_resume = subparsers.add_parser("resume", help="[Status] Query actions to RESUME.")
    parser_resume.add_argument("--store-dir", default=".", help="Directory of the current StateStore")
    parser_resume.set_defaults(func=cmd_alias_resume)

    # Guard
    parser_guard = subparsers.add_parser("guard", help="[Preflight] Drift guard / invariant preflight check.")
    parser_guard.add_argument("--store-dir", default=".", help="Directory of the StateStore")
    parser_guard.add_argument("--strict", action="store_true", help="Exit non-zero if constraints or decisions missing")
    parser_guard.add_argument("--emit-timeline", action="store_true", help="Append a timeline event recording this guard run")
    parser_guard.add_argument("--actor", default="cli_user", help="Actor ID for timeline events")
    parser_guard.set_defaults(func=cmd_guard)

    # Grievance Closeout Commands: Nested subparsers
    parser_attempts = subparsers.add_parser("attempts", help="[Log] Manage attempt logs.")
    attempts_subparsers = parser_attempts.add_subparsers(dest="subcommand", required=True)
    
    parser_attempts_add = attempts_subparsers.add_parser("add", help="Add an attempt with evidence.")
    parser_attempts_add.add_argument("work_item_id", help="The Work Item ID")
    parser_attempts_add.add_argument("--title", required=True, help="Title of the attempt")
    parser_attempts_add.add_argument("--evidence", required=True, help="Evidence path or link")
    parser_attempts_add.add_argument("--store-dir", default=".", help="Directory of the StateStore")
    parser_attempts_add.add_argument("--actor", default="cli_user", help="Actor ID")
    parser_attempts_add.set_defaults(func=cmd_attempts_add)
    
    parser_decisions = subparsers.add_parser("decisions", help="[Log] Manage project decisions.")
    decisions_subparsers = parser_decisions.add_subparsers(dest="subcommand", required=True)
    
    parser_decisions_propose = decisions_subparsers.add_parser("propose", help="Propose a decision with rationale and tradeoffs.")
    parser_decisions_propose.add_argument("--title", required=True, help="Title of the decision")
    parser_decisions_propose.add_argument("--rationale", required=True, help="Why this decision is proposed")
    parser_decisions_propose.add_argument("--tradeoffs", required=True, help="Tradeoffs considered")
    parser_decisions_propose.add_argument("--store-dir", default=".", help="Directory of the StateStore")
    parser_decisions_propose.add_argument("--actor", default="cli_user", help="Actor ID")
    parser_decisions_propose.set_defaults(func=cmd_decisions_propose)
    
    parser_lock = subparsers.add_parser("lock", help="[Workflow] Acquire an exclusive lease/lock on a work item.")
    parser_lock.add_argument("work_item_id", help="The Work Item ID")
    parser_lock.add_argument("--expected-version", type=int, required=True, help="Expected version of the item")
    parser_lock.add_argument("--ttl", default="5m", help="Time to live (lease duration), e.g. 5m, 1h. Default 5m.")
    parser_lock.add_argument("--force", action="store_true", help="Force acquire the lock")
    parser_lock.add_argument("--store-dir", default=".", help="Directory of the StateStore")
    parser_lock.add_argument("--actor", default="cli_user", help="Actor ID")
    parser_lock.set_defaults(func=cmd_lock)

    args = parser.parse_args()
    setup_logging(args.json, getattr(args, "quiet", False))
    
    try:
        args.func(args)
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, str(e), args.json)
    
if __name__ == "__main__":
    main()
