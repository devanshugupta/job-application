"""Deterministic tailoring pipeline — one job in, one scored tailored resume out.

The old `run` command launched a full browser agent loop per job (40 turns of
tool-calling). This replaces it with a fixed pipeline where the LLM is called
exactly TWICE per job, via the Brain seam, with structured outputs:

    fetch JD (HTTP)                       deterministic
    pick master profile                   deterministic (keyword overlap)
    -> Brain call 1: tailoring patch      judgment
    apply patch + lint                    deterministic
    (one corrective Brain pass if lint blocks)
    render PDF (LaTeX or Markdown)        deterministic
    final_check                           deterministic
    -> Brain call 2: senior-reviewer score  judgment
    save record + artifacts               deterministic

Cheaper, faster, and far more predictable than the agent loop — and because the
Brain is pluggable, the same pipeline runs with no API key in manual mode.
"""

from __future__ import annotations

from datetime import date

from .. import config, prompts
from ..brain import BrainPending
from . import artifacts, ats, final_check, jd_fetch, profiles, resume, scorer, tracker

PATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "technical_skills": {"type": "string"},
        "top_bullets": {"type": "array", "items": {"type": "string"}},
        "experience_section_index": {"type": "integer"},
        "reasoning": {"type": "string"},
    },
    "required": ["summary", "technical_skills", "top_bullets",
                 "experience_section_index", "reasoning"],
    "additionalProperties": False,
}

# Review/QA pass (prompts.REVIEW_SYSTEM). Flat + all-required so structured output is
# happy; empty new_* fields ("" / [] / -1) mean "no change to that part".
REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "repeated_bullets": {"type": "array", "items": {"type": "string"}},
        "experience_matches_jd": {"type": "boolean"},
        "experience_fit_reason": {"type": "string"},
        "summary_makes_sense": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "new_summary": {"type": "string"},
        "new_technical_skills": {"type": "string"},
        "new_top_bullets": {"type": "array", "items": {"type": "string"}},
        "new_experience_section_index": {"type": "integer"},
    },
    "required": ["ok", "repeated_bullets", "experience_matches_jd",
                 "experience_fit_reason", "summary_makes_sense", "issues",
                 "new_summary", "new_technical_skills", "new_top_bullets",
                 "new_experience_section_index"],
    "additionalProperties": False,
}

# The resume-creation system prompt lives in src/prompts.py (TAILOR_SYSTEM); we render
# it with the live section budgets so word limits stay in sync with resume.BUDGETS.
def _tailor_system() -> str:
    return prompts.render_tailor_system()


def _validate_patch(patch: dict) -> list[str]:
    problems = []
    bullets = patch.get("top_bullets") or []
    if len(bullets) != 2:
        problems.append(f"top_bullets must have exactly 2 entries (got {len(bullets)}).")
    for key in ("summary", "technical_skills"):
        if not (patch.get(key) or "").strip():
            problems.append(f"{key} is empty.")
    return problems


def _merge_review(patch: dict, review: dict) -> tuple[dict, bool]:
    """Fold a review's corrections into the patch. Returns (new_patch, changed).

    Empty review fields mean "no change": new_summary "" / new_technical_skills "" /
    new_top_bullets [] / new_experience_section_index -1. ok=true short-circuits to
    no change even if stray fields are populated.
    """
    if review.get("ok", True):
        return patch, False
    merged = dict(patch)
    changed = False
    if (review.get("new_summary") or "").strip():
        merged["summary"] = review["new_summary"].strip(); changed = True
    if (review.get("new_technical_skills") or "").strip():
        merged["technical_skills"] = review["new_technical_skills"].strip(); changed = True
    if review.get("new_top_bullets"):
        merged["top_bullets"] = review["new_top_bullets"]; changed = True
    if review.get("new_experience_section_index", -1) >= 0:
        merged["experience_section_index"] = review["new_experience_section_index"]
        changed = True
    return merged, changed


