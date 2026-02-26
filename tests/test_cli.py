import os
import tempfile
import json
import pytest
from pathlib import Path
from rekall.cli import cmd_validate, cmd_export, cmd_import, cmd_handoff, ExitCode
from argparse import Namespace


@pytest.fixture
def temp_store():
    with tempfile.TemporaryDirectory() as d:
        base_dir = Path(d)
        from rekall.cli import ensure_state_initialized
        from rekall.core.state_store import StateStore

        ensure_state_initialized(base_dir, is_json=True)

        event = {
            "event_id": "e1",
            "type": "WORK_ITEM_CREATED",
            "work_item_id": "wi_1",
            "patch": {"title": "Test Item", "status": "todo", "priority": "p1"},
        }

        store = StateStore(base_dir)
        store.append_jsonl_idempotent("work_items", event, "event_id")
        yield base_dir


def test_cmd_validate_success(temp_store, capfd):
    args = Namespace(store_dir=str(temp_store), json=False, strict=False)
    # cmd_validate should not exit on success. If it does, it's a test failure.
    cmd_validate(args)
    captured = capfd.readouterr()
    assert "Status: ✅" in captured.out


def test_cmd_validate_missing_dir(capfd):
    # Test validation when store_dir does not exist
    args = Namespace(store_dir="/nonexistent/path", json=False, strict=False)
    with pytest.raises(SystemExit) as excinfo:
        cmd_validate(args)
    assert excinfo.value.code == ExitCode.NOT_FOUND.value


def test_cmd_validate_failure():
    with tempfile.TemporaryDirectory() as d:
        base_dir = Path(d)
        (base_dir / "schema-version.txt").write_text("0.1")
        # Missing title and status so validation will flag it
        event = {
            "event_id": "e1",
            "type": "WORK_ITEM_CREATED",
            "work_item_id": "wi_1",
            "patch": {},
        }
        (base_dir / "streams/work_items").mkdir(parents=True, exist_ok=True)
        (base_dir / "streams/work_items/active.jsonl").write_text(
            json.dumps(event) + "\n"
        )

        args = Namespace(store_dir=d, json=False, strict=False)
        with pytest.raises(SystemExit) as excinfo:
            cmd_validate(args)
        assert excinfo.value.code == ExitCode.VALIDATION_FAILED.value


def test_cmd_export(temp_store):
    out_dir = temp_store / "output_dir"
    args = Namespace(store_dir=str(temp_store), out=str(out_dir), json=False)

    cmd_export(args)

    assert out_dir.exists()
    assert (out_dir / "project.yaml").exists()
    assert (out_dir / "schema-version.txt").exists()
    assert (out_dir / "streams/work_items/active.jsonl").exists()


def test_cmd_import(temp_store):
    out_dir = temp_store / "output_dir"
    args = Namespace(store_dir=str(temp_store), out=str(out_dir), json=False)
    cmd_export(args)

    # Import into a new dir
    with tempfile.TemporaryDirectory() as import_d:
        import_args = Namespace(source=str(out_dir), store_dir=import_d, json=False)
        cmd_import(import_args)

        imported_dir = Path(import_d)
        assert (imported_dir / "schema-version.txt").exists()
        assert (imported_dir / "project.yaml").exists()
        assert (imported_dir / "streams/work_items/active.jsonl").exists()


def test_cmd_handoff(temp_store):
    out_dir = temp_store / "handoff_out"
    args = Namespace(
        store_dir=str(temp_store), project_id="test_proj", out=str(out_dir)
    )

    cmd_handoff(args)

    assert out_dir.exists()
    assert (out_dir / "snapshot.json").exists()
    brief = out_dir / "boot_brief.md"
    assert brief.exists()

    content = brief.read_text()
    assert "Project Goal" in content
    assert "Status" in content
    assert "Blockers" in content
    assert "wi_1" in content


def test_validate_regression_missing_files(temp_store, capfd):
    os.remove(temp_store / "envs.yaml")
    args = Namespace(store_dir=str(temp_store), json=False, strict=True)
    with pytest.raises(SystemExit) as excinfo:
        cmd_validate(args)
    assert excinfo.value.code == ExitCode.VALIDATION_FAILED.value
    captured = capfd.readouterr()
    assert "missing" in captured.out.lower()


