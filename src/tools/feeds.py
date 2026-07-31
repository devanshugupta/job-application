"""Curated job feeds  the PRIMARY discovery source.

Blind board-crawling is slow and the dates are unreliable (Amazon detail pages and
Greenhouse hide the post date). Community-maintained GitHub lists solve both: they
publish a structured, daily-updated JSON with trustworthy `date_posted` timestamps and
the real application URL. We consume those directly  one HTTP fetch, no scraping, no
rate-limiting  then apply the same freshness + relevance gating.

Default feed: SimplifyJobs/New-Grad-Positions (`.github/scripts/listings.json`), ~17k
entries, ~1.9k active, updated daily. Add siblings (internships, summer, experienced)
by appending to FEEDS.

Two layers of filtering, learned the hard way:
  1. CATEGORY allowlist  trust the feed's own category; keep only Software / AI-ML-Data.
     This drops Hardware, Quant, Product, Product Management, etc. outright.
  2. TITLE relevance  even within those buckets the lists include non-eng roles
     (technician, operator, analyst, PM, postdoc). Gate on the title too.
A role must pass BOTH to be kept.
"""

from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timezone

from .. import config

# name -> raw listings.json URL. Extend via config/settings.json {"feeds": {...}}.
FEEDS = config.feeds()

# Feed category (as published) -> our master-resume profile. Anything not here is
# DROPPED (Hardware, Hardware Engineering, Quant, Product, Product Management, ...).
# Note the feed lumps ALL data/ML/AI into one "AI/ML/Data" bucket, so for that bucket
# we refine by title (see _profile_for) into data_engineer vs ml_ai.
CATEGORY_TO_PROFILE = {
    "Software Engineering": "sde",
    "Software": "sde",
    "AI/ML/Data": "ml_ai",                      # refined by title below
    "Data Science, AI & Machine Learning": "ml_ai",
}

# Non-US country names/patterns  drop a role if ALL its locations match one of these.
_NON_US = re.compile(
    r"\b(canada|united kingdom|uk\b|england|scotland|australia|germany|india|ireland|"
    r"netherlands|france|singapore|poland|sweden|denmark|spain|italy|brazil|"
    r"romania|mexico|japan|china|israel|portugal|czech\w*|colombia|taiwan|korea|"
    r"philippines|vietnam|hungary|bulgaria|greece|finland|norway|switzerland|"
    r"austria|belgium|t[uü]rk\w*|united arab emirates|saudi arabia|argentina|chile|"
    r"ontario|british columbia|toronto|vancouver|calgary|montreal|ottawa|"
    r"london(?! ontario)|berlin|amsterdam|sydney|melbourne)\b",
    re.I,
)

# US signals  explicit state/country mentions or plain Remote (US companies default)
_US_OK = re.compile(
    r"\b(united states|usa|\bus\b|remote|"
    r"alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|"
    r"florida|georgia|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|"
    r"louisiana|maine|maryland|massachusetts|michigan|minnesota|mississippi|"
    r"missouri|montana|nebraska|nevada|new hampshire|new jersey|new mexico|"
    r"new york|north carolina|north dakota|ohio|oklahoma|oregon|pennsylvania|"
    r"rhode island|south carolina|south dakota|tennessee|texas|utah|vermont|"
    r"virginia|washington|west virginia|wisconsin|wyoming|"
    r"\b(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|"
    r"MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|"
    r"VA|WA|WV|WI|WY|DC)\b)\b",
    re.I,
)


def _is_usa(locations: list[str]) -> bool:
    """Return True if at least one location is US or Remote, and none are exclusively non-US."""
    locations = [loc for loc in locations if loc]  # sources may carry None/"" entries
    if not locations:
        return True   # no location info → assume US (most feed entries are US companies)
    for loc in locations:
        if _US_OK.search(loc):
            return True
    # No explicit US signal  drop only if there's a clear non-US country name
    for loc in locations:
        if not _NON_US.search(loc):
            return True   # ambiguous location, give benefit of doubt
    return False


