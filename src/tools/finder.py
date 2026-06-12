"""Job finder support — freshness gating + daily cache.

The finder AGENT does the crawling (via the browser tool) over ATS boards
(Greenhouse/Lever/Ashby/Workday), company career pages, and curated GitHub "fresh jobs"
repos. This module holds the deterministic pieces around it:

- A **daily local cache** (`data/job_cache.json`) so we crawl a given query at most once
  per day — saves tokens and avoids hammering sites (anti-flagging). `--refresh` bypasses.
- A **freshness gate**: keep only roles whose posted date (read on the REAL company page,
  never LinkedIn) is within N days. No trustworthy date → "unverified", excluded by default.

The two ranking signals that matter most: recency, and match of the candidate's ORIGINAL
master resume to the role (computed by the caller via ats.ats_score against the chosen
profile master).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
from datetime import datetime, timedelta

CACHE_PATH = pathlib.Path("data/job_cache.json")
MAX_DAYS = 7  # hard ceiling on freshness window


def _cache_key(query: str, profile: str | None) -> str:
    raw = f"{query.strip().lower()}|{profile or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {}


def get_cached(query: str, profile: str | None, today: str) -> list | None:
    """Return cached results for this query if they were crawled TODAY, else None.

    ``today`` is passed in (ISO date string) rather than read from the clock so callers
    control the date source (and tests stay deterministic).
    """
    entry = _load_cache().get(_cache_key(query, profile))
    if entry and entry.get("crawled_date") == today:
        return entry["results"]
    return None


def put_cache(query: str, profile: str | None, today: str, results: list) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cache = _load_cache()
    cache[_cache_key(query, profile)] = {
        "query": query,
        "profile": profile,
        "crawled_date": today,
        "results": results,
    }
    CACHE_PATH.write_text(json.dumps(cache, indent=2))


def is_fresh(posted_date: str | None, days: int, today: str) -> bool:
    """True if posted_date (ISO yyyy-mm-dd) is within `days` of `today`.

    Unknown/unverified dates are NOT fresh (excluded by default).
    """
    if not posted_date or posted_date == "unverified":
        return False
    try:
        posted = datetime.strptime(posted_date, "%Y-%m-%d").date()
        ref = datetime.strptime(today, "%Y-%m-%d").date()
    except ValueError:
        return False
    window = min(days, MAX_DAYS)
    return timedelta(0) <= (ref - posted) <= timedelta(days=window)


def rank(roles: list[dict]) -> list[dict]:
    """Rank RECENCY-FIRST, then by original-resume match.

    Order: fresh roles before non-fresh; within that, most-recently-posted first; then
    higher match_score. Each role dict carries: posted_date, is_fresh (bool),
    match_score (int). Unparseable/unverified dates sort oldest.
    """
    def key(r: dict):
        pd = r.get("posted_date") or ""
        date_rank = pd if re.match(r"\d{4}-\d{2}-\d{2}", pd) else "0000-00-00"
        return (r.get("is_fresh", False), date_rank, r.get("match_score", 0))

    return sorted(roles, key=key, reverse=True)
