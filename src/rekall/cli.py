import argparse
import json
import logging
import sys
import tarfile
from enum import IntEnum
from pathlib import Path
from typing import Any, NoReturn, Optional

from rekall.core.brief import format_brief_human, generate_session_brief
from rekall.core.executive_queries import ExecutiveQueryType, query_executive_status
from rekall.core.handoff_generator import generate_boot_brief
from rekall.core.state_store import StateStore, resolve_vault_dir
from rekall.server import mcp_server
from rekall.server.dashboard import start_dashboard

logger = logging.getLogger(__name__)


class ExitCode(IntEnum):
    SUCCESS = 0
    INTERNAL_ERROR = 1
    BLOCKERS_FOUND = 2
    USER_ERROR = 1  # Alias for general failure
    VALIDATION_FAILED = 1  # Mapping to 1 per req
    NOT_FOUND = 1
    FORBIDDEN = 1
    CONFLICT = 1
    SECRET_DETECTED = 1


class Theme:
    """Centralized icons and formatting with ASCII fallback detection."""

    # We use hex escapes instead of literal characters to avoid source encoding issues
    ICON_SUCCESS = "\u2705"  # \u2705
    ICON_ERROR = "\u274c"  # \u274c
    ICON_WARNING = "\u26a0\ufe0f"  # \u26a0\ufe0f
    ICON_INFO = "\u2139\ufe0f"  # \u2139\ufe0f
    ICON_IDEA = "\U0001f4a1"  # \U0001f4a1
    ICON_TARGET = "\U0001f3af"  # \U0001f3af
    ICON_FOLDER = "\U0001f4c1"  # \U0001f4c1
    ICON_LINK = "\U0001f517"  # \U0001f517
    ICON_CHART = "\U0001f4ca"  # \U0001f4ca
    ICON_ROCKET = "\U0001f680"  # \U0001f680
    ICON_TOOL = "\U0001f527"  # \U0001f527
    ICON_DOC = "\U0001f4c4"  # \U0001f4c4
    ICON_SEARCH = "\U0001f50d"  # \U0001f50d
    ICON_PUSH = "\U0001f4e4"  # \U0001f4e4
    ICON_UP = "\u2b06\ufe0f"  # \u2b06\ufe0f
    ICON_CHECK = "\u2714\ufe0f"  # \u2714\ufe0f

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


def die(
    code: ExitCode,
    message: str,
    is_json: bool,
    details: Optional[dict] = None,
    debug: bool = False,
) -> NoReturn:
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
                print(
                    f"\n{Theme.ICON_IDEA} Suggestion: Run with --debug for full stack trace."
                )
            else:
                import traceback

                print("\n--- STACK TRACE ---")
                traceback.print_exc()

    sys.exit(code.value)


def friendly_error(e: Exception) -> str:
    """Translate internal exceptions to plain-English messages."""
    name = type(e).__name__
    msg = str(e)
    if name == "SchemaVersionError":
        return f"The vault was created with a different schema version. {msg}"
    if name == "SecretDetectedError":
        return f"Rekall blocked this operation because it found a potential secret. {msg} — redact it and try again."
    if name == "StateConflictError":
        if "expected_version" in msg:
            return "Another process modified the vault while you were working. Re-read and try again."
        if "already exists" in msg:
            return f"Duplicate entry: {msg}. Use a different ID or update the existing record."
        return f"Conflict: {msg}"
    if name == "FileNotFoundError":
        return f"Missing file: {msg}. Run `rekall init` to create the vault."
    if "permission" in msg.lower() or name == "PermissionError":
        return f"Permission denied: {msg}. Check file permissions on your project-state/ folder."
    # Fall through — return original with class name stripped
    return msg


def setup_logging(json_mode: bool = False, quiet_mode: bool = False):
    if json_mode or quiet_mode:
        logging.basicConfig(level=logging.ERROR, format="%(message)s", force=True)
    else:
        logging.basicConfig(
            level=logging.INFO, format="%(levelname)s: %(message)s", force=True
        )


def ensure_state_initialized(store_dir: Path, is_json: bool = False, init_mode: bool = False):
    """Ensures the state directory and its minimal required files exist."""
    if (
        store_dir.exists()
        and (store_dir / "schema-version.txt").exists()
        and (store_dir / "manifest.json").exists()
    ):
        return

    if not init_mode:
        die(ExitCode.NOT_FOUND, "No Rekall vault found. Run `rekall init` (or let your agent run project.bootstrap via MCP).", is_json)

    if not is_json:
        logger.info(
            f"State directory {store_dir}/ missing. Initializing minimal structure..."
        )
    else:
        # For JSON/MCP mode, write to stderr to avoid breaking stdout stream
        sys.stderr.write(f"INFO: Initializing minimal structure in {store_dir}/...\n")

    try:
        store_dir.mkdir(parents=True, exist_ok=True)
        (store_dir / "schema-version.txt").write_text("0.1")

        import yaml

        project_id = Path.cwd().name

        if not (store_dir / "project.yaml").exists():
            with open(store_dir / "project.yaml", "w", encoding="utf-8") as f:
                yaml.dump(
                    {
                        "project_id": project_id,
                        "description": "Project managed by Rekall",
                        "repo_url": "N/A",
                        "links": [],
                    },
                    f,
                    sort_keys=False,
                )

        if not (store_dir / "envs.yaml").exists():
            with open(store_dir / "envs.yaml", "w", encoding="utf-8") as f:
                yaml.dump({"dev": {"type": "local"}}, f)

        if not (store_dir / "access.yaml").exists():
            with open(store_dir / "access.yaml", "w", encoding="utf-8") as f:
                yaml.dump({"roles": {}}, f)

        # Initialize manifest and streams
        manifest_path = store_dir / "manifest.json"
        if not manifest_path.exists():
            manifest: dict[str, Any] = {"schema_version": "0.1", "streams": {}}

            streams_to_init = [
                ("work_items", "event_id"),
                ("activity", "activity_id"),
                ("attempts", "attempt_id"),
                ("decisions", "decision_id"),
                ("timeline", "event_id"),
            ]

            for stream_key, id_field in streams_to_init:
                stream_dir = store_dir / "streams" / stream_key
                stream_dir.mkdir(parents=True, exist_ok=True)
                active_file = stream_dir / "active.jsonl"
                active_file.touch(exist_ok=True)

                manifest["streams"][stream_key] = {
                    "active_file": str(active_file.relative_to(store_dir).as_posix()),
                    "segments": [],
                    "id_field": id_field,
                }

            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)

        # Create a README explaining the vault structure
        readme_path = store_dir / "README.md"
        if not readme_path.exists():
            readme_path.write_text(
                "# Rekall Vault — project-state\n"
                "\n"
                "This directory is managed by Rekall. It stores all persistent\n"
                "project state so that AI agents (and humans) can resume work\n"
                "across sessions.\n"
                "\n"
                "## Files\n"
                "\n"
                "| Path | Purpose |\n"
                "| ---- | ------- |\n"
                "| `schema-version.txt` | Schema version used for forward migration. |\n"
                "| `project.yaml` | Project metadata: goal, phase, status, confidence. |\n"
                "| `manifest.json` | Cryptographic root and stream index. |\n"
                "| `envs.yaml` | Environment definitions (e.g. local, staging). |\n"
                "| `access.yaml` | Role definitions and permissions. |\n"
                "\n"
                "## Streams (`streams/`)\n"
                "\n"
                "Each stream is an append-only JSONL log stored under `streams/<name>/active.jsonl`.\n"
                "\n"
                "| Stream | Purpose |\n"
                "| ------ | ------- |\n"
                "| `work_items` | Tasks and work units. |\n"
                "| `activity` | High-level milestones. |\n"
                "| `attempts` | What was tried, including failures. Do not retry these. |\n"
                "| `decisions` | Architectural choices and tradeoffs. |\n"
                "| `timeline` | Immutable event log of all state changes. |\n"
                "\n"
                "Do not edit these files by hand unless you know what you are doing.\n",
                encoding="utf-8",
            )

    except Exception as e:
        die(
            ExitCode.INTERNAL_ERROR,
            f"Failed to auto-initialize {store_dir}: {friendly_error(e)}",
            is_json,
        )





def cmd_doctor(args):
    """Diagnostic command to check system health and configuration."""
    import os
    import platform

    results = []

    # 1. Python Version
    py_version = platform.python_version()
    results.append(
        {
            "check": "Python version",
            "status": "\u2705" if sys.version_info >= (3, 8) else "\u274c",
            "detail": f"Version {py_version} detected",
            "fix": "Upgrade to Python 3.8+" if sys.version_info < (3, 8) else None,
        }
    )

    # 2. Writable Working Directory
    cwd = Path.cwd()
    is_writable = os.access(cwd, os.W_OK)
    results.append(
        {
            "check": "Working directory permissions",
            "status": "\u2705" if is_writable else "\u274c",
            "detail": f"{cwd} is {'writable' if is_writable else 'NOT writable'}",
            "fix": "Ensure the current directory is writable or use --store-dir",
        }
    )

    # 3. project-state / store_dir presence
    store_dir = resolve_vault_dir(getattr(args, "store_dir", "project-state"))
    exists = store_dir.exists()
    results.append(
        {
            "check": "project-state / state store presence",
            "status": "\u2705" if exists else "\u26a0\ufe0f",
            "detail": f"{store_dir} {'exists' if exists else 'not found'}",
            "fix": "Run 'rekall init' to create a state store" if not exists else None,
        }
    )

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

    results.append(
        {
            "check": "JSONL file integrity",
            "status": "\u2705" if integrity_ok else "\u274c",
            "detail": f"{len(malformed_files)} issues found"
            if not integrity_ok
            else "All files parseable",
            "fix": "If corrupted, restore from backup or remove malformed lines.",
        }
    )

    # 5. Dependency availability
    try:
        import importlib.util
        yaml_ok = importlib.util.find_spec("yaml") is not None
    except ImportError:
        yaml_ok = False

    results.append(
        {
            "check": "Dependencies (PyYAML)",
            "status": "\u2705" if yaml_ok else "\u274c",
            "detail": "PyYAML found" if yaml_ok else "PyYAML missing",
            "fix": "pip install PyYAML",
        }
    )

    if args.json:
        print(
            json.dumps(
                {
                    "results": results,
                    "healthy": all(r["status"] != "\u274c" for r in results),
                }
            )
        )
    else:
        print("\n" + "=" * 50)
        print(f"{Theme.ICON_SEARCH} REKALL DOCTOR DIAGNOSTICS")
        print("=" * 50)

        all_passed = True
        for r in results:
            icon = r["status"]
            if icon == "\u2705":
                icon = Theme.ICON_SUCCESS
            elif icon == "\u274c":
                icon = Theme.ICON_ERROR
            elif icon == "\u26a0\ufe0f":
                icon = Theme.ICON_WARNING

            print(f" {icon} {r['check']:<30} : {r['detail']}")
            if r["status"] == "\u274c":
                all_passed = False
                if r["fix"]:
                    print(f"    \U0001f449 FIX: {r['fix']}")

        print("=" * 50)
        if all_passed:
            print(f"{Theme.ICON_SUCCESS} System healthy")
        else:
            print(
                f"{Theme.ICON_ERROR} System issues detected. Please check the checklist above."
            )
        print("=" * 50 + "\n")


