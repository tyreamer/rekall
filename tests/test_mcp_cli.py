import json
import io
import sys
from argparse import Namespace
from pathlib import Path
import tempfile
import pytest

from rekall.cli import cmd_serve, main

def test_serve_help(capfd):
    """Verify rekall serve --help includes the host flag and description."""
    with pytest.raises(SystemExit) as excinfo:
        sys.argv = ["rekall", "serve", "--help"]
        main()
    
    assert excinfo.value.code == 0
    captured = capfd.readouterr()
    assert "serve" in captured.out
    assert "--host" in captured.out
    assert "--store-dir" in captured.out

def test_serve_stdio_handshake(capfd, monkeypatch):
    """Verify rekall serve responds to initialize request and diagnostic logs go to stderr."""
    with tempfile.TemporaryDirectory() as d:
        base_dir = Path(d)
        
        # Prepare input stream
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0.0"}
            }
        }
        # Add a blank line to terminate the loop after first request
        input_data = json.dumps(init_req) + "\n\n"
        monkeypatch.setattr(sys, "stdin", io.StringIO(input_data))

        args = Namespace(
            store_dir=str(base_dir),
            store_dir_flag=".",
            host="stdio",
            json=True, # Inferred from serve command context in real usage
            debug=False,
            quiet=False
        )

        # cmd_serve will call mcp_server.main() which loops over stdin
        # We need to catch the SystemExit if it happens or just let it finish.
        # Since we added \n\n, it should exit the loop and return.
        cmd_serve(args)

        captured = capfd.readouterr()
        
        # stdout should contain ONLY the JSON-RPC response
        stdout_lines = captured.out.strip().split("\n")
        assert len(stdout_lines) == 1
        resp = json.loads(stdout_lines[0])
        assert resp["id"] == 1
        assert "serverInfo" in resp["result"]
        assert resp["result"]["serverInfo"]["name"] == "rekall-mcp"

        # stderr should contain the "Initializing" log
        assert "INFO: Initializing minimal structure" in captured.err
