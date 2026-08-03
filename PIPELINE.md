# Full pipeline runbook

Paste **THE PROMPT** below to run a complete pass. The sections after it are the
hard-won watch-outs — the places the automation gets stuck or quietly does the wrong
thing, and how to catch each. Read §3 before trusting a parallel run.

---

## 1. THE PROMPT (paste this)

```text
Run a full job-applier pipeline pass (repo: ~/PycharmProjects/job-applier-agent,
use .venv/bin/python, ManualBrain mode).

1. DISCOVER — fresh roles from the last 24h across ALL sources
   (`discover --hours 24 --target 80 --refresh`). Run ONE sweep at a time
   (two concurrent sweeps rate-limit LinkedIn and one comes back empty).

2. DEDUPE / CLEAN — drop: reposts (same company+role already tracked), removed rows,
   login-wall or thin/boilerplate JDs, and hard gates (JD says no visa sponsorship /
   US-citizens-only / clearance required → skip; I need sponsorship). Verify the gate
   yourself — the regex misses some phrasings.

3. REVIEW & RATE — backfill Master-ATS first (`rescore.backfill_master_ats`) so the
   dashboard is complete, then judge TRUE fit (JD vs my profile) for every fresh
   `found` row with a real JD — not just the keyword score.

4. SELECT — the good-fit, high-interview-probability roles; tailor at least 25.
   Multiple DIFFERENT roles at the same company are fine (more shots) — only skip
   duplicate same-role postings. DO NOT tailor Google or OpenAI.

5. TAILOR — parallelize with ~6 background agents, batches of ~5. Each runs the
   `tailor "<url>"` ManualBrain loop (PATCH→REVIEW→SCORE), answering packets HONESTLY:
   source only from my master resume + achievements.md; never invent skills/metrics/
   tools/scope; 2–5 bullets of 14–30 words (first two prove the JD's top priorities);
   no forbidden leading verbs (Built/Designed/Engineered/Maintained/Raised/Automated/
   Created/Architected), vary verbs, no em-dashes, skills line ≤35 words with the fixed
   core, 1 page. Score HONESTLY: 9 exceptional / 7–8 strong / 6 borderline / 4–5 weak.
   "9+" is a filter, not a target — if it can't clear the bar, score it down and say why.

6. VERIFY (mandatory) — after tailoring, pdftotext every NEW pdf: each must contain its
   own top_bullets + last skills group and be 1 page. Re-render any bad one SEQUENTIALLY
   from the tracker's resume_diff. (Parallel agents race and cross-contaminate PDFs.)

7. REPORT — rebuild the dashboard and give me a scoreboard (company — role — score/match),
   grouped by score, with apply-first picks called out.

Never fabricate; confirm before anything irreversible; commit messages short, no
"Co-Authored-By" line.
```

---

## 2. Standing rules

- **Honesty is inviolable.** Every bullet must survive a 5-minute interview deep-dive.
  Never invent skills, metrics, tools, employers, or scope. "9+" is a **filter, not a
  target** — score mismatches down (4–5) and name the gap.
- **Do-not-tailor: Google, OpenAI.** (Existing resumes stay; just don't make new ones.)
- **Per company:** tailor multiple *different* roles (more interview shots). Only block
  the *same role* twice. Do NOT cap per company.
- **Sources for bullets:** `resume/masters/ml_sde.tex` (master) + `resume/achievements.md`
  only. `achievements.md` is **positive-only** (admin rule) — never add negative notes.
- **Commit style:** short subject, no body unless needed, **no "Co-Authored-By" trailer.**
- **Never** submit forms, enter credentials, solve CAPTCHAs, or accept agreements.

---

## 3. Known failure modes (what I had to fix by hand)

**A. Parallel agents cross-contaminate PDFs — ALWAYS verify.**
Concurrent `tailor` runs share one intermediate resume file, so agents overwrite each
other's bullets mid-render. Last run this corrupted 10/30 PDFs (correct data in the
tracker, wrong bullets in the PDF, still 1 page so it looks fine). **Mandatory fix:**
after any parallel batch, pdftotext each new PDF and confirm its own `top_bullets`
(first 5 words of each) and last skills group are present; re-render offenders
**sequentially** from `resume_diff`. Proper code fix pending: give each `tailor_job`
run a per-job temp filename instead of the shared path.