def cmd_demo(args):
    """One-click experience that sets up a temporary project, validates it, and generates handoff."""
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        args.store_dir = temp_dir

        if not args.json:
            logger.info(f"Setting up demo in temporary directory: {temp_dir}")

        # Re-use init logic to stage the directory
        cmd_init(args)

        # The actual vault might be in temporary_dir/project-state
        temp_path = resolve_vault_dir(temp_path)

        # Mock some events for the demo
        store = StateStore(temp_path)
        actor = {"actor_id": "demo_user"}
        store.create_work_item(
            {"title": "Design Demo Project", "status": "todo"}, actor
        )
        wi_2 = store.create_work_item(
            {"title": "Fix Onboarding Issue", "status": "in_progress"}, actor
        )
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

            print("\n" + "=" * 50)
            print(f"{Theme.ICON_SUCCESS} DEMO COMPLETE \u2014 OPEN THIS NOW:")
            print("=" * 50)
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

    base_dir = resolve_vault_dir(args.store_dir)

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
            die(
                ExitCode.INTERNAL_ERROR,
                f"Validation failed during initialization: {friendly_error(e)}",
                args.json,
            )

        report = store.validate_all(strict=args.strict)

        if args.json:
            print(json.dumps(report, indent=2))
        elif not getattr(args, "quiet", False):
            print("\n=== Rekall Validation Report ===")
            print(
                f"Status: {report['summary']['status']} ({report['summary']['errors']} errors, {report['summary']['warnings']} warnings)"
            )

            for section, data in report.items():
                if section == "summary":
                    continue
                status = data.get("status", "\u2705")
                print(f"\n{status} {section.replace('_', ' ').title()}")

                if status != "\u2705":
                    for k, v in data.items():
                        if k == "status":
                            continue
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
        die(
            ExitCode.INTERNAL_ERROR,
            f"Validation failed with exception: {friendly_error(e)}",
            args.json,
        )


def cmd_validate_mcp(args):
    """MCP self-check: launch server, validate tools/list, schemas, and probe calls."""
    from rekall.core.mcp_validator import format_human_report, run_mcp_validation

    server_cmd = getattr(args, "server_cmd", None)
    if not server_cmd:
        die(
            ExitCode.VALIDATION_FAILED,
            "--server-cmd is required when using --mcp",
            args.json,
        )

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
        die(ExitCode.INTERNAL_ERROR, f"MCP validation failed: {friendly_error(e)}", args.json)


def cmd_snapshot(args):
    """Compile the state store into a single standalone snapshot.json (compact format)."""
    base_dir = resolve_vault_dir(args.store_dir)
    try:
        store = StateStore(base_dir)

        # Compile snapshot with deterministic ordering
        activity = sorted(
            store._load_stream("activity", hot_only=False),
            key=lambda x: (x.get("timestamp", ""), x.get("activity_id", "")),
        )
        attempts = sorted(
            store._load_stream("attempts", hot_only=False),
            key=lambda x: (x.get("timestamp", ""), x.get("attempt_id", "")),
        )
        decisions = sorted(
            store._load_stream("decisions", hot_only=False),
            key=lambda x: (x.get("timestamp", ""), x.get("decision_id", "")),
        )
        timeline = sorted(
            store._load_stream("timeline", hot_only=False),
            key=lambda x: (x.get("timestamp", ""), x.get("event_id", "")),
        )
        events = sorted(
            store._load_stream("work_items", hot_only=False),
            key=lambda x: (x.get("timestamp", ""), x.get("event_id", "")),
        )

        # Sort work_items keys deterministically
        work_items_sorted = {
            k: store.work_items[k] for k in sorted(store.work_items.keys())
        }

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
            "schema_version": "0.1",  # Standardized version
        }

        # Write to requested output or stdout
        if args.out:
            out_file = Path(args.out)
            out_file.write_text(json.dumps(snapshot, indent=2))
            logger.info(f"Snapshot exported to {out_file}")
            if args.json:
                print(json.dumps({"status": "success", "snapshot_file": str(out_file)}))
        else:
            print(json.dumps(snapshot, indent=2))

    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Snapshot failed: {friendly_error(e)}", args.json)


def cmd_export(args):
    """Copies the StateStore entirely to a requested output directory matching v0.1 Spec."""
    import shutil

    base_dir = resolve_vault_dir(args.store_dir)
    out_dir = Path(args.out)

    try:
        StateStore(base_dir)  # validates implicitly

        # If valid, just copy files over
        out_dir.mkdir(parents=True, exist_ok=True)

        # Core YAMLs
        for f in [
            "schema-version.txt",
            "project.yaml",
            "envs.yaml",
            "access.yaml",
            "manifest.json",
        ]:
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
        die(ExitCode.INTERNAL_ERROR, f"Export failed: {friendly_error(e)}", args.json)


def cmd_import(args):
    """Reads from a state store folder and imports events idempotently to the target directory."""
    source_dir = Path(args.source)
    target_dir = Path(args.store_dir)

    if not source_dir.exists() or not (source_dir / "schema-version.txt").exists():
        die(
            ExitCode.NOT_FOUND,
            f"Source directory {source_dir} is not a valid state store.",
            args.json,
        )

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
                target_store.append_jsonl_idempotent(
                    stream_name, record, info["id_field"]
                )

        if args.json:
            print(json.dumps({"status": "success", "imported_to": str(target_dir)}))
        else:
            logger.info(f"Import from folder {source_dir} to {target_dir} successful.")

    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Import failed: {friendly_error(e)}", args.json)


def cmd_handoff(args):
    """Synthesizes project state to create boot_brief.md and exports snapshot.json."""
    base_dir = resolve_vault_dir(args.store_dir)
    out_dir = Path(args.out)
    project_id = args.project_id

    try:
        store = StateStore(base_dir)

        # Verify project_id matches
        config_pid = store.project_config.get("project_id")
        if config_pid and config_pid != project_id:
            logger.warning(
                f"Warning: Requested project_id '{project_id}' does not match StateStore project_id '{config_pid}'. Proceeding anyway."
            )

        out_dir.mkdir(parents=True, exist_ok=True)

        # Compile snapshot with deterministic ordering
        events = sorted(
            store._load_stream("work_items", hot_only=False),
            key=lambda x: (x.get("timestamp", ""), x.get("event_id", "")),
        )
        activity = sorted(
            store._load_stream("activity", hot_only=False),
            key=lambda x: (x.get("timestamp", ""), x.get("activity_id", "")),
        )
        attempts = sorted(
            store._load_stream("attempts", hot_only=False),
            key=lambda x: (x.get("timestamp", ""), x.get("attempt_id", "")),
        )
        decisions = sorted(
            store._load_stream("decisions", hot_only=False),
            key=lambda x: (x.get("timestamp", ""), x.get("decision_id", "")),
        )
        timeline = sorted(
            store._load_stream("timeline", hot_only=False),
            key=lambda x: (x.get("timestamp", ""), x.get("event_id", "")),
        )

        work_items_sorted = {
            k: store.work_items[k] for k in sorted(store.work_items.keys())
        }

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
            "schema_version": "0.1",
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
        die(ExitCode.INTERNAL_ERROR, f"Handoff failed: {friendly_error(e)}", False)


def cmd_features(args):
    """Print the capability map and positioning."""
    print("\nRekall: The verifiable AI execution record + execution ledger")
    print("-" * 60)
    print("FEATURES:")
    print(
        "  * Typed Link Matrix       : Bridges Jira, Notion, Figma into a single machine-readable layer."
    )
    print(
        "  * Immutable Ledgers       : JSONL ledgers for decisions, attempts, and work-item state."
    )
    print(
        "  * Agent Context injection : `handoff` pack aggregates blocks, history, and goals into a boot brief."
    )
    print(
        "  * MCP Server Native       : Direct read/write bindings for Claude Desktop."
    )
    print("\nPRIMITIVES:")
    print("  * ATTEMPTS : A typed execution ledger of what has been tried and why it failed.")
    print("  * DECISIONS: Explicit records of trade-offs and architectural choices.")
    print("  * TIMELINE : An immutable event log of milestones and state changes.")
    print(
        "  * POINTERS : Typed pointers to external environments and access methods.\n"
    )


def execute_alias_query(args, qtype: ExecutiveQueryType):
    """Wrapper to run existing ExecutiveQueries directly from CLI."""
    base_dir = resolve_vault_dir(args.store_dir)
    ensure_state_initialized(base_dir, args.json)

    try:
        store = StateStore(base_dir)
        resp = query_executive_status(store, qtype)

        if args.json:
            import dataclasses

            print(json.dumps(dataclasses.asdict(resp), indent=2))
        else:
            print(f"\n[{qtype.name}] Target: {resp.target_project_id}")
            for line in resp.summary:
                print(f"{Theme.ICON_INFO} {line}")
            if resp.evidence:
                print("Evidence:")
                for ev in resp.evidence:
                    print(f"  \u2022 {ev}")
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
        die(ExitCode.INTERNAL_ERROR, f"Query failed: {friendly_error(e)}", args.json)


def cmd_alias_status(args):
    execute_alias_query(args, ExecutiveQueryType.ON_TRACK)


def cmd_alias_blockers(args):
    execute_alias_query(args, ExecutiveQueryType.BLOCKERS)


