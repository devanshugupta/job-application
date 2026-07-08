"""Discovery orchestrator — find the top N fresh roles across every source, fast.

One deterministic pass, no LLM, no browser:

    GitHub feeds (SimplifyJobs etc.)  ──┐
                                        ├─> normalize -> dedupe -> filter
    ATS board APIs (watchlist)        ──┘   (freshness · US · title/seniority ·
                                             excluded companies)
                                            -> ATS-match vs master resume
                                            -> composite rank (recency+match)
                                            -> top N saved as status='found'

Freshness is hour-granular (--hours 24 = "past 1 day"); sources provide unix
timestamps where available, dates otherwise. Dedupe keys on the canonical URL
first, then on (company, normalized-title) so the same role from a feed and a
board API counts once.
"""

from __future__ import annotations

import re
import time
from datetime import date

from . import ats, boards, feeds, profiles, scoring, tracker

# Titles that are never a fit for an entry-level SWE/ML/Data search, regardless
# of source. Seniority gating only applies to board-API results (the new-grad
# feed is already level-filtered).
_SENIOR = re.compile(
    r"\b(senior|staff|principal|sr\.?|lead|director|head of|manager|vp|"
    r"distinguished|fellow|intern(ship)?)\b", re.I)


def _profile_for_title(title: str) -> str | None:
    """Map a raw posting title to a master-resume profile (None = not relevant)."""
    if feeds._TITLE_NO.search(title) or not feeds._TITLE_OK.search(title):
        return None
    if feeds._DATA_ENG.search(title):
        return "data_engineer"
    if re.search(r"machine learning|\bml\b|\bai\b|deep learning|llm|data scien|"
                 r"computer vision|nlp|research (scientist|engineer)", title, re.I):
        return "ml_ai"
    return "sde"


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def _dedupe(jobs: list[dict]) -> list[dict]:
    seen_url: set[str] = set()
    seen_pair: set[tuple[str, str]] = set()
    out = []
    for j in jobs:
        url = (j.get("url") or "").split("?")[0].rstrip("/")
        pair = (j["company"].lower().strip(), _norm_title(j["role"]))
        if (url and url in seen_url) or pair in seen_pair:
            continue
        if url:
            seen_url.add(url)
        seen_pair.add(pair)
        out.append(j)
    return out


def _is_fresh(job: dict, cutoff_ts: int, cutoff_date: str) -> bool:
    """A job is fresh if its timestamp (preferred) or date is within the window."""
    ts = job.get("posted_ts") or 0
    if ts:
        return ts >= cutoff_ts
    pd = job.get("posted_date") or ""
    return bool(pd) and pd >= cutoff_date  # unknown date -> not fresh (excluded)


def gather(hours: int, *, profile: str | None = None, sources: list[str] | None = None,
           verbose: bool = True, now_ts: int | None = None) -> dict:
    """Collect from the SELECTED sources, then filter + rank uniformly. Returns
    {"jobs": ranked, "stats": {...}, "errors": [...]}  — does NOT save.

    `sources` selects backends by name/keyword (None = all available / settings.json).
    Every source returns the normalized job shape; the freshness/US/title/seniority/
    profile gates and ranking below apply identically to all of them — so a new source
    (LinkedIn, ScoutBetter, a new ATS) needs no changes here.
    """
    from .. import sources as source_registry

    now = now_ts or int(time.time())
    cutoff_ts = now - hours * 3600
    cutoff_date = date.fromtimestamp(cutoff_ts).isoformat()
    today = date.today().isoformat()
    raw: list[dict] = []
    errors: list[str] = []
    stats: dict[str, int] = {}

    chosen = source_registry.resolve(sources)
    if verbose:
        print(f"sources: {', '.join(s.name for s in chosen) or '(none)'}")
    for src in chosen:
        try:
            jobs_s, errs_s = src.fetch(hours, profile=profile, verbose=verbose)
        except Exception as e:  # a source must never kill the run
            errors.append(f"{src.name}: {e}")
            continue
        errors.extend(errs_s)
        stats[src.name] = len(jobs_s)
        raw.extend(jobs_s)

    # --- unified filters (apply to every source identically) ------------------
    exclude = feeds._load_exclude_companies()
    jobs = []
    for j in _dedupe(raw):
        if not _is_fresh(j, cutoff_ts, cutoff_date):
            continue
        if not feeds._is_usa([j.get("locations") or ""]):
            continue
        if any(ex in j["company"].lower() for ex in exclude):
            continue
        # assign a profile if the source didn't, dropping non-relevant titles
        if not j.get("profile"):
            prof = _profile_for_title(j["role"])
            if prof is None:
                continue
            j["profile"] = prof
        # seniority gate for sources that didn't pre-filter level
        if not j.get("seniority_checked") and _SENIOR.search(j["role"]):
            continue
        if profile and j.get("profile") != profile:
            continue
        jobs.append(j)

    # --- match + rank -----------------------------------------------------------
    masters = {p: profiles.read_master_for(p) for p in {j["profile"] for j in jobs}}
    for j in jobs:
        text = f"{j['role']} {j.get('locations', '')}"
        j["match"] = ats.ats_score(text, masters[j["profile"]])["score"]
        comp = scoring.composite(ats_score=j["match"], posted_date=j["posted_date"],
                                 today=today)
        j["found_score"] = comp["score"]
    # Rank by the composite found_score (master-match + recency); everything here is
    # already inside the freshness window, so fit — not minutes of recency — leads.
    jobs.sort(key=lambda j: (j["found_score"] or 0, j["match"] or 0,
                             j.get("posted_ts") or 0), reverse=True)

    # Per-company coverage: how many we PULLED from each portal vs how many survived the
    # freshness/US/title/seniority filter — so you can verify nothing is silently dropped.
    from collections import Counter
    pulled = Counter(j["company"] for j in raw)
    kept = Counter(j["company"] for j in jobs)
    stats["coverage"] = {co: {"pulled": pulled[co], "kept": kept.get(co, 0)}
                         for co in pulled}
    stats["total_after_filters"] = len(jobs)
    return {"jobs": jobs, "stats": stats, "errors": errors}


