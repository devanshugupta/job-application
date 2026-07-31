#!/usr/bin/env bash
# Bootstrap the Job Applier Agent on a machine that has NOTHING set up yet.
# Safe to re-run (idempotent). Works on macOS and Linux (incl. WSL).
#
#   ./setup.sh
#
# After it finishes:
#   source .venv/bin/activate
#   python -m src.cli score "<job-url>"
set -euo pipefail
cd "$(dirname "$0")"

echo "==> 1/6  Checking Python (need 3.11+)"
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found. Install Python 3.11+ first:"
  echo "  macOS:  brew install python@3.12"
  echo "  Ubuntu: sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
  exit 1
fi
PYV=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
echo "    found Python $PYV"

echo "==> 2/6  Creating virtual environment (.venv)"
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip

echo "==> 3/6  Installing Python dependencies (requirements.txt)"
pip install --quiet -r requirements.txt

echo "==> 4/6  Installing the Chromium browser for Playwright"
python -m playwright install chromium
# On headless Linux you may also need OS libs (no-op on macOS):
if [ "$(uname)" = "Linux" ]; then
  python -m playwright install-deps chromium || \
    echo "    (could not auto-install system deps; you may need: sudo python -m playwright install-deps)"
fi

echo "==> 5/6  Seeding config files (won't overwrite existing)"
[ -f .env ]                  || { cp .env.example .env;                                   echo "    created .env (add your ANTHROPIC_API_KEY)"; }
[ -f config/profile.json ]   || { cp config/profile.example.json config/profile.json;     echo "    created config/profile.json (fill in your details)"; }
[ -f resume/master_resume.md ] || { cp resume/master_resume.example.md resume/master_resume.md; echo "    created resume/master_resume.md (legacy single master)"; }
# Seed the role-targeted master resumes (ml_ai / sde / data_engineer / sde_ml_ai)
for p in ml_ai sde data_engineer sde_ml_ai; do
  [ -f "resume/masters/$p.md" ] || { cp "resume/masters/$p.example.md" "resume/masters/$p.md"; echo "    created resume/masters/$p.md"; }
done
mkdir -p data

echo "==> 5b/6  (Optional) pdfLaTeX for polished resume PDFs from your .tex master"
PDFLATEX="$(command -v pdflatex || echo /Library/TeX/texbin/pdflatex)"
if [ -x "$PDFLATEX" ]; then
  echo "    pdflatex found  LaTeX rendering enabled."
elif command -v brew >/dev/null 2>&1; then
  echo "    Installing BasicTeX via brew (optional; Markdown rendering works without it)..."
  brew install --cask basictex >/dev/null 2>&1 && {
    echo "    BasicTeX installed; installing packages used by the resume template..."
    sudo /Library/TeX/texbin/tlmgr update --self >/dev/null 2>&1 || true
    sudo /Library/TeX/texbin/tlmgr install fontawesome5 marvosym titlesec enumitem \
      tabularx multicol fancyhdr latexsym preprint psnfss helvetic >/dev/null 2>&1 \
      && echo "    LaTeX packages installed." \
      || echo "    (some tlmgr packages may need a manual retry; Markdown fallback remains.)"
  } || echo "    (BasicTeX install skipped/failed  Markdown PDF fallback remains.)"
else
  echo "    No pdflatex and no brew. LaTeX is OPTIONAL  Markdown PDF is the fallback."
  echo "    To enable: install BasicTeX/TeX Live and put your resume at resume/masters/main.tex."
fi

echo "==> 6/6  Sanity check"
python - <<'PY'
import anthropic, playwright  # noqa: F401
print("    anthropic + playwright import OK")
PY

echo ""
echo "✅ Setup complete. Next steps:"
echo "   1) Put your API key in .env            (ANTHROPIC_API_KEY=sk-ant-...)"
echo "   2) Edit config/profile.json and resume/master_resume.md"
echo "   3) source .venv/bin/activate"
echo "   4) python -m src.cli score \"<job-url>\""
echo ""
echo "   (Re-run 'source .venv/bin/activate' in every new terminal.)"
