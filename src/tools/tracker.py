"""Profile + application tracking  the agent's memory of who you are and what
you've applied to.

``read_profile`` loads your details so Claude can fill forms and tailor materials.
``save_application`` appends an outcome record to ``data/applications.json`` so you
have a history (and so the agent can dedupe / follow up later).
"""

from __future__ import annotations

import contextlib
import json
import re
from datetime import datetime

from .. import config

try:
    import fcntl  # POSIX only (macOS/Linux); used to serialize concurrent tracker writes
except ImportError:  # pragma: no cover  Windows fallback: no cross-process lock
    fcntl = None


@contextlib.contextmanager
def _db_lock():
    """Serialize the load-modify-save of applications.json across processes, so parallel
    tailor runs (e.g. several agents) can't lose each other's row updates via a
    last-writer-wins whole-file overwrite. Best-effort: a no-op where fcntl is absent."""
    if fcntl is None:
        yield
        return
    APPLICATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_path = APPLICATIONS_PATH.with_suffix(".lock")
    with open(lock_path, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)

PROFILE_PATH = config.PROFILE_PATH
APPLICATIONS_PATH = config.APPLICATIONS_PATH
RESUME_RULES_PATH = config.RESUME_RULES_PATH


def _stamp() -> str:
    """Timestamp stored on a row's `date` (minute precision) so the dashboard can show
    WHEN a job was found/last touched, not just the day. `[:10]` still yields the date."""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def read_resume_rules() -> str:
    """Load the resume-rewriting rules the agent must follow when tailoring."""
    if not RESUME_RULES_PATH.exists():
        return "No resume formatting rules file found at resume/formatting_rules.md."
    return RESUME_RULES_PATH.read_text()


def read_profile() -> dict:
    if not PROFILE_PATH.exists():
        raise FileNotFoundError(
            "config/profile.json not found. Copy config/profile.example.json to "
            "config/profile.json and fill it in."
        )
    return json.loads(PROFILE_PATH.read_text())


def _load_applications() -> dict:
    if APPLICATIONS_PATH.exists():
        return json.loads(APPLICATIONS_PATH.read_text())
    return {"applications": []}


def _save_db(db: dict) -> None:
    APPLICATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    APPLICATIONS_PATH.write_text(json.dumps(db, indent=2))


def _norm_url(url: str) -> str:
    """Canonical form for matching one posting across lifecycle stages: drop the query
    string and trailing slash so 'find' and 'apply' URLs of the same job still match."""
    return (url or "").split("?")[0].rstrip("/")


def _find_by_url(apps: list[dict], url: str) -> dict | None:
    """Most recent record whose URL matches `url` (query/​slash-insensitive). None if
    `url` is empty (no stable key → always treated as a new record)."""
    if not url:
        return None
    key = _norm_url(url)
    return next((r for r in reversed(apps) if _norm_url(r.get("url", "")) == key), None)


def save_application(
    company: str,
    role: str,
    url: str,
    status: str,
    fit_score: float | None = None,
    ats_score: int | None = None,
    notes: str = "",
    *,
    match_score: int | None = None,   # keyword/ATS overlap of the TAILORED resume, 0-100
    master_ats: int | None = None,    # keyword/ATS overlap of the MASTER (pre-tailor baseline)
    resume_score: int | None = None,  # senior-reviewer quality, 0-10 (from `score_resume`)
    match_pct: int | None = None,     # % of JD must-haves satisfied, 0-100 (scorer)
    scorer_verdict: str | None = None,
    scorer_gaps: list | None = None,
    resume_diff: dict | None = None,
    source: str | None = None,
    posted_date: str | None = None,
    profile: str | None = None,
    tailored_pdf: str | None = None,
    applied_date: str | None = None,
    jd_text: str | None = None,     # JD captured at discovery (ATS API), if any
) -> dict:
    """Upsert one application record, keyed on ``url``.

    A job moves through stages (found → scored → tailored → applied); each call
    UPDATES that job's single row rather than appending a duplicate. A record with the
    same URL (query/​slash-insensitive) is merged in place  ``status`` always advances,
    and any field passed non-empty overwrites while unspecified fields keep their
    existing value (so discovery's ``source``/``posted_date`` survive a later scoring
    call). An empty ``url`` has no stable key, so it is always appended.

    ``status`` is free-form: 'found', 'scored', 'tailored', 'applied', 'skipped', …
    The optional fields feed the BI dashboard: what changed (``resume_diff``), reviewer
    signals (``match_score``/``resume_score``/``match_pct``/``scorer_verdict``/
    ``scorer_gaps``), provenance (``source``/``posted_date``/``profile``), and the
    rendered ``tailored_pdf`` path. All backward compatible."""
    # Fields the caller actually supplied (drop None so they never clobber on merge).
    incoming = {
        "company": company, "role": role, "url": url, "status": status,
        "fit_score": fit_score, "ats_score": ats_score,
        "match_score": match_score, "master_ats": master_ats, "resume_score": resume_score,
        "match_pct": match_pct, "scorer_verdict": scorer_verdict,
        "scorer_gaps": scorer_gaps, "resume_diff": resume_diff,
        "source": source, "posted_date": posted_date, "profile": profile,
        "tailored_pdf": tailored_pdf, "notes": notes or None,
        "applied_date": applied_date, "jd_text": jd_text or None,
    }
    incoming = {k: v for k, v in incoming.items() if v is not None}

    # Locked so parallel writers (agents) don't lose each other's row updates.
    with _db_lock():
        db = _load_applications()
        apps = db["applications"]
        existing = _find_by_url(apps, url)
        if existing is not None:
            # Status only ever ADVANCES. A later call writing a less-advanced status (e.g.
            # rerank_by_jd's sponsorship gate writing 'skipped' onto a row already tailored
            # or applied) must not erase the fact that we built a resume / sent it. Unknown
            # free-form statuses rank -1 and are always accepted.
            old_rank = _STATUS_RANK.get(existing.get("status"), -1)
            if _STATUS_RANK.get(status, -1) < old_rank:
                incoming.pop("status", None)
            existing.update(incoming)
            # `date` is the FOUND date: set once at creation, never bumped by later
            # touches (scoring, tailoring, apply clicks).
            existing.setdefault("date", _stamp())
            record = existing
        else:
            record = {
                "id": max((r.get("id", 0) for r in apps), default=0) + 1,
                "scorer_gaps": [], "resume_diff": {},
                **incoming,
                "date": _stamp(),
            }
            apps.append(record)
        _save_db(db)
    return record


