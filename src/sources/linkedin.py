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


def _parse_cards(html: str, now: int) -> list[dict]:
    """Extract job cards from the guest endpoint's HTML fragment."""
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
        jobs.append({
            "company": re.sub(r"<[^>]+>", "", comp_m.group(1)).strip(),
            "role": re.sub(r"<[^>]+>", "", title_m.group(1)).strip(),
            "url": url_m.group(1).split("?")[0],
            "posted_date": posted_date, "posted_ts": posted_ts,
            "locations": (loc_m.group(1).strip() if loc_m else ""),
            "source": "linkedin",
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
        return jobs, errors


def _attach_jds(jobs: list[dict]) -> None:
    """Fill jd_text (in place) for each card from the guest JD endpoint, concurrently."""
    from concurrent.futures import ThreadPoolExecutor
    todo = [j for j in jobs if not (j.get("jd_text") or "").strip()]
    if not todo:
        return
    with ThreadPoolExecutor(max_workers=6) as ex:
        for j, jd in zip(todo, ex.map(lambda x: _jd(_job_id(x["url"])), todo)):
            j["jd_text"] = jd


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
    return out


register(LinkedInSource())
