# Checkpointing

Losing agent context mid-task is painful. `rekall checkpoint` is a "save game" for your project. It creates a durable export of your current state so you can roll back or branch off if things go sideways.

## Usage

```powershell
# Save a checkpoint before a risky change
rekall checkpoint my_project -o ./checkpoints/pre-deploy --store-dir ./project-state --label "pre-deploy v2.1"

# JSON output for automation
rekall --json checkpoint my_project -o ./checkpoints/pre-deploy --store-dir ./project-state --label "pre-deploy v2.1"
```

## What each checkpoint does:
1. Exports the full state folder to `<out_dir>` (passes `rekall validate`)
2. Appends a `milestone` timeline event with the label, export path, and evidence ref
3. Supports `--event-id` for idempotent re-runs (same event_id -> no duplicate timeline entries)
