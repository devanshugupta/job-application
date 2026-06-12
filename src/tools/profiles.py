"""Master-resume profiles.

A candidate often targets several role families (ML/AI, SDE, Data, SDE+ML/AI). Each
gets its own *master resume* tuned for that family, living in ``resume/masters/``.
``index.json`` maps each profile id -> a label + the role keywords it targets, so we
can auto-pick the best master for a given job description by keyword overlap.

Backward compatible: if ``resume/masters/`` is absent, everything falls back to the
single ``resume/master_resume.md``.
"""

from __future__ import annotations

import json
import pathlib
import re

MASTERS_DIR = pathlib.Path("resume/masters")
INDEX_PATH = MASTERS_DIR / "index.json"
LEGACY_MASTER = pathlib.Path("resume/master_resume.md")

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]{1,}")


def have_profiles() -> bool:
    return INDEX_PATH.exists()


def load_index() -> dict:
    """Return {profile_id: {"label": str, "keywords": [..], "file": "..."}}."""
    if not INDEX_PATH.exists():
        return {}
    return json.loads(INDEX_PATH.read_text())


def list_profiles() -> list[str]:
    return list(load_index().keys())


def master_path(profile: str | None) -> pathlib.Path:
    """Resolve the master-resume file for a profile.

    profile=None -> legacy single master. Unknown profile -> legacy master.
    """
    if profile and have_profiles():
        entry = load_index().get(profile)
        if entry:
            return MASTERS_DIR / entry["file"]
    return LEGACY_MASTER


def read_master_for(profile: str | None) -> str:
    path = master_path(profile)
    if not path.exists():
        return (
            f"No master resume found at {path}. Create it (see resume/masters/ or "
            "resume/master_resume.example.md)."
        )
    return path.read_text()


def auto_pick(jd_text: str) -> tuple[str | None, dict]:
    """Pick the profile whose target keywords best overlap the JD.

    Returns (profile_id_or_None, scores) where scores maps profile -> overlap count.
    None means no profiles configured (caller should use the legacy master).
    """
    index = load_index()
    if not index:
        return None, {}
    jd_tokens = {t.lower() for t in _TOKEN.findall(jd_text)}
    scores: dict[str, int] = {}
    for pid, entry in index.items():
        kws = {k.lower() for k in entry.get("keywords", [])}
        scores[pid] = len(jd_tokens & kws)
    best = max(scores, key=scores.get) if scores else None
    # If nothing overlaps at all, leave the choice to the caller/human.
    if best is not None and scores[best] == 0:
        best = None
    return best, scores
