"""Source: company careers-page scraping via headless browser (opt-in, per-company).

The fallback for portals with no clean API (Google careers, Eightfold, Amazon, custom
sites). Uses the Chromium that Playwright already installed in the venv. Opt-in per
company: only watchlist entries carrying a `scrape` block are visited, so the browser
never runs for companies we can pull via API.

Watchlist config (config/watchlist.json):
    {"name": "Google", "scrape": {
        "url": "https://www.google.com/about/careers/applications/jobs/results/?sort_by=date&q=software+engineer",
        "wait": 5,                 # human-like seconds to dwell after load (default 5)
        "assume_recent": true,     # page is date-sorted but shows no per-card date ->
                                   # stamp results with today's date so they survive the
                                   # freshness window (use ONLY for a sorted-recent URL)
        "link_re": "/jobs/results/\\d+",   # optional: override the job-detail href pattern
        "max": 40                  # cap cards taken (default 40)
    }}

Politeness: a real UA, a randomized ~5s dwell, one slow scroll to trigger lazy-load, one
page per company. It extracts title / url / location / date best-effort from each job
card's container text; undated cards stay undated unless `assume_recent` is set.
"""

from __future__ import annotations

import random
import re
import time
from datetime import datetime, timedelta, timezone

from . import Source, register
from ..tools import boards

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
# default: hrefs that look like a job-detail page across common portals
_DEFAULT_LINK_RE = (r"/jobs?/\d|/job/|/jobs/results/\d|/details/\d|/postings?/|"
                    r"gh_jid=|[?&]pid=\d|/position/|/careers?/job")
# tokens that mark the end of a title / start of metadata in a card's flattened text
_NOISE = re.compile(r"\b(corporate_fare|place|bar_chart|Minimum qualifications|"
                    r"Apply now|Apply|Learn more|Save|Share)\b")
_MONTHS = ("january february march april may june july august september october "
           "november december").split()


