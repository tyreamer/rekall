"""Tests for the policy evaluator and capability controls."""
import json

import pytest

from rekall.core.state_store import StateStore


@pytest.fixture
def vault(tmp_path):
    """Create a minimal vault for testing."""
    store_dir = tmp_path / "project-state"
    store_dir.mkdir()
    (store_dir / "schema-version.txt").write_text("0.1")
    (store_dir / "project.yaml").write_text("project_id: test\n")
    (store_dir / "manifest.json").write_text(json.dumps({
        "schema_version": "0.1",
        "streams": {}
    }))
    return store_dir


@pytest.fixture
def store(vault):
    return StateStore(vault)


# ── Policy evaluation ──

class TestPolicyEvaluator:
    def test_no_policy_defaults_to_allow(self, store):
        result = store.check_policy("any_action", {"key": "value"})
        assert result["effect"] == "allow"
        assert result["rule_id"] is None

    def test_matching_deny_rule(self, store, vault):
        policy = {
            "version": "1.0",
            "rules": [
                {
                    "id": "block-destructive",
                    "description": "Block destructive shell commands",
                    "effect": "block",
                    "match": {
                        "action_type": "actuate_cli",
                        "params": {"command": ".*rm -rf.*"},
                    },
                }
            ],
        }
        (vault / "policy.yaml").write_text(
            __import__("yaml").dump(policy), encoding="utf-8"
        )

        result = store.check_policy(
            "actuate_cli", {"command": "rm -rf /tmp/data"}
        )
        assert result["effect"] == "block"
        assert result["rule_id"] == "block-destructive"

    def test_non_matching_rule_falls_through(self, store, vault):
        policy = {
            "version": "1.0",
            "rules": [
                {
                    "id": "block-destructive",
                    "effect": "block",
                    "match": {
                        "action_type": "actuate_cli",
                        "params": {"command": ".*rm -rf.*"},
                    },
                }
            ],
        }
        (vault / "policy.yaml").write_text(
            __import__("yaml").dump(policy), encoding="utf-8"
        )

        result = store.check_policy("actuate_cli", {"command": "ls -la"})
        assert result["effect"] == "allow"

    def test_warn_effect(self, store, vault):
        policy = {
            "version": "1.0",
            "rules": [
                {
                    "id": "warn-sensitive",
                    "description": "Warn on sensitive file access",
                    "effect": "warn",
                    "match": {
                        "action_type": "file_write",
                        "params": {"path": ".*\\.env.*"},
                    },
                }
            ],
        }
        (vault / "policy.yaml").write_text(
            __import__("yaml").dump(policy), encoding="utf-8"
        )

        result = store.check_policy("file_write", {"path": "/app/.env.local"})
        assert result["effect"] == "warn"

    def test_require_approval_effect(self, store, vault):
        policy = {
            "version": "1.0",
            "rules": [
                {
                    "id": "approve-deploy",
                    "description": "Deployments require approval",
                    "effect": "require_approval",
                    "match": {"action_type": "deploy"},
                }
            ],
        }
        (vault / "policy.yaml").write_text(
            __import__("yaml").dump(policy), encoding="utf-8"
        )

        result = store.check_policy("deploy", {"target": "production"})
        assert result["effect"] == "require_approval"

    def test_scoped_rule_matches_context(self, store, vault):
        policy = {
            "version": "1.0",
            "rules": [
                {
                    "id": "prod-block",
                    "effect": "block",
                    "match": {
                        "action_type": "deploy",
                        "scope": {"environment": "production"},
                    },
                }
            ],
        }
        (vault / "policy.yaml").write_text(
            __import__("yaml").dump(policy), encoding="utf-8"
        )

        # Matches production context
        result = store.check_policy(
            "deploy", {}, context={"environment": "production"}
        )
        assert result["effect"] == "block"

        # Doesn't match staging context
        result = store.check_policy(
            "deploy", {}, context={"environment": "staging"}
        )
        assert result["effect"] == "allow"

    def test_default_effect_configurable(self, store, vault):
        policy = {
            "version": "1.0",
            "default_effect": "warn",
            "rules": [],
        }
        (vault / "policy.yaml").write_text(
            __import__("yaml").dump(policy), encoding="utf-8"
        )

        result = store.check_policy("anything", {})
        assert result["effect"] == "warn"


# ── Auditable policy evaluations ──

