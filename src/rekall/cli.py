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
    BLOCKERS_FOUND = 2
    USER_ERROR = 1 # Alias for general failure
    VALIDATION_FAILED = 1 # Mapping to 1 per req
    NOT_FOUND = 1
    FORBIDDEN = 1
    CONFLICT = 1
    SECRET_DETECTED = 1
    
class Theme:
    """Centralized icons and formatting with ASCII fallback detection."""
    # We use hex escapes instead of literal characters to avoid source encoding issues
    ICON_SUCCESS = "\u2705" # \u2705
    ICON_ERROR = "\u274c"   # \u274c
    ICON_WARNING = "\u26a0\ufe0f" # \u26a0\ufe0f
    ICON_INFO = "\u2139\ufe0f"    # \u2139\ufe0f
    ICON_IDEA = "\ud83d\udca1"    # \U0001f4a1
    ICON_TARGET = "\ud83c\udfaf"  # \U0001f3af
    ICON_FOLDER = "\ud83d\udcc1"  # \U0001f4c1
    ICON_LINK = "\ud83d\udd17"    # \U0001f517
    ICON_CHART = "\ud83d\udcca"   # \U0001f4ca
    ICON_ROCKET = "\ud83d\ude80"  # \U0001f680
    ICON_TOOL = "\ud83d\udd27"    # \U0001f527
    ICON_DOC = "\ud83d\udcc4"     # \U0001f4c4
    ICON_SEARCH = "\ud83d\udd0d"  # \U0001f50d
    ICON_PUSH = "\ud83d\udce4"    # \U0001f4e4
    ICON_UP = "\u2b06\ufe0f"      # \u2b06\ufe0f
    ICON_CHECK = "\u2714\ufe0f"   # \u2714\ufe0f
    
    @classmethod
    def use_ascii(cls):
        """Force ASCII fallback for icons."""
        cls.ICON_SUCCESS = "[OK]"
        cls.ICON_ERROR = "[ERR]"
        cls.ICON_WARNING = "[WARN]"
        cls.ICON_INFO = "[INFO]"
        cls.ICON_IDEA = "[SUGGEST]"
        cls.ICON_TARGET = "[TARGET]"
        cls.ICON_FOLDER = "[DIR]"
        cls.ICON_LINK = "[LINK]"
        cls.ICON_CHART = "[STATS]"
        cls.ICON_ROCKET = "[START]"
        cls.ICON_TOOL = "[TOOL]"
        cls.ICON_DOC = "[FILE]"
        cls.ICON_SEARCH = "[SCAN]"
        cls.ICON_PUSH = "[PUSH]"
        cls.ICON_UP = "[UP]"
        cls.ICON_CHECK = "[DONE]"

    @classmethod
    def autoprobe(cls):
        """Autodetect if we should use ASCII based on stream encoding."""
        # If stdout is redirected or doesn't support UTF-8, use ASCII
        try:
            encoding = (sys.stdout.encoding or "ascii").lower()
            if "utf-8" not in encoding and "utf8" not in encoding:
                cls.use_ascii()
        except Exception:
            cls.use_ascii()
    
def die(code: ExitCode, message: str, is_json: bool, details: dict = None, debug: bool = False):
    """Standardized exit formatter."""
    if is_json:
        payload = {"ok": False, "code": code.name, "message": message}
        if details:
            payload["details"] = details
        print(json.dumps(payload))
    else:
        # Success Criterion 4: Print clean human-readable error
        if code == ExitCode.INTERNAL_ERROR:
            prefix = "INTERNAL ERROR"
        elif code == ExitCode.BLOCKERS_FOUND:
            prefix = "BLOCKERS"
        else:
            prefix = "ERROR"
        print(f"\n{Theme.ICON_ERROR} {prefix}: {message}")
        
        if details:
             print(f"Details: {details}")
             
        if code == ExitCode.INTERNAL_ERROR or debug:
            if not debug:
                print(f"\n{Theme.ICON_IDEA} Suggestion: Run with --debug for full stack trace.")
            else:
                import traceback
                print("\n--- STACK TRACE ---")
                traceback.print_exc()
                 
    sys.exit(code.value)

def setup_logging(json_mode: bool = False, quiet_mode: bool = False):
    if json_mode or quiet_mode:
        logging.basicConfig(level=logging.ERROR, format="%(message)s", force=True)
    else:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s", force=True)

