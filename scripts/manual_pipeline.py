#!/usr/bin/env python3
"""Manual (no-API-key) pipeline driver — Claude acts as the tailoring "brain".

The normal `python -m src.cli run` path routes every tailoring decision through
`run_agent()` (a live LLM call) and hard-exits without an API key. This script drives
only the DETERMINISTIC half of the pipeline and lets a human/Claude supply the tailoring
patches by hand, in stages:

    shortlist  -> pull the feed, dedupe, take a LARGER candidate pool per profile
                  (POOL_PER_PROFILE each), save as status='found', write _shortlist.json
    fetch      -> open each candidate posting (Playwright) and dump the real JD text +
                  posted date to data/_jd_batch.json
    select     -> score every fetched JD against the ORIGINAL master (ats.py) and keep the
                  best-matching KEEP_PER_PROFILE SDE + ML — "recent AND actually a match".
                  Writes data/_selected.json. This is the JD-based filter.
    apply      -> read data/_patches.json (authored after select, keyed by url), edit the
                  LaTeX master (Summary + first 2 bullets + Technical Skills), compile the
                  PDF, lint the patch, ATS-score against the real JD, record status='scored',
                  and regenerate the dashboard.

Nothing is ever submitted. Reuses src/tools/* — reimplements nothing except a
template-specific Technical Skills editor (edit_tex intentionally leaves skills alone).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

# Make `src` importable when run as `python scripts/manual_pipeline.py`.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.tools import ats, artifacts, dashboard, feeds, finder, latex, profiles, tracker
from src.tools.resume import BUDGETS
# Browser (Playwright) is imported lazily inside stage_fetch so shortlist/select/apply
# work even in an env without playwright installed.

DATA = pathlib.Path("data")
SHORTLIST_PATH = DATA / "_shortlist.json"
JD_BATCH_PATH = DATA / "_jd_batch.json"
SELECTED_PATH = DATA / "_selected.json"
PATCHES_PATH = DATA / "_patches.json"

POOL_PER_PROFILE = 40   # how many candidates per profile to FETCH JDs for
KEEP_PER_PROFILE = 20   # how many best-matching to KEEP after the JD filter


# --------------------------------------------------------------------------- #
# Stage 0 — shortlist (build the candidate pool)
# --------------------------------------------------------------------------- #
def _dedupe(roles: list[dict]) -> list[dict]:
    """Drop near-duplicate postings (same company + normalized role title), keeping the
    most-recent. The feed lists the same req multiple times (e.g. Coca-Cola 'Software
    Engineer 1' x5) — tailoring each is wasted effort and not 'jobs that make sense'."""
    seen, out = set(), []
    for r in roles:  # already recency-sorted, so first seen = newest
        norm_role = re.sub(r"[^a-z0-9]+", " ", r["role"].lower()).strip()
        norm_role = re.sub(r"\b\d+\b", "", norm_role).strip()  # 'engineer 1' == 'engineer'
        key = (r["company"].lower(), norm_role)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def stage_shortlist(days: int, refresh: bool) -> None:
    from datetime import date
    today = date.today().isoformat()
    cache_key = f"feed-{days}-auto"
    roles = None if refresh else finder.get_cached(cache_key, None, today)
    if roles is None:
        listings = feeds.fetch_feed()
        roles = feeds.fresh_roles(listings, days)
        finder.put_cache(cache_key, None, today, roles)
        print(f"Fetched feed: {len(roles)} fresh+relevant roles (<= {days}d).")
    else:
        print(f"Using today's cache: {len(roles)} roles (use --refresh to re-fetch).")

    roles = _dedupe(roles)
    avail = {p: sum(r["profile"] == p for r in roles) for p in ("sde", "ml_ai", "data_engineer")}
    print(f"Available (deduped): {avail}")
    sde = [r for r in roles if r["profile"] == "sde"][:POOL_PER_PROFILE]
    ml = [r for r in roles if r["profile"] == "ml_ai"][:POOL_PER_PROFILE]

    # watchlist flag + ATS pre-score against the ORIGINAL master (same as _feed_shortlist).
    wl_path = pathlib.Path("config/watchlist.json")
    watch = set()
    if wl_path.exists():
        watch = {c["name"].lower() for c in json.loads(wl_path.read_text()).get("companies", [])}

    pool = sde + ml
    masters = {p: profiles.read_master_for(p) for p in {r["profile"] for r in pool}}
    for r in pool:
        text = f"{r['role']} {r.get('locations', '')}"
        r["match_pre"] = ats.ats_score(text, masters[r["profile"]])["score"]
        r["watchlist"] = r["company"].lower() in watch
        tracker.save_application(
            company=r["company"], role=r["role"], url=r["url"], status="found",
            match_score=r["match_pre"], source="SimplifyJobs/New-Grad-Positions",
            posted_date=r["posted_date"], profile=r["profile"],
            notes="watchlist H1B-friendly" if r["watchlist"] else "",
        )

    SHORTLIST_PATH.write_text(json.dumps(pool, indent=2))
    print(f"\nCandidate pool: {len(sde)} SDE + {len(ml)} ML = {len(pool)} -> {SHORTLIST_PATH}")
    print("(fetch JDs for the pool, then `select` keeps the best "
          f"{KEEP_PER_PROFILE}+{KEEP_PER_PROFILE} by real JD match.)")


# --------------------------------------------------------------------------- #
# Stage 1 — fetch JD text for the whole pool
# --------------------------------------------------------------------------- #
def stage_fetch(headless: bool, limit: int | None) -> None:
    from datetime import date
    from src.tools.browser import Browser
    if not SHORTLIST_PATH.exists():
        sys.exit("No data/_shortlist.json — run `--stage shortlist` first.")
    pool = json.loads(SHORTLIST_PATH.read_text())
    if limit:
        pool = pool[:limit]
    today = date.today().isoformat()

    out, skipped = [], []
    browser = Browser(headless=headless)
    try:
        for i, r in enumerate(pool, 1):
            print(f"[{i}/{len(pool)}] {r['profile']:<6} {r['company'][:22]:<22} {r['role'][:42]}")
            try:
                browser.open_page(r["url"])
                jd = browser.get_page_text(max_chars=8000)
                # A login wall / bot page yields almost no JD text — flag, don't trust it.
                if not jd or len(jd) < 400:
                    skipped.append({**r, "reason": f"thin page ({len(jd or '')} chars)"})
                    print(f"     ! skipped: thin page ({len(jd or '')} chars)")
                    continue
                out.append({
                    "url": r["url"], "company": r["company"], "role": r["role"],
                    "profile": r["profile"], "posted_date": r.get("posted_date", ""),
                    "locations": r.get("locations", ""), "jd_text": jd,
                })
            except Exception as e:  # noqa: BLE001 — log & continue per repo convention
                skipped.append({**r, "reason": f"load error: {e}"})
                print(f"     ! skipped: {e}")
    finally:
        browser.close()

    JD_BATCH_PATH.write_text(json.dumps(out, indent=2))
    print(f"\nFetched {len(out)} JDs -> {JD_BATCH_PATH}; skipped {len(skipped)}.")
    if skipped:
        (DATA / "_jd_skipped.json").write_text(json.dumps(skipped, indent=2))
        print("  skipped roles logged -> data/_jd_skipped.json")


# --------------------------------------------------------------------------- #
# Stage 2 — select: filter by REAL JD match, keep best per profile
# --------------------------------------------------------------------------- #
def stage_select() -> None:
    """Score every fetched JD against the ORIGINAL master and keep the best-matching
    KEEP_PER_PROFILE per profile. This is the 'jobs that actually make sense' filter —
    recency already bounded the pool; now we rank by genuine fit before tailoring."""
    if not JD_BATCH_PATH.exists():
        sys.exit("No data/_jd_batch.json — run `--stage fetch` first.")
    jds = json.loads(JD_BATCH_PATH.read_text())
    masters = {p: profiles.read_master_for(p) for p in {j["profile"] for j in jds}}
    for j in jds:
        res = ats.ats_score(j["jd_text"], masters[j["profile"]])
        j["match_orig"] = res["score"]
        j["missing_keywords"] = res["missing_keywords"][:25]  # hint for tailoring

    selected = []
    for prof in ("sde", "ml_ai"):
        cands = sorted((j for j in jds if j["profile"] == prof),
                       key=lambda x: x["match_orig"], reverse=True)
        keep = cands[:KEEP_PER_PROFILE]
        selected += keep
        print(f"{prof}: {len(cands)} fetched -> keep top {len(keep)} by JD match "
              f"(range {keep[-1]['match_orig'] if keep else 0}-{keep[0]['match_orig'] if keep else 0}%)")

    SELECTED_PATH.write_text(json.dumps(selected, indent=2))
    print(f"\nSelected {len(selected)} roles -> {SELECTED_PATH}")
    for j in selected:
        print(f"  {j['match_orig']:>3}%  {j['profile']:<6} {j['company'][:24]:<24} {j['role'][:40]}")


# --------------------------------------------------------------------------- #
# Stage 3 — apply patches (edit .tex incl. skills, compile, lint, ATS, record)
# --------------------------------------------------------------------------- #
def _edit_skills(tex: str, skills: str) -> str:
    r"""Replace the Technical Skills block body. edit_tex deliberately leaves skills
    intact (it's a structured block); both of this repo's masters use the identical
    shape under \section{Technical Skills}:

        \begin{itemize}[leftmargin=0in, label={}]
          \small{\item{
            \textbf{Languages}{: ...} \\
            ...
          }}
        \end{itemize}

    `skills` is plain text with newline-separated "Category: a, b, c" lines; we render
    each as `\textbf{Category}{: a, b, c} \\` and swap the inner block. LaTeX-escapes
    values (but keeps our own \textbf/backslashes). Returns tex unchanged if not found."""
    if not skills:
        return tex
    lines = []
    for ln in skills.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        if ":" in ln:
            cat, rest = ln.split(":", 1)
            lines.append(rf"    \textbf{{{latex.latex_escape(cat.strip())}}}"
                         rf"{{: {latex.latex_escape(rest.strip())}}} \\")
        else:
            lines.append(rf"    {latex.latex_escape(ln)} \\")
    block = "  \\small{\\item{\n" + "\n".join(lines) + "\n  }}"

    # Match from the \section{Technical Skills} up to its \end{itemize}, replace the
    # inner \small{\item{...}} body while keeping the \begin/\end itemize wrapper.
    pat = re.compile(
        r"(\\section\{Technical Skills\}.*?\\begin\{itemize\}[^\n]*\n)(.*?)(\n\s*\\end\{itemize\})",
        re.DOTALL,
    )
    if not pat.search(tex):
        return tex
    return pat.sub(lambda m: m.group(1) + block + m.group(3), tex, count=1)


def _strip_tex(tex: str) -> str:
    """Crude LaTeX->text for ATS keyword scoring: drop commands/braces, keep words."""
    t = re.sub(r"%.*", "", tex)                       # comments
    t = re.sub(r"\\[a-zA-Z]+\*?", " ", t)             # commands
    t = re.sub(r"[{}\\$&#~^_]", " ", t)               # control chars
    return re.sub(r"\s+", " ", t)


# Only true function words are dropped when checking must-have coverage. We must NOT
# reuse ats._STOPWORDS here: that list is anti-signal for JD keyword *extraction* and
# includes domain words like "scale"/"requirements"/"impact" that are perfectly valid
# things a resume can cover.
_COVER_STOP = {"and", "or", "the", "a", "an", "of", "to", "in", "on", "for", "with", "as"}


def _covers(must_have: str, resume_text: str) -> bool:
    """True if the tailored resume genuinely covers this role-defining must-have.

    Mirrors scorer.py's 'exact OR synonym' counting, deterministically: a must-have is
    covered if ALL its significant tokens (minus function words) appear in the resume.
    Synonyms are handled by writing them into the must-have string itself, e.g.
    'kubernetes|k8s' or 'vector search faiss' — any one alternative (split on '|') that
    is fully present counts as covered."""
    text = resume_text.lower()
    for alt in must_have.lower().split("|"):
        toks = [t for t in re.findall(r"[a-z0-9+#.]+", alt) if t not in _COVER_STOP]
        if toks and all(t in text for t in toks):
            return True
    return False


def _match_must_haves(must_haves: list[str], resume_text: str) -> dict:
    """Deterministic role-fit: % of the patch's role-defining must_haves the tailored
    resume covers. This is the trusted match number (scorer.py-style), NOT the full-page
    ats.py keyword soup (which is polluted by nav/benefits/legal boilerplate)."""
    matched = [m for m in must_haves if _covers(m, resume_text)]
    missing = [m for m in must_haves if m not in matched]
    pct = round(100 * len(matched) / len(must_haves)) if must_haves else 0
    return {"match_pct": pct, "matched": matched, "missing": missing}


def _word_count(s: str) -> int:
    return len(s.split())


def _lint_patch(patch: dict) -> list[str]:
    """Validate a patch against the same budgets resume.lint enforces (it lints Markdown;
    we lint the raw patch fields so it works for the .tex flow)."""
    issues = []
    summ = (patch.get("summary") or "").strip()
    if summ:
        sw = _word_count(summ)
        if sw < BUDGETS["summary_min_words"]:
            issues.append(f"summary {sw}w < {BUDGETS['summary_min_words']}")
        if sw > BUDGETS["summary_max_words"]:
            issues.append(f"summary {sw}w > {BUDGETS['summary_max_words']}")
    skills = (patch.get("technical_skills") or "").strip()
    if skills and _word_count(skills) > BUDGETS["technical_skills_max_words"] + 25:
        # skills here is multi-line "Cat: a,b,c" text; allow more than the MD budget but
        # still guard against dumping everything.
        issues.append(f"skills {_word_count(skills)}w is very long")
    verbs = []
    for b in (patch.get("top_bullets") or []):
        wc = _word_count(b)
        if wc < BUDGETS["bullet_min_words"] or wc > BUDGETS["bullet_max_words"]:
            issues.append(f"bullet {wc}w (want {BUDGETS['bullet_min_words']}-"
                          f"{BUDGETS['bullet_max_words']}): {b[:45]}...")
        if re.search(r"\b(responsible for|helped|various|successfully|in order to)\b", b, re.I):
            issues.append(f"filler in bullet: {b[:45]}...")
        if b.split():
            verbs.append(b.split()[0].lower())
    if len(verbs) != len(set(verbs)):
        issues.append(f"repeated leading verb across bullets: {verbs}")
    return issues


def stage_apply(strict: bool) -> None:
    src_path = SELECTED_PATH if SELECTED_PATH.exists() else JD_BATCH_PATH
    if not src_path.exists():
        sys.exit("No data/_selected.json or _jd_batch.json — run fetch/select first.")
    if not PATCHES_PATH.exists():
        sys.exit("No data/_patches.json — author the patches (keyed by url) first.")
    jds = {j["url"]: j for j in json.loads(src_path.read_text())}
    patches = json.loads(PATCHES_PATH.read_text())

    rows, failures = [], []
    for url, patch in patches.items():
        j = jds.get(url)
        if not j:
            print(f"! no JD for {url} — skipping"); continue
        company, role, profile = j["company"], j["role"], j["profile"]
        print(f"\n=== {company} — {role[:50]} [{profile}] ===")

        lint_issues = _lint_patch(patch)
        if lint_issues:
            print("  LINT ISSUES:", *lint_issues, sep="\n    ")
            if strict:
                failures.append({"url": url, "lint": lint_issues}); continue

        tex_path = latex.tex_master_path(profile)
        if not tex_path:
            print(f"  ! no .tex master for profile {profile}"); failures.append({"url": url}); continue
        edited = latex.edit_tex(tex_path.read_text(), patch)        # summary + 2 bullets
        edited = _edit_skills(edited, patch.get("technical_skills", ""))  # + skills

        out_pdf = artifacts.folder(company, role, url) / "zsAIEngineer.pdf"
        ok, msg = latex.compile_pdf(edited, out_pdf)
        if not ok:
            print(f"  ! compile failed: {msg[:200]}"); failures.append({"url": url, "compile": msg}); continue
        size = out_pdf.stat().st_size

        # Trusted match = coverage of the patch's role-defining must_haves (scorer.py-style),
        # measured deterministically on the tailored resume. Falls back to whole-page ats.py
        # only if the patch carries no must_haves.
        tailored_text = _strip_tex(edited)
        must = patch.get("must_haves") or []
        if must:
            mh_after = _match_must_haves(must, tailored_text)
            mh_before = _match_must_haves(must, _strip_tex(tex_path.read_text()))
            ats_now, ats_before = mh_after["match_pct"], mh_before["match_pct"]
            if mh_after["missing"]:
                print(f"  still-missing must-haves: {mh_after['missing']}")
        else:
            ats_now = ats.ats_score(j["jd_text"], tailored_text)["score"]
            ats_before = ats.ats_score(j["jd_text"], _strip_tex(tex_path.read_text()))["score"]

        artifacts.save_artifacts(company, role, tailored_md=edited, patch=patch, url=url)
        tracker.save_application(
            company=company, role=role, url=url, status="scored",
            match_score=ats_now, resume_diff=patch, tailored_pdf=str(out_pdf),
            scorer_verdict="manual", scorer_gaps=(mh_after["missing"] if must else None),
            profile=profile, posted_date=j.get("posted_date", ""),
            source="SimplifyJobs/New-Grad-Positions",
        )
        flag = "" if ats_now >= 90 else "  <-- below 95% target"
        print(f"  OK  PDF {size}B  match {ats_before}->{ats_now}%{flag}")
        rows.append({"company": company, "role": role, "profile": profile,
                     "ats_before": ats_before, "ats_after": ats_now, "pdf": str(out_pdf)})

    dashboard.render()
    print(f"\n=== DONE: {len(rows)} tailored, {len(failures)} failed ===")
    for r in sorted(rows, key=lambda x: x["ats_after"], reverse=True):
        flag = "" if r["ats_after"] >= 90 else "  (below target)"
        print(f"  {r['profile']:<6} {r['ats_before']:>3}->{r['ats_after']:>3}  "
              f"{r['company'][:22]:<22} {r['role'][:38]}{flag}")
    if failures:
        print(f"\nFailures ({len(failures)}):")
        for f in failures:
            print(f"  {f}")
    print("\nDashboard regenerated -> data/dashboard.html")


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="Manual no-API pipeline driver.")
    ap.add_argument("--stage", required=True,
                    choices=["shortlist", "fetch", "select", "apply"])
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--refresh", action="store_true", help="re-fetch the feed (shortlist).")
    ap.add_argument("--headless", action="store_true", help="headless browser (fetch).")
    ap.add_argument("--limit", type=int, default=None, help="cap roles processed (fetch).")
    ap.add_argument("--strict", action="store_true", help="reject patches that fail lint (apply).")
    args = ap.parse_args()

    if args.stage == "shortlist":
        stage_shortlist(args.days, args.refresh)
    elif args.stage == "fetch":
        stage_fetch(args.headless, args.limit)
    elif args.stage == "select":
        stage_select()
    elif args.stage == "apply":
        stage_apply(args.strict)


if __name__ == "__main__":
    main()
