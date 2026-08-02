"""Source: LinkedIn job search (OPT-IN, keyword-driven).

⚠️ Terms of Service: automated access to LinkedIn violates their User Agreement and can
get an account or IP restricted. This source is therefore DISABLED by default and uses
only LinkedIn's public, unauthenticated guest job-search endpoint (the same one that
backs the logged-out jobs page)  no login, no credentials. Enable it deliberately and
keep volume low. You own how you use it.

This is the FIRST keyword-driven source: unlike the ATS/feed sources (which pull whole
job lists), LinkedIn needs search terms. Configure them in config/settings.json:

    "linkedin": {
      "enabled": true,
      "searches": [
        {"keywords": "software engineer", "location": "United States"},
        {"keywords": "machine learning engineer", "location": "United States"}
      ],
      "pages": 2,            // 25 results/page; 2 -> ~50 per search
      "max_per_search": 60
    }

Returns the normalized job dict. Dates are relative on LinkedIn ("3 days ago"); we map
them to an approximate posted_ts so discover's freshness window still applies. Treat
LinkedIn-sourced URLs as DISCOVERY pointers  the apply step opens the real company page.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from . import Source, register
from .. import config

_GUEST = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
          "?keywords={kw}&location={loc}&start={start}")
# Public guest JD endpoint  returns the full description HTML with NO login, same ToS
# posture as the guest search above. Lets us capture jd_text at discovery.
_GUEST_JD = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}"
_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def _job_id(url: str) -> str:
    """The numeric posting id trailing a /jobs/view/<slug>-<id> URL ('' if absent)."""
    m = re.search(r"-(\d+)/?$", url or "")
    return m.group(1) if m else ""


def _strip(html: str) -> str:
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html or "")
    html = re.sub(r"(?i)<(br|/p|/div|/li|/h[1-6]|/ul)[^>]*>", "\n", html)
    html = re.sub(r"<[^>]+>", " ", html)
    import html as _h
    html = _h.unescape(html)
    html = re.sub(r"[ \t]+", " ", html)
    return re.sub(r"\n\s*\n+", "\n\n", html).strip()


def _jd(job_id: str) -> str:
    """Full JD text from the public guest jobPosting endpoint (no login). '' on failure."""
    if not job_id:
        return ""
    try:
        req = urllib.request.Request(_GUEST_JD.format(jid=job_id), headers=_UA)
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
            html = r.read().decode("utf-8", errors="replace")
    except Exception:
        return ""
    m = re.search(r'(?is)(show-more-less-html__markup|description__text).*?>(.*?)</div>', html)
    return _strip(m.group(2)) if m else ""


def _rel_to_ts(text: str, now: int) -> tuple[str, int]:
    """Map 'datetime=YYYY-MM-DD' or 'N days/hours ago' to (ISO, unix). ('',0) if unknown."""
    m = re.search(r'datetime="(\d{4}-\d{2}-\d{2})"', text)
    if m:
        try:
            ts = int(datetime.strptime(m.group(1), "%Y-%m-%d")
                     .replace(tzinfo=timezone.utc).timestamp())
            return m.group(1), ts
        except ValueError:
            pass
    m = re.search(r"(\d+)\s+(hour|day|week|month)s?\s+ago", text, re.I)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        delta = {"hour": timedelta(hours=n), "day": timedelta(days=n),
                 "week": timedelta(weeks=n), "month": timedelta(days=30 * n)}[unit]
        dt = datetime.fromtimestamp(now, timezone.utc) - delta
        return dt.date().isoformat(), int(dt.timestamp())
    return "", 0


_BENEFITS_TEXT = re.compile(r'job-posting-benefits__text">\s*(.*?)\s*<', re.S)


def _parse_cards(html: str, now: int) -> list[dict]:
    """Extract job cards from the guest endpoint's HTML fragment.

    Two fields beyond the basics, both confirmed present in the raw card markup (not
    documented anywhere, found by inspecting the actual response): LinkedIn itself marks
    a subset of cards `job-search-card__listdate--new` (vs the plain `--listdate` class
    every other card gets) -- that's LinkedIn's own "genuinely fresh" judgment, a
    stronger signal than our own relative-date parsing. And a `job-posting-benefits__text`
    chip carries "Be an early applicant" (low competition, real positive signal) or
    "Actively Hiring" (generic engagement noise, not discriminating) or an actual benefits
    list -- captured as `hiring_tag` so callers can use "Be an early applicant" and ignore
    the rest. Neither field exists at all for a JD-sparse card (both '' / False if absent).
    """
    jobs = []
    for card in re.split(r"<li>", html):
        url_m = re.search(r'href="(https://[^"]*?/jobs/view/[^"?]+)', card)
        title_m = re.search(r'base-search-card__title">\s*(.*?)\s*</h3>', card, re.S)
        comp_m = re.search(r'base-search-card__subtitle">\s*(?:<a[^>]*>)?\s*(.*?)\s*'
                           r'(?:</a>)?\s*</h4>', card, re.S)
        loc_m = re.search(r'job-search-card__location">\s*(.*?)\s*</span>', card, re.S)
        if not (url_m and title_m and comp_m):
            continue
        posted_date, posted_ts = _rel_to_ts(card, now)
        benefits_m = _BENEFITS_TEXT.search(card)
        jobs.append({
            "company": re.sub(r"<[^>]+>", "", comp_m.group(1)).strip(),
            "role": re.sub(r"<[^>]+>", "", title_m.group(1)).strip(),
            "url": url_m.group(1).split("?")[0],
            "posted_date": posted_date, "posted_ts": posted_ts,
            "locations": (loc_m.group(1).strip() if loc_m else ""),
            "source": "linkedin",
            "is_new": "job-search-card__listdate--new" in card,
            "hiring_tag": (re.sub(r"\s+", " ", benefits_m.group(1)).strip()
                          if benefits_m else ""),
        })
    return jobs


class LinkedInSource(Source):
    name = "linkedin"
    keywords = ("li", "linkedin")
    description = "LinkedIn guest job search (opt-in, keyword-driven, ToS-sensitive)"

    def _cfg(self) -> dict:
        c = config._settings().get("linkedin")
        return c if isinstance(c, dict) else {}

    def available(self) -> bool:
        c = self._cfg()
        return bool(c.get("enabled") and c.get("searches"))

    def fetch(self, hours, *, profile=None, verbose=True):
        cfg = self._cfg()
        if not cfg.get("enabled"):
            return [], ["linkedin: disabled (set settings.json linkedin.enabled=true)"]
        searches = cfg.get("searches", [])
        pages = int(cfg.get("pages", 2))
        cap = int(cfg.get("max_per_search", 60))
        now = int(time.time())
        jobs: list[dict] = []
        errors: list[str] = []
        for s in searches:
            kw = urllib.parse.quote(s.get("keywords", ""))
            loc = urllib.parse.quote(s.get("location", "United States"))
            got = 0
            for p in range(pages):
                url = _GUEST.format(kw=kw, loc=loc, start=p * 25)
                try:
                    req = urllib.request.Request(url, headers=_UA)
                    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
                        html = r.read().decode("utf-8", errors="replace")
                except Exception as e:  # 403/429 are common  fail soft
                    errors.append(f"linkedin '{s.get('keywords')}' p{p}: {e}")
                    break
                cards = _parse_cards(html, now)
                if not cards:
                    break
                jobs.extend(cards)
                got += len(cards)
                if got >= cap:
                    break
                time.sleep(1.5)  # be gentle
            if verbose:
                print(f"  linkedin '{s.get('keywords', '')[:24]:<24}' {got:>4} cards")
        _attach_jds(jobs)                       # capture JD at discovery (guest endpoint)
        jobs = _dedupe_near_duplicates(jobs)
        _flag_reposts(jobs, now - hours * 3600, verbose=verbose)
        return [j for j in jobs if not j.get("repost")], errors


def _attach_jds(jobs: list[dict]) -> None:
    """Fill jd_text (in place) for each card from the guest JD endpoint, concurrently."""
    from concurrent.futures import ThreadPoolExecutor
    todo = [j for j in jobs if not (j.get("jd_text") or "").strip()]
    if not todo:
        return
    with ThreadPoolExecutor(max_workers=6) as ex:
        for j, jd in zip(todo, ex.map(lambda x: _jd(_job_id(x["url"])), todo)):
            j["jd_text"] = jd


_DUP_WORD = re.compile(r"[a-z0-9]+")
_DUP_THRESHOLD = 0.85   # word-overlap ratio above which two same-company JDs are one job


_LD_JSON = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
_ORGANIC_WINDOW_S = 30 * 86400   # organic posts: validThrough = datePosted + exactly 30d
_WINDOW_TOL_S = 6 * 3600


def _is_repost(url: str) -> bool | None:
    """True if the posting page's JSON-LD says this listing is a repost.

    The guest card feed bumps a repost's relative date ('4 hours ago'), and the JSON-LD
    ``datePosted`` is bumped with it  but ``validThrough`` stays anchored to the
    ORIGINAL posting: an organic post carries validThrough = datePosted + exactly 30
    days (same time-of-day), while reposts show 60+ day windows with a mismatched
    clock. Verified empirically on live postings (Paramount/Obin/Archil reposts vs an
    organic same-day post). None = couldn't determine (fetch/parse failure)  fail
    open, don't drop. One full-page fetch (~330KB); call only for cards already inside
    the freshness window."""
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
            html = r.read().decode("utf-8", errors="replace")
        m = _LD_JSON.search(html)
        d = json.loads(m.group(1))
        dp = datetime.fromisoformat(d["datePosted"].replace("Z", "+00:00"))
        vt = datetime.fromisoformat(d["validThrough"].replace("Z", "+00:00"))
        return abs((vt - dp).total_seconds() - _ORGANIC_WINDOW_S) > _WINDOW_TOL_S
    except Exception:
        return None


def _flag_reposts(jobs: list[dict], cutoff_ts: int, *, verbose: bool = True) -> None:
    """Mark repost=True (in place) on freshness-window cards whose posting page shows a
    reset listing clock. Only cards that would survive the freshness cut are checked
    stale cards get dropped downstream anyway, so no page fetch is spent on them."""
    fresh = [j for j in jobs if (j.get("posted_ts") or 0) >= cutoff_ts]
    dropped = 0
    for j in fresh:
        if _is_repost(j["url"]):
            j["repost"] = True
            dropped += 1
        time.sleep(1.0)  # be gentle: one page per fresh card
    if verbose and fresh:
        print(f"  linkedin repost check: {dropped}/{len(fresh)} fresh cards were reposts")


def _dedupe_near_duplicates(jobs: list[dict]) -> list[dict]:
    """Collapse the same underlying job surfacing more than once in one batch  common
    on LinkedIn (re-listed under a slightly different title, or picked up by more than
    one of our search terms, each carrying its own job id/url). Two postings only ever
    count as duplicates when they share a company AND their JD word-overlap clears
    ``_DUP_THRESHOLD``  cross-company overlap is never compared (two different
    employers' JDs sharing generic boilerplate is coincidence, not a duplicate), and a
    same-company but genuinely different role won't share 85%+ of its JD text. Keeps
    the FIRST occurrence of each cluster, in input order."""
    kept: list[dict] = []
    seen_by_company: dict[str, list[set[str]]] = {}
    for j in jobs:
        company = (j.get("company") or "").strip().lower()
        words = set(_DUP_WORD.findall((j.get("jd_text") or "").lower()))
        bucket = seen_by_company.setdefault(company, [])
        if words and any(other and len(words & other) / min(len(words), len(other)) >= _DUP_THRESHOLD
                        for other in bucket):
            continue
        if words:  # empty word-sets (no JD captured) can't identify a duplicate
            bucket.append(words)
        kept.append(j)
    return kept


def search(keywords: str, *, location: str = "United States", hours: int = 168,
           pages: int = 2, limit: int = 25) -> list[dict]:
    """Reusable LinkedIn guest search: newest cards for `keywords`, with jd_text attached
    from the guest JD endpoint. ToS-sensitive  keep volume low. Returns normalized jobs."""
    now = int(time.time())
    cutoff = now - hours * 3600
    kw, loc = urllib.parse.quote(keywords), urllib.parse.quote(location)
    out: list[dict] = []
    for p in range(pages):
        try:
            req = urllib.request.Request(_GUEST.format(kw=kw, loc=loc, start=p * 25), headers=_UA)
            with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
                cards = _parse_cards(r.read().decode("utf-8", errors="replace"), now)
        except Exception:
            break
        if not cards:
            break
        out.extend(c for c in cards if not c["posted_ts"] or c["posted_ts"] >= cutoff)
        if len(out) >= limit:
            break
        time.sleep(1.5)
    out = out[:limit]
    _attach_jds(out)
    return _dedupe_near_duplicates(out)


register(LinkedInSource())