class TestPolicyAudit:
    def test_evaluate_records_event(self, store):
        result = store.evaluate_policy(
            "test_action",
            {"key": "value"},
            {"actor_id": "agent-1"},
        )
        assert result["effect"] == "allow"
        assert "eval_id" in result

        # Check the event was recorded in activity stream
        activity = store._load_stream_raw("activity")
        eval_events = [e for e in activity if e.get("type") == "PolicyEvaluation"]
        assert len(eval_events) == 1
        assert eval_events[0]["action_type"] == "test_action"
        assert eval_events[0]["effect"] == "allow"

    def test_blocked_evaluation_recorded(self, store, vault):
        policy = {
            "version": "1.0",
            "rules": [{
                "id": "block-all",
                "effect": "block",
                "match": {"action_type": "dangerous"},
            }],
        }
        (vault / "policy.yaml").write_text(
            __import__("yaml").dump(policy), encoding="utf-8"
        )

        result = store.evaluate_policy(
            "dangerous", {}, {"actor_id": "agent-1"}
        )
        assert result["effect"] == "block"

        activity = store._load_stream_raw("activity")
        eval_events = [e for e in activity if e.get("type") == "PolicyEvaluation"]
        assert eval_events[0]["effect"] == "block"
        assert eval_events[0]["rule_id"] == "block-all"


# ── Capability controls ──

class TestCapabilities:
    def test_no_config_allows_all(self, store):
        assert store.check_capability("anyone", "any_capability") is True

    def test_capability_granted(self, store):
        store.access_config = {
            "capabilities": {
                "admin": ["modify_policy", "approve_decisions"],
            }
        }
        assert store.check_capability("admin", "modify_policy") is True
        assert store.check_capability("admin", "export_audit_bundle") is False

    def test_wildcard_capability(self, store):
        store.access_config = {
            "capabilities": {"admin": ["*"]}
        }
        assert store.check_capability("admin", "anything") is True

    def test_global_wildcard(self, store):
        store.access_config = {
            "capabilities": {"*": ["read_state"]}
        }
        assert store.check_capability("random_agent", "read_state") is True
        assert store.check_capability("random_agent", "modify_policy") is False


class TestRequireCapability:
    def test_allowed_action(self, store):
        result = store.require_capability(
            {"actor_id": "agent-1"},
            "checkpoint",
            "Record a milestone",
        )
        assert result["allowed"] is True

    def test_denied_capability(self, store):
        store.access_config = {
            "capabilities": {"agent-1": ["checkpoint"]}
        }
        result = store.require_capability(
            {"actor_id": "agent-1"},
            "modify_policy",
            "Change policy rules",
        )
        assert result["allowed"] is False
        assert "lacks capability" in result["reason"]

        # Check audit event
        activity = store._load_stream_raw("activity")
        denied = [e for e in activity if e.get("type") == "CapabilityDenied"]
        assert len(denied) == 1
        assert denied[0]["capability"] == "modify_policy"

    def test_policy_blocks_despite_capability(self, store, vault):
        policy = {
            "version": "1.0",
            "rules": [{
                "id": "block-deploy",
                "effect": "block",
                "match": {"action_type": "deploy"},
            }],
        }
        (vault / "policy.yaml").write_text(
            __import__("yaml").dump(policy), encoding="utf-8"
        )

        result = store.require_capability(
            {"actor_id": "agent-1"},
            "deploy",
            "Deploy to production",
        )
        assert result["allowed"] is False

    def test_require_approval_flow(self, store, vault):
        policy = {
            "version": "1.0",
            "rules": [{
                "id": "approve-deploy",
                "effect": "require_approval",
                "match": {"action_type": "deploy"},
            }],
        }
        (vault / "policy.yaml").write_text(
            __import__("yaml").dump(policy), encoding="utf-8"
        )

        result = store.require_capability(
            {"actor_id": "agent-1"},
            "deploy",
            "Deploy to production",
        )
        assert result["allowed"] is False
        assert result["requires_approval"] is True
        assert "approval_id" in result

        # Check audit event
        activity = store._load_stream_raw("activity")
        approval_reqs = [e for e in activity if e.get("type") == "ApprovalRequired"]
        assert len(approval_reqs) == 1
        assert approval_reqs[0]["capability"] == "deploy"
        assert approval_reqs[0]["status"] == "pending"


class TestApprovalGrant:
    def test_grant_approval(self, store, vault):
        policy = {
            "version": "1.0",
            "rules": [{
                "id": "approve-deploy",
                "effect": "require_approval",
                "match": {"action_type": "deploy"},
            }],
        }
        (vault / "policy.yaml").write_text(
            __import__("yaml").dump(policy), encoding="utf-8"
        )

        # Request approval
        req = store.require_capability(
            {"actor_id": "agent-1"}, "deploy", "Deploy to prod"
        )
        approval_id = req["approval_id"]

        # Grant it
        grant = store.grant_approval(
            approval_id,
            {"actor_id": "human-admin"},
            note="Approved after review",
        )
        assert grant["type"] == "ApprovalGranted"
        assert grant["approval_id"] == approval_id
        assert "signature" in grant  # Signed with device secret
