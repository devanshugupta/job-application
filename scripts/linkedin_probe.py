"""LinkedIn parseability probe — ZERO LLM tokens.

Answers, with evidence, "how much can deterministic Playwright parsing actually
get from LinkedIn?" before we write any real parsers (verify-before-coding).

For each page type it records:
  - where we actually land (authwall / login redirect / real page)
  - whether LinkedIn still embeds voyager JSON in <code> blocks, and how much
  - raw HTML size (the token cost we're avoiding by parsing deterministically)
  - a few sample fields pulled via cheap selectors, as a parser feasibility check

Read-only: never clicks Connect/Message/Apply, never scrolls aggressively.
Human-paced delays between pages. One pass, ~8 pages total.

Usage:
    python scripts/linkedin_probe.py --login          # first run: log in manually, then Enter
    python scripts/linkedin_probe.py --company stripe # probe using company slug
    python scripts/linkedin_probe.py --company stripe --person-url https://www.linkedin.com/in/someone/

Output: data/network/linkedin_probe.json + console summary.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / "data" / ".linkedin_profile"
OUT = ROOT / "data" / "network" / "linkedin_probe.json"

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def human_pause(lo: float = 4.0, hi: float = 9.0) -> None:
    time.sleep(random.uniform(lo, hi))


def probe_page(page, name: str, url: str) -> dict:
    """Visit one page and measure what a deterministic parser could extract."""
    rec: dict = {"page": name, "url": url}
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(3_500)  # let hydrating content settle
        rec["status"] = resp.status if resp else None
        rec["final_url"] = page.url
        rec["walled"] = any(
            w in page.url for w in ("authwall", "/login", "checkpoint", "signup")
        )

        html = page.content()
        rec["html_bytes"] = len(html)
        rec["approx_tokens_if_raw"] = len(html) // 4  # the cost we're avoiding

        # 1) voyager JSON embedded in <code> blocks — the robust parse path
        codes = page.locator("code").all()
        voyager = {"code_tags": len(codes), "json_blobs": 0, "interesting_types": []}
        types_seen: set[str] = set()
        for c in codes[:80]:
            try:
                txt = c.text_content(timeout=1_000) or ""
            except Exception:
                continue
            t = txt.strip()
            if not (t.startswith("{") and len(t) > 200):
                continue
            try:
                blob = json.loads(t)
            except Exception:
                continue
            voyager["json_blobs"] += 1
            for m in re.finditer(r'"\$type"\s*:\s*"([^"]+)"', t):
                types_seen.add(m.group(1).rsplit(".", 1)[-1])
        voyager["interesting_types"] = sorted(types_seen)[:25]
        rec["voyager"] = voyager

        # 2) cheap selector samples — is visible DOM parseable at all?
        samples = {}
        for key, sel in {
            "h1": "h1",
            "profile_cards": "[data-view-name], .org-people-profile-card, .entity-result",
            "job_cards": ".job-card-container, [data-job-id], .jobs-search-results__list-item",
            "about_text": "section p",
        }.items():
            try:
                loc = page.locator(sel)
                n = loc.count()
                first = (loc.first.text_content(timeout=1_500) or "").strip()[:120] if n else ""
                samples[key] = {"count": n, "first": first}
            except Exception as e:  # selector may not apply on this page type
                samples[key] = {"error": str(e)[:80]}
        rec["selectors"] = samples

    except Exception as e:
        rec["error"] = str(e)[:200]
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true", help="pause for manual login first")
    ap.add_argument("--company", default="anthropic", help="company slug for /company/<slug>/")
    ap.add_argument("--person-url", default="", help="optional public profile URL to probe")
    ap.add_argument("--school", default="arizona-state-university", help="school slug for alumni page")
    args = ap.parse_args()

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=False, user_agent=_UA,
            viewport={"width": 1380, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        page.wait_for_timeout(3_000)
        logged_in = "feed" in page.url and "login" not in page.url
        if args.login or not logged_in:
            print(">> Log into LinkedIn in the opened browser window (I never see the password).")
            input(">> Press Enter here once the feed loads... ")
        results.append({"page": "feed_login_check", "final_url": page.url, "logged_in": logged_in})

        co = args.company
        targets = [
            ("company_about", f"https://www.linkedin.com/company/{co}/about/"),
            ("company_people", f"https://www.linkedin.com/company/{co}/people/"),
            ("company_jobs", f"https://www.linkedin.com/company/{co}/jobs/"),
            ("people_search",
             f"https://www.linkedin.com/search/results/people/?keywords=machine%20learning%20engineer%20{co}"),
            ("job_search",
             "https://www.linkedin.com/jobs/search/?keywords=machine%20learning%20engineer&f_TPR=r86400"),
            ("alumni", f"https://www.linkedin.com/school/{args.school}/people/"),
        ]
        if args.person_url:
            targets.append(("person_profile", args.person_url))

        for name, url in targets:
            print(f"probing {name} ...")
            results.append(probe_page(page, name, url))
            human_pause()

        ctx.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"probed_at": datetime.now(timezone.utc).isoformat(), "results": results}, indent=2))

    print(f"\n== probe summary -> {OUT}")
    for r in results:
        if "page" not in r or r["page"] == "feed_login_check":
            continue
        wall = "WALLED" if r.get("walled") else "ok"
        v = r.get("voyager", {})
        print(f"  {r['page']:16s} {wall:7s} blobs={v.get('json_blobs', '?'):>3} "
              f"html≈{r.get('approx_tokens_if_raw', 0)//1000}k tok "
              f"types={','.join(v.get('interesting_types', [])[:4])}")


if __name__ == "__main__":
    main()
