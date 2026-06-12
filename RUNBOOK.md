# Runbook — daily job-application flow

Practical, copy-paste steps for using the agent day to day. Assumes setup is done
(`./setup.sh`, `ANTHROPIC_API_KEY` in `.env`, profiles filled in). Activate the venv
first in every new terminal:

```bash
cd job-applier-agent && source .venv/bin/activate
```

---

## The funnel (how the pieces fit)

```
  feed / find  ──►  score  ──►  apply
  (discover,        (LLM        (tailor + fill form +
   cheap, many)      review,     human-confirmed submit,
                     one role)   one role)
        │              │              │
        └──────────────┴──────────────┴──►  status / dashboard  (see everything)
```

- **discover cheap, commit expensive.** `feed`/`find` surface many roles with a cheap
  ATS keyword match. You pick the good ones. `score` runs the senior-reviewer LLM (one
  call/role). `apply` tailors + fills + submits (the only step that makes a PDF and
  touches a real form).

---

## 0. One command (the easy path)

```bash
# feed -> score + tailor the top N -> dashboard. STOPS before submit.
python -m src.cli run --days 7 --profile ml_ai --top 5
# then review the dashboard and submit a chosen role:
python -m src.cli apply "<url>"
python -m src.cli usage          # see token + $ cost per run and totals
```

Or run the steps separately (more control):

## 1. Daily discovery (no API key needed for `feed`)

```bash
# Curated, dated, reliable source (SimplifyJobs new-grad feed). Recency-ranked, filtered
# to SDE/ML/Data, junk (hardware/quant/product/technician) dropped automatically.
python -m src.cli feed --days 7 --limit 20
python -m src.cli feed --days 7 --profile ml_ai     # one profile only
python -m src.cli feed --refresh                     # bypass today's cache
```

`find` is the agent-driven crawler (needs the API key) for a specific search across
company boards — use it when you want roles beyond the curated feed:

```bash
python -m src.cli find "machine learning engineer" --days 7 --profile ml_ai
```

Check the curated H1B/OPT sponsor watchlist (companies to watch + their boards):

```bash
python -m src.cli watchlist
```

## 2. See what was found

```bash
python -m src.cli status              # compact table
python -m src.cli status --verbose    # + posted date, profile, source
python -m src.cli dashboard           # regenerate data/dashboard.html, prints path
open data/dashboard.html              # macOS; or open the file in a browser
```

Columns: **ATS /100** = keyword overlap (from find/feed). **Score /10** = senior-reviewer
quality (from score/apply). They're different metrics — don't compare across columns.
"What changed" + "PDF" populate only after `score`/`apply`.

## 3. Score the promising ones (needs API key)

```bash
python -m src.cli score "<real company posting URL>" --profile sde
```

Runs ATS + the strict senior-reviewer (`score_resume`), prints a /10 verdict + gaps,
saves to the dashboard. No applying.

## 4. Apply (needs API key; human-confirmed)

```bash
python -m src.cli apply "<real company posting URL>" --profile sde
```

The agent: reads profile + master → classifies the portal → tailors the resume (summary,
skills, top-2 bullets) → lints → scores → renders the PDF → fills the form → **asks you
to confirm before submitting**. Tailored files land in
`data/applications/<company-role-jobid>/` (md, pdf, changes.json).

> **Portals:** Greenhouse/Lever/Ashby = simple form. Workday = needs you logged into the
> persistent browser profile (`JOB_AGENT_USER_DATA_DIR`); the agent backs off if not.
> CAPTCHA/SSO = the agent stops and hands to you. It never enters credentials.

## 5. QA / debugging (optional)

```bash
JOB_AGENT_QA=1 python -m src.cli apply "<url>"   # enable per-step self-checks
python -m src.cli report                          # view the QA run-log (issues per step)
```

---

## Cost & safety knobs (env vars)

| Var | Default | Purpose |
|---|---|---|
| `JOB_AGENT_MODEL` | `claude-opus-4-8` | model for apply/tailor |
| `JOB_AGENT_FAST_MODEL` | `claude-sonnet-4-6` | model for find/score |
| `JOB_AGENT_SCORER_MODEL` | `claude-opus-4-8` | model for the reviewer |
| `JOB_AGENT_PROVIDER` | `anthropic` | global LLM provider (`anthropic`\|`openai`) |
| `JOB_AGENT_TAILOR_PROVIDER` | (global) | provider for resume tailoring (e.g. `anthropic`) |
| `JOB_AGENT_SCORE_PROVIDER` | (global) | provider for the scorer (e.g. `openai`) |
| `JOB_AGENT_FIND_PROVIDER` | (global) | provider for the finder |
| `JOB_AGENT_OPENAI_MODEL` / `JOB_AGENT_ANTHROPIC_MODEL` | gpt-4o / opus-4-8 | per-provider model |
| `JOB_AGENT_TOKEN_BUDGET` | `0` (off) | per-run token ceiling — stops ONE application from overusing (set e.g. `40000`) |
| `JOB_AGENT_MIN_DELAY` / `MAX_DELAY` | `0.6` / `1.8` | human-like pacing between browser actions |
| `JOB_AGENT_MAX_ACTIONS` | `120` | per-session browser action cap |
| `JOB_AGENT_USER_DATA_DIR` | unset | persistent Chrome profile (stay logged in) |
| `JOB_AGENT_QA` | unset | `1` enables the per-step self-check agent |

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `401 invalid x-api-key` | `.env` still has the placeholder — put a real key in `ANTHROPIC_API_KEY` (or set a provider to `openai` with `OPENAI_API_KEY`). |
| Want Claude resume + OpenAI scoring | set `JOB_AGENT_TAILOR_PROVIDER=anthropic`, `JOB_AGENT_SCORE_PROVIDER=openai` (need both keys). |
| Dashboard shows 0 / stale | hard-refresh the browser tab; `data/applications.json` may have been cleared. |
| All roles `posted_date: unverified` | the board hides the date (e.g. Greenhouse) — prefer the `feed` source which has reliable dates. |
| PDF looks plain, not LaTeX | pdflatex not installed or no `resume/masters/main.tex` — Markdown fallback is in use. Install BasicTeX (`brew install --cask basictex`) + put your resume at `resume/masters/main.tex`. |
| Hardware/technician roles appear | shouldn't — `feeds.py` drops them by category+title. If from `find`, the agent should filter by title. |
| Browser hits a login wall | log into the site once in the `JOB_AGENT_USER_DATA_DIR` profile, then re-run. |

---

## Tests

```bash
python -m pytest tests/ -q     # 24 unit tests, no API/browser needed
```
