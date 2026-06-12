# CLAUDE.md — build & extend guide for the Job Applier Agent

This file orients an AI coding assistant (or a new human contributor) working in
this repo. It explains the architecture, how to run it, the conventions to follow,
and the open extension paths. Read it before making changes.

---

## Commands (current)

```
python -m src.cli run   [--days 7] [--profile ml_ai] [--top 5]   # ONE command: feed→score+tailor top N→dashboard (no submit)
python -m src.cli feed  [--days 7] [--profile ml_ai] [--limit 20] [--refresh]  # curated GitHub feed (no API key)
python -m src.cli find  "<query>" [--days 7] [--profile ml_ai]   # agent crawls boards (API key)
python -m src.cli score "<url>"  [--profile ml_ai]               # ATS + reviewer, no apply
python -m src.cli apply "<url>"  [--profile ml_ai]               # full flow + human confirm
python -m src.cli status [--verbose]                             # history table
python -m src.cli dashboard                                      # regenerate dashboard.html
python -m src.cli watchlist                                      # curated H1B/OPT sponsor list
python -m src.cli usage                                          # token + cost per run and totals
python -m src.cli report                                         # QA run-log (when JOB_AGENT_QA=1)
```
`run` is the primary daily command (stops before submit; submit each chosen role with `apply`).
`--profile` ∈ {ml_ai, sde, data_engineer, sde_ml_ai}; omit to auto-pick by JD.
See **RUNBOOK.md** for the day-to-day flow. Run tests with `python -m pytest tests/ -q`.

## Capabilities added beyond the core loop

- **Multiple master resumes** (`resume/masters/*.md` + `index.json`): one per role family.
  `src/tools/profiles.py` resolves/auto-picks by keyword overlap. `resume.read_master`,
  `apply_patch` take a `profile`. Backward compatible with the single `master_resume.md`.
- **Strict scorer** (`src/tools/scorer.py`, tool `score_resume`): a senior hiring-manager /
  Sr-SDE reviewer (NOT an ATS) returns `overall_score` (/10), `verdict`, per-dimension
  scores, `gaps`, `top_fixes` via structured output. Loop is ≤2 passes — *improve the
  rules, not the loop count* (see `resume/formatting_rules.md` §0a/§0b).
- **Match scoring (two tiers):** the LLM scorer also extracts the JD's role-defining
  `must_haves` and returns `matched_must_haves`/`missing_must_haves`/`match_pct` (0-100),
  counting EXACT and SIMILAR/synonym evidence (k8s≈Kubernetes, FAISS≈vector search) — so
  an ML resume scores low against an SDE JD (no generic-overlap inflation). This is the
  trusted match number for scored/applied roles, folded into the existing score_resume
  call (no extra LLM cost). The cheap keyword `ats.py` (fully dynamic, no hardcoded skill
  vocab — derives important terms from the JD) is ONLY the free find-time pre-filter.
- **Job finder** (`src/tools/finder.py` + `_FINDER_SYSTEM` in agent.py): ATS boards +
  GitHub fresh-job repos; freshness verified on the REAL company page (`find_posted_date`);
  daily cache `data/job_cache.json`; ranked by recency AND original-resume match. Never
  LinkedIn Easy Apply.
- **Portal awareness** (`src/tools/portals.py`, tool `classify_portal`): Greenhouse/Lever/
  Ashby → simple form; Workday → needs login (human-auth persistent profile, back off if
  not logged in); CAPTCHA/SSO → human handoff. Detects **prefilled** fields from a prior
  application so we don't overwrite saved data. Credentials are NEVER handled by the agent.
- **Curated feeds** (`src/tools/feeds.py`, `feed` command): pulls SimplifyJobs
  New-Grad-Positions `listings.json` (reliable `date_posted`, real URLs). Two-layer filter
  — category allowlist (Software/AI-ML-Data; drops Hardware/Quant/Product) + title gating
  (drops technician/operator/analyst/PM); AI-ML-Data bucket split into ml_ai vs
  data_engineer by title. The PRIMARY discovery source (board-crawling is the fallback).