def ensure_state_initialized(store_dir: Path, is_json: bool = False):
    """Ensures the state directory and its minimal required files exist."""
    if store_dir.exists() and (store_dir / "schema-version.txt").exists() and (store_dir / "manifest.json").exists():
        return

    if not is_json:
        logger.info(f"State directory {store_dir}/ missing. Initializing minimal structure...")
        
    try:
        store_dir.mkdir(parents=True, exist_ok=True)
        (store_dir / "schema-version.txt").write_text("0.1")
        
        import yaml
        project_id = Path.cwd().name
        
        if not (store_dir / "project.yaml").exists():
            with open(store_dir / "project.yaml", "w", encoding="utf-8") as f:
                yaml.dump({
                    "project_id": project_id,
                    "description": "Project managed by Rekall",
                    "repo_url": "N/A",
                    "links": []
                }, f, sort_keys=False)
                
        if not (store_dir / "envs.yaml").exists():
            with open(store_dir / "envs.yaml", "w", encoding="utf-8") as f:
                yaml.dump({"dev": {"type": "local"}}, f)
                
        if not (store_dir / "access.yaml").exists():
            with open(store_dir / "access.yaml", "w", encoding="utf-8") as f:
                yaml.dump({"roles": {}}, f)
                
        # Initialize manifest and streams
        manifest_path = store_dir / "manifest.json"
        if not manifest_path.exists():
            manifest = {
                "schema_version": "0.1",
                "streams": {}
            }
            
            streams_to_init = [
                ("work_items", "event_id"),
                ("activity", "activity_id"),
                ("attempts", "attempt_id"),
                ("decisions", "decision_id"),
                ("timeline", "event_id")
            ]
            
            for stream_key, id_field in streams_to_init:
                stream_dir = store_dir / "streams" / stream_key
                stream_dir.mkdir(parents=True, exist_ok=True)
                active_file = stream_dir / "active.jsonl"
                active_file.touch(exist_ok=True)
                
                manifest["streams"][stream_key] = {
                    "active_file": str(active_file.relative_to(store_dir).as_posix()),
                    "segments": [],
                    "id_field": id_field
                }
            
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
            
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Failed to auto-initialize {store_dir}: {str(e)}", is_json)

def cmd_init(args):
    """Initializes a new Rekall project state directory."""
    base_dir = Path(args.store_dir)
    
    if base_dir.exists() and any(base_dir.iterdir()):
        die(ExitCode.CONFLICT, f"Directory {base_dir} is not empty.", args.json)
        
    ensure_state_initialized(base_dir, args.json)
        
    if args.json:
        print(json.dumps({"status": "success", "store_dir": str(base_dir)}))
    else:
        logger.info(f"Initialized empty Rekall state at {base_dir}/")

def cmd_doctor(args):
    """Diagnostic command to check system health and configuration."""
    import platform
    import shutil
    import os
    
    results = []
    
    # 1. Python Version
    py_version = platform.python_version()
    results.append({
        "check": "Python version",
        "status": "\u2705" if sys.version_info >= (3, 8) else "\u274c",
        "detail": f"Version {py_version} detected",
        "fix": "Upgrade to Python 3.8+" if sys.version_info < (3, 8) else None
    })
    
    # 2. Writable Working Directory
    cwd = Path.cwd()
    is_writable = os.access(cwd, os.W_OK)
    results.append({
        "check": "Working directory permissions",
        "status": "\u2705" if is_writable else "\u274c",
        "detail": f"{cwd} is {'writable' if is_writable else 'NOT writable'}",
        "fix": "Ensure the current directory is writable or use --store-dir"
    })
    
    # 3. project-state / store_dir presence
    store_dir = Path(getattr(args, "store_dir", "project-state"))
    exists = store_dir.exists()
    results.append({
        "check": "project-state / state store presence",
        "status": "\u2705" if exists else "\u26a0\ufe0f",
        "detail": f"{store_dir} {'exists' if exists else 'not found'}",
        "fix": "Run 'rekall init' to create a state store" if not exists else None
    })
    
    # 4. JSONL file integrity (if exists)
    integrity_ok = True
    malformed_files = []
    if exists:
        try:
            store = StateStore(store_dir)
            report = store.validate_all()
            if report["summary"]["status"] == "\u274c":
                integrity_ok = False
                malformed_files = report["jsonl_integrity"].get("malformed", [])
        except Exception as e:
            integrity_ok = False
            malformed_files = [str(e)]
            
    results.append({
        "check": "JSONL file integrity",
        "status": "\u2705" if integrity_ok else "\u274c",
        "detail": f"{len(malformed_files)} issues found" if not integrity_ok else "All files parseable",
        "fix": "If corrupted, restore from backup or remove malformed lines."
    })
    
    # 5. Dependency availability
    try:
        import yaml
        yaml_ok = True
    except ImportError:
        yaml_ok = False
        
    results.append({
        "check": "Dependencies (PyYAML)",
        "status": "\u2705" if yaml_ok else "\u274c",
        "detail": "PyYAML found" if yaml_ok else "PyYAML missing",
        "fix": "pip install PyYAML"
    })
    
    if args.json:
        print(json.dumps({"results": results, "healthy": all(r["status"] != "\u274c" for r in results)}))
    else:
        print("\n" + "="*50)
        print(f"{Theme.ICON_SEARCH} REKALL DOCTOR DIAGNOSTICS")
        print("="*50)
        
        all_passed = True
        for r in results:
            icon = r['status']
            if icon == "\u2705": icon = Theme.ICON_SUCCESS
            elif icon == "\u274c": icon = Theme.ICON_ERROR
            elif icon == "\u26a0\ufe0f": icon = Theme.ICON_WARNING
            
            print(f" {icon} {r['check']:<30} : {r['detail']}")
            if r['status'] == "\u274c":
                all_passed = False
                if r['fix']: print(f"    \ud83d\udc49 FIX: {r['fix']}")
                
        print("="*50)
        if all_passed:
            print(f"{Theme.ICON_SUCCESS} System healthy")
        else:
            print(f"{Theme.ICON_ERROR} System issues detected. Please check the checklist above.")
        print("="*50 + "\n")

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
            print(f"{Theme.ICON_SUCCESS} DEMO COMPLETE \u2014 OPEN THIS NOW:")
            print("="*50)
            print(f"\nYour boot brief is ready: {brief_file}")
            print(f"Your state artifact is dumped at: {state_dir}")
            print("\nView it now:")
            print(f"  {view_cmd}\n")
            print("-" * 50)
            print(f"{Theme.ICON_IDEA} Next Steps:")
            print("  - run 'rekall status' to see project health")
            print("  - run 'rekall guard' for preflight checks")
            print("-" * 50 + "\n")