**B. Subagents stall (`no progress 600s`) on long manual-brain loops.**
Last big run 3–4 of 6 agents stalled. Mitigate: batches of ≤5, tell agents to keep
packet reasoning concise, and **finish stragglers yourself** — a stalled agent usually
pre-wrote some `.response.json` files, so just re-run `tailor "<url>"` to consume them
and answer whatever packet is still pending.

**C. Login-wall / boilerplate JDs masquerade as real.**
A logged-out LinkedIn page (~12–290 KB of "Sign in / Join now" chrome) and careers-page
nav ("How we hire", "2027 start") both clear the length check but contain no JD. The
`_looks_like_login_wall` + real-marker filters catch most; still eyeball that a JD has
actual responsibilities/qualifications before tailoring. Never build a resume from
boilerplate.

**D. Sponsorship / clearance gate misses phrasings.**
Analytica ("US citizenship + clearance") and Cox ("no visa sponsorship") were NOT
auto-skipped and had to be marked by hand. Always scan the JD yourself for
citizenship/clearance/sponsorship language and skip if present (candidate needs
sponsorship).

**E. Reposts.** LinkedIn resets a repost's date, and the JSON-LD signal is now behind a
login wall, so the only reliable guest signal is **same (company, role) already tracked**
(auto-dropped in discovery). A *never-before-seen* repost is undetectable as a guest —
only the logged-in feed's "Reposted X ago" label reveals it. Don't claim guest repost
detection works beyond same-company+role.

**F. Concurrency + CLI foot-guns.**
- Two `discover` runs at once → LinkedIn rate-limits → one returns 0. Run one.
- `--source all` used to resolve to zero sources (fixed); prefer no `--source` flag.
- `--top 0` used to silently discard finds (target now floored at 50).

**G. Lint rejections (expect 1 corrective pass each).**
The linter checks leading verbs across the **whole rendered resume** (top bullets AND
project bullets), so a "Built" in a project collides with a "Built" top bullet. Also:
skills line >35 words, bullets <14 or >30 words. Fix exactly what it names and rewrite
the same `.response.json`.

**H. Editing prompts.py mid-run invalidates pending packets.**
Changing prompt text changes the ManualBrain packet hash, so a pending PATCH gets
re-issued under a new filename. Don't edit prompts while packets are open; if you must,
copy the old `.response.json` to the new packet name.

**I. `cmd_tailor` substring match can hit the wrong row.**
"OpenAI Software Engineer" matched the Cooperative-AI row, not the privacy one. When a
company has several similar roles, pass a **URL fragment** to `tailor` for precision.

**J. Small API/behavior gotchas.**
- `jd_fetch.fetch_jd()` returns a dict `{text, source, looks_complete}`, not a string.
- Applied/removed rows must never be re-tailored (gates exist in `tailor_job`; don't
  bypass them by editing PDFs directly).
- Fresh rows often lack Master-ATS until `backfill_master_ats` runs — blank ≠ bug.
- `experience_section_index`: 0 = Amazon (ML/retrieval/ranking/RAG/agents/eval),
  1 = TCS (data-eng/Spark/ETL). Use **index 1 for pure data-engineering JDs** or the
  bullets misattribute.

**K. AdPrompter project.** It's a group course-project fork; frame as "built the backend
and rating components," and don't put the GitHub link on a resume (the commit history
doesn't show individual authorship).

---

## 4. Manual verification checklist (before saying "done")

- [ ] Every new PDF: own bullets + last skills group present, exactly 1 page (§3A).
- [ ] No sponsorship/clearance/citizenship-gated role left in the apply pile (§3D).
- [ ] No Google/OpenAI newly tailored (§2).
- [ ] Scores are honest — mismatches scored 4–6 with the gap named, not inflated.
- [ ] Dashboard rebuilt; scoreboard reported with apply-first picks.
