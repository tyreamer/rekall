# scan_secrets.ps1 — Lightweight secret / PII scanner for Rekall repo (PowerShell)
# Run from repo root: powershell -ExecutionPolicy Bypass -File scripts\scan_secrets.ps1
param()

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ExitCode = 0

Write-Host "=== Rekall Secret / PII Scan ===" -ForegroundColor Cyan
Write-Host "Scanning: $RepoRoot"
Write-Host ""

# ── 1. Dangerous file patterns ──────────────────────────────────────────────
Write-Host "── Checking for dangerous files ──" -ForegroundColor Yellow
$DangerousPatterns = @(
    "*.env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "id_ed25519*",
    "*.keystore",
    "credentials.json",
    "service_account*.json",
    "*.secret"
)

$FileIssues = $false
foreach ($pattern in $DangerousPatterns) {
    $found = Get-ChildItem -Path $RepoRoot -Recurse -Filter $pattern -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch '[\\/](\.git|venv|__pycache__|node_modules)[\\/]' }
    if ($found) {
        Write-Host "FOUND dangerous file pattern '$pattern':" -ForegroundColor Red
        $found | ForEach-Object { Write-Host "  $($_.FullName)" }
        $FileIssues = $true
        $ExitCode = 1
    }
}

if (-not $FileIssues) {
    Write-Host "No dangerous files found." -ForegroundColor Green
}
Write-Host ""

# ── 2. Token / key patterns in source ───────────────────────────────────────
Write-Host "── Checking for hardcoded tokens / keys ──" -ForegroundColor Yellow
$TokenPatterns = @(
    @{ Name = "AWS Access Key";    Regex = 'AKIA[0-9A-Z]{16}' },
    @{ Name = "GitHub PAT";        Regex = 'ghp_[A-Za-z0-9_]{36}' },
    @{ Name = "OpenAI/Stripe Key"; Regex = 'sk-[A-Za-z0-9]{20,}' },
    @{ Name = "Slack Token";       Regex = 'xox[bprs]-[0-9A-Za-z\-]{10,}' },
    @{ Name = "Google API Key";    Regex = 'AIza[0-9A-Za-z\-_]{35}' },
    @{ Name = "GitLab PAT";        Regex = 'glpat-[0-9A-Za-z\-_]{20}' },
    @{ Name = "npm Token";         Regex = 'npm_[A-Za-z0-9]{36}' },
    @{ Name = "JWT";               Regex = 'eyJ[A-Za-z0-9_\-]{30,}\.' },
    @{ Name = "PEM Private Key";   Regex = 'PRIVATE KEY-----' },
    @{ Name = "Hardcoded Password"; Regex = 'password\s*[:=]\s*["\x27][^\x27"]{8,}' }
)

$Extensions = @("*.py","*.yaml","*.yml","*.json","*.md","*.toml","*.cfg","*.sh","*.ps1","*.txt")
$AllFiles = foreach ($ext in $Extensions) {
    Get-ChildItem -Path $RepoRoot -Recurse -Filter $ext -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch '[\\/](\.git|venv|__pycache__|node_modules)[\\/]' -and $_.Name -notmatch 'scan_secrets' }
}

$TokenIssues = $false
foreach ($tp in $TokenPatterns) {
    foreach ($file in $AllFiles) {
        $matches = Select-String -Path $file.FullName -Pattern $tp.Regex -ErrorAction SilentlyContinue
        if ($matches) {
            Write-Host "[$($tp.Name)] Match in $($file.FullName):" -ForegroundColor Red
            $matches | ForEach-Object { Write-Host "  Line $($_.LineNumber): $($_.Line.Trim())" }
            $TokenIssues = $true
            $ExitCode = 1
        }
    }
}

if (-not $TokenIssues) {
    Write-Host "No hardcoded tokens or keys found." -ForegroundColor Green
}
Write-Host ""

# ── 3. Summary ──────────────────────────────────────────────────────────────
if ($ExitCode -eq 0) {
    Write-Host "`u{2705} Scan passed — repo looks clean." -ForegroundColor Green
} else {
    Write-Host "`u{274C} Scan found issues — review above." -ForegroundColor Red
}

exit $ExitCode