def cmd_validate(args):
    """Validate StateStore schema and invariants, or MCP server surface."""
    # Resolve store_dir: positional arg takes precedence over --store-dir flag
    if args.store_dir is not None:
        resolved_store = args.store_dir
    else:
        resolved_store = getattr(args, "store_dir_flag", ".")
    args.store_dir = resolved_store

    # Dispatch to MCP validation if --mcp flag is set
    if getattr(args, "mcp", False):
        cmd_validate_mcp(args)
        return

    base_dir = Path(args.store_dir)

    if not base_dir.exists():
        die(ExitCode.NOT_FOUND, f"Directory {base_dir} does not exist.", args.json)
    ensure_state_initialized(base_dir, args.json)
        
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
                status = data.get("status", "\u2705")
                print(f"\n{status} {section.replace('_', ' ').title()}")
                
                if status != "\u2705":
                    for k, v in data.items():
                        if k == "status": continue
                        if isinstance(v, list) and v:
                            for item in v:
                                print(f"  - [{k}] {item}")
                        elif v:
                             print(f"  - {v}")
                             
            print("================================\n")
            
        if report["summary"]["status"] == "\u274c":
            if not args.json:
                print("\n" + "!" * 50)
                print("\U0001f6a8 VALIDATION FAILED")
                print("!" * 50)
                if "recovery" in report["summary"]:
                    print(f"\nRECOVERY GUIDANCE:\n{report['summary']['recovery']}")
                print("!" * 50 + "\n")
            sys.exit(ExitCode.VALIDATION_FAILED.value)
        elif args.strict and report["summary"]["warnings"] > 0:
            sys.exit(ExitCode.BLOCKERS_FOUND.value)
            
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Validation failed with exception: {str(e)}", args.json)


def cmd_validate_mcp(args):
    """MCP self-check: launch server, validate tools/list, schemas, and probe calls."""
    from rekall.core.mcp_validator import run_mcp_validation, format_human_report

    server_cmd = getattr(args, "server_cmd", None)
    if not server_cmd:
        die(ExitCode.VALIDATION_FAILED, "--server-cmd is required when using --mcp", args.json)

    try:
        report = run_mcp_validation(
            server_cmd=server_cmd,
            strict=args.strict,
            run_probes=True,
        )

        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(format_human_report(report))

        if not report["ok"]:
            sys.exit(ExitCode.VALIDATION_FAILED.value)

    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"MCP validation failed: {str(e)}", args.json)

def cmd_snapshot(args):
    """Compile the state store into a single standalone snapshot.json (compact format)."""
    base_dir = Path(args.store_dir)
    try:
        store = StateStore(base_dir)
        
        # Compile snapshot with deterministic ordering
        activity = sorted(store._load_stream("activity", hot_only=False), key=lambda x: (x.get("timestamp", ""), x.get("activity_id", "")))
        attempts = sorted(store._load_stream("attempts", hot_only=False), key=lambda x: (x.get("timestamp", ""), x.get("attempt_id", "")))
        decisions = sorted(store._load_stream("decisions", hot_only=False), key=lambda x: (x.get("timestamp", ""), x.get("decision_id", "")))
        timeline = sorted(store._load_stream("timeline", hot_only=False), key=lambda x: (x.get("timestamp", ""), x.get("event_id", "")))
        events = sorted(store._load_stream("work_items", hot_only=False), key=lambda x: (x.get("timestamp", ""), x.get("event_id", "")))
        
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
        
        # Core YAMLs
        for f in ["schema-version.txt", "project.yaml", "envs.yaml", "access.yaml", "manifest.json"]:
            src = base_dir / f
            if src.exists():
                shutil.copy2(src, out_dir / f)
        
        # Streams directory
        src_streams = base_dir / "streams"
        if src_streams.exists():
            shutil.copytree(src_streams, out_dir / "streams", dirs_exist_ok=True)
                
        if args.json:
            print(json.dumps({"status": "success", "export_dir": str(out_dir)}))
        else:
            logger.info(f"Exported project state to {out_dir}")
            
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Export failed: {str(e)}", args.json)