- **Watchlist** (`config/watchlist.json`, `watchlist` command): 20 curated H1B/OPT-friendly
  companies + their board URLs for daily checking. `feed` flags roles at these companies.
- **LaTeX rendering** (`src/tools/latex.py`): renders the user's real LaTeX template
  (`resume/masters/main.tex` or `<profile>.tex`) via **pdflatex** (BasicTeX/TeX Live).
  Marker-free, code-side editing: `edit_tex` regex-replaces the `\section{Summary}` body
  and the first two `\resumeItem{...}` (skips the preamble macro def + commented lines),
  LaTeX-escaping the patch values. The agent only emits the patch (no raw LaTeX). Compiles
  via `compile_pdf`; falls back to Markdown→Chromium if pdflatex is absent or compile
  fails. Install is optional in `setup.sh`. (tectonic and Overleaf MCP were evaluated and
  not used.)
- **QA self-check** (`src/tools/qa.py` + `runlog.py`, `report` command): deterministic
  per-step pass/fail + issues log. OFF by default (`JOB_AGENT_QA=1` to enable); temporary
  debugging aid, zero token cost itself.
- **BI dashboard** (`src/tools/dashboard.py`): static `data/dashboard.html` — date,
  company, role, profile, status, **ATS /100** + **Score /10** (separate columns, not
  mixed), verdict, posted date, *what changed*, links to source + tailored PDF (PDF link
  only shown for genuinely tailored rows).
- **Multi-provider LLM routing** (`src/tools/llm.py`): every LLM step routes through a
  shim with `anthropic` + `openai` backends, chosen per task via env vars
  (`JOB_AGENT_PROVIDER` global; `JOB_AGENT_TAILOR_PROVIDER` / `_SCORE_PROVIDER` /
  `_FIND_PROVIDER` per task; `JOB_AGENT_<PROVIDER>_MODEL` for models). So resume tailoring
  can run on Claude while scoring/finding run on OpenAI (or any mix). `run_agent` takes
  `task_kind`; `scorer.score_resume` routes via the shim. Deterministic tools (edit_tex,
  ats, final_check, dedupe, render) use NO LLM. A task only needs the key for its provider.
- **Token + cost tracking** (`src/tools/usage.py`): `run_agent` meters input/output/cache
  tokens per run via `UsageMeter`, estimates USD cost, enforces a per-run ceiling
  (`JOB_AGENT_TOKEN_BUDGET`, raises `BudgetExceeded` to stop ONE application from
  overusing), and appends each run to `data/usage_log.jsonl`. `python -m src.cli usage`
  shows per-run + totals. Each run is labeled (e.g. "apply <url>") so cost is attributable.
- **Anti-flagging & cost** (`src/tools/browser.py`, `run_agent`): human-like pacing delays
  + per-session action cap + real UA + `networkidle` waits; prompt-caching on the system
  block; daily job cache; model tiering (find/score on Sonnet, apply/score_resume on Opus).

Env knobs: `JOB_AGENT_MODEL`, `JOB_AGENT_FAST_MODEL`, `JOB_AGENT_SCORER_MODEL`,
`JOB_AGENT_TOKEN_BUDGET`, `JOB_AGENT_MIN_DELAY`/`MAX_DELAY`, `JOB_AGENT_MAX_ACTIONS`,
`JOB_AGENT_USER_DATA_DIR`.

---

## What this project is

A standalone Python CLI that uses the **Anthropic Claude API + Playwright** to read
job postings, score fit, tailor materials, fill application forms in a real
browser, and submit with human confirmation. It is a from-scratch rebuild of the
`theaayushstha1/job-applier-agent` Claude Code *skill*, reworked as a real program
so the agent loop, tools, and browser driver are all explicit and editable.

