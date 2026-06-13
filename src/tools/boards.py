"""Public ATS board APIs — deterministic discovery, no scraping, no LLM.

Greenhouse, Lever, Ashby, SmartRecruiters, and Workable all expose free, public,
unauthenticated JSON endpoints for a company's live postings — with real URLs and
trustworthy timestamps. Hitting these is faster, cheaper, and far more reliable
than crawling career pages with a browser agent, and it's exactly what the boards
publish them for. One GET per company.

Each fetcher returns normalized job dicts:
    {company, role, url, posted_date (ISO), posted_ts (unix), locations, source}

Companies come from config/watchlist.json entries carrying "ats" + "token":
    {"name": "Stripe", "ats": "greenhouse", "token": "stripe", ...}
Entries without ats/token are skipped here (they remain agent-crawl targets).

All fetchers fail soft: a company whose endpoint errors is reported in the
returned ``errors`` list, never raised — one bad token must not kill a run.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

from .. import config

_UA = {"User-Agent": "job-applier-agent/2.0 (personal job search)"}
TIMEOUT = 20


def _get_json(url: str):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310
        return json.loads(r.read().decode())


def _iso(ts_or_str) -> tuple[str, int]:
    """Normalize a unix-ms / unix-s / ISO string to ('YYYY-MM-DD', unix_seconds)."""
    if isinstance(ts_or_str, (int, float)):
        ts = ts_or_str / 1000 if ts_or_str > 1e12 else ts_or_str
        dt = datetime.fromtimestamp(ts, timezone.utc)
        return dt.date().isoformat(), int(ts)
    s = str(ts_or_str or "").strip()
    if not s:
        return "", 0
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.date().isoformat(), int(dt.timestamp())
    except ValueError:
        return s[:10], 0


def _job(company: str, role: str, url: str, posted, locations: str, source: str) -> dict:
    date, ts = _iso(posted)
    return {
        "company": company,
        "role": (role or "").strip(),
        "url": url or "",
        "posted_date": date,
        "posted_ts": ts,
        "locations": locations or "",
        "source": source,
    }


# ----------------------------------------------------------------- per-ATS fetchers

def fetch_greenhouse(company: str, token: str) -> list[dict]:
    data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs")
    return [
        _job(company, j.get("title", ""), j.get("absolute_url", ""),
             j.get("first_published") or j.get("updated_at", ""),
             (j.get("location") or {}).get("name", ""), "greenhouse-api")
        for j in data.get("jobs", [])
    ]


def fetch_lever(company: str, token: str) -> list[dict]:
    data = _get_json(f"https://api.lever.co/v0/postings/{token}?mode=json")
    return [
        _job(company, j.get("text", ""), j.get("hostedUrl", ""),
             j.get("createdAt", 0),
             (j.get("categories") or {}).get("location", ""), "lever-api")
        for j in data
    ]


def fetch_ashby(company: str, token: str) -> list[dict]:
    data = _get_json(
        f"https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=false")
    out = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        out.append(_job(company, j.get("title", ""),
                        j.get("jobUrl") or j.get("applyUrl", ""),
                        j.get("publishedAt", ""), j.get("location", ""), "ashby-api"))
    return out


def fetch_smartrecruiters(company: str, token: str) -> list[dict]:
    data = _get_json(f"https://api.smartrecruiters.com/v1/companies/{token}/postings?limit=100")
    out = []
    for j in data.get("content", []):
        loc = j.get("location") or {}
        loc_s = ", ".join(filter(None, [loc.get("city", ""), loc.get("region", ""),
                                        loc.get("country", "")]))
        url = f"https://jobs.smartrecruiters.com/{token}/{j.get('id', '')}"
        out.append(_job(company, j.get("name", ""), url,
                        j.get("releasedDate", ""), loc_s, "smartrecruiters-api"))
    return out


def fetch_workable(company: str, token: str) -> list[dict]:
    data = _get_json(
        f"https://apply.workable.com/api/v1/widget/accounts/{token}?details=false")
    out = []
    for j in data.get("jobs", []):
        loc_s = ", ".join(filter(None, [j.get("city", ""), j.get("state", ""),
                                        j.get("country", "")]))
        out.append(_job(company, j.get("title", ""), j.get("url", ""),
                        j.get("published_on", ""), loc_s, "workable-api"))
    return out


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "smartrecruiters": fetch_smartrecruiters,
    "workable": fetch_workable,
}


# ----------------------------------------------------------------- watchlist sweep

def watchlist_companies() -> list[dict]:
    if not config.WATCHLIST_PATH.exists():
        return []
    data = json.loads(config.WATCHLIST_PATH.read_text())
    return data.get("companies", [])


def fetch_watchlist_jobs(companies: list[dict] | None = None,
                         verbose: bool = True) -> tuple[list[dict], list[str]]:
    """Sweep every API-able watchlist company. Returns (jobs, errors)."""
    companies = companies if companies is not None else watchlist_companies()
    jobs: list[dict] = []
    errors: list[str] = []
    for c in companies:
        ats, token = c.get("ats"), c.get("token")
        if not ats or not token or ats not in FETCHERS:
            continue
        try:
            found = FETCHERS[ats](c["name"], token)
            jobs.extend(found)
            if verbose:
                print(f"  {c['name']:<16} {ats:<15} {len(found):>4} postings")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, KeyError, OSError) as e:
            errors.append(f"{c['name']} ({ats}/{token}): {e}")
            if verbose:
                print(f"  {c['name']:<16} {ats:<15} ERROR: {e}")
    return jobs, errors