def tailor_job(url: str, *, brain, profile: str | None = None,
               company: str = "", role: str = "", posted_date: str | None = None,
               source: str | None = None, jd_text: str | None = None,
               verbose: bool = True) -> dict:
    """Run the full pipeline for one job URL. Returns the saved record (or raises
    BrainPending in manual mode when a packet awaits its response)."""
    today = date.today().isoformat()

    # 1. JD ---------------------------------------------------------------------
    if not jd_text:
        fetched = jd_fetch.fetch_jd(url)
        jd_text = fetched["text"]
        if not fetched["looks_complete"]:
            raise RuntimeError(
                f"Could not extract a usable JD from {url} (source={fetched['source']}, "
                f"{len(jd_text)} chars). Use `apply`/`score` (browser agent) for this one.")

    # 2. Profile + master --------------------------------------------------------
    if not profile:
        profile, _scores = profiles.auto_pick(jd_text)
    master = profiles.read_master_for(profile)
    if master.startswith("No master resume"):
        raise RuntimeError(master)

    # 3. Brain call 1: the patch ---------------------------------------------------
    user = (f"JOB DESCRIPTION:\n{jd_text.strip()}\n\n"
            f"MASTER RESUME:\n{master.strip()}")
    patch = brain.structured("tailor", system=_tailor_system(), user=user,
                             schema=PATCH_SCHEMA)
    problems = _validate_patch(patch)
    if problems:
        raise RuntimeError(f"Brain returned an invalid patch: {problems}")

    # 4. Apply + lint (one corrective pass max) -----------------------------------
    resume.apply_patch(dict(patch), profile=profile, company=company or "Unknown",
                       role=role or "Unknown", url=url)
    lint = resume.lint(focus_bullets=patch["top_bullets"])
    if not lint["ok"]:
        fix_user = (user + "\n\nYOUR PREVIOUS PATCH:\n" + str({
            k: patch[k] for k in ("summary", "technical_skills", "top_bullets")})
            + "\n\nLINT REJECTED IT FOR:\n- " + "\n- ".join(lint["issues"])
            + "\n\nReturn a corrected patch that fixes every issue.")
        patch = brain.structured("tailor", system=_tailor_system(), user=fix_user,
                                 schema=PATCH_SCHEMA)
        if _validate_patch(patch):
            raise RuntimeError("Corrective patch still invalid; aborting this job.")
        resume.apply_patch(dict(patch), profile=profile, company=company or "Unknown",
                           role=role or "Unknown", url=url)
        lint = resume.lint(focus_bullets=patch["top_bullets"])

    # 5. Brain call 2: REVIEW + revise — repeated bullets? does the tailored experience
    #    actually fit the JD? does the summary make sense? Applies one correction pass.
    tailored_md = (config.TAILORED_MD_PATH.read_text()
                   if config.TAILORED_MD_PATH.exists() else "")
    review_user = (
        f"JOB DESCRIPTION:\n{jd_text.strip()}\n\n"
        f"TAILORED RESUME (Markdown — full document):\n{tailored_md.strip()}\n\n"
        f"The tailored experience block is index {patch.get('experience_section_index', 0)} "
        f"(0 = most recent). Its two rewritten bullets are:\n"
        f"1. {patch['top_bullets'][0]}\n2. {patch['top_bullets'][1]}")
    review = brain.structured("review", system=prompts.REVIEW_SYSTEM, user=review_user,
                             schema=REVIEW_SCHEMA)
    review_issues = list(review.get("issues") or [])
    merged, changed = _merge_review(patch, review)
    if changed and not _validate_patch(merged):  # only adopt a structurally valid revision
        patch = merged
        resume.apply_patch(dict(patch), profile=profile, company=company or "Unknown",
                           role=role or "Unknown", url=url)
        lint = resume.lint(focus_bullets=patch["top_bullets"])
        tailored_md = (config.TAILORED_MD_PATH.read_text()
                       if config.TAILORED_MD_PATH.exists() else "")
    if verbose:
        print(f"    review: revised ({len(review_issues)} issue(s))" if changed
              else "    review: clean (no repeats, experience fits, summary ok)")

    # 6. Render + final check ------------------------------------------------------
    resume.render_pdf(company=company or "Unknown", role=role or "Unknown",
                      url=url, profile=profile, patch=patch)
    # Both render paths copy the PDF into the per-application folder under this name.
    pdf_file = artifacts.folder(company or "Unknown", role or "Unknown",
                                url) / config.resume_pdf_name()
    pdf_path = str(pdf_file) if pdf_file.exists() else None
    tailored_md = (config.TAILORED_MD_PATH.read_text()
                   if config.TAILORED_MD_PATH.exists() else "")
    check = final_check.check_resume(tailored_md=tailored_md, pdf_path=pdf_path,
                                     jd_text=jd_text, focus_bullets=patch["top_bullets"])

    # 7. Brain call 3: senior-reviewer score ---------------------------------------
    score_user = ("JOB DESCRIPTION:\n" + jd_text.strip()
                  + "\n\nTAILORED RESUME (Markdown):\n" + tailored_md.strip())
    verdict = brain.structured("score", system=scorer._SCORER_SYSTEM, user=score_user,
                               schema=scorer.SCORE_SCHEMA, max_tokens=2000)

    # 8. Record ---------------------------------------------------------------------
    kw = ats.ats_score(jd_text, master)["score"]
    notes = "; ".join(check["problems"] + [f"review: {i}" for i in review_issues])
    rec = tracker.save_application(
        company=company or "Unknown", role=role or "Unknown", url=url, status="scored",
        match_score=kw, resume_score=verdict.get("overall_score"),
        match_pct=verdict.get("match_pct"), scorer_verdict=verdict.get("verdict"),
        scorer_gaps=verdict.get("gaps"), resume_diff={
            "summary": patch.get("summary"),
            "technical_skills": patch.get("technical_skills"),
            "top_bullets": patch.get("top_bullets"),
        },
        source=source, posted_date=posted_date, profile=profile,
        tailored_pdf=pdf_path,
        notes=notes,
    )
    if verbose:
        flag = "" if check["ok"] else f"  ⚠ final_check: {len(check['problems'])} problem(s)"
        print(f"    scored {verdict.get('overall_score')}/10 "
              f"({verdict.get('verdict')}), must-haves {verdict.get('match_pct')}%{flag}")
    return rec