It is **provider-targeted to Claude** today but structured so the LLM call is
isolated in one place (`src/agent.py::run_agent`).

---

## Can this run anywhere? (portability)

Yes — it's a plain Python package with two external dependencies. It runs on macOS,
Linux, or Windows (incl. WSL) given:

1. **Python 3.11+**
2. **`pip install -r requirements.txt`** (`anthropic`, `playwright`, `python-dotenv`)
3. **`playwright install chromium`** — downloads a self-contained browser; no system
   Chrome needed. On headless Linux/CI also run `playwright install-deps`.
4. **`ANTHROPIC_API_KEY`** in the environment (or `.env`).

There is **no database, server, or cloud resource** — state is two local JSON files
(`config/profile.json`, `data/applications.json`) plus screenshots on disk. So
"clone, install, set key, run" works on any machine. For unattended/CI runs use
`--headless` and a pre-authenticated `JOB_AGENT_USER_DATA_DIR` profile.

What is **not** portable by default: logged-in sessions to job sites. Either log in
once into a persistent profile dir (`JOB_AGENT_USER_DATA_DIR`) and reuse it, or keep
a human present to handle login walls.

---

## How to build / run

```bash
# one-time
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env                                   # add ANTHROPIC_API_KEY
cp config/profile.example.json config/profile.json     # fill in your details
cp /path/to/resume.pdf resume/MyResume.pdf

# run
python -m src.cli score "<job-url>"          # cheap model, no apply
python -m src.cli apply "<job-url>"          # full flow, confirms before submit
python -m src.cli apply "<job-url>" --headless
python -m src.cli status                     # history
```

There is no build step (pure Python). "Build" = create venv + install deps +
`playwright install`.

---

## Architecture & where things live

```
src/
  cli.py            # argparse entry point; one function per command; picks the model
  agent.py          # THE AGENT LOOP + tool schemas (TOOLS) + dispatch + system prompt
  tools/
    browser.py      # Playwright wrapper; exposes accessibility snapshots w/ ref ids
    ats.py          # deterministic keyword-match scoring (pure Python)
    tracker.py      # read profile, append application records
config/profile.json # your data (gitignored; copy from .example)
data/               # applications.json + screenshots/ (gitignored)
```

**The agent loop (`run_agent`)** is the thing to understand first. Claude is given
`TOOLS`; each turn it either returns text (done) or `tool_use` blocks. We run each
tool via `_dispatch`, append the results as a `tool_result` user message, and loop
until `stop_reason != "tool_use"`. It's the manual Anthropic agentic loop — kept
manual on purpose so it's transparent.

### Adding a new tool (the main extension pattern)
1. Write a Python function (in `tools/` or inline).
2. Add a JSON schema entry to `TOOLS` in `agent.py`.
3. Route it in `_dispatch`.
That's it — Claude will start using it when the system prompt / task calls for it.

---

## Can we use different models for different tasks? (yes)

Already wired:
- `run_agent(task, model=...)` takes the model per call.
- `cli.py` uses `FAST_MODEL` (`claude-sonnet-4-6`) for `score` and `DEFAULT_MODEL`
  (`claude-opus-4-8`) for `apply`. Override with `--model` or env vars
  `JOB_AGENT_MODEL` / `JOB_AGENT_FAST_MODEL`.

Good per-task split to grow into:
| Task | Suggested model | Why |
|---|---|---|
| Quick fit scoring, keyword triage | `claude-haiku-4-5` / `claude-sonnet-4-6` | cheap, high volume |
| Reading/understanding a JD | `claude-sonnet-4-6` | fast, capable enough |
| Resume tailoring + cover letter | `claude-opus-4-8` | quality matters most |
| Driving the form-fill / submit | `claude-opus-4-8` | reliability on irreversible steps |

Model IDs (current as of writing): `claude-opus-4-8` (most capable, 1M context),
`claude-sonnet-4-6` (balanced), `claude-haiku-4-5` (fastest/cheapest). Use the exact
strings — don't append date suffixes. To verify capabilities/pricing at runtime, call
`client.models.retrieve("<id>")` rather than hardcoding assumptions.

