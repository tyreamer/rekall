from rekall.core.policy import PolicyEngine
from rekall.core.state_store import StateStore


def test_policy_engine_matches():
    policy_data = {
        "version": "1.0",
        "rules": [
            {
                "id": "deny-rm",
                "effect": "deny",
                "match": {
                    "action_type": "actuate_cli",
                    "params": {"command": "rm -rf .*"}
                }
            }
        ]
    }
    engine = PolicyEngine(policy_data)

    # 1. Match
    res = engine.check_action("actuate_cli", {"command": "rm -rf /"})
    assert res["effect"] == "deny"
    assert res["rule_id"] == "deny-rm"

    # 2. No match
    res = engine.check_action("actuate_cli", {"command": "ls -l"})
    assert res["effect"] == "allow"

def test_state_store_auto_policy(tmp_path):
    (tmp_path / "schema-version.txt").write_text("0.1", encoding="utf-8")
    StateStore(tmp_path)
    policy_file = tmp_path / "policy.yaml"
    assert policy_file.exists()
    assert "warn-destructive-shell" in policy_file.read_text()

def test_propose_action_records_policy_check(tmp_path):
    # Initialize minimal state
    (tmp_path / "schema-version.txt").write_text("0.1", encoding="utf-8")
    store = StateStore(tmp_path)
    actor = {"actor_id": "test-agent"}

    # Propose a "safe" action
    store.propose_action(
        action_type="nop",
        params={},
        risk_hint="low",
        context={},
        actor=actor
    )

    # Check activity.jsonl for PolicyCheck
    activity = store._load_stream_raw("activity.jsonl")
    checks = [e for e in activity if e.get("type") == "PolicyCheck"]
    assert len(checks) == 1
    assert checks[0]["effect"] == "allow"

    # Propose a "destructive" action
    store.propose_action(
        action_type="actuate_cli",
        params={"command": "rm -rf /"},
        risk_hint="high",
        context={},
        actor=actor
    )

    activity = store._load_stream_raw("activity.jsonl")
    checks = [e for e in activity if e.get("type") == "PolicyCheck"]
    assert len(checks) == 2
    print(f"DEBUG: checks[1] = {checks[1]}")
    assert checks[1]["effect"] == "deny"
    assert "destructive" in checks[1]["reason"].lower()