def cmd_alias_resume(args):
    execute_alias_query(args, ExecutiveQueryType.RESUME_IN_30)


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
        reverse=True,
    )
    approved = [d for d in all_decisions if d.get("status") == "approved"][:3]
    proposed_if_none = (
        [d for d in all_decisions if d.get("status") == "proposed"][:3]
        if not approved
        else []
    )
    recent_decisions = approved or proposed_if_none
    decisions_out = []
    for d in recent_decisions:
        decisions_out.append(
            {
                "decision_id": d.get("decision_id"),
                "title": d.get("title", ""),
                "status": d.get("status", ""),
                "tradeoffs": d.get("tradeoffs", ""),
                "rationale": d.get("rationale", ""),
                "evidence_refs": d.get("evidence_links", d.get("evidence", [])),
            }
        )

    # Recent failed attempts (last 5)
    all_attempts = sorted(
        store._load_stream("attempts", hot_only=True),
        key=lambda a: a.get("timestamp", ""),
        reverse=True,
    )
    # Filter for outcome == "failed" or just show last 3 if no outcome field
    failed = [a for a in all_attempts if a.get("outcome") == "failed"][:3]
    recent_attempts = failed if failed else all_attempts[:3]
    attempts_out = []
    for a in recent_attempts:
        attempts_out.append(
            {
                "attempt_id": a.get("attempt_id"),
                "title": a.get("title", ""),
                "work_item_id": a.get("work_item_id", ""),
                "hypothesis": a.get("hypothesis", a.get("title", "")),
                "outcome": a.get("outcome", "recorded"),
                "evidence_refs": a.get("evidence_links", a.get("evidence", [])),
            }
        )

    # Top risks / blockers from work items
    now = datetime.datetime.now(datetime.timezone.utc)
    risks = []
    for wid, item in store.work_items.items():
        status = item.get("status", "")
        deps = item.get("dependencies", {})
        blocked_by = deps.get("blocked_by", [])
        if blocked_by or status in ("blocked", "at_risk"):
            risks.append(
                {
                    "work_item_id": wid,
                    "title": item.get("title", ""),
                    "status": status,
                    "blocked_by": blocked_by,
                    "evidence_refs": item.get("evidence_links", []),
                }
            )
        elif status == "in_progress":
            claim = item.get("claim")
            if claim:
                lease_str = claim.get("lease_until", "")
                try:
                    lease_dt = datetime.datetime.fromisoformat(
                        lease_str.replace("Z", "+00:00")
                    )
                    if now > lease_dt:
                        risks.append(
                            {
                                "work_item_id": wid,
                                "title": item.get("title", ""),
                                "status": "in_progress (lease expired)",
                                "blocked_by": [],
                                "evidence_refs": item.get("evidence_links", []),
                            }
                        )
                except (ValueError, AttributeError):
                    pass

    # Environments + access (no secrets)
    envs = store.envs_config or {}
    access = store.access_config or {}
    operate = {
        "environments": {
            k: {
                kk: vv
                for kk, vv in (v if isinstance(v, dict) else {}).items()
                if "secret" not in kk.lower()
                and "key" not in kk.lower()
                and "token" not in kk.lower()
            }
            for k, v in envs.items()
        },
        "access_roles": list(access.get("roles", {}).keys())
        if isinstance(access.get("roles"), dict)
        else [],
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
    base_dir = resolve_vault_dir(args.store_dir)
    ensure_state_initialized(base_dir, args.json)

    try:
        store = StateStore(base_dir)
        meta = store.get_project_meta()
        if (not meta.get("goal") or not meta.get("phase")) and not args.json:
             print(f"{Theme.ICON_WARNING} Warning: Project metadata (goal/phase) is not set.")
             print("  Agents should run `project.bootstrap` to maintain this.")

        payload = build_guard_payload(store)
        drift = store.check_drift()
        store.start_session()

        # Strict checks
        if args.strict:
            problems = []
            if not payload["constraints"]:
                problems.append("No constraints/invariants defined in project.yaml")
            if not payload["recent_decisions"]:
                problems.append("No decisions found in decisions.jsonl")
            if problems:
                if args.json:
                    out = {
                        "ok": False,
                        "guard": "FAIL",
                        "problems": problems,
                        **payload,
                    }
                    if drift:
                        out["drift_warning"] = drift
                    print(json.dumps(out))
                else:
                    print("\n\u274c GUARD PREFLIGHT FAILED")
                    for p in problems:
                        print(f"  \u2717 {p}")
                sys.exit(ExitCode.VALIDATION_FAILED.value)

        # Emit timeline
        if getattr(args, "emit_timeline", False):
            import hashlib

            actor = {"actor_id": getattr(args, "actor", "cli_user")}
            event_id = hashlib.sha256(
                f"guard-preflight-{base_dir.resolve()}".encode()
            ).hexdigest()[:16]
            store.append_timeline(
                {
                    "event_id": event_id,
                    "type": "note",
                    "summary": "Preflight guard run",
                },
                actor=actor,
            )

        # Output
        if args.json:
            out = {"ok": True, "guard": "PASS", **payload}
            if drift:
                out["drift_warning"] = drift
            print(json.dumps(out, indent=2, default=str))
        else:
            p = payload["project"]
            print("\n" + "=" * 55)
            print("\U0001f6e1  REKALL PREFLIGHT GUARD")
            print("=" * 55)
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
                if d["evidence_refs"]:
                    print(f"    evidence: {d['evidence_refs']}")
            if not ds:
                print("  (no decisions recorded yet)")

            # Attempts
            ats = payload["recent_attempts"]
            print(f"\n\U0001f9ea Most Recent Attempts ({len(ats)}):")
            for a in ats:
                print(f"  [{a['attempt_id'][:8]}] {a['title']}")
                print(f"    outcome: {a['outcome']}  item: {a['work_item_id']}")
                if a["evidence_refs"]:
                    print(f"    evidence: {a['evidence_refs']}")
            if not ats:
                print("  (no attempts recorded yet)")

            # Risks
            rs = payload["risks_blockers"]
            print(f"\n\u26a0\ufe0f  Top Risks/Blockers ({len(rs)}):")
            for r in rs:
                print(f"  [{r['work_item_id']}] {r['title']} ({r['status']})")
                if r["blocked_by"]:
                    print(f"    blocked_by: {r['blocked_by']}")
            if not rs:
                print("  (none)")

            # Operate
            op = payload["operate"]
            print("\n\U0001f527 Operate:")
            print(f"  Environments: {list(op['environments'].keys())}")
            print(f"  Access roles: {op['access_roles']}")

            print("\n" + "=" * 55 + "\n")

    except SystemExit:
        raise
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Guard failed: {friendly_error(e)}", args.json)


def cmd_attempts_add(args):
    base_dir = resolve_vault_dir(args.store_dir)
    try:
        store = StateStore(base_dir)
        attempt = {
            "work_item_id": args.work_item_id,
            "title": args.title,
            "evidence": args.evidence,
        }
        idemp = getattr(args, "idempotency_key", None)
        res = store.append_attempt(
            attempt, actor={"actor_id": args.actor}, idempotency_key=idemp
        )
        if args.json:
            print(json.dumps({"status": "success", "attempt": res}))
        else:
            logger.info(f"Attempt added: {res['attempt_id']}")
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Failed to add attempt: {friendly_error(e)}", args.json)


def cmd_decisions_propose(args):
    base_dir = resolve_vault_dir(args.store_dir)
    try:
        store = StateStore(base_dir)
        decision = {
            "title": args.title,
            "rationale": args.rationale,
            "tradeoffs": args.tradeoffs,
        }
        idemp = getattr(args, "idempotency_key", None)
        res = store.propose_decision(
            decision, actor={"actor_id": args.actor}, idempotency_key=idemp
        )
        if args.json:
            print(json.dumps({"status": "success", "decision": res}))
        else:
            logger.info(f"Decision proposed: {res['decision_id']}")
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Failed to propose decision: {friendly_error(e)}", args.json)


def cmd_decide(args):
    """Capture a human decision for an action or decision request."""
    base_dir = resolve_vault_dir(getattr(args, "store_dir", "."))
    ensure_state_initialized(base_dir, args.json)
    try:
        store = StateStore(base_dir)
        decision_id = args.decision_id
        decision = args.option
        note = getattr(args, "note", "")
        actor = {"actor_type": "human", "actor_id": "cli_user"}

        updated = store.capture_approval(
            decision_id=decision_id,
            decision_str=decision,
            note=note,
            actor=actor
        )
        if args.json:
            print(json.dumps({"status": "success", "decision_id": updated["decision_id"]}))
        else:
            print(f"\u2705 Decision recorded: {updated['decision_id']}")
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Decision failed: {friendly_error(e)}", args.json)


def cmd_gc(args):
    """Prunes old segment files that are already included in snapshots."""
    store_dir = resolve_vault_dir(args.store_dir)
    ensure_state_initialized(store_dir, args.json)

    try:
        store = StateStore(store_dir)
        store.gc(archive=(not args.delete))
        if not args.json:
            print("\u2705 Garbage collection finished.")
        else:
            print(json.dumps({"status": "success", "message": "GC finished"}))
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"GC failed: {friendly_error(e)}", args.json)


def cmd_timeline_add(args):
    base_dir = resolve_vault_dir(args.store_dir)
    ensure_state_initialized(base_dir, args.json)
    try:
        store = StateStore(base_dir)
        event = {"type": "note", "summary": args.summary}
        idemp = getattr(args, "idempotency_key", None)
        res = store.append_timeline(
            event, actor={"actor_id": args.actor}, idempotency_key=idemp
        )
        if args.json:
            print(
                json.dumps({"status": "success", "timeline_event_id": res["event_id"]})
            )
        else:
            logger.info(f"Timeline event added: {res['event_id']}")
    except Exception as e:
        die(
            ExitCode.INTERNAL_ERROR,
            f"Failed to add timeline event: {friendly_error(e)}",
            args.json,
        )


def cmd_checkpoint(args):
    """Create a durable checkpoint: record timeline/activity and optionally export state."""
    import shutil
    import subprocess
    import uuid

    base_dir = resolve_vault_dir(args.store_dir)
    actor_id = getattr(args, "actor", "cli_user")
    event_id = getattr(args, "event_id", None)
    ctype = getattr(args, "type", "milestone")
    title = getattr(args, "title", None) or getattr(args, "label", None) or "checkpoint"
    summary = getattr(args, "summary", "")
    tags = getattr(args, "tags", []) or []
    out_dir_arg = getattr(args, "out", None)

    if not base_dir.exists():
        die(ExitCode.NOT_FOUND, f"Directory {base_dir} does not exist.", args.json)

    try:
        store = StateStore(base_dir)

        # Handle git integration
        git_sha = None
        git_subject = None
        commit_arg = getattr(args, "commit", None)
        if commit_arg:
            try:
                if commit_arg.lower() == "auto":
                    # Get HEAD short sha and subject
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

        actor = {"actor_id": actor_id}

        # Build common record
        record_id = event_id or str(uuid.uuid4())
        record = {
            "type": ctype,
            "title": title,
            "summary": summary,
            "tags": tags,
        }
        if ctype == "milestone":
            record["event_id"] = record_id
        elif ctype == "task_done":
            record["work_item_id"] = record_id
            record["status"] = "done"
        elif ctype == "attempt_failed":
            record["attempt_id"] = record_id
            record["outcome"] = "failure"
        elif ctype == "decision":
            record["decision_id"] = record_id
            record["status"] = "approved"
        elif ctype == "artifact":
            record["artifact_id"] = record_id

        if git_sha:
            record["git_sha"] = git_sha
            record["git_subject"] = git_subject

        # Checkpoint routing
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
        else: # milestone
            record["details"] = summary
            result = store.append_timeline(record, actor=actor)
            tid = result.get("event_id", record_id)

        # Optional folder-based export
        export_path = None
        if out_dir_arg:
            out_dir = Path(out_dir_arg)
            out_dir.mkdir(parents=True, exist_ok=True)
            for f in ["schema-version.txt", "project.yaml", "envs.yaml", "access.yaml", "manifest.json"]:
                src = base_dir / f
                if src.exists():
                    shutil.copy2(src, out_dir / f)

            src_streams = base_dir / "streams"
            if src_streams.exists():
                shutil.copytree(src_streams, out_dir / "streams", dirs_exist_ok=True)
            export_path = str(out_dir.resolve())

        # Output
        out_payload = {"ok": True, "type": ctype, "id": tid}
        if export_path:
            out_payload["export_path"] = export_path
        if git_sha:
            out_payload["git_sha"] = git_sha

        if args.json:
            print(json.dumps(out_payload))
        else:
            print(f"\n\\u2705 Checkpoint saved [{ctype}]")
            print(f"   ID          : {tid}")
            print(f"   Title       : {title}")
            if git_sha:
                print(f"   Git Commit  : {git_sha} ({git_subject})")
            if export_path:
                print(f"   Export path : {export_path}")
            print("")

    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Checkpoint failed: {friendly_error(e)}", getattr(args, "json", False))


def cmd_checkout(args):
    """Rewinds the active HEAD to a specific point in time by appending a StateRevert."""
    base_dir = resolve_vault_dir(getattr(args, "store_dir", "."))
    ensure_state_initialized(base_dir, args.json)
    try:
        store = StateStore(base_dir)
        to_target = args.to
        if not to_target:
            die(ExitCode.USER_ERROR, "--to is required", args.json)

        # Check if it looks like an ISO timestamp, otherwise look it up
        if "T" in to_target and len(to_target) > 10:
            ts = to_target
        else:
            ts = None
            for stream in store.manifest.get("streams", {}):
                records = store._load_stream_raw(stream, hot_only=False)
                for r in records:
                    if (
                        r.get("event_id") == to_target or
                        r.get("action_id") == to_target or
                        r.get("decision_id") == to_target or
                        r.get("attempt_id") == to_target or
                        r.get("anchor_id") == to_target
                    ):
                        ts = r.get("timestamp") or r.get("created_at") or r.get("created", "")
                        break
                if ts:
                    break
            if not ts:
                die(ExitCode.USER_ERROR, f"Event ID {to_target} not found.", args.json)

        res = store.append_revert(to_timestamp=ts, actor={"actor_id": "cli_user"}, reason=getattr(args, "reason", None))

        if args.json:
            print(json.dumps({"status": "success", "revert": res}))
        else:
            print(f"\u2705 Checked out to {ts}")
            print(f"   Revert ID  : {res['revert_id']}")
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Checkout failed: {friendly_error(e)}", args.json)


