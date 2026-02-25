# Security Policy

## Core Principle

**Rekall must never store secrets.** API keys, tokens, passwords, and other credentials must not appear in state artifacts, JSONL files, YAML manifests, or any file committed to a Rekall project-state folder. The `env_pointers` spec is explicitly designed to reference *where* credentials live (e.g., a vault path or env var name) without containing the credentials themselves.

Run the secret scanner before every commit:

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File scripts/scan_secrets.ps1

# macOS / Linux
bash scripts/scan_secrets.sh
```

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| v0.1.x  | :white_check_mark: |

## Reporting a Vulnerability

**Do NOT report security issues via public GitHub issues.**

If you discover a vulnerability in Rekall's validation logic, state machine architecture, CLI, directory traversal handling, or secret-detection heuristics, please email:

**security@rekall.io**

Include:
- Steps to reproduce
- Expected vs. actual behavior
- Potential impact assessment

We will acknowledge receipt within **72 hours** and provide a timeline for remediation.