def cmd_import(args):
    """Reads from a state store folder and imports events idempotently to the target directory."""
    source_dir = Path(args.source)
    target_dir = Path(args.store_dir)
    
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
                
        for stream_name, info in source_store.manifest.get("streams", {}).items():
             records = source_store._load_stream(stream_name, hot_only=False)
             for record in records:
                 target_store.append_jsonl_idempotent(stream_name, record, info["id_field"])
                    
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
        events = sorted(store._load_stream("work_items", hot_only=False), key=lambda x: (x.get("timestamp", ""), x.get("event_id", "")))
        activity = sorted(store._load_stream("activity", hot_only=False), key=lambda x: (x.get("timestamp", ""), x.get("activity_id", "")))
        attempts = sorted(store._load_stream("attempts", hot_only=False), key=lambda x: (x.get("timestamp", ""), x.get("attempt_id", "")))
        decisions = sorted(store._load_stream("decisions", hot_only=False), key=lambda x: (x.get("timestamp", ""), x.get("decision_id", "")))
        timeline = sorted(store._load_stream("timeline", hot_only=False), key=lambda x: (x.get("timestamp", ""), x.get("event_id", "")))
        
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
    print("\nRekall: The Project Reality Blackboard + Ledger")
    print("-" * 60)
    print("FEATURES:")
    print("  * Typed Link Matrix       : Bridges Jira, Notion, Figma into a single machine-readable layer.")
    print("  * Immutable Ledgers       : JSONL ledgers for decisions, attempts, and work-item state.")
    print("  * Agent Context injection : `handoff` pack aggregates blocks, history, and goals into a boot brief.")
    print("  * MCP Server Native       : Direct read/write bindings for Claude Desktop.")
    print("\nPRIMITIVES:")
    print("  * ATTEMPTS : A typed ledger of what has been tried and why it failed.")
    print("  * DECISIONS: Explicit records of trade-offs and architectural choices.")
    print("  * TIMELINE : An immutable event log of milestones and state changes.")
    print("  * POINTERS : Typed pointers to external environments and access methods.\n")

