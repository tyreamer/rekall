# Rekall Local Verification Script
echo "--- Running Ruff Check ---"
ruff check .
if ($? -ne $true) { echo "Ruff failed"; exit 1 }

echo "--- Running Mypy Type Check ---"
mypy src/rekall
if ($? -ne $true) { echo "Mypy failed"; exit 1 }

echo "--- Running Pytest ---"
pytest
if ($? -ne $true) { echo "Tests failed"; exit 1 }

echo "✅ All checks passed! Ready to push."
