import re
import yaml
from typing import Any, Dict, List, Optional

class PolicyEngine:
    def __init__(self, policy_data: Dict[str, Any]):
        self.version = policy_data.get("version", "1.0")
        self.rules = policy_data.get("rules", [])

    @classmethod
    def from_file(cls, path: str) -> "PolicyEngine":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(data or {"rules": []})

    def check_action(self, action_type: str, params: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Checks an action against the policy rules. 
        Returns { "effect": "allow"|"deny", "rule_id": str|None, "reason": str|None }
        """
        for rule in self.rules:
            if self._matches(rule, action_type, params, context or {}):
                return {
                    "effect": rule.get("effect", "deny"),
                    "rule_id": rule.get("id"),
                    "reason": rule.get("description", "Policy rule match")
                }
        
        return {"effect": "allow", "rule_id": None, "reason": "No policy rules matched"}

    def _matches(self, rule: Dict[str, Any], action_type: str, params: Dict[str, Any], context: Dict[str, Any]) -> bool:
        match_cfg = rule.get("match", {})
        
        # Match action_type
        if "action_type" in match_cfg:
            if not re.search(match_cfg["action_type"], action_type):
                return False
                
        # Match params (recursive keys)
        if "params" in match_cfg:
            if not self._match_dict(match_cfg["params"], params):
                return False
                
        # Match context
        if "context" in match_cfg:
            if not self._match_dict(match_cfg["context"], context):
                return False
                
        return True

    def _match_dict(self, pattern: Dict[str, Any], data: Dict[str, Any]) -> bool:
        for k, v in pattern.items():
            if k not in data:
                return False
            
            actual_v = data[k]
            if isinstance(v, dict) and isinstance(actual_v, dict):
                if not self._match_dict(v, actual_v):
                    return False
            elif isinstance(v, str):
                actual_str = str(actual_v)
                match = re.search(v, actual_str)
                if not match:
                    return False
            elif v != actual_v:
                return False
                
        return True

def get_default_policy() -> str:
    return """version: "1.0"
# Tier 0 Default Policy: Shadow mode (record but don't block)
rules:
  - id: "warn-destructive-shell"
    description: "Destructive shell commands detected"
    effect: "deny"
    match:
      action_type: "actuate_cli"
      params:
        command: ".*(rm -rf|del /s /q|format |mkfs|dd if=).*"
  - id: "warn-sensitive-file-write"
    description: "Writing to sensitive system files"
    effect: "deny"
    match:
      action_type: "actuate_file_write"
      params:
        path: ".*(/etc/passwd|/etc/shadow|C:\\\\Windows\\\\System32).*"
"""
