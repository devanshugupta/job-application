"""Discovery orchestrator — find the top N fresh roles across every source, fast.

One deterministic pass, no LLM, no browser:

    GitHub feeds (SimplifyJobs etc.)  ──┐
                                        ├─> normalize -> dedupe -> filter
    ATS board APIs (watchlist)        ──┘   (freshness · US · title/seniority ·
                                             excluded companies)
                                            -> ATS-match vs master resume
                                            -> composite rank (recency+match)
                                            -> top N saved as status='found'

Freshness is hour-granular (--hours 24 = "past 1 day"); sources provide unix
timestamps where available, dates otherwise. Dedupe keys on the canonical URL
first, then on (company, normalized-title) so the same role from a feed and a
board API counts once.
"""

from __future__ import annotations

import re
import time
from datetime import date

from . import ats, boards, feeds, profiles, scoring, tracker

# Titles that are never a fit for an entry-level SWE/ML/Data search, regardless
# of source. Seniority gating only applies to board-API results (the new-grad
# feed is already level-filtered).
_SENIOR = re.compile(
    r"\b(senior|staff|principal|sr\.?|lead|director|head of|manager|vp|"
    r"distinguished|fellow|intern(ship)?)\b", re.I)


def _profile_for_title(title: str) -> str | None:
    """Map a raw posting title to a master-resume profile (None = not relevant)."""
    if feeds._TITLE_NO.search(title) or not feeds._TITLE_OK.search(title):
        return None
    if feeds._DATA_ENG.search(title):
        return "data_engineer"
    if re.search(r"machine learning|\bml\b|\bai\b|deep learning|llm|data scien|"
                 r"computer vision|nlp|research (scientist|engineer)", title, re.I):
        return "ml_ai"
    return "sde"


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def _dedupe(jobs: list[dict]) -> list[dict]:
    seen_url: set[str] = set()
    seen_pair: set[tuple[str, str]] = set()
    out = []
    for j in jobs:
        url = (j.get("url") or "").split("?")[0].rstrip("/")
        pair = (j["company"].lower().strip(), _norm_title(j["role"]))
        if (url and url in seen_url) or pair in seen_pair:
            continue
        if url:
            seen_url.add(url)
        seen_pair.add(pair)
        out.append(j)
    return out


def gather(hours: int, *, profile: str | None = None,
           include_feeds: bool = True, include_boards: bool = True,
           verbose: bool = True, now_ts: int | None = None) -> dict:
    """Collect, filter, and rank fresh roles. Returns
    {"jobs": ranked, "stats": {...}, "errors": [...]}  — does NOT save."""
    now = now_ts or int(time.time())
    cutoff = now - hours * 3600
    today = date.today().isoformat()
    raw: list[dict] = []
    errors: list[str] = []
    stats: dict[str, int] = {}

    # --- GitHub curated feeds (already level- and category-filtered) ----------
    if include_feeds:
        days = max(1, -(-hours // 24))  # ceil
        for name in feeds.FEEDS:
            try:
                listings = feeds.fetch_feed(name)
                fresh = feeds.fresh_roles(listings, days, today_ts=now)
                for r in fresh:
                    r["seniority_checked"] = True  # feed is new-grad only
                raw.extend(fresh)
                stats[f"feed:{name}"] = len(fresh)
                if verbose:
                    print(f"  feed {name:<22} {len(fresh):>4} fresh roles")
            except Exception as e:  # network/parse — fail soft per source
                errors.append(f"feed {name}: {e}")

    # --- ATS board APIs for watchlist companies -------------------------------
    if include_boards:
        bjobs, berrs = boards.fetch_watchlist_jobs(verbose=verbose)
        errors.extend(berrs)
        kept = 0
        for j in bjobs:
            if j.get("posted_ts", 0) and j["posted_ts"] < cutoff:
                continue
            if not j.get("posted_ts") and j.get("posted_date", "") < (
                    date.fromtimestamp(cutoff).isoformat()):
                continue
            prof = _profile_for_title(j["role"])
            if prof is None or _SENIOR.search(j["role"]):
                continue
            if not feeds._is_usa([j.get("locations", "")]):
                continue
            j["profile"] = prof
            raw.append(j)
            kept += 1
        stats["boards"] = kept
        if verbose:
            print(f"  boards: {kept} fresh, relevant postings")

    # --- shared filters --------------------------------------------------------
    exclude = feeds._load_exclude_companies()
    jobs = []
    for j in _dedupe(raw):
        if any(ex in j["company"].lower() for ex in exclude):
            continue
        if profile and j.get("profile") != profile:
            continue
        jobs.append(j)

    # --- match + rank -----------------------------------------------------------
    masters = {p: profiles.read_master_for(p) for p in {j["profile"] for j in jobs}}
    for j in jobs:
        text = f"{j['role']} {j.get('locations', '')}"
        j["match"] = ats.ats_score(text, masters[j["profile"]])["score"]
        comp = scoring.composite(ats_score=j["match"], posted_date=j["posted_date"],
                                 today=today)
        j["found_score"] = comp["score"]
    jobs.sort(key=lambda j: (j.get("posted_ts") or 0, j["found_score"] or 0,
                             j["match"]), reverse=True)

    stats["total_after_filters"] = len(jobs)
    return {"jobs": jobs, "stats": stats, "errors": errors}


def discover(hours: int = 24, target: int = 100, *, profile: str | None = None,
             save: bool = True, verbose: bool = True, refresh: bool = False) -> list[dict]:
    """The `discover` command body: gather + take top `target` + record as found.

    Caches the gathered shortlist for the day (keyed by hours+profile) so a re-run —
    e.g. after a mid-pipeline failure — reuses it instead of re-sweeping every source.
    Pass refresh=True to force a fresh sweep.
    """
    from . import finder

    cache_key = f"discover-{hours}-{profile or 'auto'}"
    today = date.today().isoformat()
    jobs = None if refresh else finder.get_cached(cache_key, profile, today)
    if jobs is None:
        result = gather(hours, profile=profile, verbose=verbose)
        jobs = result["jobs"]
        finder.put_cache(cache_key, profile, today, jobs)
        if verbose:
            for e in result["errors"]:
                print(f"  ⚠ {e}")
    elif verbose:
        print(f"Using today's cached discovery: {len(jobs)} roles "
              "(--refresh to re-sweep).")
    shortlist = jobs[:target]
    if save:
        existing_urls = {a.get("url") for a in tracker.list_applications()}
        for j in shortlist:
            if j["url"] in existing_urls:
                continue  # already tracked — don't duplicate rows
            tracker.save_application(
                company=j["company"], role=j["role"], url=j["url"], status="found",
                match_score=j["match"], source=j.get("source", "feed"),
                posted_date=j["posted_date"], profile=j["profile"],
            )
    if verbose:
        print(f"\nDiscovered {len(jobs)} fresh roles (past {hours}h); "
              f"kept top {len(shortlist)}.")
    return shortlist
