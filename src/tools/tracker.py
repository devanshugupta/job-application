"""Profile + application tracking — the agent's memory of who you are and what
you've applied to.

``read_profile`` loads your details so Claude can fill forms and tailor materials.
``save_application`` appends an outcome record to ``data/applications.json`` so you
have a history (and so the agent can dedupe / follow up later).
"""

from __future__ import annotations

import json
import pathlib
from datetime import date

PROFILE_PATH = pathlib.Path("config/profile.json")
APPLICATIONS_PATH = pathlib.Path("data/applications.json")
RESUME_RULES_PATH = pathlib.Path("resume/formatting_rules.md")


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


def save_application(
    company: str,
    role: str,
    url: str,
    status: str,
    fit_score: float | None = None,
    ats_score: int | None = None,
    notes: str = "",
    *,
    match_score: int | None = None,   # keyword/ATS overlap, 0-100 (from `find`)
    resume_score: int | None = None,  # senior-reviewer quality, 0-10 (from `score_resume`)
    scorer_verdict: str | None = None,
    scorer_gaps: list | None = None,
    resume_diff: dict | None = None,
    source: str | None = None,
    posted_date: str | None = None,
    profile: str | None = None,
    tailored_pdf: str | None = None,
    applied_date: str | None = None,
) -> dict:
    """Append one application record. ``status`` is free-form, e.g.
    'found', 'scored', 'submitted', 'skipped', 'needs_follow_up'.

    The extra keyword fields feed the BI dashboard (transparency): what was changed in
    the resume (``resume_diff``), the human-reviewer ``match_score``/``scorer_verdict``/
    ``scorer_gaps``, where it came from (``source``), the posting ``posted_date``, which
    master ``profile`` matched, and the rendered ``tailored_pdf`` path. All optional and
    backward compatible."""
    APPLICATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = _load_applications()
    record = {
        "id": len(db["applications"]) + 1,
        "company": company,
        "role": role,
        "url": url,
        "status": status,
        "fit_score": fit_score,
        "ats_score": ats_score,
        "match_score": match_score,
        "resume_score": resume_score,
        "scorer_verdict": scorer_verdict,
        "scorer_gaps": scorer_gaps or [],
        "resume_diff": resume_diff or {},
        "source": source,
        "posted_date": posted_date,
        "profile": profile,
        "tailored_pdf": tailored_pdf,
        "notes": notes,
        "date": date.today().isoformat(),
        "applied_date": applied_date,
    }
    db["applications"].append(record)
    APPLICATIONS_PATH.write_text(json.dumps(db, indent=2))
    return record


def update_application(url: str, **fields) -> dict | None:
    """Update the most recent record matching `url` in place. Returns the record or None."""
    APPLICATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = _load_applications()
    apps = db["applications"]
    # Find the last record with this URL
    for rec in reversed(apps):
        if rec.get("url") == url:
            rec.update({k: v for k, v in fields.items() if v is not None})
            rec["date"] = date.today().isoformat()
            APPLICATIONS_PATH.write_text(json.dumps(db, indent=2))
            return rec
    return None


def list_applications() -> list[dict]:
    return _load_applications()["applications"]
