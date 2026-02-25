"""Tests for MCP self-check validation (rekall validate --mcp)."""

import json
import os
import subprocess
import sys
import tempfile
import pytest
from pathlib import Path
from argparse import Namespace
from unittest.mock import patch, MagicMock

from rekall.core.mcp_validator import (
    validate_schema,
    parse_tools_list,
    find_missing_tools,
    run_mcp_validation,
    format_human_report,
    REQUIRED_TOOLS,
)


# ── Unit: parse_tools_list ──────────────────────────────────────────────


class TestParseToolsList:
    def test_valid_response(self):
        resp = {
            "jsonrpc": "2.0",
            "id": "1",
            "result": {
                "tools": [
                    {"name": "project.list", "inputSchema": {"type": "object"}},
                    {"name": "work.list", "inputSchema": {"type": "object"}},
                ]
            },
        }
        tools, err = parse_tools_list(resp)
        assert err is None
        assert len(tools) == 2
        assert tools[0]["name"] == "project.list"

    def test_error_response(self):
        resp = {"error": {"code": -32601, "message": "Not found"}}
        tools, err = parse_tools_list(resp)
        assert tools == []
        assert "error" in err.lower()

    def test_missing_result(self):
        resp = {"jsonrpc": "2.0", "id": "1"}
        tools, err = parse_tools_list(resp)
        assert tools == []
        assert "missing" in err.lower()

    def test_missing_tools_key(self):
        resp = {"jsonrpc": "2.0", "id": "1", "result": {}}
        tools, err = parse_tools_list(resp)
        assert tools == []
        assert "tools" in err.lower()

    def test_tools_not_array(self):
        resp = {"jsonrpc": "2.0", "id": "1", "result": {"tools": "bad"}}
        tools, err = parse_tools_list(resp)
        assert tools == []
        assert "not an array" in err.lower()


# ── Unit: find_missing_tools ────────────────────────────────────────────


class TestFindMissingTools:
    def test_all_present(self):
        missing = find_missing_tools(REQUIRED_TOOLS)
        assert missing == []

    def test_some_missing(self):
        present = ["project.list", "work.list"]
        missing = find_missing_tools(present)
        assert "project.get" in missing
        assert "exec.query" in missing
        assert "project.list" not in missing

    def test_none_present(self):
        missing = find_missing_tools([])
        assert missing == REQUIRED_TOOLS

    def test_custom_required(self):
        missing = find_missing_tools(["a"], required=["a", "b", "c"])
        assert missing == ["b", "c"]


# ── Unit: validate_schema ───────────────────────────────────────────────


class TestValidateSchema:
    def test_valid_tool(self):
        tool = {
            "name": "project.list",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer"},
                    "cursor": {"type": "string"},
                },
            },
        }
        errs = validate_schema(tool)
        assert errs == []

    def test_missing_input_schema(self):
        tool = {"name": "broken_tool"}
        errs = validate_schema(tool)
        assert len(errs) == 1
        assert "missing inputSchema" in errs[0]

    def test_wrong_type(self):
        tool = {"name": "bad", "inputSchema": {"type": "string"}}
        errs = validate_schema(tool)
        assert any("not 'object'" in e for e in errs)

    def test_required_not_list(self):
        tool = {
            "name": "bad",
            "inputSchema": {"type": "object", "required": "project_id"},
        }
        errs = validate_schema(tool)
        assert any("not an array" in e for e in errs)

    def test_property_missing_type(self):
        tool = {
            "name": "bad",
            "inputSchema": {
                "type": "object",
                "properties": {"x": {"description": "no type"}},
            },
        }
        errs = validate_schema(tool)
        assert any("missing 'type'" in e for e in errs)

    def test_valid_with_required(self):
        tool = {
            "name": "work.get",
            "inputSchema": {
                "type": "object",
                "required": ["project_id", "work_item_id"],
                "properties": {
                    "project_id": {"type": "string"},
                    "work_item_id": {"type": "string"},
                },
            },
        }
        errs = validate_schema(tool)
        assert errs == []


# ── Unit: format_human_report ───────────────────────────────────────────


