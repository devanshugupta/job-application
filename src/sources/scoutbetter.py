"""Source: ScoutBetter — a public, paginated jobs API (no login required).

ScoutBetter's web app is auth-gated, but its backend API is public and far richer than
scraping the page: 318k+ US jobs, hourly-fresh, with a real `posted_at`, the full JD
(`description`), location, years-of-experience, an h1b_sponsorship flag, and — via the
per-job detail endpoint — the real apply URL on the company's ATS.

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


def _detail_url(job_id) -> str | None:
    """Resolve a job's real apply URL from the detail endpoint. None on failure."""
    try:
        d = _get(f"{API}/{job_id}/")
        return d.get("job_url") or None
    except Exception:
        return None


class ScoutBetterSource(Source):
    name = "scoutbetter"
    keywords = ("scout", "scoutbetter", "sb")
    description = "ScoutBetter public jobs API (no login; recency-sorted, real apply URLs)"

    def _cfg(self) -> dict:
        c = config._settings().get("scoutbetter")
        return c if isinstance(c, dict) else {}

    def available(self) -> bool:
        # public API — on by default; set settings.json scoutbetter.enabled=false to disable
        return self._cfg().get("enabled", True)

    def fetch(self, hours, *, profile=None, verbose=True):
        cfg = self._cfg()
        market = cfg.get("market", "US")
        searches = cfg.get("searches", DEFAULT_SEARCHES)
        page_size = int(cfg.get("page_size", 50))
        max_jobs = int(cfg.get("max_jobs", 120))     # cap kept jobs (bounds detail calls)
        now = int(datetime.now(timezone.utc).timestamp())
        cutoff = now - hours * 3600

        kept: dict[int, dict] = {}   # job_id -> normalized (dedupe across searches)
        errors: list[str] = []
        for term in searches:
            if len(kept) >= max_jobs:
                break
            offset, stop = 0, False
            while not stop and offset < 1000 and len(kept) < max_jobs:
                qs = urllib.parse.urlencode({
                    "market": market, "ordering": "-posted_at", "search": term,
                    "limit": page_size, "offset": offset})
                try:
                    page = _get(f"{API}/?{qs}").get("results", [])
                except Exception as e:
                    errors.append(f"scoutbetter '{term}' @{offset}: {e}")
                    break
                if not page:
                    break
                for j in page:
                    pd, ts = _iso_ts(j.get("posted_at"))
                    if ts and ts < cutoff:          # newest-first -> rest are older
                        stop = True
                        break
                    jid = j.get("id")
                    if jid in kept:
                        continue
                    kept[jid] = {
                        "company": (j.get("company") or {}).get("name", ""),
                        "role": j.get("title", ""),
                        "url": "",                  # filled from detail below
                        "posted_date": pd, "posted_ts": ts,
                        "locations": j.get("location", ""),
                        "source": "scoutbetter",
                        "_id": jid,
                        "_overview": j.get("job_overview", ""),
                    }
                offset += page_size
            if verbose:
                print(f"  scoutbetter '{term[:22]:<22}' kept {len(kept)} (cum.)")

        # resolve real apply URLs (threaded, bounded by max_jobs)
        items = list(kept.values())
        with ThreadPoolExecutor(max_workers=8) as ex:
            urls = list(ex.map(lambda it: _detail_url(it["_id"]), items))
        out = []
        for it, url in zip(items, urls):
            it.pop("_id", None); it.pop("_overview", None)
            it["url"] = url or f"https://scoutbetter.jobs/jobs/{it.get('posted_ts')}"
            if url:                                  # only keep jobs with a real apply link
                out.append(it)
        if verbose:
            print(f"  scoutbetter resolved {len(out)}/{len(items)} apply URLs")
        return out, errors


register(ScoutBetterSource())
