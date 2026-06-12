"""Command-line entry point.

Commands:
    find   <query>  — discover fresh, well-matched roles (no applying).
    score  <url>    — read a job + score fit/ATS, no applying (cheap model).
    apply  <url>    — full flow incl. tailor + score + form fill + human-confirmed submit.
    status          — print your application history.
    dashboard       — regenerate the static BI dashboard (data/dashboard.html).

Multi-model: cheap/fast model for find & score; the most capable for tailor/apply.
Override with --model or the JOB_AGENT_MODEL / JOB_AGENT_FAST_MODEL env vars.
--profile selects which master resume to use (ml_ai / sde / data_engineer / sde_ml_ai);
omit to let the agent auto-pick by JD.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from datetime import date

from dotenv import load_dotenv

from .agent import DEFAULT_MODEL, _FINDER_SYSTEM, run_agent
from .tools import dashboard as dash
from .tools import ats, feeds, finder, profiles, runlog, tracker, usage
from .tools.browser import Browser
from .tools import greenhouse as gh

# Cheap model for lightweight tasks (find, score). Capable model for the full flow.
FAST_MODEL = os.environ.get("JOB_AGENT_FAST_MODEL", "claude-sonnet-4-6")


def _require_key() -> None:
    # Need a key for at least one provider; the per-task provider routing (tools/llm.py)
    # decides which is actually used. So accept either Anthropic or OpenAI.
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")):
        sys.exit("Set ANTHROPIC_API_KEY and/or OPENAI_API_KEY (in .env). "
                 "Route tasks per provider via JOB_AGENT_PROVIDER / "
                 "JOB_AGENT_TAILOR_PROVIDER / JOB_AGENT_SCORE_PROVIDER.")


def _browser(headless: bool) -> Browser:
    return Browser(headless=headless, user_data_dir=os.environ.get("JOB_AGENT_USER_DATA_DIR"))


def cmd_find(query: str, days: int, model: str, headless: bool, profile: str | None) -> None:
    browser = _browser(headless)
    try:
        run_agent(
            f"Find roles matching: '{query}'. Search several related keywords (e.g. "
            "data engineer, software engineer/SDE, machine learning engineer, and close "
            "variants), pulling up to ~10 postings per keyword. FILTER ON RECENCY FIRST: "
            f"keep only roles whose posted date on the REAL company page is within {days} "
            "days of today. USA ONLY — skip any role whose location is outside the "
            "United States (drop Canada, UK, Europe, India, etc.). "
            "Then rank survivors by recency, then match to my resume. "
            "Save the shortlist with status='found'. Do NOT apply.",
            model=model,
            browser=browser,
            system=_FINDER_SYSTEM,
            profile=profile,
            max_turns=30,
            today=date.today().isoformat(),
            task_kind="find",
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
            "with status='scored' including resume_score (the 0-10 overall_score), "
            "scorer_verdict, scorer_gaps, and match_score (the 0-100 ATS overlap).",
            model=model,
            browser=browser,
            profile=profile,
            today=date.today().isoformat(),
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
            f"A tailored resume PDF already exists at '{pdf}' — skip re-tailoring "
            f"and resume scoring. Go straight to opening the application page, "
            f"classify_portal, fill the form using my profile + that PDF, then "
            f"ask_human before submitting. Save with status='applied' when done."
        )
        print(f"Using existing tailored PDF: {pdf}")
    else:
        task = (
            f"Apply to this job end to end, pausing for my confirmation before "
            f"submitting. Job URL: {url}"
        )
    browser = _browser(headless)
    try:
        run_agent(
            task,
            model=model,
            browser=browser,
            profile=profile or (existing or {}).get("profile"),
            today=date.today().isoformat(),
            usage_label=f"apply {url}",
        )
    finally:
        browser.close()
    dash.render()
    _print_results_hint()


def _feed_shortlist(days: int, profile: str | None, limit: int, refresh: bool) -> list[dict]:
    """Shared funnel step: fetch the curated feed (daily-cached), filter to fresh +
    relevant roles for the profile, ATS-rank, flag watchlist companies, save the top
    `limit` as status='found', and return them. Used by both `feed` and `run`."""
    cache_key = f"feed-{days}-{profile or 'auto'}"
    today = date.today().isoformat()
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
    import json as _json
    wl_path = pathlib.Path("config/watchlist.json")
    watch = set()
    if wl_path.exists():
        watch = {c["name"].lower() for c in _json.loads(wl_path.read_text()).get("companies", [])}
    masters = {p: profiles.read_master_for(p) for p in {r["profile"] for r in roles}}
    for r in roles:
        text = f"{r['role']} {r.get('locations','')}"
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
    """Pull curated GitHub job feeds (SimplifyJobs), filter to fresh + relevant roles,
    match against the master resume, rank by recency, save the shortlist. No API key."""
    _feed_shortlist(days, profile, limit, refresh)
    dash.render()
    _print_results_hint()


def cmd_run(days: int, profile: str | None, top: int, model: str,
            headless: bool, refresh: bool) -> None:
    """One-command funnel: feed -> rank -> score+tailor the top N -> dashboard.
    STOPS before submitting. Each role's score/tailor is one human-confirmed-free agent
    pass (no form submission); review the dashboard and run `apply <url>` to submit."""
    _require_key()
    print(f"=== RUN: feed (<= {days}d) -> score+tailor top {top} -> dashboard ===\n")
    shortlist = _feed_shortlist(days, profile, top, refresh)
    if not shortlist:
        print("No fresh roles to process."); dash.render(); return
    print(f"\n--- Scoring + tailoring the top {len(shortlist)} (no submit) ---")
    browser = _browser(headless)
    try:
        for i, r in enumerate(shortlist, 1):
            print(f"\n[{i}/{len(shortlist)}] {r['company']} — {r['role']}")
            run_agent(
                f"Score AND tailor my resume for this job, but DO NOT apply or submit. "
                f"Job URL: {r['url']}\n"
                "Open the page, read the JD, run score_resume, and if the verdict is "
                "'strong' or 'borderline' tailor the resume (apply_resume_patch + "
                "render_resume_pdf with company/role/url) so a tailored PDF is saved. "
                "Then save_application with status='scored', resume_score, scorer_verdict, "
                "match_score, resume_diff, and tailored_pdf. Stop after saving — never fill "
                "a form or submit.",
                model=model, browser=browser, profile=r["profile"],
                today=date.today().isoformat(), max_turns=30,
                usage_label=f"run/score {r['company']} — {r['role']}",
            )
    finally:
        browser.close()
    dash.render()
    _print_results_hint()
    print("\nReview the dashboard, then submit a chosen role with:  "
          "python -m src.cli apply \"<url>\"")


def cmd_watchlist() -> None:
    """Show the curated daily watchlist of H1B/OPT-friendly companies + their boards."""
    import json
    p = pathlib.Path("config/watchlist.json")
    if not p.exists():
        print("No config/watchlist.json found.")
        return
    data = json.loads(p.read_text())
    companies = data.get("companies", [])
    print(f"=== Daily watchlist — {len(companies)} H1B/OPT-friendly companies ===")
    print(data.get("_sponsorship_note", ""))
    print()
    for c in companies:
        spons = "H1B✓" if c.get("sponsors_h1b") else "?"
        print(f"  {c['name']:<18} {c.get('tier',''):<18} {spons:<6} {c['board']}")
    print("\nTo check one: python -m src.cli find \"<role>\" (point the agent at a board), "
          "or run `feed` for the curated cross-company list.")


def cmd_status(verbose: bool = False) -> None:
    apps = tracker.list_applications()
    if not apps:
        print("No applications recorded yet.")
        return
    def ats_of(a):
        return a.get("match_score") if a.get("match_score") is not None else a.get("ats_score")

    if verbose:
        print(f"{'ID':<4}{'DATE':<12}{'STATUS':<10}{'ATS/100':<8}{'SCORE/10':<9}{'VERDICT':<12}"
              f"{'POSTED':<12}{'PROFILE':<14}{'SOURCE':<14}COMPANY — ROLE")
        for a in apps:
            print(
                f"{a['id']:<4}{a['date']:<12}{a['status']:<10}"
                f"{str(ats_of(a) if ats_of(a) is not None else '-'):<8}"
                f"{str(a.get('resume_score') if a.get('resume_score') is not None else '-'):<9}"
                f"{str(a.get('scorer_verdict') or '-'):<12}"
                f"{str(a.get('posted_date') or '-'):<12}"
                f"{str(a.get('profile') or '-'):<14}"
                f"{str(a.get('source') or '-')[:20]:<22}"
                f"{a['company']} — {a['role']}"
            )
    else:
        print(f"{'ID':<4}{'DATE':<12}{'STATUS':<10}{'ATS/100':<8}{'SCORE/10':<9}{'VERDICT':<12}COMPANY — ROLE")
        for a in apps:
            print(
                f"{a['id']:<4}{a['date']:<12}{a['status']:<10}"
                f"{str(ats_of(a) if ats_of(a) is not None else '-'):<8}"
                f"{str(a.get('resume_score') if a.get('resume_score') is not None else '-'):<9}"
                f"{str(a.get('scorer_verdict') or '-'):<12}"
                f"{a['company']} — {a['role']}"
            )
    print("\nATS = keyword overlap /100 (find). SCORE = reviewer quality /10 (score/apply).")
    print(f"{len(apps)} record(s). Full view: python -m src.cli dashboard")


def _print_results_hint() -> None:
    """After a run, tell the user exactly where to see results."""
    path = pathlib.Path("data/dashboard.html").resolve()
    apps = tracker.list_applications()
    scores = [a.get("match_score") for a in apps if isinstance(a.get("match_score"), int)]
    top = max(scores) if scores else "-"
    print(f"\n📋 {len(apps)} record(s) tracked; top match score: {top}")
    print(f"   Dashboard: {path}")
    print(f"   Open it:   open {path}")
    print("   Terminal:  python -m src.cli status --verbose")


def cmd_fill(url: str, headless: bool) -> None:
    """Deterministic Greenhouse form fill — no LLM needed.

    Looks up the tailored PDF for the URL, opens the Greenhouse form in a real
    browser, fills all fields from profile.json, then asks for confirmation
    before submitting.
    """
    apps = tracker.list_applications()
    existing = next(
        (a for a in reversed(apps) if a.get("url") == url and a.get("tailored_pdf")),
        None,
    )
    if not existing:
        # Fall back to most recent entry for this URL regardless of PDF
        existing = next((a for a in reversed(apps) if a.get("url") == url), None)

    import json as _json
    pdf_path = (existing or {}).get("tailored_pdf") or "resume/MyResume.pdf"
    _p = _json.load(open("config/profile.json"))
    _per = _p["personal"]; _lnk = _p["links"]; _wa = _p["work_authorization"]

    # Show everything BEFORE opening the browser so user can abort early
    print("\n" + "="*55)
    print("ABOUT TO FILL — review before browser opens:")
    print("="*55)
    print(f"  Company:     {(existing or {}).get('company','?')} — {(existing or {}).get('role','?')}")
    print(f"  Name:        {_per['full_name']}")
    print(f"  Email:       {_per['email']}")
    print(f"  Phone:       {_per['phone']}")
    print(f"  Location:    {_per['location']}")
    print(f"  LinkedIn:    {_lnk.get('linkedin','(empty)')}")
    print(f"  GitHub:      {_lnk.get('github','(empty)')}")
    print(f"  Website:     {_lnk.get('website','(empty)')}")
    print(f"  Resume PDF:  {pdf_path}")
    print(f"  Work auth:   authorized={_wa.get('authorized_to_work')}  "
          f"sponsorship={_wa.get('requires_sponsorship')}  "
          f"visa={_wa.get('visa_status')}  "
          f"citizenship={_wa.get('citizenship_country','?')}")
    _edu = _p.get("education", {})
    print(f"  Education:   {_edu.get('school','?')} | {_edu.get('degree','?')} | grad {_edu.get('graduation','?')}")
    _exp = (_p.get("experience") or [{}])[0]
    amazon_flag = "amazon" in (_exp.get("company","")).lower()
    print(f"  Employer:    {_exp.get('company','?')} {'⚠ Amazon employee → Twitch is Amazon subsidiary' if amazon_flag else ''}")
    print("="*55)
    go = input("\nOpen browser and fill the form? [yes/no]: ").strip().lower()
    if go not in ("yes", "y"):
        print("Cancelled."); return

    browser = _browser(headless)
    try:
        result = gh.fill_greenhouse_form(browser, url, pdf_path)
        print(f"\n  Filled:  {', '.join(result['filled']) or '(none)'}")
        print(f"  Skipped: {', '.join(result['skipped']) or '(none)'}")
        print("\n>> Form filled. Review every field in the browser, then submit manually.")
        print(">> When done, come back here and press Enter to close the browser.")
        input(">> Press Enter to close …")
    finally:
        browser.close()

    # Mark as "ready_to_submit" so dashboard shows it's been filled
    updated = tracker.update_application(url, status="ready_to_submit", tailored_pdf=pdf_path)
    if not updated and existing:
        tracker.save_application(
            company=existing["company"], role=existing["role"],
            url=url, status="ready_to_submit",
            match_score=existing.get("match_score"),
            resume_score=existing.get("resume_score"),
            scorer_verdict=existing.get("scorer_verdict"),
            tailored_pdf=pdf_path,
            profile=existing.get("profile"),
            source=existing.get("source"),
            posted_date=existing.get("posted_date"),
        )

    dash.render()
    _print_results_hint()


def cmd_dashboard() -> None:
    print(dash.render())
    print(f"Open it with:  open {pathlib.Path('data/dashboard.html').resolve()}")


def cmd_report() -> None:
    """Print the QA run-log summary: per-step pass/fail and any logged issues."""
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
        print("\nNo issues logged — all steps passed.")


def cmd_usage() -> None:
    """Show token + cost usage per run and totals (from data/usage_log.jsonl)."""
    rows = usage.read_log()
    if not rows:
        print("No usage logged yet. Run score/apply/run (needs API key).")
        return
    print(f"{'DATE':<12}{'MODEL':<20}{'IN':>8}{'OUT':>8}{'TOTAL':>9}{'$':>9}  LABEL")
    for r in rows:
        print(f"{r['date']:<12}{r['model']:<20}{r['input']:>8}{r['output']:>8}"
              f"{r['total']:>9}{r['cost_usd']:>9}  {r.get('label','')[:40]}")
    t = usage.totals()
    print(f"\nTOTAL: {t['runs']} runs · {t['total_tokens']} tokens · ${t['total_cost_usd']}")
    import os
    cap = os.environ.get("JOB_AGENT_TOKEN_BUDGET", "0")
    print(f"Per-run ceiling (JOB_AGENT_TOKEN_BUDGET): {cap if cap!='0' else 'unlimited'}")


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="job-applier-agent")
    sub = parser.add_subparsers(dest="command", required=True)

    p_find = sub.add_parser("find", help="Find fresh, well-matched roles (no applying)")
    p_find.add_argument("query")
    p_find.add_argument("--days", type=int, default=3, help="freshness window (max 7)")
    p_find.add_argument("--model", default=FAST_MODEL)
    p_find.add_argument("--profile", default=None)
    p_find.add_argument("--headless", action="store_true")

    p_score = sub.add_parser("score", help="Score a job without applying")
    p_score.add_argument("url")
    p_score.add_argument("--model", default=FAST_MODEL)
    p_score.add_argument("--profile", default=None)
    p_score.add_argument("--headless", action="store_true")

    p_apply = sub.add_parser("apply", help="Apply end-to-end (confirms before submit)")
    p_apply.add_argument("url")
    p_apply.add_argument("--model", default=DEFAULT_MODEL)
    p_apply.add_argument("--profile", default=None)
    p_apply.add_argument("--headless", action="store_true")

    p_fill = sub.add_parser("fill", help="Fill a Greenhouse form from profile.json — no API key needed")
    p_fill.add_argument("url")
    p_fill.add_argument("--headless", action="store_true")

    p_status = sub.add_parser("status", help="Show application history")
    p_status.add_argument("--verbose", action="store_true", help="show all columns")
    sub.add_parser("dashboard", help="Regenerate the static BI dashboard")
    sub.add_parser("report", help="Show the QA run-log: per-step pass/fail + issues")

    sub.add_parser("watchlist", help="Show the curated daily H1B/OPT company watchlist")
    sub.add_parser("usage", help="Show token + cost usage per run and totals")

    p_feed = sub.add_parser("feed", help="Pull curated GitHub feeds (SimplifyJobs) for fresh roles")
    p_feed.add_argument("--days", type=int, default=7, help="freshness window (max 7)")
    p_feed.add_argument("--profile", default=None, help="filter to ml_ai/sde/data_engineer/sde_ml_ai")
    p_feed.add_argument("--limit", type=int, default=15, help="how many to save")
    p_feed.add_argument("--refresh", action="store_true", help="bypass the daily cache")

    p_run = sub.add_parser("run", help="One command: feed -> score+tailor top N -> dashboard (no submit)")
    p_run.add_argument("--days", type=int, default=7, help="freshness window (max 7)")
    p_run.add_argument("--profile", default=None, help="ml_ai/sde/data_engineer/sde_ml_ai")
    p_run.add_argument("--top", type=int, default=5, help="how many top roles to score+tailor")
    p_run.add_argument("--model", default=DEFAULT_MODEL)
    p_run.add_argument("--headless", action="store_true")
    p_run.add_argument("--refresh", action="store_true", help="bypass the daily cache")

    args = parser.parse_args(argv)

    if args.command in ("find", "score", "apply", "run"):
        _require_key()

    if args.command == "find":
        cmd_find(args.query, args.days, args.model, args.headless, args.profile)
    elif args.command == "score":
        cmd_score(args.url, args.model, args.headless, args.profile)
    elif args.command == "apply":
        cmd_apply(args.url, args.model, args.headless, args.profile)
    elif args.command == "status":
        cmd_status(verbose=args.verbose)
    elif args.command == "dashboard":
        cmd_dashboard()
    elif args.command == "report":
        cmd_report()
    elif args.command == "feed":
        cmd_feed(args.days, args.profile, args.limit, args.refresh)
    elif args.command == "run":
        cmd_run(args.days, args.profile, args.top, args.model, args.headless, args.refresh)
    elif args.command == "fill":
        cmd_fill(args.url, args.headless)
    elif args.command == "watchlist":
        cmd_watchlist()
    elif args.command == "usage":
        cmd_usage()


if __name__ == "__main__":
    main()
