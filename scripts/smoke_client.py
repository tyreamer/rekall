import json
import os
import subprocess
import sys
import uuid


def send_request(proc, method: str, params: dict = None) -> dict:
    req_id = str(uuid.uuid4())
    req = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params:
        req["params"] = params

    print(f"\n>>> SENDING: {method}")
    print(json.dumps(req, indent=2))

    proc.stdin.write(json.dumps(req) + "\n")
    proc.stdin.flush()

    # Read response
    line = proc.stdout.readline()
    if not line:
        return {}

    try:
        res = json.loads(line)
        print("<<< RECEIVED:")
        print(json.dumps(res, indent=2))
        return res
    except json.JSONDecodeError:
        print(f"<<< RECEIVED (RAW): {line}")
        return {}


def run_smoke_test():
    # Setup paths
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    server_script = os.path.join(root_dir, "src", "rekall", "server", "mcp_server.py")

    # Start server
    print(f"Starting server: {server_script}...")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(root_dir, "src")

    proc = subprocess.Popen(
        [sys.executable, server_script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,  # let errors go to terminal
        text=True,
        env=env,
    )

    try:
        # 1. Initialize
        send_request(proc, "initialize")

        # 2. tools/list
        print("\n" + "=" * 50)
        print("TEST: tools/list")
        res = send_request(proc, "tools/list")
        tools = res.get("result", {}).get("tools", [])
        print(f"-> Discovered {len(tools)} tools.")

        # 3. exec.query (ON_TRACK)
        print("\n" + "=" * 50)
        print("TEST: exec.query -> ON_TRACK")
        send_request(
            proc,
            "tools/call",
            {
                "name": "exec.query",
                "arguments": {"project_id": "proj_123", "query_type": "ON_TRACK"},
            },
        )

        # 4. exec.query (RESUME_IN_30)
        print("\n" + "=" * 50)
        print("TEST: exec.query -> RESUME_IN_30")
        send_request(
            proc,
            "tools/call",
            {
                "name": "exec.query",
                "arguments": {"project_id": "proj_123", "query_type": "RESUME_IN_30"},
            },
        )

        # 5. work.update (CONFLICT CASE)
        print("\n" + "=" * 50)
        print(
            "TEST: work.update -> CONFLICT (showing isError: true and structured payload)"
        )
        send_request(
            proc,
            "tools/call",
            {
                "name": "work.update",
                "arguments": {
                    "project_id": "proj_123",
                    "work_item_id": "task_auth_01",
                    "expected_version": 999,  # intentional failure, sample state is version 2
                    "patch": {"status": "done"},
                    "actor": {"actor_type": "agent", "actor_id": "smoke_test_agent"},
                },
            },
        )

    finally:
        print("\nShutting down server...")
        proc.stdin.close()
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    run_smoke_test()
