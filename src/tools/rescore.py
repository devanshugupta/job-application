"""Recompute stored deterministic keyword-ATS scores with the CURRENT ats logic.

The tracker's ``match_score`` (keyword ATS) is written once, at discovery/tailor time.
When the matcher changes  a bigger skill ontology, better JD cleaning  those stored
numbers go stale, and the unified Match on the dashboard blends a stale keyword score
with a fresh must-have. This recomputes ``match_score`` in place so the whole tracker
reflects today's ats:

  - JD text: reused from the day-cache when available, else fetched via the cheap
    API/HTTP path (no browser); a row whose JD can't be fetched is left untouched.
  - resume: the row's TAILORED resume when it has one (that's what a scored/applied row
    was actually measured against), otherwise the profile master.

Deterministic and free  no LLM, no browser. The must-have side (``match_pct``) is an
LLM judgment and is NOT recomputed here.
"""

from __future__ import annotations

import pathlib
from datetime import date

from .. import config
from . import ats, jd_fetch, latex, profiles, tracker


def _tailored_text(rec: dict) -> str | None:
    """The row's TAILORED resume text if it has one, else None (caller then scores against
    the shared combined master via ats.jd_match)."""
    pdf = rec.get("tailored_pdf")
    if pdf:
        d = pathlib.Path(pdf)
        if not d.is_absolute():
            d = config.ROOT / d
        folder = d.parent
        tex, md = folder / "tailored_resume.tex", folder / "tailored_resume.md"
        if tex.exists():
            return latex.tex_to_text(tex.read_text())
        if md.exists():
            return md.read_text()
    return None   # not tailored -> caller scores against the BEST master (see below)


def refresh_match_scores(*, verbose: bool = True) -> dict:
    """Recompute every tracker row's keyword ATS with the current matcher. Returns
    {updated, unchanged, skipped}."""
    from . import finder  # local: avoid a heavy import at module load

    db = tracker._load_applications()
    rows = db["applications"]
    today = date.today().isoformat()
    updated = unchanged = skipped = 0
    for rec in rows:
        url = rec.get("url") or ""
        cached = finder.get_cached(f"jd:{url}", None, today) if url else None
        if cached is not None:
            jd = cached[0] if cached else ""
        else:
            try:
                f = jd_fetch.fetch_jd(url, allow_browser=False)
                jd = f["text"] if f["looks_complete"] else ""
            except Exception:
                jd = ""
        if not jd:
            skipped += 1
            continue
        tailored = _tailored_text(rec)
        new = (ats.ats_score(jd, tailored)["score"] if tailored is not None
               else ats.jd_match(jd)["score"])
        old = rec.get("match_score")
        if new == old:
            unchanged += 1
            continue
        rec["match_score"] = new
        updated += 1
        if verbose:
            print(f"  {rec.get('company','?')[:22]:22} {str(old):>4} -> {new:>3}  "
                  f"{(rec.get('role') or '')[:40]}")
    if updated:
        tracker._save_db(db)
    if verbose:
        print(f"\nrescored: {updated} updated, {unchanged} unchanged, "
              f"{skipped} skipped (no JD).")
    return {"updated": updated, "unchanged": unchanged, "skipped": skipped}


def backfill_master_ats(*, verbose: bool = True) -> dict:
    """Fill in ``master_ats`` (deterministic keyword match of the JD against the
    UNCHANGED master resume) for every row that's missing it but already has a
    captured ``jd_text``. Uses only stored data  no network fetch, no LLM  so it's
    instant and safe to run any time the master resume changes. Returns
    {filled, skipped_no_jd, already_had}."""
    db = tracker._load_applications()
    rows = db["applications"]
    filled = skipped_no_jd = already_had = 0
    for rec in rows:
        if rec.get("master_ats") is not None:
            already_had += 1
            continue
        jd = rec.get("jd_text") or ""
        if not jd:
            skipped_no_jd += 1
            continue
        master = profiles.read_master_for(rec.get("profile"))
        if master.startswith("No master resume"):
            skipped_no_jd += 1
            continue
        score = ats.ats_score(jd, master)["score"]
        if score is None:
            skipped_no_jd += 1
            continue
        rec["master_ats"] = score
        filled += 1
        if verbose:
            print(f"  {rec.get('company', '?')[:22]:22} master_ats={score:>3}  "
                  f"{(rec.get('role') or '')[:40]}")
    if filled:
        tracker._save_db(db)
    if verbose:
        print(f"\nbackfilled: {filled} filled, {already_had} already had it, "
              f"{skipped_no_jd} skipped (no JD text).")
    return {"filled": filled, "already_had": already_had, "skipped_no_jd": skipped_no_jd}
