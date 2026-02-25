import argparse
import sys
import json
from pathlib import Path
import logging

from rekall.core.state_store import StateStore
from rekall.core.handoff_generator import generate_boot_brief

logger = logging.getLogger(__name__)

def setup_logging():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def cmd_validate(args):
    """Validate StateStore schema and invariants."""
    base_dir = Path(args.store_dir)
    if not base_dir.exists():
        logger.error(f"Directory {base_dir} does not exist.")
        sys.exit(1)
        
    try:
        store = StateStore(base_dir)
        # Check dangling links and basic structure
        validation_errors = []
        
        # Check for required semantic fields
        for wid, item in store.work_items.items():
            if not item.get("title"):
                validation_errors.append(f"Work item {wid} missing 'title'")
            if "status" not in item:
                validation_errors.append(f"Work item {wid} missing 'status'")
                
            # Check dependencies
            deps = item.get("dependencies", {})
            blocked_by = deps.get("blocked_by", [])
            for blocker in blocked_by:
                if blocker not in store.work_items:
                    validation_errors.append(f"Work item {wid} has dangling dependency: {blocker}")
                    
        if validation_errors:
            logger.error("Validation failed:")
            for err in validation_errors:
                logger.error(f" - {err}")
            sys.exit(1)
            
        logger.info(f"Validation successful: {len(store.work_items)} work items validated.")
    except Exception as e:
        logger.error(f"Validation failed with exception: {str(e)}")
        sys.exit(1)

def cmd_export(args):
    """Compile the state store into a single standalone snapshot.json (compact format)."""
    base_dir = Path(args.store_dir)
    try:
        store = StateStore(base_dir)
        
        # Compile snapshot
        # Load attempts, decisions, timeline as well for a complete snapshot
        activity = store._load_jsonl("activity.jsonl")
        attempts = store._load_jsonl("attempts.jsonl")
        decisions = store._load_jsonl("decisions.jsonl")
        timeline = store._load_jsonl("timeline.jsonl")
        events = store._load_jsonl("work-items.jsonl")
        
        snapshot = {
            "project": store.project_config,
            "envs": store.envs_config,
            "access": store.access_config,
            "work_items": store.work_items,
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
        else:
            print(json.dumps(snapshot, indent=2))
            
    except Exception as e:
        logger.error(f"Export failed: {str(e)}")
        sys.exit(1)

def cmd_import(args):
    """Reads a snapshot.json and writes it to the local StateStore directory (idempotently)."""
    base_dir = Path(args.store_dir)
    snapshot_file = Path(args.snapshot)
    
    if not snapshot_file.exists():
        logger.error(f"Snapshot file {snapshot_file} does not exist.")
        sys.exit(1)
        
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
        snapshot = json.loads(snapshot_file.read_text())
        
        # Write schema version
        schema_file = base_dir / "schema-version.txt"
        schema_file.write_text(snapshot.get("schema_version", "0.1"))
        
        # Write yamls safely
        import yaml
        
        def write_yaml(filename, data):
            if data:
                with open(base_dir / filename, "w", encoding="utf-8") as f:
                    yaml.dump(data, f)
                    
        write_yaml("project.yaml", snapshot.get("project", {}))
        write_yaml("envs.yaml", snapshot.get("envs", {}))
        write_yaml("access.yaml", snapshot.get("access", {}))
        
        # We need a StateStore to enforce invariants while appending jsonl, but we might just overwrite
        # the entire store or use idempotent append. The instructions say "reads a snapshot.json and writes 
        # it to the local StateStore directory (idempotently replacing or appending events)".
        # Let's instantiate StateStore and use append_jsonl_idempotent
        
        store = StateStore(base_dir) # now valid because we wrote schema-version and yamls
        
        # Import work Item events safely
        for event in snapshot.get("events", []):
            store.append_jsonl_idempotent("work-items.jsonl", event, "event_id")
            
        for act in snapshot.get("activity", []):
            store.append_jsonl_idempotent("activity.jsonl", act, "activity_id")
            
        for attempt in snapshot.get("attempts", []):
            store.append_jsonl_idempotent("attempts.jsonl", attempt, "attempt_id")
            
        for dec in snapshot.get("decisions", []):
            store.append_jsonl_idempotent("decisions.jsonl", dec, "decision_id")
            
        for t in snapshot.get("timeline", []):
            store.append_jsonl_idempotent("timeline.jsonl", t, "event_id")
            
        logger.info(f"Import from {snapshot_file} to {base_dir} successful.")
    except Exception as e:
        logger.error(f"Import failed: {str(e)}")
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
        
        # Compile snapshot
        events = store._load_jsonl("work-items.jsonl")
        activity = store._load_jsonl("activity.jsonl")
        attempts = store._load_jsonl("attempts.jsonl")
        decisions = store._load_jsonl("decisions.jsonl")
        timeline = store._load_jsonl("timeline.jsonl")
        
        snapshot = {
            "project": store.project_config,
            "envs": store.envs_config,
            "access": store.access_config,
            "work_items": store.work_items,
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
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # validate
    parser_validate = subparsers.add_parser("validate", help="Validate the StateStore invariants and schema.")
    parser_validate.add_argument("--store-dir", default=".", help="Directory of the StateStore (default: current directory)")
    parser_validate.set_defaults(func=cmd_validate)
    
    # export
    parser_export = subparsers.add_parser("export", help="Export StateStore to a single snapshot.json")
    parser_export.add_argument("--store-dir", default=".", help="Directory of the StateStore")
    parser_export.add_argument("--out", "-o", help="Output JSON file path (default: stdout)")
    parser_export.set_defaults(func=cmd_export)
    
    # import
    parser_import = subparsers.add_parser("import", help="Import a snapshot.json into a StateStore directory")
    parser_import.add_argument("snapshot", help="Path to snapshot.json")
    parser_import.add_argument("--store-dir", default=".", help="Target Directory of the StateStore")
    parser_import.set_defaults(func=cmd_import)
    
    # handoff
    parser_handoff = subparsers.add_parser("handoff", help="Create a handoff pack (boot_brief.md and snapshot.json)")
    parser_handoff.add_argument("project_id", help="The Project ID being handed off")
    parser_handoff.add_argument("--store-dir", default=".", help="Directory of the current StateStore")
    parser_handoff.add_argument("--out", "-o", required=True, help="Output directory for the handoff pack")
    parser_handoff.set_defaults(func=cmd_handoff)
    
    args = parser.parse_args()
    args.func(args)
    
if __name__ == "__main__":
    main()
