"""Source: ScoutBetter (your own job site / saved-search API).

A template for pulling from a personal/3rd-party endpoint that returns JSON. It's
DISABLED until you point it at your endpoint in config/settings.json and map its fields
to the normalized shape — no scraping guesswork, just declare where the data is:

    "scoutbetter": {
      "enabled": true,
      "url": "https://scoutbetter.example.com/api/jobs?fresh=24h",
      "headers": {"Authorization": "Bearer <token>"},   // optional
      "items_path": "data.jobs",        // dotted path to the list in the response (or "")
      "map": {                           // your field name -> normalized field
        "company": "company_name",
        "role": "title",
        "url": "apply_url",
        "posted_date": "posted_at",      // ISO date/datetime; posted_ts derived from it
        "locations": "location"
      }
    }

Once configured it behaves exactly like the other sources (discover applies the same
freshness/US/profile/ranking). If ScoutBetter exposes RSS or HTML instead of JSON,
clone this file and swap the parse step — that's the whole point of the source plugin.
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone

from . import Source, register
from .. import config


def _dig(obj, dotted: str):
    if not dotted:
        return obj
    for key in dotted.split("."):
        if isinstance(obj, dict):
            obj = obj.get(key)
        else:
            return None
    return obj


def _iso_ts(value) -> tuple[str, int]:
    s = str(value or "").strip()
    if not s:
        return "", 0
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.date().isoformat(), int(dt.timestamp())
    except ValueError:
        return s[:10], 0


class ScoutBetterSource(Source):
    name = "scoutbetter"
    keywords = ("scout", "scoutbetter")
    description = "Personal ScoutBetter endpoint (configure url + field map in settings.json)"

    def _cfg(self) -> dict:
        c = config._settings().get("scoutbetter")
        return c if isinstance(c, dict) else {}

    def available(self) -> bool:
        c = self._cfg()
        return bool(c.get("enabled") and c.get("url"))

    def fetch(self, hours, *, profile=None, verbose=True):
        cfg = self._cfg()
        if not cfg.get("enabled") or not cfg.get("url"):
            return [], ["scoutbetter: disabled (set settings.json scoutbetter.url + enabled)"]
        fmap = cfg.get("map", {})
        try:
            req = urllib.request.Request(cfg["url"], headers=cfg.get("headers", {}))
            with urllib.request.urlopen(req, timeout=25) as r:  # noqa: S310
                payload = json.loads(r.read().decode())
        except Exception as e:
            return [], [f"scoutbetter: {e}"]
        items = _dig(payload, cfg.get("items_path", "")) or []
        if not isinstance(items, list):
            return [], ["scoutbetter: items_path did not resolve to a list"]
        jobs = []
        for it in items:
            posted_date, posted_ts = _iso_ts(it.get(fmap.get("posted_date", "posted_date")))
            jobs.append({
                "company": str(it.get(fmap.get("company", "company"), "")).strip(),
                "role": str(it.get(fmap.get("role", "role"), "")).strip(),
                "url": str(it.get(fmap.get("url", "url"), "")).strip(),
                "posted_date": posted_date, "posted_ts": posted_ts,
                "locations": str(it.get(fmap.get("locations", "locations"), "")).strip(),
                "source": "scoutbetter",
            })
        if verbose:
            print(f"  scoutbetter {len(jobs):>4} jobs")
        return jobs, []


register(ScoutBetterSource())
