# Contributing to Rekall

Thanks for your interest! Here's how to get started.

## Development Setup

```bash
# Clone and create a virtual environment
git clone https://github.com/tyreamer/rekall.git
cd rekall
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install         # Optional: enables automatic checks on commit
```

## Running Tests

```bash
# Full suite
pytest tests/ -v
```

## Running Verification

Before pushing, always run the full quality suite:

```bash
# Windows (PowerShell)
./scripts/verify.ps1

# Unix/Mac
bash scripts/verify.sh
```

This runs **Ruff** (linting), **Mypy** (typing), and **Pytest** (tests).

### Smoke Test
```bash
rekall demo --quiet
```

## Code Style

- **Python 3.10+** — use type hints where practical.
- Follow PEP 8. Keep lines ≤ 120 characters.
- Every new CLI command must have a corresponding test in `tests/test_cli.py`.
- YAML/JSONL schemas must match `specs/04_state_spec_schema_v0.1.md`.
- No secrets, credentials, or PII anywhere in the repo. Run `scripts/scan_secrets.ps1` (Windows) or `bash scripts/scan_secrets.sh` before committing.

## Pull Request Process

1. Fork the repo and create a branch from `main`.
2. Make your change.
3. Add or update tests as needed.
4. Run `pytest tests/ -v` and confirm all tests pass.
5. Run the secret scanner to verify no sensitive data leaks.
6. Open a PR with a clear title and description. Reference any related issue.
7. Wait for CI to go green and a maintainer review.

## Commit Messages

Use conventional-style prefixes when possible:

```
feat: add timeline export command
fix: handle empty JSONL gracefully
docs: update quickstart with guard step
test: add checkpoint idempotency tests
chore: bump CI matrix to Python 3.13
```

## Reporting Bugs

Use the [Bug Report template](.github/ISSUE_TEMPLATE/bug_report.yml). Include `rekall validate --json` output.

## Suggesting Features

Use the [Feature Request template](.github/ISSUE_TEMPLATE/feature_request.yml). Explain why Rekall primitives fit.

## Release Gate Checklist

To ensure a high-quality release, all PRs touching CLI or MCP logic must satisfy this checklist:

- [ ] `rekall --help` contains the `serve`, `brief`, `session`, `mode`, and `agents` subcommands.
- [ ] `rekall brief --json` returns a valid brief with `focus`, `blockers`, `failed_attempts`, `pending_decisions`, `next_actions`, `mode`.
- [ ] `rekall session start` shows the brief and starts a session cleanly.
- [ ] `rekall session end --summary "test"` records the summary and reports bypass warnings.
- [ ] `rekall mode lite` / `coordination` / `governed` sets and persists the mode.
- [ ] `rekall agents` generates a valid `AGENTS.md` file.
- [ ] `rekall serve --store-dir ./project-state` starts without printing to stdout (diagnostic logs go to stderr).
- [ ] MCP handshake passes: `rekall validate --mcp --server-cmd "rekall serve --store-dir ./project-state"`.
- [ ] Documentation links in `README.md` and `docs/` are correct and reachable.
- [ ] No secrets or PII detected by `scripts/scan_secrets`.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