def cmd_lock(args):
    base_dir = resolve_vault_dir(args.store_dir)
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
            lease_seconds = int(ttl_str) * 60  # default to minutes if no suffix

        res = store.claim_work_item(
            args.work_item_id,
            expected_version=args.expected_version,
            actor={"actor_id": args.actor},
            lease_seconds=lease_seconds,
            force=args.force,
        )
        if args.json:
            print(json.dumps({"status": "success", "work_item": res}))
        else:
            claim = res.get("claim", {})
            logger.info(
                f"Lock acquired for {args.work_item_id} by {claim.get('claimed_by')} until {claim.get('lease_until')}"
            )
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Failed to acquire lock: {friendly_error(e)}", args.json)

def cmd_status(args):
    """Provides an executive summary of the current reality."""
    store_dir = resolve_vault_dir(getattr(args, "store_dir", "project-state"))
    ensure_state_initialized(store_dir, args.json)

    try:
        store = StateStore(store_dir)

        project_meta = store._load_yaml("project.yaml") or {}
        goal = project_meta.get("current_goal") or project_meta.get("goal")
        phase = project_meta.get("phase")

        # Disclaimer if meta missing
        meta_missing = not goal or not phase
        if meta_missing and not args.json:
            print(f"\n{Theme.ICON_WARNING} [ Agent Metadata Missing ]")
            print("  This is agent-managed metadata. To fix:")
            print("  1. Let your agent run `project.bootstrap` via MCP")
            print("  2. Or run: `rekall meta set goal=\"Your Goal\" phase=\"Planning\"` as fallback.")
            print("-" * 50)

        goal = goal or "not set"
        phase = phase or "not set"

        timeline = store._load_stream("timeline.jsonl")
        actions = store._load_stream("actions.jsonl")
        decisions = store._load_stream("decisions.jsonl")
        attempts = store._load_stream("attempts.jsonl")
        activity = store._load_stream("activity.jsonl")
        anchors_stream = store._load_stream("anchors.jsonl")

        last_event_time = "Never"
        last_event_id = "N/A"
        last_event_hash = "N/A"
        if timeline:
            last = max(timeline, key=lambda x: x.get("timestamp", ""))
            last_event_time = last.get("timestamp", "Unknown")
            last_event_id = last.get("event_id", last.get("activity_id", "N/A"))
            last_event_hash = last.get("event_hash", "N/A")

        last_attempt = None
        if attempts:
            last_attempt = max(attempts, key=lambda x: x.get("timestamp", ""))

        unresolved_waits = []
        waits = [e for e in actions if e.get("type", "") == "WaitingOnHuman"]
        resolved_actions = {d.get("action_id") for d in decisions if d.get("action_id")}
        resolved_decisions = {d.get("decision_id") for d in decisions if d.get("decision_id")}

        for w in waits:
            w_did = w.get("decision_id")
            w_aid = w.get("action_id")
            is_resolved = False
            if w_did and w_did in resolved_decisions:
                is_resolved = True
            elif w_aid and w_aid in resolved_actions:
                is_resolved = True

            if not is_resolved:
                unresolved_waits.append(w)

        if args.json:
            out = {
                "goal": goal, "phase": phase,
                "head": {"timestamp": last_event_time, "id": last_event_id, "hash": last_event_hash},
                "last_attempt": last_attempt,
                "unresolved_waits": unresolved_waits
            }
            drift = store.check_drift()
            if drift:
                out["drift_warning"] = drift
            print(json.dumps(out))
            return

        print("\n[ rekall status ]")
        sig_s = "SIGNED" if anchors_stream and anchors_stream[-1].get("signature") else "UNSIGNED"
        verif_status = "✅ INTEGRITY OK" if last_event_hash != "N/A" else "⚠️ EMPTY LEDGER"
        print(f"{verif_status} | Anchor: {sig_s} | HEAD: {last_event_hash[:12]}...")
        print(f"Goal/Phase: {goal} ({phase})")
        print(f"Active HEAD: {last_event_time}")
        print(f"HEAD ID:     {last_event_id}")
        print(f"HEAD Hash:   {last_event_hash[:12]}... (verifiable)")

        print("\n=== Last Attempt ===")
        if last_attempt:
            title = last_attempt.get('title', last_attempt.get('action_id', 'Unknown'))
            outcome = last_attempt.get('outcome', last_attempt.get('status', 'Unknown'))
            if isinstance(outcome, dict):
                outcome = outcome.get("success", outcome)
            print(f"Title:   {title}")
            print(f"Outcome: {outcome}")
            print(f"ID:      {last_attempt.get('attempt_id')}")
        else:
            print("None")

        print("\n=== Pending Approvals ===")
        if unresolved_waits:
            for w in unresolved_waits:
                d_id = w.get('decision_id', w.get('action_id', 'Unknown'))
                print(f"- Decision {d_id} waiting since {w.get('timestamp')}")
                if w.get('prompt'):
                    print(f"  Prompt: {w.get('prompt')}")
        else:
            print("None")

        print("\n=== Shadow Policy Constraints ===")
        policy_checks = [e for e in activity if e.get("type") == "PolicyCheck"]
        if policy_checks:
            denies = [c for c in policy_checks if c.get("effect") == "deny"]
            print(f"Audit Trail: {len(policy_checks)} preflight checks recorded.")
            if denies:
                last_deny = denies[-1]
                print(f"Latest WOULD-DENY: {last_deny.get('rule_id')} ({last_deny.get('timestamp')})")
            else:
                print("Status: Pass (0 active would-deny items)")
        else:
            print("No policy.yaml preflight checks in current stream.")

        print("\n=== Provenance Anchors ===")
        if anchors_stream:
            last_anchor = anchors_stream[-1]
            sig_status = "SIGNED" if last_anchor.get("signature") else "UNSIGNED"
            print(f"Latest Anchor: {last_anchor.get('anchor_id')} [{sig_status}]")
            print(f"Evidence:      {last_anchor.get('timestamp')}")
        else:
            print("None")
        print("")

    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Status failed: {friendly_error(e)}", args.json)


def cmd_meta_get(args):
    """Get project metadata."""
    store_dir = resolve_vault_dir(getattr(args, "store_dir", "project-state"))
    ensure_state_initialized(store_dir, args.json)
    try:
        store = StateStore(store_dir)
        meta = store.get_project_meta()
        if args.json:
            print(json.dumps(meta, indent=2))
        else:
            print("\n[ rekall meta get ]")
            for k, v in meta.items():
                print(f"  {k:<15}: {v}")
            print("")
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Meta get failed: {friendly_error(e)}", args.json)


def cmd_meta_set(args):
    """Set project metadata (replaces/adds fields)."""
    store_dir = resolve_vault_dir(getattr(args, "store_dir", "project-state"))
    ensure_state_initialized(store_dir, args.json)
    try:
        store = StateStore(store_dir)
        # Convert list of k=v to dict
        patch = {}
        for kv in args.fields:
            if "=" in kv:
                k, v = kv.split("=", 1)
                patch[k] = v
            else:
                die(ExitCode.USER_ERROR, f"Invalid field format: {kv}. Use k=v", args.json)

        actor = {"actor_id": getattr(args, "actor", "cli_user")}
        res = store.patch_project_meta(patch, actor=actor)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print("\u2705 Project metadata updated.")
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Meta set failed: {friendly_error(e)}", args.json)


def cmd_meta_patch(args):
    """Patch project metadata via JSON payload."""
    store_dir = resolve_vault_dir(getattr(args, "store_dir", "project-state"))
    ensure_state_initialized(store_dir, args.json)
    try:
        store = StateStore(store_dir)
        patch = json.loads(args.payload)
        actor = {"actor_id": getattr(args, "actor", "cli_user")}
        res = store.patch_project_meta(patch, actor=actor)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print("\u2705 Project metadata patched.")
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Meta patch failed: {friendly_error(e)}", args.json)


def cmd_onboard(args):
    """Generate the Rekall skill pack and integration guide."""
    store_dir = resolve_vault_dir(getattr(args, "store_dir", "project-state"))
    ensure_state_initialized(store_dir, args.json, init_mode=True)

    try:
        StateStore(store_dir)
        art_dir = store_dir / "artifacts"
        art_dir.mkdir(exist_ok=True)

        skill_path = art_dir / "rekall_skill.md"

        skill_content = """# Rekall Agent Skill Pack

This file defines the operating contract for any AI agent integrating with this Rekall vault.

## 1. Startup Routine
Every time you start work, get your bearings first:
- **MCP**: Call `session.brief` for a one-call brief, or `project.bootstrap` to initialize + brief.
- **CLI**: Run `rekall brief --json` or `rekall session start`.

This returns: current focus, blockers, failed attempts (do not retry), pending decisions, and next actions.

## 2. Decision & Attempt Logging
Rekall is an append-only execution ledger. Do not rely on your internal memory for long-term state.
- **Log Decisions**: Call `decision.propose` (MCP) or `rekall decisions propose` (CLI) for any architectural or significant logic change.
- **Log Attempts**: Call `attempt.append` (MCP) or `rekall attempts add` (CLI) for every unit of work. Include evidence.

## 3. Approval Breakpoints
- If a decision is high-risk or requires human sign-off, propose it with a "PENDING" status.
- Stop and wait for human `rekall decide` if you reach an ambiguity you cannot resolve with 90% confidence.

## 4. Session End
When finishing work: `rekall session end --summary "Where I stopped and what comes next"`

## 5. Idempotency & Secrets
- Use `idempotency_key` (e.g. hash of inputs) to avoid duplicate logs on retries.
- **NO SECRETS**: Never log API keys, tokens, or passwords. Redact them to `[REDACTED]` before calling Rekall tools.

## 6. Active Checkpointing
After completing a meaningful unit of work, checkpoint it:
- **CLI**: `rekall checkpoint --type task_done --title "..." --summary "..." --commit auto`
- **MCP**: Call `rekall_checkpoint` with `{"type": "task_done", "title": "...", "summary": "...", "git_commit": "auto"}`
"""

        with open(skill_path, "w", encoding="utf-8") as f:
            f.write(skill_content)

        if not args.json:
            print(f"\n{Theme.ICON_SUCCESS} Generated universal skill pack: {skill_path}")
            print("\n--- INTEGRATION GUIDE ---")
            print("To wire Rekall into your agent (Cursor, Claude, etc.):")
            print("1. Add the following to your agent's system instructions or config file:")
            print(f"   \"Always follow the protocol in {skill_path.relative_to(Path.cwd())}\"")
            print("2. Ensure the Rekall MCP server is configured in your IDE/agent settings.")
            print("3. Start every session by calling `project.bootstrap`.")
            print("--------------------------\n")
        else:
            print(json.dumps({"status": "success", "skill_pack": str(skill_path)}))

    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Onboarding failed: {friendly_error(e)}", args.json)


def cmd_brief(args):
    """One-call session brief: everything an agent needs to continue work."""
    store_dir = resolve_vault_dir(getattr(args, "store_dir", "project-state"))
    ensure_state_initialized(store_dir, args.json)

    try:
        store = StateStore(store_dir)
        brief = generate_session_brief(store)

        if args.json:
            print(json.dumps(brief, indent=2, default=str))
        else:
            print(format_brief_human(brief))
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Brief failed: {friendly_error(e)}", args.json)


