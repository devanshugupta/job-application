# Runbook  daily job-application flow

Copy-paste steps for using the system day to day. Assumes setup is done
(`./setup.sh`, profiles filled in, real `.tex` resume in `resume/masters/`).
Activate the venv first in every new terminal:

```bash
cd job-applier-agent && source .venv/bin/activate
```

---

## The funnel

```
 discover ───────► pipeline ───────────► review dashboard ───► apply / fill
 (top 50-100        (tailor + score        (AQS grades:          (one role each;
  fresh roles,       top N; 2 LLM calls     A = apply now)        human-confirmed
  past 24h,          per role  or none                           submit)
  no key)            with --brain manual)
```

## Daily (with an API key)  one command

```bash
python -m src.cli pipeline --hours 24 --top 10
open data/dashboard.html
```

That discovers the freshest roles (GitHub feeds + 25+ company ATS APIs), picks the
top 10, tailors your closest-matching master resume for each (Summary + Technical
Skills + top-2 bullets only), scores each with the senior-reviewer rubric, and
rebuilds the dashboard. Nothing is submitted.

Want more volume or a wider window?

```bash
python -m src.cli discover --hours 24 --target 100     # just the shortlist, no LLM
python -m src.cli pipeline --top 25                    # tailor more of them
python -m src.cli pipeline --from-tracker --top 15     # tailor roles discover already found
```

## Daily (NO API key)  manual brain

```bash
python -m src.cli pipeline --hours 24 --top 10 --brain manual
# -> writes data/brain/<id>.prompt.md packets and pauses those jobs
python -m src.cli brain                                # list what's awaiting answers
# Answer each packet with ANY LLM (paste it into a chat, or let Claude Code do it):
#   write ONLY the JSON object to data/brain/<id>.response.json
python -m src.cli pipeline --hours 24 --top 10 --brain manual   # re-run -> completes
```

If Claude Code is driving: "read each pending packet in data/brain/, produce the JSON
per its schema, write the .response.json files, then re-run the pipeline command."

## Submitting

```bash
python -m src.cli apply "<url>"      # any portal: agent fills, asks YOU before submit
python -m src.cli fill  "<url>"      # Greenhouse only: deterministic fill, no key;
                                     # you review every field and click submit yourself
```

Workday/SSO portals: log in once in the persistent profile
(`JOB_AGENT_USER_DATA_DIR=~/.job-applier-profile`), then `apply`.

## Reading the dashboard

- **AQS (0-100 + grade)** is the headline: 0.40·reviewer + 0.35·must-have% +
  0.10·keywords + 0.15·recency. Hover a badge for the component breakdown.
  **A (80+) = apply now. B (65+) = strong.** Below 50, skip or fix gaps.
- Reviewer /10 = senior-hiring-manager read of the tailored resume.
- Must-have % = share of THIS JD's role-defining requirements your resume shows.
- "What changed" expands to the exact summary/skills/bullets that were swapped in.
- Tailored artifacts: `data/applications/<company-role-id>/` (tex, pdf, changes.json).

## Watching costs

```bash
python -m src.cli usage          # tokens + $ per run, totals
```

The pipeline is ~2 structured calls/job (vs ~40-turn agent loops before).
`JOB_AGENT_TOKEN_BUDGET=200000` caps any single agent run.

## Maintenance

- `config/watchlist.json`  add companies; with `"ats"+"token"` they're swept by API.
- `config/question_bank.json`  teach the form-filler new questions (regex -> answer).
- `resume/masters/*.tex`  your real resumes; the pipeline reads/edits these directly.
- `python -m pytest tests/ -q` after changes.