def coverage(hours: int = 24, *, profile: str | None = None,
             sources: list[str] | None = None) -> dict:
    """Run a fresh sweep and return the per-company {pulled, kept} coverage table.
    Lets you confirm each portal's jobs are fully retrieved and see what the filters drop."""
    return gather(hours, profile=profile, sources=sources, verbose=False)["stats"]["coverage"]


def discover(hours: int = 24, target: int = 100, *, profile: str | None = None,
             sources: list[str] | None = None, save: bool = True, verbose: bool = True,
             refresh: bool = False) -> list[dict]:
    """The `discover` command body: gather + take top `target` + record as found.

    Caches the gathered shortlist for the day (keyed by hours+profile+sources) so a
    re-run — e.g. after a mid-pipeline failure — reuses it instead of re-sweeping every
    source. Pass refresh=True to force a fresh sweep.
    """
    from . import finder

    src_key = "+".join(sorted(sources)) if sources else "all"
    cache_key = f"discover-{hours}-{profile or 'auto'}-{src_key}"
    today = date.today().isoformat()
    jobs = None if refresh else finder.get_cached(cache_key, profile, today)
    if jobs is None:
        result = gather(hours, profile=profile, sources=sources, verbose=verbose)
        jobs = result["jobs"]
        finder.put_cache(cache_key, profile, today, jobs)
        if verbose:
            for e in result["errors"]:
                print(f"  ⚠ {e}")
    elif verbose:
        print(f"Using today's cached discovery: {len(jobs)} roles "
              "(--refresh to re-sweep).")
    shortlist = jobs[:target]
    if save:
        existing_urls = {a.get("url") for a in tracker.list_applications()}
        for j in shortlist:
            if j["url"] in existing_urls:
                continue  # already tracked — don't duplicate rows
            tracker.save_application(
                company=j["company"], role=j["role"], url=j["url"], status="found",
                match_score=j["match"], source=j.get("source", "feed"),
                posted_date=j["posted_date"], profile=j["profile"],
            )
    if verbose:
        print(f"\nDiscovered {len(jobs)} fresh roles (past {hours}h); "
              f"kept top {len(shortlist)}.")
    return shortlist


def rerank_by_jd(jobs: list[dict], top: int, *, verbose: bool = True) -> list[dict]:
    """Second-stage ranking: fetch each candidate's REAL job description (cheap ATS
    API/HTTP paths only — no browser) and re-rank by full-JD keyword match against
    the right master resume. Title-vs-master ranking gets the pool roughly right;
    this stage gets the ORDER right, because the JD is what the resume must match.

    Also applies the sponsorship hard gate here, so a role the candidate is
    disqualified from never spends a tailoring slot. The fetched JD rides along as
    job["jd_text"] so the tailor step doesn't fetch it again; jobs whose JD needs a
    browser keep their title-based match and rank by it (they're fetched with the
    browser fallback at tailor time)."""
    from . import finder, jd_fetch
    from .tailor import _NO_SPONSOR, _requires_sponsorship

    needs_sponsor = _requires_sponsorship()
    today = date.today().isoformat()
    masters: dict = {}
    ranked: list[dict] = []
    for j in jobs:
        prof = j.get("profile")
        if prof not in masters:
            masters[prof] = profiles.read_master_for(prof)
        # Day-cache the JD text per URL: portals aren't byte-stable between fetches,
        # and in manual-brain mode the packet id hashes the JD — an unstable JD would
        # orphan an already-answered packet on every re-run.
        cached = finder.get_cached(f"jd:{j['url']}", None, today)
        if cached is not None:
            jd = cached[0] if cached else ""
        else:
            try:
                fetched = jd_fetch.fetch_jd(j["url"], allow_browser=False)
                jd = fetched["text"] if fetched["looks_complete"] else ""
            except Exception:
                jd = ""
            finder.put_cache(f"jd:{j['url']}", None, today, [jd] if jd else [])
        if jd and needs_sponsor:
            m = _NO_SPONSOR.search(jd)
            if m:
                reason = (f'hard gate: JD states "{m.group(0).strip()}" '
                          "and profile requires sponsorship")
                tracker.save_application(
                    company=j["company"], role=j["role"], url=j["url"],
                    status="skipped", source=j.get("source"),
                    posted_date=j.get("posted_date"), profile=prof, notes=reason)
                if verbose:
                    print(f"  ⛔ {j['company']} — {j['role']}: {reason}")
                continue
        j = dict(j)
        if jd:
            j["jd_text"] = jd
            j["jd_match"] = ats.ats_score(jd, masters[prof])["score"]
        else:
            j["jd_match"] = None
        ranked.append(j)
    # A readable JD beats any title-only guess: title scores (3-5 words) are
    # inflated and NOT comparable to full-JD scores, and an unreadable JD can't be
    # tailored deterministically anyway — so fetched-JD jobs always rank first.
    ranked.sort(key=lambda x: (x["jd_match"] is not None, x["jd_match"] or 0,
                               x.get("match") or 0), reverse=True)
    shortlist = ranked[:top]
    if verbose:
        print(f"\nRe-ranked by full-JD match; tailoring top {len(shortlist)}:")
        for j in shortlist:
            jm = j["jd_match"]
            print(f"  JD-match={jm if jm is not None else '  ?'}  "
                  f"{j['company'][:22]:<22} {j['role'][:44]}")
    return shortlist
