"""Command-line entry point.

Daily flow (deterministic pipeline; LLM used only through the Brain seam):
    discover    pull top-N fresh roles (past 24h) from feeds + ATS board APIs. No key.
    pipeline    discover -> tailor+score the top N -> dashboard. --brain manual = no key.
    apply       agentic browser flow for ONE job (confirms before submit). Needs a key.
    fill        deterministic Greenhouse form fill. No key.
    dashboard / status / usage / report / brain  inspection. No key.

Legacy commands kept: find (agent crawl), score (agent score), feed, run (alias of
pipeline), watchlist.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone

from dotenv import load_dotenv

from . import config
from .agent import DEFAULT_MODEL, _FINDER_SYSTEM, run_agent
from .brain import BrainPending, get_brain, pending_packets
from .tools import dashboard as dash
from .sources import scoutbetter
from .tools import (artifacts, ashby, ats, dashboard_server, discover, feeds, finder,
                    lever, profiles, runlog, scoring, tailor, tracker, usage)
from .tools.browser import Browser
from .tools import greenhouse as gh

FAST_MODEL = config.fast_model()


def _require_key() -> None:
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")):
        sys.exit("Set ANTHROPIC_API_KEY and/or OPENAI_API_KEY (in .env)  or use "
                 "`pipeline --brain manual`, which needs no key.")


def _browser(headless: bool) -> Browser:
    return Browser(headless=headless, user_data_dir=config.user_data_dir())


def _today() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------- new pipeline

def cmd_discover(hours: int, target: int, profile: str | None,
                 sources: list[str] | None = None, coverage: bool = False,
                 refresh: bool = False) -> None:
    """Deterministic multi-source discovery. No API key, no browser."""
    print(f"=== DISCOVER: past {hours}h, top {target} "
          f"[sources: {','.join(sources) if sources else 'all available'}] ===")
    if coverage:
        cov = discover.coverage(hours, profile=profile, sources=sources)
        rows = sorted(cov.items(), key=lambda kv: kv[1]["pulled"], reverse=True)
        print(f"\n=== Per-company coverage (past {hours}h)  pulled vs kept after filter ===")
        print(f"{'COMPANY':<26}{'PULLED':>8}{'KEPT':>7}")
        for co, c in rows[:40]:
            print(f"{co[:26]:<26}{c['pulled']:>8}{c['kept']:>7}")
        print(f"\n{len(rows)} companies; PULLED = retrieved from the portal, "
              "KEPT = fresh+US+relevant+right-level. Low KEPT is usually the freshness "
              "window, not a miss. Re-run with a wider --hours to confirm completeness.\n")
    shortlist = discover.discover(hours=hours, target=target, profile=profile,
                                  sources=sources, refresh=refresh)
    for j in shortlist[:30]:
        print(f"  {j['posted_date']}  AQS={str(j['found_score'] or '-'):>3}  "
              f"ATS={j['match']:>3}  {j['profile']:<13} "
              f"{j['company'][:22]:<22} {j['role'][:44]}")
    if len(shortlist) > 30:
        print(f"  … and {len(shortlist) - 30} more (see dashboard)")
    dash.render()
    _print_results_hint()


def cmd_tailor(query: str, brain_mode: str | None, profile: str | None) -> None:
    """Tailor ONE tracked job, matched by substring against company/role/url.

    The single-job counterpart of `pipeline --from-tracker`: reuses the row's stored
    jd_text (so no re-fetch and stable ManualBrain packet hashes), the same brain
    resolution, and the same tailor_job path with all its gates. In manual-brain mode
    each of the 3 judgment calls pauses on a data/brain packet; answer it and re-run
    the same command to continue."""
    mode = brain_mode or config.brain_mode()
    if mode == "api":
        _require_key()
    brain = get_brain(mode)
    q = query.lower()
    rows = [a for a in tracker.list_applications()
            if q in f"{a.get('company','')} {a.get('role','')} {a.get('url','')}".lower()]
    if not rows:
        print(f"No tracked job matches '{query}'. Run `discover` first or check `status`.")
        return
    row = rows[-1]
    print(f"Tailoring: {row['company']}  {row['role']}")
    try:
        rec = tailor.tailor_job(
            row["url"], brain=brain, profile=profile or row.get("profile"),
            company=row["company"], role=row["role"],
            posted_date=row.get("posted_date"), source=row.get("source"),
            jd_text=(row.get("jd_text") or None))
        print(f"  -> {rec.get('status')}  score={rec.get('resume_score')}/10  "
              f"match={rec.get('match_pct')}%  pdf={rec.get('tailored_pdf')}")
    except BrainPending as e:
        print(f"  ⏸ {e}")


def cmd_pipeline(hours: int, top: int, profile: str | None, brain_mode: str | None,
                 from_tracker: bool, refresh: bool = False,
                 sources: list[str] | None = None) -> None:
    """discover -> tailor+score top N (two structured LLM calls per job) -> dashboard.

    Brain: --brain defaults to manual when no API key is set (LLM-as-brain: prompt
    packets land in data/brain/ for the running LLM to answer, then re-run). Use
    --brain api to force the API path.

    Resumable: discovery results are cached for the day, and jobs already scored for
    a URL are skipped  so re-running after a mid-run failure does NOT re-fetch or
    redo finished work. --refresh forces a fresh discovery sweep.
    """
    mode = brain_mode or config.brain_mode()
    if mode == "api":
        _require_key()
    else:
        print("Brain: MANUAL (no API key needed  this LLM answers the prompt packets).")
    brain = get_brain(mode)

    n_merged = tracker.dedupe_applications()
    if n_merged:
        print(f"Deduped {n_merged} duplicate tracker row(s) before running.")

    if from_tracker:
        backlog = [a for a in tracker.list_applications() if a.get("status") == "found"]
        # Pre-gate the WHOLE backlog with the cheap keyword scorer before picking the
        # top N, so tailoring slots go to the best-fit roles first instead of whatever
        # happens to be most recent in the tracker.
        for a in backlog:
            jd = a.get("jd_text")
            a["_pregate"] = ats.jd_match(jd)["score"] if jd else -1
        backlog.sort(key=lambda a: a["_pregate"], reverse=True)
        jobs = backlog[:top]
        print(f"=== PIPELINE: {len(jobs)} previously found roles (pre-gate ranked) "
              "-> tailor+score ===")
    else:
        print(f"=== PIPELINE: discover (past {hours}h) -> tailor+score top {top} "
              f"[brain={mode}] ===\n")
        # Stage 1: wide title-ranked pool; stage 2: re-rank the pool by REAL
        # full-JD match (+ sponsorship hard gate) so tailoring slots go to the
        # roles the resume can honestly score highest against.
        pool = discover.discover(hours=hours, target=max(top * 3, 50), profile=profile,
                                 sources=sources, refresh=refresh)
        jobs = discover.rerank_by_jd(pool, top=top)
    if not jobs:
        print("No fresh roles to process.")
        dash.render()
        return

    # Resumability: skip jobs already scored (so a re-run after a failure only
    # processes what's left). Manual mode still re-enters scored jobs only if their
    # packets were never answered  tailor_job is cheap to re-reach for those.
    scored_urls = {a.get("url") for a in tracker.list_applications()
                   if a.get("status") == "scored" and a.get("resume_score") is not None}
    remaining = [j for j in jobs if j["url"] not in scored_urls]
    skipped = len(jobs) - len(remaining)
    if skipped:
        print(f"Skipping {skipped} already-scored role(s); {len(remaining)} to process.")

    result = tailor.tailor_many(remaining, brain=brain)
    dash.render()

    print(f"\n=== PIPELINE DONE: {len(result['done'])} scored, "
          f"{len(result['pending'])} pending, {len(result['failed'])} failed ===")
    if result["pending"]:
        print("\nManual-brain packets awaiting responses (write the matching "
              ".response.json, then re-run this command):")
        for p in result["pending"]:
            print(f"  {p['job']}\n    -> {p['packet']}")
    if result["failed"]:
        print("\nFailed (use `score`/`apply` with the browser agent for these):")
        for f in result["failed"]:
            print(f"  {f['job']}: {f['error']}")
    _print_results_hint()
    print("\nSubmit a chosen role:  python -m src.cli apply \"<url>\"   "
          "(or `fill \"<url>\"` for Greenhouse, no key)")


def cmd_brain() -> None:
    """Show manual-brain packets that still need a response."""
    pend = pending_packets()
    if not pend:
        print("No pending brain packets. (Manual mode writes them to data/brain/.)")
        return
    print(f"{len(pend)} packet(s) awaiting responses in {config.BRAIN_DIR}/:")
    for name in pend:
        print(f"  {name}  ->  answer with {name.replace('.prompt.md', '.response.json')}")
    print("\nEach packet is self-contained: paste it into any LLM (or let an agent "
          "read it) and save ONLY the JSON object to the .response.json path. "
          "Then re-run your pipeline command.")


# ---------------------------------------------------------------- agent commands

def cmd_find(query: str, days: int, model: str, headless: bool, profile: str | None) -> None:
    browser = _browser(headless)
    try:
        run_agent(
            f"Find roles matching: '{query}'. Search several related keywords, pulling "
            "up to ~10 postings per keyword. FILTER ON RECENCY FIRST: keep only roles "
            f"whose posted date on the REAL company page is within {days} days of "
            "today. USA ONLY  skip roles located outside the United States. "
            "Then rank survivors by recency, then match to my resume. "
            "Save the shortlist with status='found'. Do NOT apply.",
            model=model, browser=browser, system=_FINDER_SYSTEM, profile=profile,
            max_turns=30, today=_today(), task_kind="find",
            usage_label=f"find {query}",
        )
    finally:
        browser.close()
    dash.render()
    _print_results_hint()


def cmd_score(url: str, model: str, headless: bool, profile: str | None) -> None:
    browser = _browser(headless)
    try:
        run_agent(
            f"Score this job for fit and ATS match, but DO NOT apply. Job URL: {url}\n"
            "Read my profile + master resume, open the page, run ats_score and "
            "score_resume, give me a fit verdict with reasoning, then save_application "
            "with status='scored' including resume_score (0-10), scorer_verdict, "
            "scorer_gaps, and match_score (0-100 ATS overlap).",
            model=model, browser=browser, profile=profile, today=_today(),
            usage_label=f"score {url}",
        )
    finally:
        browser.close()
    dash.render()
    _print_results_hint()


def cmd_apply(url: str, model: str, headless: bool, profile: str | None) -> None:
    # If we already have a tailored PDF for this URL, skip re-tailoring.
    existing = next(
        (a for a in reversed(tracker.list_applications())
         if a.get("url") == url and a.get("tailored_pdf")),
        None,
    )
    if existing:
        pdf = existing["tailored_pdf"]
        task = (
            f"Apply to this job, pausing for my confirmation before submitting. "
            f"Job URL: {url}\n"
            f"A tailored resume PDF already exists at '{pdf}'  skip re-tailoring "
            f"and resume scoring. Go straight to opening the application page, "
            f"classify_portal, fill the form using my profile + that PDF, then "
            f"ask_human before submitting. Save with status='applied' when done."
        )
        print(f"Using existing tailored PDF: {pdf}")
    else:
        task = (f"Apply to this job end to end, pausing for my confirmation before "
                f"submitting. Job URL: {url}")
    browser = _browser(headless)
    try:
        run_agent(task, model=model, browser=browser,
                  profile=profile or (existing or {}).get("profile"),
                  today=_today(), usage_label=f"apply {url}")
    finally:
        browser.close()
    dash.render()
    _print_results_hint()


# ---------------------------------------------------------------- legacy feed/run

def _feed_shortlist(days: int, profile: str | None, limit: int, refresh: bool) -> list[dict]:
    """Legacy curated-feed funnel (kept for back-compat; `discover` supersedes it)."""

    cache_key = f"feed-{days}-{profile or 'auto'}"
    today = _today()
    roles = None if refresh else finder.get_cached(cache_key, profile, today)
    if roles is None:
        listings = feeds.fetch_feed()
        roles = feeds.fresh_roles(listings, days)
        finder.put_cache(cache_key, profile, today, roles)
        print(f"Fetched feed: {len(roles)} fresh+relevant roles (<= {days}d).")
    else:
        print(f"Using today's cache: {len(roles)} roles (use --refresh to re-fetch).")

    if profile:
        roles = [r for r in roles if r["profile"] == profile]
    watch = set()
    if config.WATCHLIST_PATH.exists():
        watch = {c["name"].lower()
                 for c in json.loads(config.WATCHLIST_PATH.read_text()).get("companies", [])}
    masters = {p: profiles.read_master_for(p) for p in {r["profile"] for r in roles}}
    for r in roles:
        text = f"{r['role']} {r.get('locations', '')}"
        r["match"] = ats.ats_score(text, masters[r["profile"]])["score"]
        r["watchlist"] = r["company"].lower() in watch
    shortlist = roles[:limit]
    for r in shortlist:
        tracker.save_application(
            company=r["company"], role=r["role"], url=r["url"], status="found",
            match_score=r["match"], source="SimplifyJobs/New-Grad-Positions",
            posted_date=r["posted_date"], profile=r["profile"],
            notes="watchlist H1B-friendly" if r["watchlist"] else "",
        )
    wl_count = sum(1 for r in shortlist if r["watchlist"])
    print(f"\nTop {len(shortlist)} fresh roles (recency-first); "
          f"{wl_count} at watchlist (H1B-friendly) companies ★:")
    for r in shortlist:
        star = "★" if r["watchlist"] else " "
        print(f"  {star} {r['posted_date']}  ATS={r['match']:>3}  {r['profile']:<6} "
              f"{r['company'][:22]:<22} {r['role'][:40]}")
    return shortlist


def cmd_feed(days: int, profile: str | None, limit: int, refresh: bool) -> None:
    _feed_shortlist(days, profile, limit, refresh)
    dash.render()
    _print_results_hint()


def cmd_watchlist() -> None:
    if not config.WATCHLIST_PATH.exists():
        print("No config/watchlist.json found.")
        return
    data = json.loads(config.WATCHLIST_PATH.read_text())
    companies = data.get("companies", [])
    api_n = sum(1 for c in companies if c.get("ats") and c.get("token"))
    print(f"=== Watchlist  {len(companies)} companies ({api_n} with direct ATS APIs) ===")
    print(data.get("_sponsorship_note", ""))
    print()
    for c in companies:
        spons = "H1B✓" if c.get("sponsors_h1b") else "?"
        api = f"{c.get('ats')}:{c.get('token')}" if c.get("token") else "(agent crawl)"
        print(f"  {c['name']:<18} {c.get('tier', ''):<16} {spons:<6} {api:<28} "
              f"{c.get('board', '')[:50]}")
    print("\nAPI-tagged companies are swept automatically by `discover`/`pipeline`.")


def cmd_scout(query: str, hours: int, h1b: bool, limit: int, save: bool) -> None:
    """Browse the ScoutBetter API for fresh roles (reusable  no throwaway scripts).

    Prints newest-first matches with the real apply URL + JD already resolved; --h1b
    filters to sponsorship-friendly postings, --save records them as 'found' rows."""
    jobs = scoutbetter.search(query, hours=hours, h1b=h1b, limit=limit)
    tag = " [H1B sponsorship only]" if h1b else ""
    print(f"=== ScoutBetter: '{query}'  {len(jobs)} roles, past {hours}h{tag} ===\n")
    now = datetime.now(timezone.utc)
    for j in jobs:
        try:
            age = f"{int((now - datetime.fromtimestamp(j['posted_ts'], timezone.utc)).total_seconds() // 3600)}h"
        except Exception:
            age = "?"
        sal = f"${(j.get('salary_min') or 0)//1000}-{(j.get('salary_max') or 0)//1000}k" if j.get("salary_min") else ""
        print(f"  {age:>4}  {j.get('company','?')[:22]:<22} {j.get('role','')[:40]:<40} "
              f"{(j.get('locations') or '')[:16]:<16} yoe={j.get('yoe','?')} {sal}")
        print(f"        {j.get('url','')}")
    if save and jobs:
        discover.discover(hours=hours, target=limit, sources=["scoutbetter"], verbose=False)
        print(f"\nSaved to tracker. Tailor with: python -m src.cli pipeline --from-tracker")


def cmd_status(verbose: bool = False) -> None:
    apps = tracker.list_applications()
    if not apps:
        print("No applications recorded yet.")
        return

    today = _today()
    cols = (f"{'ID':<4}{'DATE':<12}{'STATUS':<10}{'AQS':<6}{'REV/10':<8}{'MUST%':<7}"
            f"{'ATS':<6}{'VERDICT':<12}")
    if verbose:
        cols += f"{'POSTED':<12}{'PROFILE':<14}{'SOURCE':<18}"
    print(cols + "COMPANY  ROLE")
    for a in apps:
        comp = scoring.score_record(a, today)
        aqs = f"{comp['score']}{comp['grade']}" if comp["score"] is not None else "-"
        line = (f"{a['id']:<4}{a['date']:<12}{a['status']:<10}{aqs:<6}"
                f"{str(a.get('resume_score') if a.get('resume_score') is not None else '-'):<8}"
                f"{str(a.get('match_pct') if a.get('match_pct') is not None else '-'):<7}"
                f"{str(a.get('match_score') if a.get('match_score') is not None else '-'):<6}"
                f"{str(a.get('scorer_verdict') or '-'):<12}")
        if verbose:
            line += (f"{str(a.get('posted_date') or '-'):<12}"
                     f"{str(a.get('profile') or '-'):<14}"
                     f"{str(a.get('source') or '-')[:16]:<18}")
        print(line + f"{a['company']}  {a['role']}")
    print("\nAQS = composite Application Quality Score /100 (+grade). "
          "REV = reviewer /10 · MUST% = JD must-haves matched · ATS = keyword overlap.")
    print(f"{len(apps)} record(s). Full view: python -m src.cli dashboard")


def _print_results_hint() -> None:
    path = config.DASHBOARD_PATH.resolve()
    apps = tracker.list_applications()
    print(f"\n📋 {len(apps)} record(s) tracked")
    print(f"   Dashboard: open {path}")
    print("   Terminal:  python -m src.cli status --verbose")


def cmd_fill(url: str, headless: bool) -> None:
    """Deterministic Greenhouse form fill  no LLM needed."""

    apps = tracker.list_applications()
    existing = next(
        (a for a in reversed(apps) if a.get("url") == url and a.get("tailored_pdf")),
        None,
    ) or next((a for a in reversed(apps) if a.get("url") == url), None)

    pdf_path = (existing or {}).get("tailored_pdf") or str(
        config.RESUME_DIR / "MyResume.pdf")
    _p = json.loads(config.PROFILE_PATH.read_text())
    _per, _lnk, _wa = _p["personal"], _p["links"], _p["work_authorization"]

    print("\n" + "=" * 55)
    print("ABOUT TO FILL  review before browser opens:")
    print("=" * 55)
    print(f"  Company:     {(existing or {}).get('company', '?')}  "
          f"{(existing or {}).get('role', '?')}")
    print(f"  Name:        {_per['full_name']}")
    print(f"  Email:       {_per['email']}")
    print(f"  Phone:       {_per['phone']}")
    print(f"  Location:    {_per['location']}")
    print(f"  LinkedIn:    {_lnk.get('linkedin', '(empty)')}")
    print(f"  GitHub:      {_lnk.get('github', '(empty)')}")
    print(f"  Resume PDF:  {pdf_path}")
    print(f"  Work auth:   authorized={_wa.get('authorized_to_work')}  "
          f"sponsorship={_wa.get('requires_sponsorship')}  "
          f"visa={_wa.get('visa_status')}")
    _edu = _p.get("education", {})
    print(f"  Education:   {_edu.get('school', '?')} | {_edu.get('degree', '?')} | "
          f"grad {_edu.get('graduation', '?')}")
    print("=" * 55)
    go = input("\nOpen browser and fill the form? [yes/no]: ").strip().lower()
    if go not in ("yes", "y"):
        print("Cancelled.")
        return

    browser = _browser(headless)
    try:
        if "ashbyhq.com" in url.lower() or "ashby" in url.lower():
            result = ashby.fill_ashby_form(browser, url, pdf_path)
        elif "lever.co" in url.lower():
            result = lever.fill_lever_form(browser, url, pdf_path)
        else:
            result = gh.fill_greenhouse_form(browser, url, pdf_path)
        print(f"\n  Filled:  {', '.join(result['filled']) or '(none)'}")
        print(f"  Skipped: {', '.join(result['skipped']) or '(none)'}")
        print("\n>> Form filled. Review every field in the browser, then submit manually.")
        input(">> When done, press Enter here to close the browser …")
    finally:
        browser.close()

    updated = tracker.update_application(url, status="ready_to_submit",
                                         tailored_pdf=pdf_path)
    if not updated and existing:
        tracker.save_application(
            company=existing["company"], role=existing["role"], url=url,
            status="ready_to_submit", match_score=existing.get("match_score"),
            resume_score=existing.get("resume_score"),
            scorer_verdict=existing.get("scorer_verdict"), tailored_pdf=pdf_path,
            profile=existing.get("profile"), source=existing.get("source"),
            posted_date=existing.get("posted_date"),
        )
    dash.render()
    _print_results_hint()


def cmd_dashboard(serve: bool = False, port: int = 8765, migrate: bool = False) -> None:
    if migrate:
        moves = artifacts.migrate_layout()
        print(f"Refiled {len(moves)} application folder(s) as <Company>/<job-id>/")
    if serve:
        return dashboard_server.serve(port)
    print(dash.render())
    print(f"Open it with:  open {config.DASHBOARD_PATH.resolve()}")
    print("Interactive (apply / find-resume buttons):  "
          "python -m src.cli dashboard --serve")


def cmd_report() -> None:
    s = runlog.summary()
    if not s["total_events"]:
        print("No QA events logged yet. Run find/score/apply first.")
        return
    print("=== Per-step quality (pass/fail) ===")
    for step, c in s["steps"].items():
        print(f"  {step:<16} ok={c['ok']:<3} fail={c['fail']}")
    if s["issues"]:
        print(f"\n=== {len(s['issues'])} issue(s) logged ===")
        for it in s["issues"]:
            print(f"  [{it['step']}] {it['target'][:50]} → {it['issue']}")
    else:
        print("\nNo issues logged  all steps passed.")


def cmd_usage() -> None:
    rows = usage.read_log()
    if not rows:
        print("No usage logged yet. Run score/apply/pipeline (API brain).")
        return
    print(f"{'DATE':<12}{'MODEL':<20}{'IN':>8}{'OUT':>8}{'TOTAL':>9}{'$':>9}  LABEL")
    for r in rows:
        print(f"{r['date']:<12}{r['model']:<20}{r['input']:>8}{r['output']:>8}"
              f"{r['total']:>9}{r['cost_usd']:>9}  {r.get('label', '')[:40]}")
    t = usage.totals()
    print(f"\nTOTAL: {t['runs']} runs · {t['total_tokens']} tokens · ${t['total_cost_usd']}")
    cap = config.token_budget()
    print(f"Per-run ceiling (JOB_AGENT_TOKEN_BUDGET): {cap if cap else 'unlimited'}")


def main(argv: list[str] | None = None) -> None:
    load_dotenv(config.ROOT / ".env")
    parser = argparse.ArgumentParser(prog="job-applier-agent")
    sub = parser.add_subparsers(dest="command", required=True)

    p_disc = sub.add_parser("discover",
                            help="Top-N fresh roles from feeds + ATS APIs (no key)")
    p_disc.add_argument("--hours", type=int, default=24, help="freshness window in hours")
    p_disc.add_argument("--target", type=int, default=100, help="how many roles to keep")
    p_disc.add_argument("--profile", default=None)
    p_disc.add_argument("--source", default=None,
                        help="comma-separated source names/keywords "
                             "(ats_boards,github_feed,linkedin,scoutbetter); default: all available")
    p_disc.add_argument("--coverage", action="store_true",
                        help="print a per-company pulled-vs-kept table to verify completeness")
    p_disc.add_argument("--refresh", action="store_true",
                        help="ignore today's cached sweep and re-pull every source")

    p_pipe = sub.add_parser("pipeline",
                            help="discover -> tailor+score top N -> dashboard (no submit)")
    p_pipe.add_argument("--hours", type=int, default=24)
    p_pipe.add_argument("--top", type=int, default=10, help="roles to tailor+score")
    p_pipe.add_argument("--profile", default=None)
    p_pipe.add_argument("--brain", choices=["api", "manual"], default=None,
                        help="manual = no API key (this LLM answers packets); "
                             "default: manual when no key is set, else api")
    p_pipe.add_argument("--from-tracker", action="store_true",
                        help="tailor previously discovered 'found' rows instead of re-discovering")
    p_pipe.add_argument("--refresh", action="store_true",
                        help="force a fresh discovery sweep (ignore today's cache)")
    p_pipe.add_argument("--source", default=None,
                        help="comma-separated source names/keywords; default: all available")

    p_tailor = sub.add_parser("tailor", help="Tailor one tracked job (match by company/role/url substring)")
    p_tailor.add_argument("query", help="substring matching the tracked job's company/role/url")
    p_tailor.add_argument("--profile", default=None)
    p_tailor.add_argument("--brain", choices=["api", "manual"], default=None)

    sub.add_parser("brain", help="List manual-brain packets awaiting responses")

    p_find = sub.add_parser("find", help="Agent crawls boards for roles (needs key)")
    p_find.add_argument("query")
    p_find.add_argument("--days", type=int, default=3)
    p_find.add_argument("--model", default=FAST_MODEL)
    p_find.add_argument("--profile", default=None)
    p_find.add_argument("--headless", action="store_true")

    p_score = sub.add_parser("score", help="Agent scores one job URL (needs key)")
    p_score.add_argument("url")
    p_score.add_argument("--model", default=FAST_MODEL)
    p_score.add_argument("--profile", default=None)
    p_score.add_argument("--headless", action="store_true")

    p_apply = sub.add_parser("apply", help="Agent applies end-to-end (confirms before submit)")
    p_apply.add_argument("url")
    p_apply.add_argument("--model", default=DEFAULT_MODEL)
    p_apply.add_argument("--profile", default=None)
    p_apply.add_argument("--headless", action="store_true")

    p_fill = sub.add_parser("fill", help="Deterministic Greenhouse/Ashby/Lever form fill (no key)")
    p_fill.add_argument("url")
    p_fill.add_argument("--headless", action="store_true")

    p_scout = sub.add_parser("scout", help="Browse the ScoutBetter API for fresh roles")
    p_scout.add_argument("query", help="search term, e.g. \"machine learning engineer\"")
    p_scout.add_argument("--hours", type=int, default=168, help="freshness window (default 7d)")
    p_scout.add_argument("--h1b", action="store_true", help="H1B-sponsorship postings only")
    p_scout.add_argument("--limit", type=int, default=20)
    p_scout.add_argument("--save", action="store_true", help="record results as 'found' rows")

    p_status = sub.add_parser("status", help="Show application history")
    p_status.add_argument("--verbose", action="store_true")
    p_dash = sub.add_parser("dashboard", help="Regenerate the scores dashboard")
    p_dash.add_argument("--serve", action="store_true",
                        help="serve it live so apply / save-pdf buttons work")
    p_dash.add_argument("--port", type=int, default=8765)
    p_dash.add_argument("--migrate", action="store_true",
                        help="refile legacy application folders as <Company>/<job-id>/")
    sub.add_parser("report", help="QA run-log: per-step pass/fail + issues")
    sub.add_parser("watchlist", help="Show the company watchlist (ATS APIs flagged)")
    sub.add_parser("usage", help="Token + cost usage per run and totals")

    p_feed = sub.add_parser("feed", help="(legacy) curated GitHub feed only")
    p_feed.add_argument("--days", type=int, default=7)
    p_feed.add_argument("--profile", default=None)
    p_feed.add_argument("--limit", type=int, default=15)
    p_feed.add_argument("--refresh", action="store_true")

    p_run = sub.add_parser("run", help="(legacy alias of `pipeline`)")
    p_run.add_argument("--days", type=int, default=1)
    p_run.add_argument("--profile", default=None)
    p_run.add_argument("--top", type=int, default=10)
    p_run.add_argument("--brain", choices=["api", "manual"], default=None)

    args = parser.parse_args(argv)

    if args.command in ("find", "score", "apply"):
        _require_key()

    def _srcs(v):
        return [s.strip() for s in v.split(",") if s.strip()] if v else None

    if args.command == "discover":
        cmd_discover(args.hours, args.target, args.profile, _srcs(args.source),
                     coverage=args.coverage, refresh=args.refresh)
    elif args.command == "pipeline":
        cmd_pipeline(args.hours, args.top, args.profile, args.brain, args.from_tracker,
                     refresh=args.refresh, sources=_srcs(args.source))
    elif args.command == "run":
        cmd_pipeline(args.days * 24, args.top, args.profile, args.brain, False)
    elif args.command == "tailor":
        cmd_tailor(args.query, args.brain, args.profile)
    elif args.command == "brain":
        cmd_brain()
    elif args.command == "find":
        cmd_find(args.query, args.days, args.model, args.headless, args.profile)
    elif args.command == "score":
        cmd_score(args.url, args.model, args.headless, args.profile)
    elif args.command == "apply":
        cmd_apply(args.url, args.model, args.headless, args.profile)
    elif args.command == "scout":
        cmd_scout(args.query, args.hours, args.h1b, args.limit, args.save)
    elif args.command == "status":
        cmd_status(verbose=args.verbose)
    elif args.command == "dashboard":
        cmd_dashboard(args.serve, args.port, args.migrate)
    elif args.command == "report":
        cmd_report()
    elif args.command == "feed":
        cmd_feed(args.days, args.profile, args.limit, args.refresh)
    elif args.command == "fill":
        cmd_fill(args.url, args.headless)
    elif args.command == "watchlist":
        cmd_watchlist()
    elif args.command == "usage":
        cmd_usage()


if __name__ == "__main__":
    main()
