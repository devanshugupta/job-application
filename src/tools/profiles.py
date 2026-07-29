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
from functools import lru_cache
import re

from .. import config

MASTERS_DIR = config.MASTERS_DIR
INDEX_PATH = config.MASTERS_INDEX_PATH
LEGACY_MASTER = config.LEGACY_MASTER_PATH

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


def all_master_texts() -> dict[str, str]:
    """Every DISTINCT real master resume, keyed by one profile that maps to it. Many
    profiles resolve to the same `.tex` (e.g. ml_ai/data_engineer -> ml_sde.tex), so
    dedupe by content."""
    out: dict[str, str] = {}
    seen: set[int] = set()
    for pid in list_profiles():
        txt = read_master_for(pid)
        if not txt or txt.startswith("No master"):
            continue
        h = hash(txt)
        if h not in seen:
            seen.add(h)
            out[pid] = txt
    return out


@lru_cache(maxsize=1)
def combined_master_text() -> str:
    """ONE superset resume = all distinct masters concatenated (ML + SDE + DE points).

    A combined-background candidate should be scored against everything they can do, so a
    JD's skills are matched if ANY of their resumes covers them — this is what stops both
    ML and SDE roles from scoring low for one narrow per-profile master. Out-of-domain
    roles (Rust, hardware) still score low because no master carries those concepts."""
    return "\n".join(all_master_texts().values())


def master_path(profile: str | None) -> pathlib.Path:
    """Resolve the master-resume file for a profile.

    profile=None -> legacy single master. Unknown profile -> legacy master.
    """
    if profile and have_profiles():
        entry = load_index().get(profile)
        if entry:
            return MASTERS_DIR / entry["file"]
    return LEGACY_MASTER


_PLACEHOLDER = re.compile(r"Your Name|your@email\.com|Company Inc|Startup LLC")


def read_master_for(profile: str | None) -> str:
    """Return the master resume TEXT for a profile.

    Source-of-truth order:
      1. The profile's ``.tex`` master (the real, rendered resume) converted to
         plain text — preferred whenever it exists, because the ``.md`` masters
         historically drifted into placeholder templates.
      2. The profile's ``.md`` master, unless it still contains template
         placeholders ("Your Name", "Company Inc", ...).
      3. The legacy single ``resume/master_resume.md``.
    """
    from . import latex  # local import: avoid cycle at module load

    tex = latex.tex_master_path(profile)
    md_path = master_path(profile)
    md_text = md_path.read_text() if md_path.exists() else ""

    if tex is not None and (not md_text or _PLACEHOLDER.search(md_text)):
        text = latex.tex_to_text(tex.read_text())
        if text.strip():
            return text
    if md_text:
        return md_text
    return (
        f"No master resume found at {md_path}. Create it (see resume/masters/ or "
        "resume/master_resume.example.md)."
    )


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