# Title signals that a role in the AI/ML/Data bucket is really DATA ENGINEERING.
_DATA_ENG = re.compile(
    r"data engineer|data engineering|\betl\b|\belt\b|data pipeline|data platform|"
    r"business intelligence|\bbi\b|data warehouse|analytics engineer",
    re.I,
)

# Title must look like an engineering role...
_TITLE_OK = re.compile(
    r"engineer|developer|\bsde\b|software|machine learning|\bml\b|\bai\b|"
    r"data scien|data engineer|backend|front.?end|full.?stack|platform|infrastructure",
    re.I,
)
# ...and must NOT be an obvious non-software title that slipped into the bucket
# (incl. physical-engineering disciplines, which contain the word "engineer").
_TITLE_NO = re.compile(
    r"technician|operator|labeler|\banalyst\b|manager|instructional|postdoc|"
    r"\bsales\b|recruit|statistician|consultant|specialist|expert\b|"
    r"mechanical|electrical\b|civil\b|aerospace|structural|thermal|optical|"
    r"soft goods|supply chain|facilities|hvac|process engineer|"
    r"technical support|customer support|support engineer|help ?desk|it support",
    re.I,
)


def fetch_feed(name: str = "simplify-newgrad", timeout: int = 30) -> list[dict]:
    """Download and parse one feed's raw listings (no filtering)."""
    url = FEEDS[name]
    with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310 (trusted host)
        return json.loads(r.read().decode())


def _profile_for(entry: dict) -> str | None:
    """Map an entry to a profile via category allowlist + title gating. None = drop."""
    prof = CATEGORY_TO_PROFILE.get(entry.get("category", ""))
    if not prof:
        return None
    title = entry.get("title", "")
    if _TITLE_NO.search(title) or not _TITLE_OK.search(title):
        return None
    # The "AI/ML/Data" bucket mixes ML and data-engineering  split by title so each
    # role is scored against the right master (data_engineer vs ml_ai).
    if prof == "ml_ai" and _DATA_ENG.search(title):
        return "data_engineer"
    return prof


def _load_exclude_companies() -> list[str]:
    """Read exclude_companies from profile.json (lowercase). Returns [] on error."""
    try:
        data = json.loads(config.PROFILE_PATH.read_text())
        return [c.lower() for c in data.get("preferences", {}).get("exclude_companies", [])]
    except Exception:
        return []


def fresh_roles(listings: list[dict], days: int, today_ts: int | None = None) -> list[dict]:
    """Filter to active + visible + relevant + posted within `days`, recency-sorted.

    `today_ts` anchors the window (unix seconds). If None, anchor to the feed's newest
    `date_posted` (so we don't depend on the local clock and stay deterministic).
    Returns normalized dicts: company, role, url, posted_date (ISO), profile, locations.
    """
    active = [x for x in listings
              if x.get("active") and x.get("is_visible") and x.get("date_posted")]
    if not active:
        return []
    anchor = today_ts or max(x["date_posted"] for x in active)
    cut = anchor - days * 86400

    exclude = _load_exclude_companies()

    out: list[dict] = []
    for x in active:
        if x["date_posted"] < cut:
            continue
        prof = _profile_for(x)
        if not prof:
            continue
        if not _is_usa(x.get("locations") or []):
            continue
        company_lc = (x.get("company_name") or "").lower()
        if any(ex in company_lc for ex in exclude):
            continue
        out.append({
            "company": x.get("company_name", ""),
            "role": x.get("title", ""),
            "url": x.get("url", ""),
            "posted_date": datetime.fromtimestamp(
                x["date_posted"], timezone.utc).date().isoformat(),
            "_ts": x["date_posted"],
            "profile": prof,
            "locations": ", ".join(x.get("locations") or []),
            "sponsorship": x.get("sponsorship", ""),
        })
    out.sort(key=lambda r: r["_ts"], reverse=True)  # recency first
    return out