Thinking/effort knobs (optional, Opus/Sonnet 4.6+): add
`thinking={"type": "adaptive"}` and `output_config={"effort": "high"}` to the
`messages.create` call in `agent.py` for harder reasoning steps. (`budget_tokens` is
removed on Opus 4.8 — use adaptive thinking.)

---

## Can we create agents for this? (two senses — both yes)

**1. Custom sub-agents within this codebase.** The clean way to grow this is multiple
specialized agent calls instead of one mega-loop. Pattern: give each its own task
prompt, tool subset, and model. Candidates:
- `ScoringAgent` — reads JD + profile, returns a structured fit verdict (Haiku/Sonnet).
- `MaterialsAgent` — tailors resume bullets + writes the cover letter (Opus).
- `FormFillingAgent` — drives the browser to submit (Opus, browser tools only).
- `OutreachAgent` — drafts recruiter emails / LinkedIn notes (Sonnet).
An orchestrator in `cli.py` runs them in sequence and passes structured data between
them. Use structured outputs (`output_config.format` with a JSON schema, or
`client.messages.parse()` with a schema) so each agent returns clean data the next
one can consume.

**2. Anthropic *Managed Agents* (server-hosted).** Anthropic offers a hosted agent
runtime: you create a persisted, versioned **Agent** (model + system prompt + tools),
then start **Sessions** against it; Anthropic runs the loop and a sandbox container.
Relevant here if you want the agent to run server-side, persist across runs, or use
hosted tools — but the browser automation in this repo is **client-side** (Playwright
on your machine), so the natural fit is to expose browser actions as **custom tools**
(the session emits `agent.custom_tool_use`; your local process executes the Playwright
action and returns `user.custom_tool_result`). For a local CLI, the in-process loop in
`agent.py` is simpler; reach for Managed Agents if you later want a hosted, multi-user,
or always-on service. (Note: Managed Agents is a beta API; LinkedIn/browser ToS
caveats still apply.)

---

## Conventions

- **Honesty is enforced in the system prompt** (`_SYSTEM_PROMPT` in agent.py). Never
  weaken the "don't fabricate" instruction.
- **Human-in-the-loop**: the `ask_human` tool must fire before any submit/send. Don't
  remove it for "automation" without the user explicitly accepting the consequences.
- **Tools return strings** to Claude (JSON-encoded for structured data). Errors are
  returned as `"ERROR: ..."` strings, not raised, so Claude can recover.
- **Snapshots over screenshots**: browser state is given to Claude as a text
  accessibility outline with `ref` ids (`e1`, `e2`, ...). Keep new browser actions
  consistent with this (return a fresh snapshot after mutating the page).
- **Secrets**: never store passwords. Use a persistent browser profile the user logs
  into. `.env`, `config/profile.json`, resumes, and `data/` are gitignored.

---

## Known rough edges / good first improvements

- `ats.py` tokenizer keeps trailing punctuation (e.g. `systems.`) and lets a few noise
  words through — tighten the regex / stopword list.
- The accessibility snapshot is a flat list; for complex SPAs (Workday) consider
  scoping snapshots to the visible form region and adding `select`-option handling.
- No dedupe/follow-up logic yet (the original skill had `dedup`, `followup`,
  `status weekly`). `tracker.py` is the place to add them.
- No tests. Add unit tests for `ats.py` and `tracker.py` first (pure functions); mock
  Playwright for `browser.py`.
- Consider structured outputs for the scoring step so `fit_score` is machine-readable
  rather than parsed from prose.

---

## Responsible use (do not delete)

Automating job sites and LinkedIn can violate their Terms of Service and get accounts
restricted. Default to human-in-the-loop, never fabricate application content, rate-
limit yourself, and prefer official APIs / automation-friendly boards. The operator is
responsible for how this is used.