def find_advanced_duplicate(company: str, role: str, *, min_status: str = "scored") -> dict | None:
    """The existing record for the same job (company+role, source/URL-independent) IF
    it's already at ``min_status`` or beyond. Callers use this BEFORE tailoring/applying
    to a newly discovered posting, since the same underlying job resurfaces under a
    different URL on re-sweep  most commonly a LinkedIn repost minting a new job id for
    a requisition already applied to elsewhere. Returns None (never merges/mutates) so
    the original record's URL and application data are never at risk of being
    overwritten by a fresh, unvetted tailoring pass; the caller decides what to do
    (typically: skip and mark the new row 'skipped' with a note)."""
    key = _job_key({"company": company, "role": role})
    threshold = _STATUS_RANK.get(min_status, 0)
    apps = list_applications()
    return next((r for r in reversed(apps) if _job_key(r) == key
                and _STATUS_RANK.get(r.get("status"), -1) >= threshold), None)


def update_application(url: str, **fields) -> dict | None:
    """Update the most recent record matching `url` in place. Returns the record or None."""
    with _db_lock():
        db = _load_applications()
        record = _find_by_url(db["applications"], url)
        if record is None:
            return None
        record.update({k: v for k, v in fields.items() if v is not None})
        record.setdefault("date", _stamp())
        _save_db(db)
    return record


# Lifecycle order  a merged job takes the status of its most-advanced record.
_STATUS_RANK = {"found": 0, "skipped": 1, "scored": 2, "tailored": 3, "applied": 4}


def _job_key(rec: dict) -> tuple[str, str]:
    """Identity of a job across records: normalized (company, role). Company suffixes
    like 'Inc.'/'LLC' and role punctuation vary between discovery and tailoring, so
    strip them  'Cohort AI' and 'Cohort AI Inc.' are the same employer."""
    company = re.sub(r"[^a-z0-9 ]", "", (rec.get("company") or "").lower())
    company = re.sub(r"\b(inc|llc|corp|co|ltd|systems|labs|technologies)\b", "", company)
    role = re.sub(r"[^a-z0-9 ]", "", (rec.get("role") or "").lower())
    return " ".join(company.split()), " ".join(role.split())


def _merge_records(group: list[dict]) -> dict:
    """Fold several records for one job into one: the most-advanced status wins, the
    last non-empty value of each field survives, and a real posting URL beats a
    synthetic 'manual:' placeholder."""
    merged = dict(group[0])
    for rec in group[1:]:
        for k, v in rec.items():
            if v in (None, "", [], {}):
                continue
            if k == "url" and str(v).startswith("manual:") and merged.get("url"):
                continue  # never let a placeholder overwrite a real posting URL
            merged[k] = v
    merged["status"] = max((r.get("status") for r in group),
                           key=lambda s: _STATUS_RANK.get(s, -1))
    merged["id"] = min(r.get("id", 1 << 30) for r in group)
    return merged


def dedupe_applications() -> int:
    """Collapse duplicate rows for the same job (same normalized company+role) into a
    single merged record. Returns how many duplicates were removed. Order is preserved
    by the first occurrence of each job."""
    db = _load_applications()
    apps = db["applications"]
    groups: dict[tuple[str, str], list[dict]] = {}
    order: list[tuple[str, str]] = []
    for rec in apps:
        key = _job_key(rec)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(rec)
    deduped = [_merge_records(groups[k]) for k in order]
    removed = len(apps) - len(deduped)
    if removed:
        db["applications"] = deduped
        _save_db(db)
    return removed


def list_applications() -> list[dict]:
    return _load_applications()["applications"]