def _parse_date(text: str, now: int) -> tuple[str, int]:
    """Best-effort posted date from a card's text. Returns ('', 0) if none found."""
    t = text.lower()
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        try:
            ts = int(datetime.strptime(m.group(1), "%Y-%m-%d")
                     .replace(tzinfo=timezone.utc).timestamp())
            return m.group(1), ts
        except ValueError:
            pass
    m = re.search(r"([a-z]+)\s+(\d{1,2}),?\s+(\d{4})", t)
    if m and m.group(1) in _MONTHS:
        mo = _MONTHS.index(m.group(1)) + 1
        iso = f"{int(m.group(3)):04d}-{mo:02d}-{int(m.group(2)):02d}"
        try:
            ts = int(datetime.strptime(iso, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
            return iso, ts
        except ValueError:
            pass
    if "today" in t:
        d = datetime.fromtimestamp(now, timezone.utc); return d.date().isoformat(), now
    if "yesterday" in t:
        d = datetime.fromtimestamp(now, timezone.utc) - timedelta(days=1)
        return d.date().isoformat(), int(d.timestamp())
    m = re.search(r"(\d+)\+?\s*(minute|hour|day|week|month)s?\s+ago", t)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {"minute": timedelta(minutes=n), "hour": timedelta(hours=n),
                 "day": timedelta(days=n),
                 "week": timedelta(weeks=n), "month": timedelta(days=30 * n)}[unit]
        d = datetime.fromtimestamp(now, timezone.utc) - delta
        return d.date().isoformat(), int(d.timestamp())
    return "", 0


def _title_and_location(link_text: str, ctx: str) -> tuple[str, str]:
    """Pull a clean title + location out of an anchor's text and its container text."""
    # An anchor may wrap the whole card (title\nlocation\nPosted …) — title is line 1.
    lines = [l.strip() for l in (link_text or "").splitlines() if l.strip()]
    title = lines[0] if lines else ""
    if len(title) < 6:  # icon-only link (Google etc.) — title is in the container text
        title = _NOISE.split(ctx, 1)[0].strip() if _NOISE.search(ctx) else ctx[:80].strip()
    loc = ""
    m = re.search(r"\bplace\s+(.+?)(?:\s+bar_chart|\s+Minimum|\s*;|\s*$)", ctx)
    if m:
        loc = m.group(1).strip()
    elif title and title in ctx:
        # generic card shape "Title Location Posted X ago" (Microsoft etc.): the chunk
        # between the title and the Posted marker is the location. Without this,
        # non-US roles would slip the US filter as "location unknown".
        m = re.search(re.escape(title) + r"\s*(.+?)\s+Posted\b", ctx)
        if m:
            loc = m.group(1).strip(" |·-")
    return title[:120], loc[:80]


def scrape_careers(company: str, cfg: dict, verbose: bool = True) -> list[dict]:
    """Open one careers URL, dwell ~human-like, and extract job cards. Never raises."""
    from playwright.sync_api import sync_playwright

    url = cfg["url"]
    wait = float(cfg.get("wait", 5))
    link_re = cfg.get("link_re", _DEFAULT_LINK_RE)
    cap = int(cfg.get("max", 40))
    now = int(time.time())
    today = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
    out: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(user_agent=_UA).new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=8_000)
            except Exception:
                pass
            time.sleep(random.uniform(wait, wait + 2.5))   # human-like dwell
            try:                                            # nudge lazy-loaded lists
                page.mouse.wheel(0, 2400)
                time.sleep(random.uniform(1.0, 2.0))
            except Exception:
                pass
            cards = page.eval_on_selector_all("a[href]", """(els, pat) => {
                const re = new RegExp(pat, 'i');
                const seen = new Set(); const res = [];
                for (const a of els) {
                    if (!re.test(a.href) || seen.has(a.href)) continue;
                    seen.add(a.href);
                    const c = a.closest('li,article,div[role=listitem],tr') || a.parentElement;
                    res.push({url: a.href.split('#')[0],
                              t: (a.innerText||'').trim(),
                              ctx: (c ? c.innerText : '').replace(/\\s+/g,' ').slice(0,260)});
                }
                return res;
            }""", link_re)
        except Exception as e:
            browser.close()
            raise RuntimeError(f"scrape failed: {e}")
        browser.close()

    for c in cards[:cap]:
        title, loc = _title_and_location(c.get("t", ""), c.get("ctx", ""))
        if len(title) < 4:
            continue
        pd, ts = _parse_date(c.get("ctx", ""), now)
        if not pd and cfg.get("assume_recent"):
            pd, ts = today, now      # date-sorted page w/o per-card dates -> treat as fresh
        out.append({"company": company, "role": title, "url": c["url"],
                    "posted_date": pd, "posted_ts": ts, "locations": loc,
                    "source": f"careers:{company.lower().replace(' ', '')}"})
    if verbose:
        print(f"  careers {company:<16} {len(out):>4} cards "
              f"({'dated' if any(j['posted_date'] for j in out) else 'undated→sort-order'})")
    return out


class CareersPageSource(Source):
    name = "careers_page"
    keywords = ("careers", "scrape", "browser")
    description = "Headless-browser scrape of company careers pages (opt-in via watchlist scrape block)"

    def _targets(self) -> list[dict]:
        return [c for c in boards.watchlist_companies() if isinstance(c.get("scrape"), dict)
                and c["scrape"].get("url")]

    def available(self) -> bool:
        return bool(self._targets())

    def fetch(self, hours, *, profile=None, verbose=True):
        jobs, errors = [], []
        for c in self._targets():
            try:
                jobs.extend(scrape_careers(c["name"], c["scrape"], verbose=verbose))
            except Exception as e:
                errors.append(f"careers {c['name']}: {e}")
                if verbose:
                    print(f"  careers {c['name']:<16} ERROR: {e}")
        return jobs, errors


register(CareersPageSource())
