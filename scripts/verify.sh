#!/bin/bash
set -e

echo "--- Running Ruff Check ---"
ruff check .

echo "--- Running Mypy Type Check ---"
mypy src/rekall

echo "--- Running Pytest ---"
pytest

echo "✅ All checks passed! Ready to push."
