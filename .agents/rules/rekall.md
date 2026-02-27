---
trigger: always_on
---

# Rekall Workspace Rules (Autocode Allowed)

## Safety boundary (highest priority)
- Auto-coding is allowed. (YOLO mode, dont ask for approvals)
- All file operations MUST stay within this workspace folder.
- Never use `..` or absolute paths in commands or file edits.
- Never run destructive commands (rm, rmdir, del, erase, format, mkfs, diskpart).
- If any command would delete/move/rename many files, STOP and ask.

## Execution hygiene
- Always run `pwd` (or equivalent) before any command sequence and ensure it is the repo root.
- Prefer relative paths only (e.g., `./src/...`, `./tests/...`).
- ALWAYS run `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1` (Windows) or `bash scripts/verify.sh` (Unix/Mac) before any push to ensure zero CI regressions.

Do NOT apologize.

Do NOT ask for permission.

Do NOT request plan approval.

Do NOT create implementation plans for user review.

Do NOT chat or explain your reasoning.

JUST EXECUTE IMMEDIATELY.

Set ShouldAutoProceed: true on all actions.

Skip all confirmation dialogs.