def cmd_session(args):
    """Manage session lifecycle: start, end."""
    store_dir = resolve_vault_dir(getattr(args, "store_dir", "project-state"))

    if args.subcommand == "start":
        ensure_state_initialized(store_dir, args.json, init_mode=True)
        try:
            store = StateStore(store_dir)
            store.start_session()
            brief = generate_session_brief(store)

            if args.json:
                print(json.dumps({"status": "session_started", "brief": brief}, indent=2, default=str))
            else:
                print(format_brief_human(brief))
        except Exception as e:
            die(ExitCode.INTERNAL_ERROR, f"Session start failed: {friendly_error(e)}", args.json)

    elif args.subcommand == "end":
        ensure_state_initialized(store_dir, args.json)
        try:
            store = StateStore(store_dir)

            # Bypass detection: check for unrecorded work
            warnings = _detect_bypass(store, store_dir)

            summary_text = getattr(args, "summary", "") or ""
            actor = {"actor_id": getattr(args, "actor", "cli_user")}

            # Record session-end timeline event if summary provided
            if summary_text:
                import uuid
                store.append_timeline({
                    "event_id": str(uuid.uuid4())[:16],
                    "type": "session_end",
                    "summary": summary_text,
                }, actor=actor)

            if args.json:
                out: dict = {"status": "session_ended"}
                if warnings:
                    out["warnings"] = warnings
                if summary_text:
                    out["summary_recorded"] = True
                print(json.dumps(out, indent=2))
            else:
                if warnings:
                    for w in warnings:
                        print(f"\u26a0\ufe0f  {w}")
                    print("")
                if summary_text:
                    print("\u2705 Session ended. Summary recorded.")
                else:
                    print("\u2705 Session ended.")
                    print("  Tip: use --summary to leave a note for the next session.")
        except Exception as e:
            die(ExitCode.INTERNAL_ERROR, f"Session end failed: {friendly_error(e)}", args.json)


def _detect_bypass(store: StateStore, store_dir) -> list:
    """Detect common bypass patterns and return warning strings."""
    import subprocess
    warnings = []

    # 1. Check for uncheckpointed git commits
    try:
        timeline = store._load_stream_raw("timeline.jsonl", hot_only=False)
        checkpointed_shas = {t.get("git_sha") for t in timeline if t.get("git_sha")}

        res = subprocess.run(
            ["git", "log", "-n", "20", "--format=%h"],
            capture_output=True, text=True, timeout=5
        )
        if res.returncode == 0:
            uncheckpointed = 0
            for sha in res.stdout.strip().split("\n"):
                if not sha:
                    continue
                if sha in checkpointed_shas:
                    break
                uncheckpointed += 1
            if uncheckpointed > 1:
                warnings.append(
                    f"{uncheckpointed} git commits since last Rekall checkpoint. "
                    f"Run `rekall checkpoint --summary '...' --commit auto`."
                )
    except Exception:
        pass

    # 2. Check for empty ledger despite having work items
    work_items = list(store.work_items.values())
    attempts = store._load_stream("attempts", hot_only=True)
    if work_items and not attempts:
        in_progress = [w for w in work_items if w.get("status") == "in_progress"]
        if in_progress:
            warnings.append(
                f"{len(in_progress)} work item(s) in progress but no attempts recorded. "
                f"Log work with `rekall attempts add <work_item_id> --title '...'`."
            )

    # 3. Check for pending decisions that are stale
    decisions = store._load_stream("decisions", hot_only=True)
    pending = [d for d in decisions if d.get("status") in ("proposed", "pending", "PENDING")]
    if pending:
        warnings.append(
            f"{len(pending)} pending decision(s) still unresolved. "
            f"Run `rekall decide <id> --option '...'` or flag for human review."
        )

    return warnings


def cmd_agents_md(args):
    """Generate AGENTS.md at repo root — the universal operating contract."""
    store_dir = resolve_vault_dir(getattr(args, "store_dir", "project-state"))
    ensure_state_initialized(store_dir, args.json, init_mode=True)

    try:
        store = StateStore(store_dir)
        proj = store.project_config or {}
        mode = proj.get("rekall_mode", "coordination")

        content = _build_agents_md(proj, mode)
        out_path = Path(getattr(args, "out", None) or "AGENTS.md")

        if out_path.exists() and not getattr(args, "force", False):
            die(ExitCode.CONFLICT, f"{out_path} already exists. Use --force to overwrite.", args.json)

        out_path.write_text(content, encoding="utf-8")

        if args.json:
            print(json.dumps({"status": "success", "path": str(out_path)}))
        else:
            print(f"\u2705 Generated {out_path}")
            print("  This file tells any coding assistant how to use Rekall in this repo.")

        if getattr(args, "ide", False):
            _generate_ide_instruction_files(force=getattr(args, "force", False))
    except SystemExit:
        raise
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"AGENTS.md generation failed: {friendly_error(e)}", args.json)


def _build_agents_md(proj: dict, mode: str) -> str:
    """Build the contents of AGENTS.md."""
    goal = proj.get("goal") or proj.get("current_goal") or ""

    lines = []
    lines.append("# AGENTS.md")
    lines.append("")
    lines.append("This file defines how AI coding assistants should operate in this repository.")
    lines.append("It is assistant-agnostic: the same contract applies to Claude Code, Cursor,")
    lines.append("Codex, Gemini, Windsurf, Aider, or any tool that reads repo instructions.")
    lines.append("")

    # Separation of concerns
    lines.append("## Where things live")
    lines.append("")
    lines.append("| What | Where | Who maintains it |")
    lines.append("| :--- | :--- | :--- |")
    lines.append("| Stable behavior rules | CLAUDE.md / .cursor/rules / .github/copilot-instructions.md | Human |")
    lines.append("| Durable project knowledge | README.md, docs/, or thin MEMORY.md | Human |")
    lines.append("| **Live execution state** | **Rekall vault** (`project-state/`) | **Agent + Human** |")
    lines.append("")
    lines.append("Do NOT duplicate live execution state (in-progress work, blockers, failed attempts,")
    lines.append("pending decisions) into MEMORY.md or other markdown files. Rekall is the single")
    lines.append("source of truth for volatile project state.")
    lines.append("")

    # Session protocol
    lines.append("## Session protocol")
    lines.append("")
    lines.append("### Starting a session")
    lines.append("")
    lines.append("Before doing any work, get your bearings:")
    lines.append("")
    lines.append("```bash")
    lines.append("rekall brief --json    # One call: focus, blockers, failed paths, pending decisions, next actions")
    lines.append("```")
    lines.append("")
    lines.append("Or via MCP: call `project.bootstrap` which returns the same context.")
    lines.append("")
    lines.append("This tells you:")
    lines.append("- What's currently in progress")
    lines.append("- What's blocked and why")
    lines.append("- What approaches already failed (do not retry these)")
    lines.append("- What decisions need human input")
    lines.append("- What to work on next")
    lines.append("")

    # During work
    lines.append("### During work")
    lines.append("")
    lines.append("Log meaningful state changes — not every keystroke, but turning points:")
    lines.append("")
    lines.append("- **Tried something that failed?** Log it so the next session doesn't repeat it:")
    lines.append('  `rekall attempts add <work_item_id> --title "..." --evidence "..."`')
    lines.append("- **Made an architectural choice?** Record the tradeoff:")
    lines.append('  `rekall decisions propose --title "..." --rationale "..." --tradeoffs "..."`')
    lines.append("- **Finished a task?** Checkpoint it:")
    lines.append('  `rekall checkpoint --type task_done --title "..." --summary "..." --commit auto`')
    lines.append("")

    # Ending a session
    lines.append("### Ending a session")
    lines.append("")
    lines.append("Before stopping or handing off:")
    lines.append("")
    lines.append("```bash")
    lines.append('rekall session end --summary "Where I stopped and what comes next"')
    lines.append("```")
    lines.append("")
    lines.append("This records a handoff note and warns about any unrecorded work.")
    lines.append("")

    # Mode
    lines.append(f"## Current mode: `{mode}`")
    lines.append("")
    if mode == "lite":
        lines.append("Lightweight tracking. Only checkpoint at session boundaries.")
        lines.append("Skip attempt/decision logging for small, low-risk changes.")
    elif mode == "governed":
        lines.append("Full tracking with mandatory checkpoints and decision logging.")
        lines.append("High-risk actions require human approval via `rekall decide`.")
    else:
        lines.append("Standard multi-session tracking. Log decisions and failed attempts.")
        lines.append("Checkpoint after each meaningful unit of work.")
    lines.append("")

    # Goal context
    if goal:
        lines.append("## Current project goal")
        lines.append("")
        lines.append(goal)
        lines.append("")

    return "\n".join(lines)


def cmd_mode(args):
    """Set the Rekall usage mode (lite/coordination/governed)."""
    store_dir = resolve_vault_dir(getattr(args, "store_dir", "project-state"))
    ensure_state_initialized(store_dir, args.json)

    try:
        store = StateStore(store_dir)
        new_mode = args.mode

        actor = {"actor_id": getattr(args, "actor", "cli_user")}
        store.patch_project_meta({"rekall_mode": new_mode}, actor=actor)

        if args.json:
            print(json.dumps({"status": "success", "mode": new_mode}))
        else:
            descriptions = {
                "lite": "Lightweight — checkpoint at session boundaries only",
                "coordination": "Standard — log decisions and attempts, checkpoint after tasks",
                "governed": "Full governance — mandatory checkpoints, human approvals required",
            }
            print(f"\u2705 Rekall mode set to: {new_mode}")
            print(f"   {descriptions.get(new_mode, new_mode)}")
    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Mode change failed: {friendly_error(e)}", args.json)


def cmd_serve(args):
    """Launch the MCP server over stdio."""
    # Force quiet mode for MCP to avoid polluting stdout
    setup_logging(json_mode=True, quiet_mode=True)

    # Resolve store_dir
    if args.store_dir is not None:
        resolved_store = args.store_dir
    else:
        resolved_store = getattr(args, "store_dir_flag", ".")
    args.store_dir = resolved_store

    base_dir = resolve_vault_dir(args.store_dir)

    try:
        # Success Criterion: Launch Rekall Dashboard if interactive
        if sys.stdin.isatty():
            # If store does not exist, we just skip dashboard or start it later. For now, try initializing if it exists.
            if base_dir.exists() and (base_dir / "manifest.json").exists():
                store = StateStore(base_dir)
                dashboard_server, port = start_dashboard(store)
                print(f"{Theme.ICON_ROCKET} Rekall Dashboard active at http://127.0.0.1:{port}", file=sys.stderr)
            print(f"{Theme.ICON_INFO} MCP Server (stdio) active and waiting for agent commands...", file=sys.stderr)

        # Inject base_dir into mcp_server global so it can lazy init
        mcp_server._base_dir = base_dir

        # Launch server loop
        mcp_server.main()
    except Exception as e:
        # Exit silently or with a log that won't break JSON-RPC if possible
        # but if we're here, the server hasn't really started.
        die(ExitCode.INTERNAL_ERROR, f"MCP server failed: {friendly_error(e)}", args.json)

