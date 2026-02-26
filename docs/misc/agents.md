# Rekall Agent Boundary Rules

- You may only read/write files under this repository root.
- Never access parent directories (no `..`) and never use absolute paths (`/`, `C:\`, `~`).
- Never run destructive commands (rm, rmdir, del, erase, format, mkfs, diskpart).
- If you think a destructive operation is required, STOP and ask.
- Before running commands, ensure you are in the repo root and print `pwd` / current directory.