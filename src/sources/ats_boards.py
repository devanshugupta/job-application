"""Source: company ATS APIs (Greenhouse/Lever/Ashby/SmartRecruiters/Workable).

Sweeps every config/watchlist.json company that has an `ats`+`token`, hitting its
public JSON API once and returning its entire live job list. Thin wrapper over
tools/boards.py (the per-ATS fetchers)  this module just adapts it to the Source
interface and registers it.
"""

from __future__ import annotations

from . import Source, register
from ..tools import boards


class AtsBoardsSource(Source):
    name = "ats_boards"
    keywords = ("ats", "boards", "greenhouse", "lever", "ashby")
    description = "Public ATS APIs for watchlist companies (token-tagged in watchlist.json)"

    def available(self) -> bool:
        return any(boards._is_api_company(c) for c in boards.watchlist_companies())

    def fetch(self, hours, *, profile=None, verbose=True):
        # pass the window so Workday early-stops at the freshness boundary
        jobs, errors = boards.fetch_watchlist_jobs(verbose=verbose, within_hours=hours)
        # ATS titles aren't pre-level-filtered, so leave seniority_checked unset
        # (discover applies its seniority + profile gates). source name already set.
        return jobs, errors


register(AtsBoardsSource())