def execute_alias_query(args, qtype: ExecutiveQueryType):
    """Wrapper to run existing ExecutiveQueries directly from CLI."""
    base_dir = Path(args.store_dir)
    ensure_state_initialized(base_dir, args.json)
        
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
            else:
                print("\u2713 No blockers detected")
            print("")
            if qtype == ExecutiveQueryType.BLOCKERS and resp.blockers:
                sys.exit(ExitCode.BLOCKERS_FOUND.value)
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
    
    # Recent approved decisions (last 3) - search HOT stream
    all_decisions = sorted(
        store._load_stream("decisions", hot_only=True),
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
    
    # Recent failed attempts (last 5)
    all_attempts = sorted(
        store._load_stream("attempts", hot_only=True),
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
    ensure_state_initialized(base_dir, args.json)
    
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
                    print("\n\u274c GUARD PREFLIGHT FAILED")
                    for p in problems:
                        print(f"  \u2717 {p}")
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
            print("\U0001f6e1  REKALL PREFLIGHT GUARD")
            print("="*55)
            print(f"  Project   : {p['name']}")
            print(f"  Goal      : {p['current_goal']}")
            print(f"  Phase     : {p['phase']}")
            print(f"  Status    : {p['status']}")
            print(f"  Confidence: {p['confidence']}")
            
            # Constraints
            cs = payload["constraints"]
            print(f"\n\U0001f4cc Constraints/Invariants ({len(cs)}):")
            if cs:
                for c in cs:
                    print(f"  \u2022 {c}")
            else:
                print("  (none defined \u2014 add 'constraints' to project.yaml)")
            
            # Decisions
            ds = payload["recent_decisions"]
            print(f"\n\U0001f4dc Most Recent Decisions ({len(ds)}):")
            for d in ds:
                print(f"  [{d['decision_id'][:8]}] {d['title']}")
                print(f"    status: {d['status']}  tradeoffs: {d['tradeoffs']}")
                if d['evidence_refs']:
                    print(f"    evidence: {d['evidence_refs']}")
            if not ds:
                print("  (no decisions recorded yet)")
            
            # Attempts
            ats = payload["recent_attempts"]
            print(f"\n\U0001f9ea Most Recent Attempts ({len(ats)}):")
            for a in ats:
                print(f"  [{a['attempt_id'][:8]}] {a['title']}")
                print(f"    outcome: {a['outcome']}  item: {a['work_item_id']}")
                if a['evidence_refs']:
                    print(f"    evidence: {a['evidence_refs']}")
            if not ats:
                print("  (no attempts recorded yet)")
            
            # Risks
            rs = payload["risks_blockers"]
            print(f"\n\u26a0\ufe0f  Top Risks/Blockers ({len(rs)}):")
            for r in rs:
                print(f"  [{r['work_item_id']}] {r['title']} ({r['status']})")
                if r['blocked_by']:
                    print(f"    blocked_by: {r['blocked_by']}")
            if not rs:
                print("  (none)")
            
            # Operate
            op = payload["operate"]
            print(f"\n\U0001f527 Operate:")
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
        idemp = getattr(args, "idempotency_key", None)
        res = store.append_attempt(attempt, actor={"actor_id": args.actor}, idempotency_key=idemp)
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
        idemp = getattr(args, "idempotency_key", None)
        res = store.propose_decision(decision, actor={"actor_id": args.actor}, idempotency_key=idemp)
        if args.json:
            print(json.dumps({"status": "success", "decision": res}))
        else:
            logger.info(f"Decision proposed: {res['decision_id']}")
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Failed to propose decision: {str(e)}", args.json)

def cmd_snapshot(args):
    """Compile the state store into a single standalone snapshot.json (compact format)."""
    store_dir = Path(args.store_dir)
    ensure_state_initialized(store_dir, args.json)
    
    try:
        store = StateStore(store_dir)
        # Full export to dict
        data = {
            "project": store._load_yaml("project.yaml"),
            "work_items": store.work_items,
            "timeline": store._load_jsonl("timeline.jsonl"),
            "decisions": store._load_jsonl("decisions.jsonl"),
            "attempts": store._load_jsonl("attempts.jsonl"),
            "activity": store._load_jsonl("activity.jsonl")
        }
        
        out_path = Path(args.out) if args.out else Path.cwd() / "snapshot.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            
        success(f"State exported to {out_path}", args.json)
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Snapshot failed: {str(e)}", args.json)

def cmd_gc(args):
    """Prunes old segment files that are already included in snapshots."""
    store_dir = Path(args.store_dir)
    ensure_state_initialized(store_dir, args.json)
    
    try:
        store = StateStore(store_dir)
        store.gc(archive=(not args.delete))
        if not args.json:
            print("\u2705 Garbage collection finished.")
        else:
            print(json.dumps({"status": "success", "message": "GC finished"}))
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"GC failed: {str(e)}", args.json)

def cmd_timeline_add(args):
    base_dir = Path(args.store_dir)
    ensure_state_initialized(base_dir, args.json)
    try:
        store = StateStore(base_dir)
        event = {
            "type": "note",
            "summary": args.summary
        }
        idemp = getattr(args, "idempotency_key", None)
        res = store.append_timeline(event, actor={"actor_id": args.actor}, idempotency_key=idemp)
        if args.json:
            print(json.dumps({"status": "success", "timeline_event_id": res['event_id']}))
        else:
            logger.info(f"Timeline event added: {res['event_id']}")
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Failed to add timeline event: {str(e)}", args.json)

def cmd_checkpoint(args):
    """Create a durable checkpoint: export state + append timeline milestone."""
    import shutil
    import datetime

    base_dir = Path(args.store_dir)
    out_dir = Path(args.out)
    label = getattr(args, "label", None) or "checkpoint"
    actor_id = getattr(args, "actor", "cli_user")
    event_id = getattr(args, "event_id", None)

    if not base_dir.exists():
        die(ExitCode.NOT_FOUND, f"Directory {base_dir} does not exist.", args.json)

    try:
        store = StateStore(base_dir)

        # 1. Folder-based export (reuse export logic)
        out_dir.mkdir(parents=True, exist_ok=True)
        # YAMLs and Manifest
        for f in ["schema-version.txt", "project.yaml", "envs.yaml", "access.yaml", "manifest.json"]:
            src = base_dir / f
            if src.exists():
                shutil.copy2(src, out_dir / f)
        
        # Streams
        src_streams = base_dir / "streams"
        if src_streams.exists():
            shutil.copytree(src_streams, out_dir / "streams", dirs_exist_ok=True)

        export_path = str(out_dir.resolve())

        # 2. Append timeline milestone
        actor = {"actor_id": actor_id}
        event = {
            "type": "milestone",
            "summary": f"Checkpoint created: {label}",
            "details": f"Exported to {export_path}",
            "evidence_links": [{"kind": "link", "id": export_path, "note": "checkpoint export path"}],
        }
        if event_id:
            event["event_id"] = event_id

        result = store.append_timeline(event, actor=actor)
        tid = result.get("event_id", "unknown")

        # 3. Output
        if args.json:
            print(json.dumps({"ok": True, "export_path": export_path, "timeline_event_id": tid}))
        else:
            print(f"\n\u2705 Checkpoint saved")
            print(f"   Export path : {export_path}")
            print(f"   Timeline ID : {tid}")
            print(f"   Label       : {label}\n")

    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Checkpoint failed: {str(e)}", args.json)


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

def cmd_onboard(args):
    """Generates an onboarding \u201ccheat sheet\u201d for a repo."""
    import datetime
    
    # Target state dir: default to project-state if not specified
    if getattr(args, "state_dir", None):
        store_dir = Path(args.state_dir)
    elif getattr(args, "dotdir", False):
        store_dir = Path(".rekall")
    else:
        store_dir = Path(getattr(args, "store_dir", "project-state"))
    
    # Auto-init if missing
    ensure_state_initialized(store_dir, args.json)

    try:
        store = StateStore(store_dir)
        
        # Integrity check: fail if JSONL is corrupted
        report = store.validate_all()
        if report["summary"]["status"] == "\u274c" and report["jsonl_integrity"]["status"] == "\u274c":
            malformed = report["jsonl_integrity"].get("malformed", [])
            errors = report["jsonl_integrity"].get("errors", [])
            msg = "; ".join(malformed + errors)
            die(ExitCode.INTERNAL_ERROR, f"Onboarding failed: corrupted state files detected. {msg}", args.json)

        repo_name = Path.cwd().name
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Get last timeline update
        last_updated = "Never"
        timeline_events = store._load_jsonl("timeline.jsonl")
        if timeline_events:
            last_event = max(timeline_events, key=lambda x: x.get("timestamp", ""))
            last_updated = last_event.get("timestamp", "Unknown")
        
        # 1. Gather data
        status_resp = query_executive_status(store, ExecutiveQueryType.ON_TRACK)
        blockers_resp = query_executive_status(store, ExecutiveQueryType.BLOCKERS)
        guard_payload = build_guard_payload(store)
        
        # 2. Build Markdown
        lines = []
        lines.append(f"# Onboarding Cheat Sheet: {repo_name}")
        lines.append(f"**Generated**: {timestamp}")
        lines.append(f"**Ledger Last Updated**: {last_updated}")
        lines.append("")
        
        lines.append("## What is Rekall?")
        lines.append("Rekall is a project state ledger for AI agents and human collaborators.")
        lines.append("It tracks decisions, attempts, and work items as a machine-readable event stream.")
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
                wid = b.get('work_item_id')
                title = b.get('title', 'Untitled')
                lines.append(f"- **{wid}**: {title}")
        else:
            lines.append("No blockers detected.")
        lines.append("")
        
        lines.append("## State Artifact Layout")
        lines.append("```text")
        lines.append(f"{store_dir.name}/")
        lines.append("\u251c\u2500\u2500 project.yaml          # Project identity & goals")
        lines.append("\u251c\u2500\u2500 manifest.json         # Stream index")
        lines.append("\u251c\u2500\u2500 streams/              # Partitioned event streams")
        lines.append("\u2502   \u2514\u2500\u2500 work_items/")
        lines.append("\u2502       \u251c\u2500\u2500 active.jsonl  # Hot events")
        lines.append("\u2502       \u2514\u2500\u2500 snapshot.json # Fast-load state")
        lines.append("\u2514\u2500\u2500 artifacts/            # Generated summaries & briefs")
        lines.append("```")
        lines.append("")
        
        lines.append("## How to update state")
        lines.append("If you try something and fail, add an attempt:")
        lines.append("`rekall attempts add REQ-1 --title \"Tried changing font size\" --evidence \"UI broke\"`")
        lines.append("If you make an architectural choice, propose a decision:")
        lines.append("`rekall decisions propose --title \"Use Postgres\" --rationale \"Need relational data\" --tradeoffs \"Heavier than SQLite\"`")
        lines.append("")
        
        lines.append("## Next Recommended Commands")
        lines.append("```bash")
        lines.append("rekall status")
        lines.append("rekall guard")
        lines.append("rekall blockers")
        lines.append(f"rekall handoff {store.project_config.get('project_id', repo_name)} -o ./handoff/")
        lines.append("```")
        lines.append("")

        lines.append("## Links")
        lines.append("- [Quickstart Guide](https://github.com/run-rekall/rekall#quick-start-for-humans--agents)")
        lines.append("- [BETA.md](https://github.com/run-rekall/rekall/blob/main/docs/BETA.md)")
        lines.append("- [GitHub Discussions](https://github.com/run-rekall/rekall/discussions)")
        
        content = "\n".join(lines)
        
        # 3. Write to file
        artifacts_dir = store_dir / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)
        
        out_path = Path(args.out) if args.out else artifacts_dir / "onboard_cheatsheet.md"
        
        if out_path.exists() and not args.force:
            die(ExitCode.CONFLICT, f"File {out_path} already exists. Use --force to overwrite.", args.json)
            
        out_path.write_text(content, encoding="utf-8")
        
        # 4. Success output
        if args.print:
            print("\n--- ONBOARDING CHEAT SHEET ---")
            print(content)
            print("--- END OF CHEAT SHEET ---\n")
            
        if args.json:
            print(json.dumps({"status": "success", "path": str(out_path)}))
        else:
            print(f"Created: {out_path}")
            print(f"Next: rekall status | rekall blockers | rekall handoff {store.project_config.get('project_id', repo_name)}")

    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Onboarding failed: {str(e)}", args.json, debug=args.debug)