def _is_auth_error(e: Exception) -> bool:
    """Provider failures that hit EVERY job identically (bad key, exhausted quota) —
    retrying the rest of the shortlist would just repeat the failure N times.
    Transient rate limits are not matched (plain 429 without insufficient_quota)."""
    if type(e).__name__ in ("AuthenticationError", "PermissionDeniedError"):
        return True
    s = str(e)
    return ("invalid_api_key" in s or "authentication_error" in s
            or "insufficient_quota" in s or " 401 " in f" {s} ")


def tailor_many(jobs: list[dict], *, brain, verbose: bool = True) -> dict:
    """Tailor+score a discovery shortlist. In manual mode, jobs whose Brain packets
    lack responses are collected as 'pending' instead of failing the run. Auth
    errors abort the whole run immediately — they can never succeed job-by-job."""
    done, pending, failed = [], [], []
    for i, j in enumerate(jobs, 1):
        label = f"{j.get('company', '?')} — {j.get('role', '?')}"
        if verbose:
            print(f"\n[{i}/{len(jobs)}] {label}")
        try:
            rec = tailor_job(j["url"], brain=brain, profile=j.get("profile"),
                             company=j.get("company", ""), role=j.get("role", ""),
                             posted_date=j.get("posted_date"), source=j.get("source"),
                             verbose=verbose)
            done.append(rec)
        except BrainPending as bp:
            pending.append({"job": label, "packet": str(bp.packet_path)})
            if verbose:
                print(f"    ⏸ {bp}")
        except Exception as e:
            if _is_auth_error(e):
                raise SystemExit(
                    f"\n✗ API authentication failed: {e}\n\n"
                    "Aborting the run — every remaining job would hit the same error.\n"
                    "Check which key/provider is in use:\n"
                    "  - .env: ANTHROPIC_API_KEY / OPENAI_API_KEY and JOB_AGENT_PROVIDER\n"
                    "  - a stale exported key in your shell overrides .env "
                    "(`env | grep -E 'OPENAI|ANTHROPIC'`)\n"
                    "  - or run with no key at all: `pipeline --brain manual`")
            failed.append({"job": label, "error": str(e)})
            if verbose:
                print(f"    ✗ {e}")
    return {"done": done, "pending": pending, "failed": failed}