def test_validate_regression_malformed_jsonl():
    with tempfile.TemporaryDirectory() as d:
        base_dir = Path(d)
        (base_dir / "schema-version.txt").write_text("0.1")
        (base_dir / "project.yaml").write_text("project_id: test_proj\n")
        (base_dir / "envs.yaml").write_text("dev: {}")
        (base_dir / "access.yaml").write_text("roles: {}")

        # Malformed jsonl
        (base_dir / "streams/work_items").mkdir(parents=True, exist_ok=True)
        (base_dir / "streams/work_items/active.jsonl").write_text("{bad json\n")

        args = Namespace(store_dir=d, json=False, strict=False)
        with pytest.raises(SystemExit) as excinfo:
            cmd_validate(args)
        assert excinfo.value.code == ExitCode.VALIDATION_FAILED.value


def test_validate_regression_duplicate_ids():
    with tempfile.TemporaryDirectory() as d:
        base_dir = Path(d)
        (base_dir / "schema-version.txt").write_text("0.1")
        (base_dir / "project.yaml").write_text("project_id: test_proj\n")
        (base_dir / "envs.yaml").write_text("dev: {}")
        (base_dir / "access.yaml").write_text("roles: {}")

        event = {
            "event_id": "duplicate_1",
            "type": "WORK_ITEM_CREATED",
            "work_item_id": "wi_1",
            "patch": {"title": "Test", "status": "todo"},
        }
        content = json.dumps(event) + "\n" + json.dumps(event) + "\n"
        (base_dir / "streams/work_items").mkdir(parents=True, exist_ok=True)
        (base_dir / "streams/work_items/active.jsonl").write_text(content)

        args = Namespace(store_dir=d, json=False, strict=True)
        with pytest.raises(SystemExit) as excinfo:
            cmd_validate(args)
        assert excinfo.value.code == ExitCode.VALIDATION_FAILED.value


def test_validate_regression_expired_claim(temp_store, capfd):
    import datetime

    store = temp_store

    # Manually inject an expired claim into work-items.jsonl
    event = {
        "event_id": "e_claim",
        "type": "WORK_ITEM_CLAIMED",
        "work_item_id": "wi_1",
        "patch": {
            "claimed_by": "test_user",
            "lease_until": (
                datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(hours=1)
            ).isoformat(),
        },
    }
    with open(store / "streams/work_items/active.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")

    args = Namespace(store_dir=str(store), json=False, strict=True)
    with pytest.raises(SystemExit) as excinfo:
        cmd_validate(args)
    assert excinfo.value.code == ExitCode.VALIDATION_FAILED.value
    captured = capfd.readouterr()
    assert "expired" in captured.out.lower()


def test_validate_json_schema(temp_store, capfd):
    args = Namespace(store_dir=str(temp_store), json=True, strict=False)
    # Should not raise
    cmd_validate(args)
    captured = capfd.readouterr()
    report = json.loads(captured.out)

    assert "summary" in report
    assert "schema_version" in report
    assert "files_present" in report
    assert "jsonl_integrity" in report
    assert "id_uniqueness" in report
    assert "references" in report
    assert "secrets" in report
    assert "claims" in report


def test_cmd_demo_os_output_windows(capfd, monkeypatch):
    import platform
    from rekall.cli import cmd_demo

    monkeypatch.setattr(platform, "system", lambda: "Windows")

    args = Namespace(json=False, quiet=True)
    cmd_demo(args)
    captured = capfd.readouterr()

    assert "✅ DEMO COMPLETE — OPEN THIS NOW:" in captured.out
    assert "notepad" in captured.out
    assert "Get-Content" in captured.out
    assert "rekall status" in captured.out


def test_cmd_demo_os_output_mac(capfd, monkeypatch):
    import platform
    from rekall.cli import cmd_demo

    monkeypatch.setattr(platform, "system", lambda: "Darwin")

    args = Namespace(json=False, quiet=True)
    cmd_demo(args)
    captured = capfd.readouterr()

    assert "✅ DEMO COMPLETE — OPEN THIS NOW:" in captured.out
    assert "open " in captured.out
    assert "rekall status" in captured.out


def test_cmd_demo_os_output_linux(capfd, monkeypatch):
    import platform
    from rekall.cli import cmd_demo

    monkeypatch.setattr(platform, "system", lambda: "Linux")

    args = Namespace(json=False, quiet=True)
    cmd_demo(args)
    captured = capfd.readouterr()

    assert "✅ DEMO COMPLETE — OPEN THIS NOW:" in captured.out
    assert "xdg-open" in captured.out


