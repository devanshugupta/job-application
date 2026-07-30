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
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

from .. import config

_UA = {"User-Agent": "job-applier-agent/2.0 (personal job search)"}
TIMEOUT = 20


MAX_PER_COMPANY = 1000  # safety cap on pagination so one giant board can't run away


def _get_json(url: str):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310
        return json.loads(r.read().decode())


def _post_json(url: str, body: dict):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={
        **_UA, "Content-Type": "application/json", "Accept": "application/json"})
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


def _strip_html(html: str) -> str:
    """Cheap HTML→text for JDs the ATS APIs return as HTML (Greenhouse/Ashby).
    Not a full parser — unescape entities, drop tags, collapse whitespace. Good
    enough for keyword matching and the tailor prompt; no browser, no deps."""
    import html as _html
    if not html:
        return ""
    # Greenhouse returns `content` entity-encoded (&lt;div&gt;…), so unescape first,
    # then strip the now-real tags.
    t = _html.unescape(html)
    t = re.sub(r"(?i)<\s*br\s*/?>", "\n", t)
    t = re.sub(r"(?i)</\s*(p|div|li|h[1-6]|tr)\s*>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = _html.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n\s*\n+", "\n\n", t)
    return t.strip()


def _job(company: str, role: str, url: str, posted, locations: str, source: str,
         jd_text: str = "") -> dict:
    date, ts = _iso(posted)
    job = {
        "company": company,
        "role": (role or "").strip(),
        "url": url or "",
        "posted_date": date,
        "posted_ts": ts,
        "locations": locations or "",
        "source": source,
    }
    # Capture the JD at discovery when the board API already returned it, so the
    # tailor step doesn't re-fetch (and can tailor even when the posting URL points
    # at a portal jd_fetch can't read).
    if jd_text and jd_text.strip():
        job["jd_text"] = jd_text.strip()
    return job


# ----------------------------------------------------------------- per-ATS fetchers

def fetch_greenhouse(company: str, token: str) -> list[dict]:
    # content=true returns every posting's full JD (HTML) in this one call, so we
    # capture the JD at discovery instead of re-fetching each URL later.
    data = _get_json(
        f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
    return [
        _job(company, j.get("title", ""), j.get("absolute_url", ""),
             j.get("first_published") or j.get("updated_at", ""),
             (j.get("location") or {}).get("name", ""), "greenhouse-api",
             _strip_html(j.get("content", "")))
        for j in data.get("jobs", [])
    ]


def fetch_lever(company: str, token: str) -> list[dict]:
    data = _get_json(f"https://api.lever.co/v0/postings/{token}?mode=json")
    return [
        _job(company, j.get("text", ""), j.get("hostedUrl", ""),
             j.get("createdAt", 0),
             (j.get("categories") or {}).get("location", ""), "lever-api",
             j.get("descriptionPlain") or _strip_html(j.get("description", "")))
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
                        j.get("publishedAt", ""), j.get("location", ""), "ashby-api",
                        j.get("descriptionPlain")
                        or _strip_html(j.get("descriptionHtml", ""))))
    return out


def fetch_smartrecruiters(company: str, token: str) -> list[dict]:
    """Paginated — SmartRecruiters caps each page at 100, so walk offset to totalFound."""
    out, offset = [], 0
    while offset < MAX_PER_COMPANY:
        data = _get_json("https://api.smartrecruiters.com/v1/companies/"
                         f"{token}/postings?limit=100&offset={offset}")
        page = data.get("content", [])
        for j in page:
            loc = j.get("location") or {}
            loc_s = ", ".join(filter(None, [loc.get("city", ""), loc.get("region", ""),
                                            loc.get("country", "")]))
            url = f"https://jobs.smartrecruiters.com/{token}/{j.get('id', '')}"
            out.append(_job(company, j.get("name", ""), url,
                            j.get("releasedDate", ""), loc_s, "smartrecruiters-api"))
        offset += 100
        if offset >= data.get("totalFound", 0) or not page:
            break
    return out


def fetch_workable(company: str, token: str) -> list[dict]:
    """Paginated — Workable widget returns `total`; page via offset until covered."""
    out, offset = [], 0
    while offset < MAX_PER_COMPANY:
        data = _get_json("https://apply.workable.com/api/v1/widget/accounts/"
                         f"{token}?details=false&offset={offset}")
        page = data.get("jobs", [])
        for j in page:
            loc_s = ", ".join(filter(None, [j.get("city", ""), j.get("state", ""),
                                            j.get("country", "")]))
            out.append(_job(company, j.get("title", ""), j.get("url", ""),
                            j.get("published_on", ""), loc_s, "workable-api"))
        offset += len(page)
        if not page or offset >= data.get("total", len(out)):
            break
    return out


