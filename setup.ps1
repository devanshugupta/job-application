# Bootstrap the Job Applier Agent on Windows (PowerShell) from nothing.
# Run from the project folder:   ./setup.ps1
# If blocked: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "==> 1/6  Checking Python (need 3.11+)"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Error "python not found. Install Python 3.11+ from https://www.python.org/downloads/ (check 'Add to PATH')."
}

Write-Host "==> 2/6  Creating virtual environment (.venv)"
if (-not (Test-Path .venv)) { python -m venv .venv }
& .\.venv\Scripts\Activate.ps1
python -m pip install --quiet --upgrade pip

Write-Host "==> 3/6  Installing Python dependencies"
pip install --quiet -r requirements.txt

Write-Host "==> 4/6  Installing Chromium for Playwright"
python -m playwright install chromium

Write-Host "==> 5/6  Seeding config files (won't overwrite existing)"
if (-not (Test-Path .env))                  { Copy-Item .env.example .env;                                   Write-Host "    created .env (add ANTHROPIC_API_KEY)" }
if (-not (Test-Path config/profile.json))   { Copy-Item config/profile.example.json config/profile.json;     Write-Host "    created config/profile.json" }
if (-not (Test-Path resume/master_resume.md)) { Copy-Item resume/master_resume.example.md resume/master_resume.md; Write-Host "    created resume/master_resume.md" }
foreach ($p in @("ml_ai","sde","data_engineer","sde_ml_ai")) {
  if (-not (Test-Path "resume/masters/$p.md")) { Copy-Item "resume/masters/$p.example.md" "resume/masters/$p.md"; Write-Host "    created resume/masters/$p.md" }
}
New-Item -ItemType Directory -Force -Path data | Out-Null

Write-Host "==> 6/6  Sanity check"
python -c "import anthropic, playwright; print('    anthropic + playwright import OK')"

Write-Host ""
Write-Host "Setup complete. Next:"
Write-Host "  1) Put your API key in .env"
Write-Host "  2) Edit config/profile.json and resume/master_resume.md"
Write-Host "  3) .\.venv\Scripts\Activate.ps1"
Write-Host "  4) python -m src.cli score `"<job-url>`""