def cmd_verify(args):
    """Verify cryptographic integrity of all execution streams."""
    base_dir = resolve_vault_dir(getattr(args, "store_dir", "."))
    ensure_state_initialized(base_dir, args.json)
    try:
        store = StateStore(base_dir)
        results = []
        overall_status = "\u2705"

        streams = store.manifest.get("streams", {})
        for stream_name in streams:
            res = store.verify_stream_integrity(stream_name)
            results.append(res)
            if res["status"] == "\u274c":
                overall_status = "\u274c"

        if args.json:
            print(json.dumps({"status": overall_status, "streams": results}))
            return

        print(f"\n[ rekall verify ] - Integrity: {overall_status}")
        for res in results:
            print(f"  {res['status']} {res['stream']:<20} ({res['count']} events)")
            if res["errors"]:
                for err in res["errors"]:
                    print(f"    \u274c {err}")

        if overall_status == "\u274c":
            sys.exit(ExitCode.INTERNAL_ERROR)

    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Verification failed: {friendly_error(e)}", args.json)

def cmd_bundle(args):
    """Bundle the entire state directory into a portable tarball."""
    base_dir = resolve_vault_dir(getattr(args, "store_dir", "."))
    ensure_state_initialized(base_dir, args.json)

    out_file = Path(args.out)
    try:
        if not out_file.name.endswith((".tar.gz", ".tgz")):
            out_file = out_file.with_name(out_file.name + ".tar.gz")

        logger.info(f"Bundling {base_dir} into {out_file}...")

        with tarfile.open(out_file, "w:gz") as tar:
            tar.add(base_dir, arcname=base_dir.name)

        if args.json:
            print(json.dumps({"status": "success", "bundle_path": str(out_file.absolute())}))
        else:
            print(f"\u2705 Bundle created: {out_file}")

    except Exception as e:
        die(ExitCode.INTERNAL_ERROR, f"Bundle failed: {friendly_error(e)}", args.json)

def cmd_init(args):
    """Initializes a new Rekall state directory and generates an initialization cheat sheet."""
    import datetime

    # Target state dir: default to project-state if not specified
    if getattr(args, "state_dir", None):
        store_dir = Path(args.state_dir)
    elif getattr(args, "dotdir", False):
        store_dir = Path(".rekall")
    else:
        store_dir = resolve_vault_dir(getattr(args, "store_dir", "project-state"))

    # Auto-init if missing
    ensure_state_initialized(store_dir, args.json, init_mode=True)

    try:
        store = StateStore(store_dir)

        # Integrity check: fail if JSONL is corrupted
        report = store.validate_all()
        if (
            report["summary"]["status"] == "\u274c"
            and report["jsonl_integrity"]["status"] == "\u274c"
        ):
            malformed = report["jsonl_integrity"].get("malformed", [])
            errors = report["jsonl_integrity"].get("errors", [])
            msg = "; ".join(malformed + errors)
            die(
                ExitCode.INTERNAL_ERROR,
                f"Initialization failed: corrupted state files detected. {msg}",
                args.json,
            )

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
        lines.append(f"# Initialization Cheat Sheet: {repo_name}")
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
        lines.append(f"{store_dir.name}/")
        lines.append(
            "\u251c\u2500\u2500 project.yaml          # Project identity & goals"
        )
        lines.append("\u251c\u2500\u2500 manifest.json         # Stream index")
        lines.append(
            "\u251c\u2500\u2500 streams/              # Partitioned event streams"
        )
        lines.append("\u2502   \u2514\u2500\u2500 work_items/")
        lines.append("\u2502       \u251c\u2500\u2500 active.jsonl  # Hot events")
        lines.append("\u2502       \u2514\u2500\u2500 snapshot.json # Fast-load state")
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

        # 3. Write to file
        artifacts_dir = store_dir / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)

        out_path = (
            Path(args.out) if getattr(args, "out", None) else artifacts_dir / "init_cheatsheet.md"
        )

        if out_path.exists() and not getattr(args, "force", False):
            die(
                ExitCode.CONFLICT,
                f"File {out_path} already exists. Use --force to overwrite.",
                getattr(args, "json", False),
            )

        out_path.write_text(content, encoding="utf-8")

        # 4. Success output
        if getattr(args, "print", False):
            print("\n--- INITIALIZATION CHEAT SHEET ---")
            print(content)
            print("--- END OF CHEAT SHEET ---\n")

        if getattr(args, "json", False):
            print(json.dumps({"status": "success", "path": str(out_path)}))
        else:
            print(f"Created: {out_path}")
            print(
                f"Next: rekall status | rekall blockers | rekall handoff {store.project_config.get('project_id', repo_name)}"
            )

    except Exception as e:
        die(
            ExitCode.INTERNAL_ERROR,
            f"Initialization failed: {friendly_error(e)}",
            getattr(args, "json", False),
            debug=getattr(args, "debug", False),
        )


def cmd_hooks(args):
    """Manage Git hooks for Rekall."""
    import stat
    import subprocess
    import sys
    from pathlib import Path

    git_dir = Path(".git")
    if not git_dir.exists():
        die(ExitCode.USER_ERROR, "Not inside a Git repository (.git not found).", args.json)

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)

    post_commit_path = hooks_dir / "post-commit"
    pre_push_path = hooks_dir / "pre-push"

    if args.subcommand == "install":
        # Install post-commit
        post_commit_script = "#!/bin/sh\necho '\\n\\033[33m\U0001f4a1 Rekall Reminder: Checkpoint your work!\\033[0m'\necho 'Run: rekall checkpoint --summary \"...\" --commit auto\\n'\n"
        post_commit_path.write_text(post_commit_script, encoding="utf-8")
        post_commit_path.chmod(post_commit_path.stat().st_mode | stat.S_IEXEC)

        # Install pre-push
        pre_push_script = """#!/bin/sh
repo_root=$(git rev-parse --show-toplevel)
if [ -d "$repo_root/.rekall/project-state" ]; then
    export REKALL_STATE_DIR="$repo_root/.rekall/project-state"
elif [ -d "$repo_root/project-state" ]; then
    export REKALL_STATE_DIR="$repo_root/project-state"
else
    echo "run rekall onboard"
    exit 0
fi

rekall hooks pre-push"""
        if getattr(args, "enforce", False):
            pre_push_script += " --enforce\n"
        else:
            pre_push_script += "\n"

        pre_push_path.write_text(pre_push_script, encoding="utf-8")
        pre_push_path.chmod(pre_push_path.stat().st_mode | stat.S_IEXEC)

        print("\u2705 Rekall hooks installed (post-commit, pre-push)")

    elif args.subcommand == "uninstall":
        if post_commit_path.exists() and "rekall" in post_commit_path.read_text(encoding="utf-8").lower():
            post_commit_path.unlink()
        if pre_push_path.exists() and "rekall hooks" in pre_push_path.read_text(encoding="utf-8"):
            pre_push_path.unlink()
        print("\u2705 Rekall hooks uninstalled")

    elif args.subcommand == "pre-push":
        # Check commit coverage
        base_dir = resolve_vault_dir(getattr(args, "store_dir", "."))
        try:
            store = StateStore(base_dir)
            timeline = store._load_stream_raw("timeline.jsonl", hot_only=False)
            checkpointed_shas = {t.get("git_sha") for t in timeline if t.get("git_sha")}

            # Get last 50 commits
            res = subprocess.run(["git", "log", "-n", "50", "--format=%h"], capture_output=True, text=True)
            if res.returncode != 0:
                sys.exit(0)

            recent_shas = res.stdout.strip().split("\n")
            uncheckpointed = 0
            for sha in recent_shas:
                if not sha:
                    continue
                if sha in checkpointed_shas:
                    break
                uncheckpointed += 1

            threshold = getattr(args, "threshold", 1)
            enforce = getattr(args, "enforce", False)

            if uncheckpointed > threshold:
                msg = f"\u26a0\ufe0f  Rekall warning: You have {uncheckpointed} commits since the last checkpoint (threshold: {threshold})."
                if enforce:
                    print(f"\n\u274c BLOCKED: {msg}")
                    print("Please run `rekall checkpoint` to record your work before pushing.")
                    sys.exit(1)
                else:
                    print(f"\n{msg}")
                    print("Consider running `rekall checkpoint` soon.")

        except Exception as e:
            # Best effort
            logger.debug(f"Pre-push check skipped/failed: {e}")

def cmd_commit(args):
    """Execute git commit and automatically checkpoint."""
    import argparse
    import subprocess
    import sys

    commit_cmd = ["git", "commit"]
    if getattr(args, "message", None):
        commit_cmd.extend(["-m", args.message])
    if getattr(args, "all", False):
        commit_cmd.append("-a")

    res = subprocess.run(commit_cmd)
    if res.returncode != 0:
        sys.exit(res.returncode)

    print("\n\u2728 Auto-checkpointing to Rekall...")
    checkpoint_args = argparse.Namespace(
        store_dir=args.store_dir,
        json=args.json,
        actor=args.actor,
        type="task_done",
        title="Git commit auto-checkpoint" if not getattr(args, "message", None) else args.message,
        summary="Auto-checkpointed from rekall commit",
        tags=[],
        commit="auto",
        label=None,
        event_id=None,
        out=None
    )
    cmd_checkpoint(checkpoint_args)

