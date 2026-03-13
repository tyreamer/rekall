from pathlib import Path

mcp_path = Path("d:/Projects/Rekall/src/rekall/server/mcp_server.py")
content = mcp_path.read_text(encoding="utf-8")

new_defs = """TOOLS_DEF = [
    {
        "name": "session.brief",
        "description": "One-call session brief. Returns current focus, blockers, failed attempts (do not retry), pending decisions, recommended next actions, and drift warnings. Call this at the start of every session to get full working context.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "project.bootstrap",
        "description": "Idempotent startup tool. Ensures vault exists, sets project metadata, and returns current state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string"},
                "phase": {"type": "string"},
                "status": {"type": "string"},
                "confidence": {"type": "string"},
                "actor": {"type": "object"}
            }
        }
    },
    {
        "name": "attempt.append",
        "description": "Append an attempt note.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "attempt", "actor"],
            "properties": {
                "project_id": {"type": "string"},
                "attempt": {"type": "object"},
                "actor": {"type": "object"},
                "reason": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
        },
    },
    {
        "name": "decision.propose",
        "description": "Propose a decision log.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "decision", "actor"],
            "properties": {
                "project_id": {"type": "string"},
                "decision": {"type": "object"},
                "actor": {"type": "object"},
                "reason": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
        },
    },
    {
        "name": "decision.approve",
        "description": "Approve a decision.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "decision_id", "actor"],
            "properties": {
                "project_id": {"type": "string"},
                "decision_id": {"type": "string"},
                "actor": {"type": "object"},
                "reason": {"type": "string"},
            },
        },
    },
    {
        "name": "timeline.append",
        "description": "Append a timeline event.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id", "event", "actor"],
            "properties": {
                "project_id": {"type": "string"},
                "event": {"type": "object"},
                "actor": {"type": "object"},
                "reason": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
        },
    },
    {
        "name": "rekall_checkpoint",
        "description": "Record a timeline checkpoint (task_done, decision, etc) and optionally attach git commit.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {
                "project_id": {"type": "string"},
                "type": {
                    "type": "string",
                    "description": "task_done | decision | attempt_failed | artifact | milestone"
                },
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "git_commit": {
                    "type": "string",
                    "description": "'auto' to resolve HEAD, or a specific SHA"
                },
                "actor": {"type": "object"}
            }
        }
    },
    {
        "name": "guard.query",
        "description": "Preflight drift guard. Returns project constraints, recent decisions, recent attempts, risks/blockers, and environment pointers. Read-only.",
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {"project_id": {"type": "string"}},
        },
    },
]

TOOL_REGISTRY = {
    "session.brief": session_brief,
    "project.bootstrap": project_bootstrap,
    "attempt.append": attempt_append,
    "decision.propose": decision_propose,
    "decision.approve": decision_approve,
    "timeline.append": timeline_append,
    "rekall_checkpoint": rekall_checkpoint,
    "guard.query": guard_query,
}"""

# Find the start of TOOLS_DEF
start_idx = content.find("TOOLS_DEF = [")
# Find the start of `def send_response` which comes after TOOL_REGISTRY
end_idx = content.find("def send_response(response: dict):")

if start_idx != -1 and end_idx != -1:
    new_content = content[:start_idx] + new_defs + "\\n\\n\\n" + content[end_idx:]
    mcp_path.write_text(new_content, encoding="utf-8")
    print("Successfully pruned mcp_server.py")
else:
    print("Could not find boundaries")