def test_cmd_attempts_add(temp_store):
    from rekall.cli import cmd_attempts_add

    args = Namespace(
        store_dir=str(temp_store),
        json=False,
        work_item_id="wi_1",
        title="Attempt 1",
        evidence="link.com",
        actor="user1",
    )
    cmd_attempts_add(args)

    with open(temp_store / "streams/attempts/active.jsonl") as f:
        data = f.read()
        assert "Attempt 1" in data
        assert "link.com" in data


def test_cmd_decisions_propose(temp_store):
    from rekall.cli import cmd_decisions_propose

    args = Namespace(
        store_dir=str(temp_store),
        json=False,
        title="Decision 1",
        rationale="because",
        tradeoffs="speed",
        actor="user1",
    )
    cmd_decisions_propose(args)

    with open(temp_store / "streams/decisions/active.jsonl") as f:
        data = f.read()
        assert "Decision 1" in data
        assert "because" in data


def test_cmd_lock(temp_store):
    from rekall.cli import cmd_lock

    args = Namespace(
        store_dir=str(temp_store),
        json=False,
        work_item_id="wi_1",
        expected_version=1,
        ttl="5m",
        force=False,
        actor="user1",
    )
    cmd_lock(args)

    with open(temp_store / "streams/work_items/active.jsonl") as f:
        data = f.read()
        assert "WORK_ITEM_CLAIMED" in data
        assert "user1" in data


def test_cmd_guard_human_output(temp_store, capfd):
    """Guard output contains constraints + evidence refs section headers."""
    from rekall.cli import cmd_guard, cmd_attempts_add, cmd_decisions_propose

    # Seed an attempt and decision so sections aren't empty
    cmd_attempts_add(
        Namespace(
            store_dir=str(temp_store),
            json=False,
            work_item_id="wi_1",
            title="A1",
            evidence="link1",
            actor="u1",
        )
    )
    cmd_decisions_propose(
        Namespace(
            store_dir=str(temp_store),
            json=False,
            title="D1",
            rationale="R1",
            tradeoffs="T1",
            actor="u1",
        )
    )

    args = Namespace(
        store_dir=str(temp_store),
        json=False,
        strict=False,
        emit_timeline=False,
        actor="cli_user",
    )
    cmd_guard(args)
    captured = capfd.readouterr()

    assert "REKALL PREFLIGHT GUARD" in captured.out
    assert "Constraints/Invariants" in captured.out
    assert "Most Recent Decisions" in captured.out
    assert "Most Recent Attempts" in captured.out
    assert "Risks/Blockers" in captured.out
    assert "Operate" in captured.out


def test_cmd_guard_json_output(temp_store, capfd):
    """--json outputs valid JSON with required keys."""
    from rekall.cli import cmd_guard

    args = Namespace(
        store_dir=str(temp_store),
        json=True,
        strict=False,
        emit_timeline=False,
        actor="cli_user",
    )
    cmd_guard(args)
    captured = capfd.readouterr()
    data = json.loads(captured.out)

    assert data["ok"] is True
    assert data["guard"] == "PASS"
    assert "project" in data
    assert "constraints" in data
    assert "recent_decisions" in data
    assert "recent_attempts" in data
    assert "risks_blockers" in data
    assert "operate" in data


def test_cmd_guard_strict_fails_no_constraints(temp_store):
    """--strict exits non-zero when no constraints defined."""
    from rekall.cli import cmd_guard, ExitCode

    args = Namespace(
        store_dir=str(temp_store),
        json=False,
        strict=True,
        emit_timeline=False,
        actor="cli_user",
    )
    with pytest.raises(SystemExit) as excinfo:
        cmd_guard(args)
    assert excinfo.value.code == ExitCode.VALIDATION_FAILED.value


def test_cmd_guard_emit_timeline_idempotent(temp_store):
    """--emit-timeline appends exactly one event and is idempotent on repeat."""
    from rekall.cli import cmd_guard

    args = Namespace(
        store_dir=str(temp_store),
        json=True,
        strict=False,
        emit_timeline=True,
        actor="cli_user",
    )

    cmd_guard(args)
    with open(temp_store / "streams/timeline/active.jsonl") as f:
        lines1 = [line for line in f.readlines() if line.strip()]

    cmd_guard(args)
    with open(temp_store / "streams/timeline/active.jsonl") as f:
        lines2 = [line for line in f.readlines() if line.strip()]

    # Should be exactly 1 event (idempotent by event_id)
    assert len(lines1) == 1
    assert len(lines2) == 1
    assert "Preflight guard run" in lines1[0]
