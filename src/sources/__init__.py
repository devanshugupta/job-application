"""Job sources — pluggable, independent discovery backends.

Each source is a standalone module exposing one `Source` instance: given a freshness
window it returns normalized job dicts. `discover.py` pulls from whichever sources are
SELECTED (all available by default, or a subset by name) and merges the results — so
adding a new place to find jobs (LinkedIn, ScoutBetter, a new ATS, an RSS export) is a
new file here plus one registry line, with zero changes to the rest of the pipeline.

A source returns dicts in this normalized shape (the only contract):
    {
      "company": str, "role": str, "url": str,
      "posted_date": "YYYY-MM-DD" | "",      # "" if unknown
      "posted_ts": int,                       # unix seconds; 0 if unknown
      "locations": str,                       # comma-joined; "" if unknown
      "source": str,                          # this source's name (for the dashboard)
      # optional hints — discover fills these in if absent:
      "profile": str | None,                  # ml_ai|sde|data_engineer (else inferred)
      "seniority_checked": bool,              # True = skip discover's seniority gate
    }

Selecting sources:
    - default: every source whose `.available()` is True.
    - settings.json {"sources": ["ats_boards", "github_feed"]} or
      CLI --source ats_boards,linkedin  -> only those (by name OR keyword).
A source that needs config it doesn't have reports `available() == False` and is simply
skipped (never errors the run).
"""

from __future__ import annotations

from .. import config


class Source:
    """Base class for a job source. Subclass and set name/keywords, implement fetch()."""

    name: str = "source"
    keywords: tuple[str, ...] = ()       # aliases for --source selection
    description: str = ""

    def available(self) -> bool:
        """True if this source can run now (creds/config present). Default: always."""
        return True

    def fetch(self, hours: int, *, profile: str | None = None,
              verbose: bool = True) -> tuple[list[dict], list[str]]:
        """Return (jobs, errors). jobs use the normalized shape above. Must FAIL SOFT —
        return collected errors as strings, never raise, so one bad source can't kill a run."""
        raise NotImplementedError


# --- registry ---------------------------------------------------------------

_REGISTRY: dict[str, Source] = {}


def register(src: Source) -> Source:
    _REGISTRY[src.name] = src
    return src


def _load_builtins() -> None:
    if _REGISTRY:
        return
    from . import ats_boards, careers_page, github_feed, linkedin, scoutbetter  # noqa: F401


def all_sources() -> dict[str, Source]:
    _load_builtins()
    return dict(_REGISTRY)


def resolve(selectors: list[str] | None) -> list[Source]:
    """Pick sources to run.

    selectors=None -> settings.json 'sources' if set, else every AVAILABLE source.
    selectors given -> match each against a source name OR keyword (unknown names ignored
    with no error; selection bypasses the availability gate so you can force one on).
    """
    _load_builtins()
    if selectors is None:
        cfg = config._settings().get("sources")
        if isinstance(cfg, list):
            selectors = cfg
        else:
            return [s for s in _REGISTRY.values() if s.available()]
    chosen: list[Source] = []
    for sel in selectors:
        key = sel.strip().lower()
        for s in _REGISTRY.values():
            if (key == s.name or key in s.keywords) and s not in chosen:
                chosen.append(s)
    return chosen