def main():
    # Detect terminal capabilities and set icons accordingly
    Theme.autoprobe()
    
    # Reconfigure stdout/stderr to handle Unicode on Windows (cp1252 falls back to ?)
    # This prevents UnicodeEncodeError when printing emojis.
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "reconfigure"):
            try:
                if sys.platform == "win32":
                    # Force UTF-8 on Windows for better emoji support in modern terminals
                    stream.reconfigure(encoding='utf-8', errors='replace')
                else:
                    stream.reconfigure(errors='replace')
            except Exception:
                try:
                    stream.reconfigure(errors='replace')
                except Exception:
                    pass
    
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
    parser.add_argument("--debug", action="store_true", help="Show full stack traces on failure")
    
    # Shared flags parent so --json/--quiet/--debug work after subcommand args too
    shared_flags = argparse.ArgumentParser(add_help=False)
    shared_flags.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    shared_flags.add_argument("--quiet", "-q", action="store_true", help=argparse.SUPPRESS)
    shared_flags.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)
    
    subparsers = parser.add_subparsers(dest="command", required=True, title="Commands", metavar="")
    
    # Try It
    parser_demo = subparsers.add_parser("demo", help="[Try] Run a 1-click demo to see Rekall in action.", parents=[shared_flags])
    parser_demo.set_defaults(func=cmd_demo)
    
    parser_features = subparsers.add_parser("features", help="[Try] Print capability map and 'Not Kanban' explainer.", parents=[shared_flags])
    parser_features.set_defaults(func=cmd_features)
    
    # Init
    parser_init = subparsers.add_parser("init", help="[Portability] Initialize a new Rekall directory.", parents=[shared_flags])
    parser_init.add_argument("store_dir", nargs="?", default="project-state", help="Directory to initialize")
    parser_init.set_defaults(func=cmd_init)
    
    # Doctor
    parser_doctor = subparsers.add_parser("doctor", help="[Health] Run diagnostics on the system and configuration.", parents=[shared_flags])
    parser_doctor.add_argument("store_dir", nargs="?", default="project-state", help="Directory of the StateStore to check")
    parser_doctor.set_defaults(func=cmd_doctor)
    
    # Validate
    parser_validate = subparsers.add_parser("validate", help="[Status] Validate the StateStore invariants (or MCP surface with --mcp).", parents=[shared_flags])
    parser_validate.add_argument("store_dir", nargs="?", default=None, help="Directory of the StateStore (positional, or use --store-dir)")
    parser_validate.add_argument("--store-dir", dest="store_dir_flag", default=".", help="Directory of the StateStore")
    parser_validate.add_argument("--strict", action="store_true", help="Fail with ExitCode 3 on warnings")
    parser_validate.add_argument("--mcp", action="store_true", help="Run MCP server self-check instead of StateStore validation")
    parser_validate.add_argument("--server-cmd", default=None, help="Server launch command for MCP validation (required with --mcp)")
    parser_validate.set_defaults(func=cmd_validate)
    
    # Portability
    parser_export = subparsers.add_parser("export", help="[Portability] Export to a new directory.", parents=[shared_flags])
    parser_export.add_argument("--store-dir", default=".", help="Directory of the StateStore")
    parser_export.add_argument("--out", "-o", required=True, help="Output directory path")
    parser_export.set_defaults(func=cmd_export)
    
    parser_snapshot = subparsers.add_parser("snapshot", help="[Portability] Export to a single snapshot.json blob.", parents=[shared_flags])
    parser_snapshot.add_argument("--store-dir", default=".", help="Directory of the StateStore")
    parser_snapshot.add_argument("--out", "-o", help="Output JSON file path")
    parser_snapshot.set_defaults(func=cmd_snapshot)
    
    # GC
    parser_gc = subparsers.add_parser("gc", help="[Health] Prune old segments captured in snapshots.", parents=[shared_flags])
    parser_gc.add_argument("store_dir", nargs="?", default="project-state", help="Directory of the StateStore")
    parser_gc.add_argument("--delete", action="store_true", help="Delete segments instead of archiving them")
    parser_gc.set_defaults(func=cmd_gc)
    
    parser_import = subparsers.add_parser("import", help="[Portability] Import events from a source folder.", parents=[shared_flags])
    parser_import.add_argument("source", help="Path to source state store folder")
    parser_import.add_argument("--store-dir", default=".", help="Target Directory of the StateStore")
    parser_import.set_defaults(func=cmd_import)
    
    # Handoff
    parser_handoff = subparsers.add_parser("handoff", help="[Handoff] Create a boot_brief.md context pack.", parents=[shared_flags])
    parser_handoff.add_argument("project_id", help="The Project ID being handed off")
    parser_handoff.add_argument("--store-dir", default=".", help="Directory of the current StateStore")
    parser_handoff.add_argument("--out", "-o", required=True, help="Output directory")
    parser_handoff.set_defaults(func=cmd_handoff)
    
    # Aliases
    parser_status = subparsers.add_parser("status", help="[Status] Query items ON_TRACK.", parents=[shared_flags])
    parser_status.add_argument("--store-dir", default=".", help="Directory of the current StateStore")
    parser_status.set_defaults(func=cmd_alias_status)
    
    parser_blockers = subparsers.add_parser("blockers", help="[Status] Query items BLOCKERS.", parents=[shared_flags])
    parser_blockers.add_argument("--store-dir", default=".", help="Directory of the current StateStore")
    parser_blockers.set_defaults(func=cmd_alias_blockers)
    
    parser_resume = subparsers.add_parser("resume", help="[Status] Query actions to RESUME.", parents=[shared_flags])
    parser_resume.add_argument("--store-dir", default=".", help="Directory of the current StateStore")
    parser_resume.set_defaults(func=cmd_alias_resume)

    # Guard
    parser_guard = subparsers.add_parser("guard", help="[Preflight] Drift guard / invariant preflight check.", parents=[shared_flags])
    parser_guard.add_argument("--store-dir", default=".", help="Directory of the StateStore")
    parser_guard.add_argument("--strict", action="store_true", help="Exit non-zero if constraints or decisions missing")
    parser_guard.add_argument("--emit-timeline", action="store_true", help="Append a timeline event recording this guard run")
    parser_guard.add_argument("--actor", default="cli_user", help="Actor ID for timeline events")
    parser_guard.set_defaults(func=cmd_guard)

    # Grievance Closeout Commands: Nested subparsers
    parser_attempts = subparsers.add_parser("attempts", help="[Log] Manage attempt logs.", parents=[shared_flags])
    attempts_subparsers = parser_attempts.add_subparsers(dest="subcommand", required=True)
    
    parser_attempts_add = attempts_subparsers.add_parser("add", help="Add an attempt with evidence.")
    parser_attempts_add.add_argument("work_item_id", help="The Work Item ID")
    parser_attempts_add.add_argument("--title", required=True, help="Title of the attempt")
    parser_attempts_add.add_argument("--evidence", required=True, help="Evidence path or link")
    parser_attempts_add.add_argument("--store-dir", default=".", help="Directory of the StateStore")
    parser_attempts_add.add_argument("--actor", default="cli_user", help="Actor ID")
    parser_attempts_add.add_argument("--idempotency-key", default=None, help="Optional string to deduplicate records")
    parser_attempts_add.set_defaults(func=cmd_attempts_add)
    
    parser_decisions = subparsers.add_parser("decisions", help="[Log] Manage project decisions.", parents=[shared_flags])
    decisions_subparsers = parser_decisions.add_subparsers(dest="subcommand", required=True)
    
    parser_decisions_propose = decisions_subparsers.add_parser("propose", help="Propose a decision with rationale and tradeoffs.")
    parser_decisions_propose.add_argument("--title", required=True, help="Title of the decision")
    parser_decisions_propose.add_argument("--rationale", required=True, help="Why this decision is proposed")
    parser_decisions_propose.add_argument("--tradeoffs", required=True, help="Tradeoffs considered")
    parser_decisions_propose.add_argument("--store-dir", default=".", help="Directory of the StateStore")
    parser_decisions_propose.add_argument("--actor", default="cli_user", help="Actor ID")
    parser_decisions_propose.add_argument("--idempotency-key", default=None, help="Optional string to deduplicate records")
    parser_decisions_propose.set_defaults(func=cmd_decisions_propose)
    
    parser_timeline = subparsers.add_parser("timeline", help="[Log] Manage timeline events.", parents=[shared_flags])
    timeline_subparsers = parser_timeline.add_subparsers(dest="subcommand", required=True)
    
    parser_timeline_add = timeline_subparsers.add_parser("add", help="Add a timeline event.")
    parser_timeline_add.add_argument("--summary", required=True, help="Summary of the timeline event")
    parser_timeline_add.add_argument("--store-dir", default=".", help="Directory of the StateStore")
    parser_timeline_add.add_argument("--actor", default="cli_user", help="Actor ID")
    parser_timeline_add.add_argument("--idempotency-key", default=None, help="Optional string to deduplicate records")
    parser_timeline_add.set_defaults(func=cmd_timeline_add)
    
    parser_lock = subparsers.add_parser("lock", help="[Workflow] Acquire an exclusive lease/lock on a work item.", parents=[shared_flags])
    parser_lock.add_argument("work_item_id", help="The Work Item ID")
    parser_lock.add_argument("--expected-version", type=int, required=True, help="Expected version of the item")
    parser_lock.add_argument("--ttl", default="5m", help="Time to live (lease duration), e.g. 5m, 1h. Default 5m.")
    parser_lock.add_argument("--force", action="store_true", help="Force acquire the lock")
    parser_lock.add_argument("--store-dir", default=".", help="Directory of the StateStore")
    parser_lock.add_argument("--actor", default="cli_user", help="Actor ID")
    parser_lock.set_defaults(func=cmd_lock)

    # Checkpoint
    parser_checkpoint = subparsers.add_parser("checkpoint", help="[Resilience] Export state + mark timeline milestone (local save-game).", parents=[shared_flags])
    parser_checkpoint.add_argument("project_id", help="The Project ID being checkpointed")
    parser_checkpoint.add_argument("--out", "-o", required=True, help="Output directory for the checkpoint export")
    parser_checkpoint.add_argument("--store-dir", default=".", help="Directory of the StateStore")
    parser_checkpoint.add_argument("--label", default="checkpoint", help="Human-readable label for this checkpoint")
    parser_checkpoint.add_argument("--actor", default="cli_user", help="Actor ID")
    parser_checkpoint.add_argument("--event-id", default=None, help="Explicit event_id for idempotent timeline append")
    parser_checkpoint.set_defaults(func=cmd_checkpoint)

    # Onboard
    parser_onboard = subparsers.add_parser("onboard", help="[Handoff] Generate a repository onboarding cheat sheet.", parents=[shared_flags])
    parser_onboard.add_argument("--store-dir", default="project-state", help="Directory of the state store (default: project-state)")
    parser_onboard.add_argument("--state-dir", help="Custom state directory (e.g. .rekall)")
    parser_onboard.add_argument("--dotdir", action="store_true", help="Shortcut for --state-dir .rekall")
    parser_onboard.add_argument("--print", action="store_true", help="Also print the cheat sheet to stdout")
    parser_onboard.add_argument("--out", "-o", help="Custom output path for the cheat sheet")
    parser_onboard.add_argument("--force", action="store_true", help="Overwrite if file exists")
    parser_onboard.set_defaults(func=cmd_onboard)

    args = parser.parse_args()

    setup_logging(args.json, getattr(args, "quiet", False))
    
    try:
        args.func(args)
    except SystemExit as e:
        sys.exit(e.code)
    except KeyboardInterrupt:
        die(ExitCode.USER_ERROR, "Operation cancelled by user.", getattr(args, "json", False))
    except Exception as e:
        # Success Criterion 4: Global exception wrapper
        # Suppress traceback unless --debug
        msg = str(e) or "An unexpected error occurred."
        die(ExitCode.INTERNAL_ERROR, msg, getattr(args, "json", False), debug=getattr(args, "debug", False))
    
if __name__ == "__main__":
    main()