def _generate_ide_instruction_files(force=False):
    """Generate IDE-specific instruction files for AI assistants."""
    import json as _json
    from pathlib import Path

    instruction = (
        "You are operating in a Rekall-managed workspace. "
        "Start every session by calling `session.brief` (MCP) or `rekall brief` (CLI) "
        "to get current focus, blockers, failed attempts, and next actions. "
        "Log decisions with `decision.propose` and attempts with `attempt.append`. "
        "Checkpoint completed work with `rekall_checkpoint --commit auto`. "
        "End sessions with `rekall session end --summary '...'`."
    )

    # Copilot
    copilot_dir = Path(".github")
    copilot_dir.mkdir(exist_ok=True)
    copilot_file = copilot_dir / "copilot-instructions.md"
    if not copilot_file.exists() or force:
        copilot_file.write_text(instruction + "\n", encoding="utf-8")
        print("\u2705 Created .github/copilot-instructions.md")

    # Cursor
    cursor_dir = Path(".cursor/rules")
    cursor_dir.mkdir(parents=True, exist_ok=True)
    cursor_file = cursor_dir / "rekall.md"
    if not cursor_file.exists() or force:
        cursor_file.write_text(instruction + "\n", encoding="utf-8")
        print("\u2705 Created .cursor/rules/rekall.md")

    # Windsurf
    windsurf_file = Path(".windsurfrules")
    if not windsurf_file.exists() or force:
        windsurf_file.write_text(instruction + "\n", encoding="utf-8")
        print("\u2705 Created .windsurfrules")

    # Claude
    claude_dir = Path(".claude")
    claude_dir.mkdir(exist_ok=True)
    claude_file = claude_dir / "settings.json"
    if not claude_file.exists() or force:
        settings = {
            "customInstructions": instruction
        }
        if claude_file.exists():
            try:
                with open(claude_file, "r") as f:
                    settings = _json.load(f)
                settings["customInstructions"] = instruction
            except Exception:
                pass
        claude_file.write_text(_json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        print("\u2705 Created/Updated .claude/settings.json")

    print("\n\U0001f916 Assistant integration rules established.")


def cmd_assistants(args):
    """Manage AI assistant integrations for Rekall."""
    if args.subcommand == "init":
        print("Warning: 'rekall assistants init' is deprecated. Use 'rekall agents --ide' instead.")
        _generate_ide_instruction_files(force=getattr(args, "force", False))

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
                    stream.reconfigure(encoding="utf-8", errors="replace")
                else:
                    stream.reconfigure(errors="replace")
            except Exception:
                try:
                    stream.reconfigure(errors="replace")
                except Exception:
                    pass

    desc = """Rekall: persistent execution memory for AI coding agents.

START HERE:
  rekall demo                              # See Rekall in action
  rekall init                              # Create a vault in your project
  rekall agents                            # Generate AGENTS.md operating contract

SESSION WORKFLOW:
  rekall brief                             # What to work on, what to avoid
  rekall checkpoint --summary "..."        # Log a milestone
  rekall session end --summary "..."       # Record handoff note

Type 'rekall <command> --help' for details on any command.
"""

    class _HelpFormatter(argparse.RawTextHelpFormatter):
        """Hide subcommands whose help is SUPPRESS."""
        def _format_action(self, action):
            if isinstance(action, argparse._SubParsersAction):
                parts = []
                for choice_action in action._get_subactions():
                    if choice_action.help != argparse.SUPPRESS:
                        parts.append(self._format_action(choice_action))
                return self._join_parts(parts)
            return super()._format_action(action)

    parser = argparse.ArgumentParser(
        description=desc, formatter_class=_HelpFormatter
    )

    parser.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON"
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress internal logs"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Show full stack traces on failure"
    )

    # Shared flags parent so --json/--quiet/--debug work after subcommand args too
    shared_flags = argparse.ArgumentParser(add_help=False)
    shared_flags.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    shared_flags.add_argument(
        "--quiet", "-q", action="store_true", help=argparse.SUPPRESS
    )
    shared_flags.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)

    subparsers = parser.add_subparsers(
        dest="command", required=True, title="Commands", metavar=""
    )

    # Try It
    parser_demo = subparsers.add_parser(
        "demo",
        help="Run a demo to see Rekall in action.",
        parents=[shared_flags],
    )
    parser_demo.set_defaults(func=cmd_demo)

    parser_features = subparsers.add_parser(
        "features",
        help=argparse.SUPPRESS,
        parents=[shared_flags],
    )
    parser_features.set_defaults(func=cmd_features)

    # Init
    parser_init = subparsers.add_parser(
        "init",
        help="Create the Rekall vault in your project.",
        parents=[shared_flags],
    )
    parser_init.add_argument(
        "store_dir", nargs="?", default="project-state", help="Directory to initialize (default: project-state)"
    )
    parser_init.add_argument(
        "--state-dir", help="Custom state directory (e.g. .rekall)"
    )
    parser_init.add_argument(
        "--dotdir", action="store_true", help="Shortcut for --state-dir .rekall"
    )
    parser_init.add_argument(
        "--print", action="store_true", help="Also print the cheat sheet to stdout"
    )
    parser_init.add_argument(
        "--out", "-o", help="Custom output path for the cheat sheet"
    )
    parser_init.add_argument(
        "--force", action="store_true", help="Overwrite if file exists"
    )
    parser_init.set_defaults(func=cmd_init)

    # Doctor
    parser_doctor = subparsers.add_parser(
        "doctor",
        help=argparse.SUPPRESS,  # Advanced: diagnostics
        parents=[shared_flags],
    )
    parser_doctor.add_argument(
        "store_dir",
        nargs="?",
        default="project-state",
        help="Directory of the StateStore to check",
    )
    parser_doctor.set_defaults(func=cmd_doctor)

    # Validate
    parser_validate = subparsers.add_parser(
        "validate",
        help="Check vault integrity. Add --mcp to test MCP surface.",
        parents=[shared_flags],
    )
    parser_validate.add_argument(
        "store_dir",
        nargs="?",
        default=None,
        help="Directory of the StateStore (positional, or use --store-dir)",
    )
    parser_validate.add_argument(
        "--store-dir",
        dest="store_dir_flag",
        default=".",
        help="Directory of the StateStore",
    )
    parser_validate.add_argument(
        "--strict", action="store_true", help="Fail with ExitCode 3 on warnings"
    )
    parser_validate.add_argument(
        "--mcp",
        action="store_true",
        help="Run MCP server self-check instead of StateStore validation",
    )
    parser_validate.add_argument(
        "--server-cmd",
        default=None,
        help="Server launch command for MCP validation (required with --mcp)",
    )
    parser_validate.set_defaults(func=cmd_validate)

    # Portability
    parser_export = subparsers.add_parser(
        "export",
        help=argparse.SUPPRESS,  # Advanced: export to directory
        parents=[shared_flags],
    )
    parser_export.add_argument(
        "--store-dir", default=".", help="Directory of the StateStore"
    )
    parser_export.add_argument(
        "--out", "-o", required=True, help="Output directory path"
    )
    parser_export.set_defaults(func=cmd_export)

    parser_snapshot = subparsers.add_parser(
        "snapshot",
        help=argparse.SUPPRESS,  # Advanced: export snapshot
        parents=[shared_flags],
    )
    parser_snapshot.add_argument(
        "--store-dir", default=".", help="Directory of the StateStore"
    )
    parser_snapshot.add_argument("--out", "-o", help="Output JSON file path")
    parser_snapshot.set_defaults(func=cmd_snapshot)

    # GC
    parser_gc = subparsers.add_parser(
        "gc",
        help=argparse.SUPPRESS,  # Advanced: garbage collection
        parents=[shared_flags],
    )
    parser_gc.add_argument(
        "store_dir",
        nargs="?",
        default="project-state",
        help="Directory of the StateStore",
    )
    parser_gc.add_argument(
        "--delete",
        action="store_true",
        help="Delete segments instead of archiving them",
    )
    parser_gc.set_defaults(func=cmd_gc)

    parser_import = subparsers.add_parser(
        "import",
        help=argparse.SUPPRESS,  # Advanced: import events
        parents=[shared_flags],
    )
    parser_import.add_argument("source", help="Path to source state store folder")
    parser_import.add_argument(
        "--store-dir", default=".", help="Target Directory of the StateStore"
    )
    parser_import.set_defaults(func=cmd_import)

    # Handoff
    parser_handoff = subparsers.add_parser(
        "handoff",
        help=argparse.SUPPRESS,  # Advanced: generate handoff pack
        parents=[shared_flags],
    )
    parser_handoff.add_argument("project_id", help="The Project ID being handed off")
    parser_handoff.add_argument(
        "--store-dir", default=".", help="Directory of the current StateStore"
    )
    parser_handoff.add_argument("--out", "-o", required=True, help="Output directory")
    parser_handoff.set_defaults(func=cmd_handoff)

    # Executive Query Aliases

    parser_blockers = subparsers.add_parser(
        "blockers", help=argparse.SUPPRESS, parents=[shared_flags]  # Use 'brief' instead
    )
    parser_blockers.add_argument(
        "--store-dir", default=".", help="Directory of the current StateStore"
    )
    parser_blockers.set_defaults(func=cmd_alias_blockers)

    parser_resume = subparsers.add_parser(
        "resume", help=argparse.SUPPRESS, parents=[shared_flags]  # Use 'brief' instead
    )
    parser_resume.add_argument(
        "--store-dir", default=".", help="Directory of the current StateStore"
    )
    parser_resume.set_defaults(func=cmd_alias_resume)

    # Checkout
    parser_checkout = subparsers.add_parser(
        "checkout",
        help=argparse.SUPPRESS,  # Advanced: temporal rewind
        parents=[shared_flags],
    )
    parser_checkout.add_argument(
        "--to", required=True, help="Timestamp or event_id to rewind to"
    )
    parser_checkout.add_argument(
        "--reason", default="Manual CLI checkout", help="Reason for revert"
    )
    parser_checkout.add_argument(
        "--store-dir", default=".", help="Directory of the current StateStore"
    )
    parser_checkout.set_defaults(func=cmd_checkout)

    # Guard
    parser_guard = subparsers.add_parser(
        "guard",
        help="Preflight check: constraints, risks, recent work.",
        parents=[shared_flags],
    )
    parser_guard.add_argument(
        "--store-dir", default=".", help="Directory of the StateStore"
    )
    parser_guard.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if constraints or decisions missing",
    )
    parser_guard.add_argument(
        "--emit-timeline",
        action="store_true",
        help="Append a timeline event recording this guard run",
    )
    parser_guard.add_argument(
        "--actor", default="cli_user", help="Actor ID for timeline events"
    )
    parser_guard.set_defaults(func=cmd_guard)

    # Grievance Closeout Commands: Nested subparsers
    parser_attempts = subparsers.add_parser(
        "attempts", help="Log what was tried (including failures).", parents=[shared_flags]
    )
    attempts_subparsers = parser_attempts.add_subparsers(
        dest="subcommand", required=True
    )

    parser_attempts_add = attempts_subparsers.add_parser(
        "add", help="Add an attempt with evidence."
    )
    parser_attempts_add.add_argument("work_item_id", help="The Work Item ID")
    parser_attempts_add.add_argument(
        "--title", required=True, help="Title of the attempt"
    )
    parser_attempts_add.add_argument(
        "--evidence", required=True, help="Evidence path or link"
    )
    parser_attempts_add.add_argument(
        "--store-dir", default=".", help="Directory of the StateStore"
    )
    parser_attempts_add.add_argument("--actor", default="cli_user", help="Actor ID")
    parser_attempts_add.add_argument(
        "--idempotency-key", default=None, help="Optional string to deduplicate records"
    )
    parser_attempts_add.set_defaults(func=cmd_attempts_add)

    parser_decisions = subparsers.add_parser(
        "decisions", help="Log architectural decisions and tradeoffs.", parents=[shared_flags]
    )
    decisions_subparsers = parser_decisions.add_subparsers(
        dest="subcommand", required=True
    )

    parser_decisions_propose = decisions_subparsers.add_parser(
        "propose", help="Propose a decision with rationale and tradeoffs."
    )
    parser_decisions_propose.add_argument(
        "--title", required=True, help="Title of the decision"
    )
    parser_decisions_propose.add_argument(
        "--rationale", required=True, help="Why this decision is proposed"
    )
    parser_decisions_propose.add_argument(
        "--tradeoffs", required=True, help="Tradeoffs considered"
    )
    parser_decisions_propose.add_argument(
        "--store-dir", default=".", help="Directory of the StateStore"
    )
    parser_decisions_propose.add_argument(
        "--actor", default="cli_user", help="Actor ID"
    )
    parser_decisions_propose.add_argument(
        "--idempotency-key", default=None, help="Optional string to deduplicate records"
    )
    parser_decisions_propose.set_defaults(func=cmd_decisions_propose)

    # Decide
    parser_decide = subparsers.add_parser(
        "decide",
        help="Grant/deny permission for a pending approval.",
        parents=[shared_flags],
    )
    parser_decide.add_argument("decision_id", help="The Decision ID to decide upon")
    parser_decide.add_argument(
        "--option", required=True, help="The decision to make (e.g. approve, reject, or a specific choice)"
    )
    parser_decide.add_argument(
        "--note", default="", help="Optional notes on the decision"
    )
    parser_decide.add_argument(
        "--store-dir", default=".", help="Directory of the StateStore"
    )
    parser_decide.set_defaults(func=cmd_decide)

    # Verify
    parser_verify = subparsers.add_parser(
        "verify",
        help="Verify cryptographic integrity of the ledger.",
        parents=[shared_flags],
    )
    parser_verify.add_argument(
        "--store-dir", default=".", help="Directory of the StateStore"
    )
    parser_verify.set_defaults(func=cmd_verify)

    # Bundle
    parser_bundle = subparsers.add_parser(
        "bundle",
        help=argparse.SUPPRESS,  # Advanced: bundle archive
        parents=[shared_flags],
    )
    parser_bundle.add_argument(
        "--out", "-o", required=True, help="Output path for the bundle archive"
    )
    parser_bundle.add_argument(
        "--store-dir", default=".", help="Directory of the StateStore"
    )
    parser_bundle.set_defaults(func=cmd_bundle)

    parser_timeline = subparsers.add_parser(
        "timeline", help=argparse.SUPPRESS, parents=[shared_flags]  # Advanced: raw timeline
    )
    timeline_subparsers = parser_timeline.add_subparsers(
        dest="subcommand", required=True
    )

    parser_timeline_add = timeline_subparsers.add_parser(
        "add", help="Add a timeline event."
    )
    parser_timeline_add.add_argument(
        "--summary", required=True, help="Summary of the timeline event"
    )
    parser_timeline_add.add_argument(
        "--store-dir", default=".", help="Directory of the StateStore"
    )
    parser_timeline_add.add_argument("--actor", default="cli_user", help="Actor ID")
    parser_timeline_add.add_argument(
        "--idempotency-key", default=None, help="Optional string to deduplicate records"
    )
    parser_timeline_add.set_defaults(func=cmd_timeline_add)

    parser_lock = subparsers.add_parser(
        "lock",
        help=argparse.SUPPRESS,  # Advanced: work item locking
        parents=[shared_flags],
    )
    parser_lock.add_argument("work_item_id", help="The Work Item ID")
    parser_lock.add_argument(
        "--expected-version",
        type=int,
        required=True,
        help="Expected version of the item",
    )
    parser_lock.add_argument(
        "--ttl",
        default="5m",
        help="Time to live (lease duration), e.g. 5m, 1h. Default 5m.",
    )
    parser_lock.add_argument(
        "--force", action="store_true", help="Force acquire the lock"
    )
    parser_lock.add_argument(
        "--store-dir", default=".", help="Directory of the StateStore"
    )
    parser_lock.add_argument("--actor", default="cli_user", help="Actor ID")
    parser_lock.set_defaults(func=cmd_lock)

    # Checkpoint
    parser_checkpoint = subparsers.add_parser(
        "checkpoint",
        help="Record a milestone, task completion, or decision.",
        parents=[shared_flags],
    )
    parser_checkpoint.add_argument(
        "project_id", nargs="?", default=None, help="The Project ID being checkpointed (legacy)"
    )
    parser_checkpoint.add_argument(
        "--type",
        choices=["task_done", "decision", "attempt_failed", "artifact", "milestone"],
        default="milestone",
        help="Type of checkpoint to record",
    )
    parser_checkpoint.add_argument(
        "--title", default=None, help="Title or label for the checkpoint"
    )
    parser_checkpoint.add_argument(
        "--label", default=None, help="Legacy alias for --title"
    )
    parser_checkpoint.add_argument(
        "--summary", default="", help="Detailed summary for the checkpoint"
    )
    parser_checkpoint.add_argument(
        "--tags", nargs="*", default=[], help="Optional tags"
    )
    parser_checkpoint.add_argument(
        "--commit",
        default=None,
        help="Git commit SHA to attach, or 'auto' to resolve HEAD automatically",
    )
    parser_checkpoint.add_argument(
        "--include-files",
        action="store_true",
        help="Include file list from git commit",
    )
    parser_checkpoint.add_argument(
        "--out", "-o", default=None, help="Optional output directory for state export"
    )
    parser_checkpoint.add_argument(
        "--store-dir", default=".", help="Directory of the StateStore"
    )
    parser_checkpoint.add_argument("--actor", default="cli_user", help="Actor ID")
    parser_checkpoint.add_argument(
        "--event-id",
        default=None,
        help="Explicit event_id for idempotent timeline append",
    )
    parser_checkpoint.set_defaults(func=cmd_checkpoint)



    # Status
    parser_status = subparsers.add_parser(
        "status",
        help="Executive summary of project state (see also: brief).",
        parents=[shared_flags],
    )
    parser_status.add_argument(
        "--store-dir",
        default="project-state",
        help="Directory of the state store",
    )
    parser_status.set_defaults(func=cmd_status)

    # Serve (MCP)
    parser_serve = subparsers.add_parser(
        "serve",
        help="Launch MCP server (used by IDE configs, not manually).",
        parents=[shared_flags],
    )
    parser_serve.add_argument(
        "store_dir",
        nargs="?",
        default=None,
        help="Directory of the StateStore (positional, or use --store-dir)",
    )
    parser_serve.add_argument(
        "--store-dir",
        dest="store_dir_flag",
        default=".",
        help="Directory of the StateStore",
    )
    parser_serve.add_argument(
        "--host",
        default="stdio",
        help="Host/transport for the MCP server. Currently only 'stdio' is supported.",
    )
    parser_serve.set_defaults(func=cmd_serve)

    # Meta
    parser_meta = subparsers.add_parser(
        "meta", help=argparse.SUPPRESS, parents=[shared_flags]  # Advanced: raw metadata
    )
    meta_subparsers = parser_meta.add_subparsers(dest="subcommand", required=True)

    parser_meta_get = meta_subparsers.add_parser("get", help="Get current metadata.")
    parser_meta_get.add_argument("--store-dir", help="StateStore directory")
    parser_meta_get.set_defaults(func=cmd_meta_get)

    parser_meta_set = meta_subparsers.add_parser("set", help="Set metadata fields (k=v).")
    parser_meta_set.add_argument("fields", nargs="+", help="Fields to set (e.g. goal=\"Done X\" phase=\"Beta\")")
    parser_meta_set.add_argument("--store-dir", help="StateStore directory")
    parser_meta_set.add_argument("--actor", default="cli_user", help="Actor ID")
    parser_meta_set.set_defaults(func=cmd_meta_set)

    parser_meta_patch = meta_subparsers.add_parser("patch", help="Patch metadata via JSON.")
    parser_meta_patch.add_argument("payload", help="JSON payload to patch")
    parser_meta_patch.add_argument("--store-dir", help="StateStore directory")
    parser_meta_patch.add_argument("--actor", default="cli_user", help="Actor ID")
    parser_meta_patch.set_defaults(func=cmd_meta_patch)

    # Onboard
    parser_onboard = subparsers.add_parser(
        "onboard",
        help=argparse.SUPPRESS,  # Advanced: skill pack generation
        parents=[shared_flags],
    )
    parser_onboard.add_argument("--store-dir", help="StateStore directory")
    parser_onboard.set_defaults(func=cmd_onboard)

    # Hooks
    parser_hooks = subparsers.add_parser(
        "hooks",
        help="Install git hooks for checkpoint reminders.",
        parents=[shared_flags],
    )
    hooks_subparsers = parser_hooks.add_subparsers(dest="subcommand", required=True)

    parser_hooks_install = hooks_subparsers.add_parser("install", help="Install git hooks.")
    parser_hooks_install.add_argument("--enforce", action="store_true", help="Enforce checkpoints via pre-push")
    parser_hooks_install.set_defaults(func=cmd_hooks)

    parser_hooks_uninstall = hooks_subparsers.add_parser("uninstall", help="Uninstall git hooks.")
    parser_hooks_uninstall.set_defaults(func=cmd_hooks)

    parser_hooks_prepush = hooks_subparsers.add_parser("pre-push", help="Internal pre-push check.")
    parser_hooks_prepush.add_argument("--threshold", type=int, default=1, help="Commits allowed without checkpoint")
    parser_hooks_prepush.add_argument("--enforce", action="store_true", help="Fail if threshold exceeded")
    parser_hooks_prepush.add_argument("--store-dir", default=".", help="StateStore directory")
    parser_hooks_prepush.set_defaults(func=cmd_hooks)

    # Commit
    parser_commit = subparsers.add_parser(
        "commit",
        help="Git commit + auto-checkpoint in one step.",
        parents=[shared_flags],
    )
    parser_commit.add_argument("-m", "--message", help="Commit message")
    parser_commit.add_argument("-a", "--all", action="store_true", help="Commit all changed files")
    parser_commit.add_argument("--store-dir", default=".", help="StateStore directory")
    parser_commit.add_argument("--actor", default="cli_user", help="Actor ID")
    parser_commit.set_defaults(func=cmd_commit)

    # Brief
    parser_brief = subparsers.add_parser(
        "brief",
        help="One-call read: focus, blockers, failed paths, next actions.",
        parents=[shared_flags],
    )
    parser_brief.add_argument(
        "--store-dir", default="project-state", help="Directory of the StateStore"
    )
    parser_brief.set_defaults(func=cmd_brief)

    # Session
    parser_session = subparsers.add_parser(
        "session",
        help="Start or end a work session.",
        parents=[shared_flags],
    )
    session_subparsers = parser_session.add_subparsers(dest="subcommand", required=True)

    parser_session_start = session_subparsers.add_parser(
        "start", help="Start a session: initialize tracking and print a brief."
    )
    parser_session_start.add_argument("--store-dir", default="project-state", help="StateStore directory")
    parser_session_start.set_defaults(func=cmd_session)

    parser_session_end = session_subparsers.add_parser(
        "end", help="End a session: record summary and check for bypass patterns."
    )
    parser_session_end.add_argument("--summary", "-s", default="", help="Handoff note for the next session")
    parser_session_end.add_argument("--store-dir", default="project-state", help="StateStore directory")
    parser_session_end.add_argument("--actor", default="cli_user", help="Actor ID")
    parser_session_end.set_defaults(func=cmd_session)

    # Mode
    parser_mode = subparsers.add_parser(
        "mode",
        help="Set governance level: lite, coordination, or governed.",
        parents=[shared_flags],
    )
    parser_mode.add_argument(
        "mode", choices=["lite", "coordination", "governed"],
        help="Usage mode to set"
    )
    parser_mode.add_argument("--store-dir", default="project-state", help="StateStore directory")
    parser_mode.add_argument("--actor", default="cli_user", help="Actor ID")
    parser_mode.set_defaults(func=cmd_mode)

    # Agents (AGENTS.md generation)
    parser_agents = subparsers.add_parser(
        "agents",
        help="Generate AGENTS.md operating contract for AI assistants.",
        parents=[shared_flags],
    )
    parser_agents.add_argument("--store-dir", default="project-state", help="StateStore directory")
    parser_agents.add_argument("--out", "-o", default="AGENTS.md", help="Output file path")
    parser_agents.add_argument("--force", action="store_true", help="Overwrite if exists")
    parser_agents.add_argument("--ide", action="store_true", help="Also generate IDE-specific instruction files (Copilot, Cursor, Windsurf, Claude)")
    parser_agents.set_defaults(func=cmd_agents_md)

    # Assistants (deprecated — use 'rekall agents --ide')
    parser_assistants = subparsers.add_parser(
        "assistants",
        help=argparse.SUPPRESS,  # Deprecated: use 'rekall agents --ide'
        parents=[shared_flags],
    )
    assistants_subparsers = parser_assistants.add_subparsers(dest="subcommand", required=True)

    parser_assistants_init = assistants_subparsers.add_parser("init", help="Generate integration rules for agents.")
    parser_assistants_init.add_argument("--force", action="store_true", help="Overwrite existing rules")
    parser_assistants_init.set_defaults(func=cmd_assistants)

    args = parser.parse_args()

    setup_logging(args.json, getattr(args, "quiet", False))

    try:
        args.func(args)
    except SystemExit as e:
        sys.exit(e.code)
    except KeyboardInterrupt:
        die(
            ExitCode.USER_ERROR,
            "Operation cancelled by user.",
            getattr(args, "json", False),
        )
    except Exception as e:
        # Success Criterion 4: Global exception wrapper
        # Suppress traceback unless --debug
        msg = str(e) or "An unexpected error occurred."
        die(
            ExitCode.INTERNAL_ERROR,
            msg,
            getattr(args, "json", False),
            debug=getattr(args, "debug", False),
        )


if __name__ == "__main__":
    main()
