# Idempotency Keys

Agents crash. Networks fail. Idempotency keys make sure high-impact actions—like sending an email or running a migration—only happen **exactly once**, even if the agent retries.

## How it works
If you try to write a record with a key that already exists, Rekall returns the existing record instead of creating a duplicate.

## Example JSON-RPC call
```json
{
  "method": "tools/call",
  "params": {
    "name": "attempt.append",
    "arguments": {
      "project_id": "my_project",
      "idempotency_key": "send-deploy-email-v2.1",
      "attempt": { "work_item_id": "wi_1", "title": "Send deploy notification", "outcome": "success" },
      "actor": { "actor_id": "deploy_agent" }
    }
  }
}
```

## CLI Usage
```powershell
rekall attempts add wi_1 --title "Deploy email" --evidence "logs/out.log" --idempotency-key "send-deploy-email-v2.1"
rekall timeline add --summary "Migration complete" --idempotency-key "run-migration-001"
```

## Validation
`rekall validate` warns (or fails with `--strict`) if duplicate idempotency keys are detected in JSONL files.
