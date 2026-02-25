# Contributing to Rekall

Thanks for your interest! Here's how to get started.

## Development Setup

```bash
# Clone and create a virtual environment
git clone https://github.com/anthropic-labs/rekall.git
cd rekall
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -e ".[dev]"    # or: pip install -e . && pip install pytest
```

## Running Tests

```bash
# Full suite
pytest tests/ -v

# Smoke test
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

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
