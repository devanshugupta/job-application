"""Source: curated GitHub job feeds (SimplifyJobs New-Grad-Positions, etc.).

One HTTP GET per feed of a community-maintained listings.json  thousands of postings
with trustworthy dates and real URLs, already category/title/level filtered. Thin wrapper
over tools/feeds.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from . import Source, register
from ..tools import feeds


class GithubFeedSource(Source):
    name = "github_feed"
    keywords = ("feed", "github", "simplify", "simplifyjobs")
    description = "Curated GitHub new-grad feeds (SimplifyJobs)"

    def fetch(self, hours, *, profile=None, verbose=True):
        jobs: list[dict] = []
        errors: list[str] = []
        days = max(1, -(-hours // 24))  # ceil(hours/24); discover re-filters to the hour
        now = int(datetime.now(timezone.utc).timestamp())
        for name in feeds.FEEDS:
            try:
                fresh = feeds.fresh_roles(feeds.fetch_feed(name), days, today_ts=now)
                for r in fresh:
                    r["posted_ts"] = r.get("_ts", 0)        # normalize key name
                    r["source"] = f"github:{name}"
                    # NB: do NOT set seniority_checked  the new-grad feed still carries
                    # some dual-level "Principal/Staff/Senior" postings, so let discover's
                    # seniority gate drop those.
                jobs.extend(fresh)
                if verbose:
                    print(f"  github_feed {name:<18} {len(fresh):>4} fresh roles")
            except Exception as e:
                errors.append(f"github_feed {name}: {e}")
        return jobs, errors


register(GithubFeedSource())