class TestFormatHumanReport:
    def test_pass_report(self):
        report = {
            "ok": True,
            "summary": {"total_tools": 21, "passed": 21, "warnings": 0, "errors": 0},
            "tools": [{"name": "project.list", "status": "✅", "errors": []}],
            "missing_tools": [],
            "schema_errors": [],
            "call_failures": [],
            "extra_tools": [],
        }
        out = format_human_report(report)
        assert "PASS" in out
        assert "MCP SELF-CHECK" in out
        assert "✅" in out

    def test_fail_report(self):
        report = {
            "ok": False,
            "summary": {"total_tools": 5, "passed": 3, "warnings": 0, "errors": 2},
            "tools": [{"name": "broken", "status": "❌", "errors": ["bad schema"]}],
            "missing_tools": ["exec.query"],
            "schema_errors": ["broken: bad schema"],
            "call_failures": [],
            "extra_tools": [],
        }
        out = format_human_report(report)
        assert "FAIL" in out
        assert "❌" in out
        assert "exec.query" in out


# ── Integration: run against actual MCP server ──────────────────────────


class TestRunMCPValidationIntegration:
    """Integration tests that launch the real MCP server subprocess."""

    @pytest.fixture
    def server_cmd(self):
        root = Path(__file__).parent.parent
        server_script = root / "src" / "rekall" / "server" / "mcp_server.py"
        return f"{sys.executable} {server_script}"

    def test_full_validation_passes(self, server_cmd):
        report = run_mcp_validation(server_cmd, strict=False)
        assert report["ok"] is True
        assert report["summary"]["total_tools"] >= len(REQUIRED_TOOLS)
        assert report["missing_tools"] == []
        assert len(report["schema_errors"]) == 0

    def test_full_validation_json_keys(self, server_cmd):
        report = run_mcp_validation(server_cmd, strict=False)
        # Required top-level keys per the spec
        assert "ok" in report
        assert "summary" in report
        assert "missing_tools" in report
        assert "schema_errors" in report
        assert "call_failures" in report

    def test_strict_mode(self, server_cmd):
        report = run_mcp_validation(server_cmd, strict=True)
        # Strict may or may not pass depending on probe calls with dummy IDs,
        # but the report structure must be valid
        assert isinstance(report["ok"], bool)
        assert isinstance(report["summary"], dict)

    def test_json_output_is_valid(self, server_cmd):
        """Ensure the report is JSON-serializable."""
        report = run_mcp_validation(server_cmd, strict=False)
        json_str = json.dumps(report)
        parsed = json.loads(json_str)
        assert parsed["ok"] == report["ok"]

    def test_human_output_format(self, server_cmd):
        report = run_mcp_validation(server_cmd, strict=False)
        output = format_human_report(report)
        assert "REKALL MCP SELF-CHECK" in output
        assert "Tools discovered:" in output


# ── CLI integration ─────────────────────────────────────────────────────


class TestCLIIntegration:
    def test_validate_mcp_missing_server_cmd(self, capfd):
        from rekall.cli import cmd_validate
        args = Namespace(
            store_dir=".", json=False, strict=False, mcp=True, server_cmd=None, quiet=False
        )
        with pytest.raises(SystemExit) as excinfo:
            cmd_validate(args)
        assert excinfo.value.code == 2  # VALIDATION_FAILED

    def test_validate_mcp_json_output(self, capfd):
        root = Path(__file__).parent.parent
        server_script = root / "src" / "rekall" / "server" / "mcp_server.py"
        server_cmd = f"{sys.executable} {server_script}"

        from rekall.cli import cmd_validate
        args = Namespace(
            store_dir=".", json=True, strict=False, mcp=True,
            server_cmd=server_cmd, quiet=False
        )
        try:
            cmd_validate(args)
        except SystemExit:
            pass

        captured = capfd.readouterr()
        data = json.loads(captured.out)
        assert "ok" in data
        assert "summary" in data
        assert "missing_tools" in data
        assert "schema_errors" in data
        assert "call_failures" in data

    def test_validate_mcp_human_output(self, capfd):
        root = Path(__file__).parent.parent
        server_script = root / "src" / "rekall" / "server" / "mcp_server.py"
        server_cmd = f"{sys.executable} {server_script}"

        from rekall.cli import cmd_validate
        args = Namespace(
            store_dir=".", json=False, strict=False, mcp=True,
            server_cmd=server_cmd, quiet=False
        )
        try:
            cmd_validate(args)
        except SystemExit:
            pass

        captured = capfd.readouterr()
        assert "MCP SELF-CHECK" in captured.out
        assert "Tools discovered:" in captured.out
