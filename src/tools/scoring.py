"""Composite scoring  ONE number that says how good an application is.

The pipeline produces several signals on different scales, which made the old
dashboard hard to read. This module folds them into a single **Application
Quality Score (AQS, 0-100)** with a transparent, documented formula and a
per-component breakdown the dashboard can show on hover.

Components (each normalized to 0-100 before weighting):

    reviewer   senior-reviewer overall_score (0-10 -> x10).  The deepest signal:
               does the tailored resume actually read well for THIS JD.
    match      ONE JD↔resume fit number blending two things ATS systems both use:
               the scorer's must-have coverage (semantic  exact + synonym) and
               the deterministic concept-keyword overlap (ats.py). Both present ->
               0.6·must-have + 0.4·keywords; only one -> that one. (See match_pct.)
    recency    freshness of the posting. Applying within hours of posting is a
               real edge: 100 at <=6h, decaying to 0 at the window edge (7d).

Weights (when every component is present):
    reviewer 0.40 · match 0.45 · recency 0.15

Missing components are dropped and the remaining weights renormalized, so a
just-discovered role (match+recency only) still gets a meaningful rank and
a fully scored one gets the richer blend. ``breakdown`` always records which
components participated.
"""

from __future__ import annotations

from datetime import datetime, timezone

WEIGHTS = {
    "reviewer": 0.40,
    "match": 0.45,
    "recency": 0.15,
}

# Within the unified match number, the semantic must-have coverage outweighs the
# shallow keyword overlap  but both count, since real ATS pipelines use both.
_MUST_HAVE_W = 0.6
_KEYWORD_W = 0.4


def match_pct_combined(match_pct: int | float | None,
                       ats_score: int | float | None) -> float | None:
    """Unify must-have coverage and keyword-ATS into one 0-100 fit number.

    Both present -> weighted blend; exactly one -> that one; neither -> None. This is
    THE match number the dashboard shows and the composite weights."""
    mh = None if match_pct is None else max(0.0, min(100.0, float(match_pct)))
    kw = None if ats_score is None else max(0.0, min(100.0, float(ats_score)))
    if mh is not None and kw is not None:
        return _MUST_HAVE_W * mh + _KEYWORD_W * kw
    return mh if mh is not None else kw

GRADES = [  # (min_score, grade, meaning)
    (80, "A", "apply now"),
    (65, "B", "strong  apply"),
    (50, "C", "decent  apply if volume allows"),
    (35, "D", "weak  needs work or skip"),
    (0, "F", "mismatch  skip"),
]


def recency_score(posted_date: str | None, today: str, *, window_days: int = 7) -> int | None:
    """0-100 freshness: 100 within ~6h, linear decay to 0 at the window edge.

    Date granularity is days (feeds give timestamps but pages give dates), so
    same-day=100, then linear. Unverified/missing dates -> None (component absent).
    """
    if not posted_date or posted_date == "unverified":
        return None
    try:
        posted = datetime.strptime(posted_date[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        ref = datetime.strptime(today[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    age_days = (ref - posted).days
    if age_days < 0:
        return 100  # posted "tomorrow" per feed tz skew  treat as brand new
    if age_days >= window_days:
        return 0
    return round(100 * (1 - age_days / window_days))


def composite(
    *,
    reviewer_score: int | float | None = None,   # 0-10
    match_pct: int | float | None = None,        # 0-100
    ats_score: int | float | None = None,        # 0-100
    posted_date: str | None = None,
    today: str | None = None,
    window_days: int = 7,
) -> dict:
    """Blend available signals into {score, grade, meaning, breakdown}.

    Any component may be None; weights renormalize over what's present.
    Returns score=None when no component is available at all.
    """
    parts: dict[str, float] = {}
    if reviewer_score is not None:
        parts["reviewer"] = max(0.0, min(10.0, float(reviewer_score))) * 10
    match = match_pct_combined(match_pct, ats_score)
    if match is not None:
        parts["match"] = match
    if today:
        rec = recency_score(posted_date, today, window_days=window_days)
        if rec is not None:
            parts["recency"] = float(rec)

    if not parts:
        return {"score": None, "grade": None, "meaning": "no signals yet", "breakdown": {}}

    # The reviewer is the deepest fit signal. When it's absent (a discovered-but-
    # un-reviewed role), we DON'T renormalize its weight away  we keep it in the
    # denominator as an unmet ceiling, so skill-coverage + recency alone can't push an
    # un-reviewed role to an "A" above roles the LLM actually vetted. Other missing
    # components (e.g. recency) renormalize normally.
    total_w = sum(WEIGHTS[k] for k in parts)
    if "reviewer" not in parts:
        total_w += WEIGHTS["reviewer"]
    score = round(sum(parts[k] * WEIGHTS[k] for k in parts) / total_w)
    grade, meaning = next((g, m) for cut, g, m in GRADES if score >= cut)
    return {
        "score": score,
        "grade": grade,
        "meaning": meaning,
        "breakdown": {k: round(v) for k, v in parts.items()},
    }


def score_record(rec: dict, today: str | None = None) -> dict:
    """Compute the composite for one tracker record (as stored by tracker.py)."""
    return composite(
        reviewer_score=rec.get("resume_score"),
        match_pct=rec.get("match_pct"),
        ats_score=rec.get("match_score") if rec.get("match_score") is not None
        else rec.get("ats_score"),
        posted_date=rec.get("posted_date"),
        today=today or rec.get("date"),
    )
