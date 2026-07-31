"""Source: ScoutBetter  a public, paginated jobs API (no login required).

ScoutBetter's web app is auth-gated, but its backend API is public and far richer than
scraping the page: 318k+ US jobs, hourly-fresh, with a real `posted_at`, the full JD
(`description`), location, years-of-experience, an h1b_sponsorship flag, and  via the
per-job detail endpoint  the real apply URL on the company's ATS.

    list:   GET .../api/v1/jobs/?market=US&ordering=-posted_at&search=<q>&limit=&offset=
    detail: GET .../api/v1/jobs/<id>/   -> adds `job_url` (real ATS link) + full description

We pull the list newest-first per search term, stop at the freshness window, then resolve
each kept job's real `job_url` from the detail endpoint (threaded, capped) so the rest of
the pipeline (dedupe, apply, jd_fetch) works on a normal ATS URL. Tunable via
config/settings.json {"scoutbetter": {...}}; sensible defaults need no config.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import Source, register
from .. import config

API = "https://scoutbetter-production-webapp.azurewebsites.net/api/v1/jobs"
_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
       "Accept": "application/json"}
DEFAULT_SEARCHES = ["software engineer", "machine learning engineer", "data engineer"]


def _get(url: str, timeout: int = 25):
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(url, headers=_UA), timeout=timeout).read())


def _iso_ts(s: str) -> tuple[str, int]:
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.date().isoformat(), int(dt.timestamp())
    except (ValueError, TypeError):
        return "", 0


def _strip_html(raw: str) -> str:
    import html as _html
    import re
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw or "")
    raw = re.sub(r"(?i)<(br|/p|/div|/li|/h[1-6])[^>]*>", "\n", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = _html.unescape(raw)
    raw = re.sub(r"[ \t]+", " ", raw)
    return re.sub(r"\n\s*\n+", "\n\n", raw).strip()


def _detail(job_id) -> tuple[str | None, str]:
    """From the detail endpoint, return (real_apply_url, jd_text). The JD is fetched
    here at DISCOVERY time (it comes free in the same call that resolves the apply URL),
    so a ScoutBetter job is tailorable immediately and never needs a later re-fetch."""
    try:
        d = _get(f"{API}/{job_id}/")
        jd = _strip_html(d.get("description") or "") or (d.get("job_overview") or "")
        return (d.get("job_url") or None), jd
    except Exception:
        return None, ""


def _collect(term: str, *, market: str, cutoff_ts: int, h1b: bool,
             page_size: int, max_jobs: int, kept: dict, errors: list) -> None:
    """Page one search term newest-first into `kept` (id -> normalized job), stopping at
    the freshness cutoff or max_jobs. `h1b=True` adds the API's h1b_sponsorship filter."""
    offset, stop = 0, False
    while not stop and offset < 1000 and len(kept) < max_jobs:
        params = {"market": market, "ordering": "-posted_at", "search": term,
                  "limit": page_size, "offset": offset}
        if h1b:
            params["h1b_sponsorship"] = "true"
        try:
            page = _get(f"{API}/?{urllib.parse.urlencode(params)}").get("results", [])
        except Exception as e:
            errors.append(f"scoutbetter '{term}' @{offset}: {e}")
            return
        if not page:
            return
        for j in page:
            pd, ts = _iso_ts(j.get("posted_at"))
            if ts and ts < cutoff_ts:            # newest-first -> the rest are older
                stop = True
                break
            jid = j.get("id")
            if jid in kept:
                continue
            kept[jid] = {
                "company": (j.get("company") or {}).get("name", ""),
                "role": j.get("title", ""), "url": "",
                "posted_date": pd, "posted_ts": ts,
                "locations": j.get("location", ""),
                "yoe": j.get("yoe"), "salary_min": j.get("salary_min"),
                "salary_max": j.get("salary_max"), "work_mode": j.get("work_mode"),
                "source": "scoutbetter", "_id": jid,
                "_overview": j.get("job_overview", ""),
            }
        offset += page_size


def _resolve(items: list[dict], *, keep_all: bool = False) -> list[dict]:
    """Resolve each job's real apply URL AND full JD from the detail endpoint (threaded).
    The JD is captured here, at discovery  never deferred to tailor time. By default
    keeps only jobs with a real apply link; keep_all=True keeps every job (for browsing)."""
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=8) as ex:
        details = list(ex.map(lambda it: _detail(it["_id"]), items))
    out = []
    for it, (url, jd) in zip(items, details):
        it.pop("_id", None)
        it["jd_text"] = jd or it.pop("_overview", "") or ""
        it.pop("_overview", None)
        it["url"] = url or f"https://scoutbetter.jobs/jobs/{it.get('posted_ts')}"
        if url or keep_all:
            out.append(it)
    return out


def search(term: str, *, hours: int = 168, h1b: bool = False, limit: int = 25,
           market: str = "US") -> list[dict]:
    """Reusable ScoutBetter query: newest-first jobs matching `term` within `hours`,
    optionally H1B-sponsorship only. Returns up to `limit` normalized job dicts with the
    real apply URL and full JD already attached. This is the single entry point for
    browsing/pulling ScoutBetter  CLI and discovery both use it, so no throwaway scripts."""
    cutoff = int(datetime.now(timezone.utc).timestamp()) - hours * 3600
    kept: dict[int, dict] = {}
    errors: list[str] = []
    _collect(term, market=market, cutoff_ts=cutoff, h1b=h1b,
             page_size=min(50, max(10, limit)), max_jobs=limit, kept=kept, errors=errors)
    return _resolve(list(kept.values()), keep_all=True)[:limit]


class ScoutBetterSource(Source):
    name = "scoutbetter"
    keywords = ("scout", "scoutbetter", "sb")
    description = "ScoutBetter public jobs API (no login; recency-sorted, real apply URLs)"

    def _cfg(self) -> dict:
        c = config._settings().get("scoutbetter")
        return c if isinstance(c, dict) else {}

    def available(self) -> bool:
        # public API  on by default; set settings.json scoutbetter.enabled=false to disable
        return self._cfg().get("enabled", True)

    def fetch(self, hours, *, profile=None, verbose=True):
        cfg = self._cfg()
        market = cfg.get("market", "US")
        searches = cfg.get("searches", DEFAULT_SEARCHES)
        page_size = int(cfg.get("page_size", 50))
        max_jobs = int(cfg.get("max_jobs", 120))
        h1b = bool(cfg.get("h1b_only", False))
        cutoff = int(datetime.now(timezone.utc).timestamp()) - hours * 3600
        kept: dict[int, dict] = {}
        errors: list[str] = []
        for term in searches:
            if len(kept) >= max_jobs:
                break
            _collect(term, market=market, cutoff_ts=cutoff, h1b=h1b,
                     page_size=page_size, max_jobs=max_jobs, kept=kept, errors=errors)
            if verbose:
                print(f"  scoutbetter '{term[:22]:<22}' kept {len(kept)} (cum.)")
        out = _resolve(list(kept.values()))
        if verbose:
            print(f"  scoutbetter resolved {len(out)}/{len(kept)} apply URLs")
        return out, errors


register(ScoutBetterSource())