def _workday_posted_iso(text: str) -> str:
    """Workday gives 'Posted Today' / 'Posted Yesterday' / 'Posted N Days Ago' / 'Posted
    30+ Days Ago'. Map to an ISO date relative to now ('' if unknown)."""
    from datetime import timedelta
    t = (text or "").lower()
    now = datetime.now(timezone.utc)
    if "today" in t:
        return now.date().isoformat()
    if "yesterday" in t:
        return (now - timedelta(days=1)).date().isoformat()
    m = re.search(r"(\d+)\+?\s*day", t)
    if m:
        return (now - timedelta(days=int(m.group(1)))).date().isoformat()
    return ""


def fetch_workday(company: str, host: str, site: str,
                  within_hours: int | None = None) -> list[dict]:
    """Workday career portal via the public CXS jobs search API (paginated).

    host = '<tenant>.wdN.myworkdayjobs.com', site = the career-site path segment
    (e.g. 'NVIDIAExternalCareerSite'). One POST per page of 20 until `total` is covered
    or, when `within_hours` is set (a daily pull), until we've paged past the freshness
    window — Workday returns newest-first, so once a couple of pages are entirely older
    than the window we stop early instead of dragging the whole 2000-job board.
    """
    from datetime import timedelta
    tenant = host.split(".")[0]
    api = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=within_hours)).date().isoformat() \
        if within_hours else None
    out, offset, total, stale_pages = [], 0, None, 0
    while offset < MAX_PER_COMPANY:
        data = _post_json(api, {"appliedFacets": {}, "limit": 20, "offset": offset,
                                "searchText": ""})
        page = data.get("jobPostings", [])
        if total is None:  # Workday reports `total` only on the FIRST page
            total = data.get("total", 0)
        page_dates = []
        for j in page:
            path = j.get("externalPath", "")
            pd = _workday_posted_iso(j.get("postedOn", ""))
            page_dates.append(pd)
            url = f"https://{host}/{site}{path}" if path else ""  # apply URL needs the site
            out.append(_job(company, j.get("title", ""), url, pd,
                            j.get("locationsText", ""), "workday-api"))
        offset += 20
        if not page or offset >= total:
            break
        if cutoff:  # early-stop once results fall outside the daily window
            stale_pages = stale_pages + 1 if all(d and d < cutoff for d in page_dates) else 0
            if stale_pages >= 2:
                break
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


def _is_api_company(c: dict) -> bool:
    """True if we can pull this company's portal via API: a token-based ATS, or Workday
    with host+site (or a parseable myworkdayjobs board URL)."""
    ats = c.get("ats")
    if ats in FETCHERS and c.get("token"):
        return True
    if ats == "workday" and (c.get("workday") or "myworkdayjobs.com" in (c.get("board") or "")):
        return True
    return False


def _workday_params(c: dict) -> tuple[str, str] | None:
    """Resolve (host, site) for a Workday company from explicit config or its board URL."""
    wd = c.get("workday")
    if isinstance(wd, dict) and wd.get("host") and wd.get("site"):
        return wd["host"], wd["site"]
    m = re.search(r"https?://([a-z0-9-]+\.wd\d+\.myworkdayjobs\.com)/(?:[a-z-]+/)?([^/?]+)",
                  c.get("board", ""), re.I)
    if m:
        return m.group(1), m.group(2)
    return None


def fetch_watchlist_jobs(companies: list[dict] | None = None, verbose: bool = True,
                         within_hours: int | None = None) -> tuple[list[dict], list[str]]:
    """Sweep every API-able watchlist company (token ATS + Workday). Returns (jobs, errors).

    `within_hours` lets the big paginated portals (Workday) early-stop at the freshness
    window instead of pulling their entire board; the single-call ATS APIs ignore it
    (they return everything in one request and discover filters after)."""
    companies = companies if companies is not None else watchlist_companies()
    jobs: list[dict] = []
    errors: list[str] = []
    for c in companies:
        ats = c.get("ats")
        if not _is_api_company(c):
            continue
        try:
            if ats == "workday":
                params = _workday_params(c)
                if not params:
                    errors.append(f"{c['name']} (workday): need workday.host+site or a "
                                  "myworkdayjobs board URL")
                    continue
                found = fetch_workday(c["name"], *params, within_hours=within_hours)
            else:
                found = FETCHERS[ats](c["name"], c["token"])
            jobs.extend(found)
            if verbose:
                print(f"  {c['name']:<16} {ats:<15} {len(found):>4} postings")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, KeyError, OSError) as e:
            errors.append(f"{c['name']} ({ats}): {e}")
            if verbose:
                print(f"  {c['name']:<16} {ats:<15} ERROR: {e}")
    return jobs, errors
