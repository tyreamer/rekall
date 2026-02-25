#!/usr/bin/env bash
# scan_secrets.sh — Lightweight secret / PII scanner for Rekall repo
# Run from repo root: bash scripts/scan_secrets.sh
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXIT_CODE=0

echo "=== Rekall Secret / PII Scan ==="
echo "Scanning: $REPO_ROOT"
echo ""

# ── 1. Dangerous file patterns ──────────────────────────────────────────────
echo "── Checking for dangerous files ──"
DANGEROUS_PATTERNS=(
  "*.env"
  ".env.*"
  "*.pem"
  "*.key"
  "*.p12"
  "*.pfx"
  "id_rsa*"
  "id_ed25519*"
  "*.keystore"
  "credentials.json"
  "service_account*.json"
  "*.secret"
)

for pattern in "${DANGEROUS_PATTERNS[@]}"; do
  found=$(find "$REPO_ROOT" -name "$pattern" \
    -not -path "*/.git/*" \
    -not -path "*/venv/*" \
    -not -path "*/__pycache__/*" \
    -not -path "*/node_modules/*" 2>/dev/null || true)
  if [ -n "$found" ]; then
    echo -e "${RED}FOUND dangerous file pattern '$pattern':${NC}"
    echo "$found"
    EXIT_CODE=1
  fi
done

if [ $EXIT_CODE -eq 0 ]; then
  echo -e "${GREEN}No dangerous files found.${NC}"
fi
echo ""

# ── 2. Token / key patterns in source ───────────────────────────────────────
echo "── Checking for hardcoded tokens / keys ──"
TOKEN_PATTERNS=(
  'AKIA[0-9A-Z]{16}'                     # AWS access key
  'ghp_[A-Za-z0-9_]{36}'                 # GitHub PAT
  'sk-[A-Za-z0-9]{20,}'                  # OpenAI / Stripe secret key
  'xox[bprs]-[0-9A-Za-z\-]{10,}'         # Slack token
  'AIza[0-9A-Za-z\-_]{35}'               # Google API key
  'glpat-[0-9A-Za-z\-_]{20}'             # GitLab PAT
  'npm_[A-Za-z0-9]{36}'                  # npm token
  'eyJ[A-Za-z0-9_\-]{30,}\.'             # JWT (long base64)
  'PRIVATE KEY-----'                      # PEM private key block
  'password\s*[:=]\s*["\x27][^"\x27]{8,}' # password assignment
)

SCAN_EXIT=0
for pat in "${TOKEN_PATTERNS[@]}"; do
  hits=$(grep -rn --include="*.py" --include="*.yaml" --include="*.yml" \
    --include="*.json" --include="*.md" --include="*.toml" --include="*.cfg" \
    --include="*.sh" --include="*.ps1" --include="*.txt" \
    -E "$pat" "$REPO_ROOT" \
    --exclude-dir=.git --exclude-dir=venv --exclude-dir=__pycache__ \
    --exclude-dir=node_modules --exclude-dir=tests \
    --exclude="scan_secrets*" 2>/dev/null || true)
  if [ -n "$hits" ]; then
    echo -e "${RED}Potential secret match for pattern '$pat':${NC}"
    echo "$hits"
    SCAN_EXIT=1
  fi
done

if [ $SCAN_EXIT -eq 0 ]; then
  echo -e "${GREEN}No hardcoded tokens or keys found.${NC}"
else
  EXIT_CODE=1
fi
echo ""

# ── 3. Summary ──────────────────────────────────────────────────────────────
if [ $EXIT_CODE -eq 0 ]; then
  echo -e "${GREEN}✅ Scan passed — repo looks clean.${NC}"
else
  echo -e "${RED}❌ Scan found issues — review above.${NC}"
fi

exit $EXIT_CODE
