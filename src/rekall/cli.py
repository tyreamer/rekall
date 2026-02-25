import argparse
import sys
import json
from pathlib import Path
import logging

from rekall.core.state_store import StateStore
from rekall.core.handoff_generator import generate_boot_brief

logger = logging.getLogger(__name__)

def setup_logging(json_mode: bool = False):
    if json_mode:
        logging.basicConfig(level=logging.ERROR, format="%(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def cmd_init(args):
    """Initializes a new Rekall project state directory."""
    base_dir = Path(args.store_dir)
    
    if base_dir.exists() and any(base_dir.iterdir()):
        logger.error(f"Directory {base_dir} is not empty.")
        if args.json: print(json.dumps({"error": f"Directory {base_dir} is not empty."}))
        sys.exit(1)
        
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
        logger.error(f"Init failed: {str(e)}")
        if args.json: print(json.dumps({"error": str(e)}))
        sys.exit(1)

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
            print("\n" + "="*50)
            print("🚀 DEMO COMPLETE: REKALL PROJECT STATE GENERATED 🚀")
            print("="*50)
            print(f"\nWe just seeded a mock project, injected 2 work items, validated the local ledger implicitly, and ran the executive handoff synthesis.\n")
            print("To see the magic, copy and run this command:\n")
            print(f"  cat {out_dir}/boot_brief.md\n")
            print("-" * 50)
            print("Ready to integrate Rekall with your agents or team?")
            print("  1. Run `rekall init ./project-state` in your repo.")
            print("  2. Boot the MCP server: `python -m rekall.server.mcp_server`.")
            print("-" * 50 + "\n")

def cmd_validate(args):
    """Validate StateStore schema and invariants."""
    base_dir = Path(args.store_dir)
    if not base_dir.exists():
        logger.error(f"Directory {base_dir} does not exist.")
        if args.json: print(json.dumps({"error": f"Directory {base_dir} does not exist."}))
        sys.exit(1)
        
    try:
        # We instantiate StateStore but don't want it to crash if schema-version is missing during init,
        # so we might need a raw validate. Actually, StateStore.initialize() raises exceptions. 
        # Let's bypass full init for validate so it can report *all* errors instead of crashing on the first.
        # But for now, let's wrap the init:
        try:
            store = StateStore(base_dir)
        except Exception as e:
            if args.json:
                print(json.dumps({"summary": {"status": "❌", "errors": 1, "warnings": 0}, "init_error": str(e)}))
            else:
                logger.error(f"Validation failed during initialization: {str(e)}")
            sys.exit(1)
            
        report = store.validate_all(strict=args.strict)
        
        if args.json:
            print(json.dumps(report, indent=2))
        else:
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
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Validation failed with exception: {str(e)}")
        if args.json: print(json.dumps({"error": str(e)}))
        sys.exit(1)

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
        logger.error(f"Snapshot failed: {str(e)}")
        if args.json: print(json.dumps({"error": str(e)}))
        sys.exit(1)

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
        logger.error(f"Export failed: {str(e)}")
        if args.json: print(json.dumps({"error": str(e)}))
        sys.exit(1)

def cmd_import(args):
    """Reads from a state store folder and imports events idempotently to the target directory."""
    target_dir = Path(args.store_dir)
    source_dir = Path(args.source)
    
    if not source_dir.exists() or not (source_dir / "schema-version.txt").exists():
        logger.error(f"Source directory {source_dir} is not a valid state store.")
        if args.json: print(json.dumps({"error": "Invalid source directory."}))
        sys.exit(1)
        
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
        logger.error(f"Import failed: {str(e)}")
        if args.json: print(json.dumps({"error": str(e)}))
        sys.exit(1)

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
        logger.error(f"Handoff failed: {str(e)}")
        sys.exit(1)

def main():
    setup_logging()
    parser = argparse.ArgumentParser(description="Rekall CLI utility for portability and validation.")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # init
    parser_init = subparsers.add_parser("init", help="Initialize a new Rekall project-state directory.")
    parser_init.add_argument("store_dir", nargs="?", default="project-state", help="Directory to initialize (default: project-state/)")
    parser_init.set_defaults(func=cmd_init)
    
    # demo
    parser_demo = subparsers.add_parser("demo", help="Run a quick 1-click demo to see Rekall in action.")
    parser_demo.set_defaults(func=cmd_demo)
    
    # validate
    parser_validate = subparsers.add_parser("validate", help="Validate the StateStore invariants and schema.")
    parser_validate.add_argument("--store-dir", default=".", help="Directory of the StateStore (default: current directory)")
    parser_validate.add_argument("--strict", action="store_true", help="Fail with non-zero exit code on warnings as well as errors")
    parser_validate.set_defaults(func=cmd_validate)
    
    # export
    parser_export = subparsers.add_parser("export", help="Export StateStore to a new directory (YAML+JSONL folder format).")
    parser_export.add_argument("--store-dir", default=".", help="Directory of the StateStore")
    parser_export.add_argument("--out", "-o", required=True, help="Output directory path")
    parser_export.set_defaults(func=cmd_export)
    
    # snapshot
    parser_snapshot = subparsers.add_parser("snapshot", help="Export StateStore to a single snapshot.json blob.")
    parser_snapshot.add_argument("--store-dir", default=".", help="Directory of the StateStore")
    parser_snapshot.add_argument("--out", "-o", help="Output JSON file path (default: stdout)")
    parser_snapshot.set_defaults(func=cmd_snapshot)
    
    # import
    parser_import = subparsers.add_parser("import", help="Import events from a source state store folder into the target folder.")
    parser_import.add_argument("source", help="Path to source state store folder")
    parser_import.add_argument("--store-dir", default=".", help="Target Directory of the StateStore")
    parser_import.set_defaults(func=cmd_import)
    
    # handoff
    parser_handoff = subparsers.add_parser("handoff", help="Create a handoff pack (boot_brief.md and snapshot.json)")
    parser_handoff.add_argument("project_id", help="The Project ID being handed off")
    parser_handoff.add_argument("--store-dir", default=".", help="Directory of the current StateStore")
    parser_handoff.add_argument("--out", "-o", required=True, help="Output directory for the handoff pack")
    parser_handoff.set_defaults(func=cmd_handoff)
    
    args = parser.parse_args()
    setup_logging(args.json)
    args.func(args)
    
if __name__ == "__main__":
    main()
