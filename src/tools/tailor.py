"""Deterministic tailoring pipeline  one job in, one scored tailored resume out.

The old `run` command launched a full browser agent loop per job (40 turns of
tool-calling). This replaces it with a fixed pipeline where the LLM is called up
to THREE times per job, via the Brain seam, with structured outputs. Each call is
its own callable helper (`_patch_and_lint`, `_review_and_revise`, `_score_tier`):

    fetch JD (HTTP)                       deterministic
    pick master profile                   deterministic (keyword overlap)
    -> Brain call 1: tailoring patch      judgment   (_patch_and_lint)
    apply patch + lint                    deterministic
    (one corrective Brain pass if lint blocks)
    -> Brain call 2: review + revise      judgment   (_review_and_revise)
    render PDF (LaTeX or Markdown)        deterministic
    final_check                           deterministic
    -> Brain call 3: senior-reviewer score  judgment (_score_tier; gated, may reuse
                                            the patch's self-score instead)
    save record + artifacts               deterministic

Cheaper, faster, and far more predictable than the agent loop  and because the
Brain is pluggable, the same pipeline runs with no API key in manual mode.
"""

from __future__ import annotations

import json
import re

from .. import config, prompts
from ..brain import BrainPending
from . import (artifacts, ats, final_check, jd_fetch, latex, profiles, resume,
               role_cache, scorer, tracker)

PATCH_SCHEMA = {
    "type": "object",
    "properties": {
        # STEP 2 output: the 3-5 ranked priorities extracted from THIS JD (all
        # requirement types equal-class: technical, general/soft, scale/metrics).
        "jd_priorities": {"type": "array", "items": {"type": "string"}},
        # STEP 3 output: which priority each of the two lead bullets proves,
        # e.g. {"B1": "<priority text>", "B2": "..."} - the forcing function that
        # makes the priority extraction load-bearing instead of ignorable.
        "bullet_mapping": {"type": "object",
                           "additionalProperties": {"type": "string"}},
        "summary": {"type": "string"},
        "technical_skills": {"type": "string"},
        "top_bullets": {"type": "array", "items": {"type": "string"}},
        "experience_section_index": {"type": "integer"},
        # optional re-selection of the Projects section from the resume +
        # achievements projects pool; [] = keep the master's Projects unchanged
        "projects": {"type": "array", "items": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "url": {"type": "string"},
                           "bullet": {"type": "string"}},
            "required": ["name", "url", "bullet"],
            "additionalProperties": False}},
        "reasoning": {"type": "string"},
        # Cheap self-assessment, same rubric as the strict senior-reviewer scorer
        # (prompts.py STEP 3)  the default verdict for every job; a real separate
        # SCORE brain call only runs for jobs that clear the keyword pre-gate (see
        # tailor_job's two-tier scoring below).
        "self_score": {"type": "integer"},
        "self_verdict": {"type": "string",
                         "enum": ["strong", "borderline", "weak", "true_mismatch"]},
        "self_match_pct": {"type": "integer"},
        "self_gaps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["jd_priorities", "bullet_mapping", "summary", "technical_skills",
                 "top_bullets", "experience_section_index", "projects", "reasoning",
                 "self_score", "self_verdict", "self_match_pct", "self_gaps"],
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
    # The priority pipeline's forcing function: priorities extracted, lead bullets
    # mapped to them. Without these the selection step was skipped, not done.
    pris = patch.get("jd_priorities") or []
    if not 3 <= len(pris) <= 5:
        problems.append(f"jd_priorities must have 3-5 ranked entries (got {len(pris)}).")
    mapping = patch.get("bullet_mapping") or {}
    if not (mapping.get("B1") or "").strip() or not (mapping.get("B2") or "").strip():
        problems.append("bullet_mapping must map B1 and B2 to the priorities they prove.")
    chosen_idx = int(patch.get("experience_section_index", 0) or 0)
    lo, hi = latex.min_bullets_for_block(chosen_idx), latex.MAX_BULLETS_PER_BLOCK
    if not lo <= len(bullets) <= hi:  # density floor: a thin chosen block reads as a weak resume
        problems.append(f"top_bullets must have {lo}-{hi} entries (got {len(bullets)}).")
    for key in ("summary", "technical_skills"):
        if not (patch.get(key) or "").strip():
            problems.append(f"{key} is empty.")
    # Technical Skills must have exactly NUM_SKILL_GROUPS "Group: ..." segments so the
    # rendered skills block is full and keyword-dense for ATS  not a thin 2-3 line list.
    skills = patch.get("technical_skills") or ""
    groups = [s for s in re.split(r"(?<!\w)\|(?!\w)", skills) if ":" in s]
    if skills.strip() and len(groups) != latex.NUM_SKILL_GROUPS:
        problems.append(f"technical_skills must have exactly {latex.NUM_SKILL_GROUPS} "
                        f"'Group: ...' sections (got {len(groups)}).")
    # Projects: the tailor usually leaves this [] (the renderer selects NUM_PROJECTS from
    # the master pool). If it DOES re-select, it must supply exactly NUM_PROJECTS.
    projects = patch.get("projects") or []
    if projects and len(projects) != latex.NUM_PROJECTS:
        problems.append(f"projects, if provided, must have exactly {latex.NUM_PROJECTS} "
                        f"entries (got {len(projects)}).")
    if any(not (p.get("name") or "").strip() or not (p.get("bullet") or "").strip()
           for p in projects if isinstance(p, dict)):
        problems.append("every project needs a non-empty name and bullet.")
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


# JD phrases that hard-disqualify a sponsorship-needing candidate no matter how well
# the resume matches. Deterministic and cheap  catches these BEFORE any tailoring work.
_NO_SPONSOR = re.compile(
    r"without (?:the )?need (?:for|of) (?:employer |visa )?sponsorship|"
    r"(?:will not|won't|unable to|cannot|can't|do(?:es)? not|not able to) (?:provide|offer|support)?\s*(?:visa |work |employment )*sponsor|"
    r"no (?:visa )?sponsorship|not eligible for (?:visa )?sponsorship|"
    r"sponsorship (?:is )?not (?:available|offered|provided)|"
    r"(?:visa|immigration) sponsorship is not|"
    r"u\.?s\.? citizens? only|citizenship (?:is )?required|"
    r"(?:active|current) (?:security )?clearance (?:is )?required|top secret",
    re.I)


def _requires_sponsorship() -> bool:
    try:
        prof = json.loads(config.PROFILE_PATH.read_text())
        return bool(prof.get("work_authorization", {}).get("requires_sponsorship"))
    except Exception:
        return False


def _read_tailored_md() -> str:
    """The tailored resume Markdown as last written by resume.apply_patch/render_pdf."""
    return (config.TAILORED_MD_PATH.read_text()
            if config.TAILORED_MD_PATH.exists() else "")


def _patch_and_lint(brain, *, master: str, jd_text: str, profile: str,
                    company: str, role: str, url: str) -> dict:
    """Brain call 1  the tailoring patch, applied to disk and lint-checked (one
    corrective pass if lint blocks). Returns the accepted patch; raises if it can't be
    made valid.

    The master resume is the SINGLE source and is byte-identical for every job tailored
    against this profile in a run, so it's sent as a cache block (prompt caching): only
    the first call per profile pays full price. The role-family brief rides as a SECOND
    cache block after it - byte-identical for every job in the same family - so the
    master caches across all jobs and master+brief across a family."""
    brief = role_cache.get_or_create(role, jd_text, brain)  # BrainPending on first miss
    cache_blocks = [f"MASTER RESUME (the full pool of the candidate's real work  every "
                    f"bullet you select or reframe MUST come from here):\n{master.strip()}",
                    role_cache.as_context(brief)]
    user = f"JOB DESCRIPTION:\n{jd_text.strip()}"
    patch = brain.structured("tailor", system=_tailor_system(), user=user,
                             schema=PATCH_SCHEMA, cache_blocks=cache_blocks)
    problems = _validate_patch(patch)
    if problems:
        raise RuntimeError(f"Brain returned an invalid patch: {problems}")
    # First-block title follows the target role family (the real role is a rolling
    # one, so SDE / MLE / forward-deployed are all true framings of the same job).
    patch = dict(patch)
    patch["employer_title"] = role_cache.amazon_title(role)

    resume.apply_patch(dict(patch), profile=profile, company=company,
                       role=role, url=url, jd_text=jd_text)
    lint = resume.lint(focus_bullets=patch["top_bullets"])
    if not lint["ok"]:
        fix_user = (user + "\n\nYOUR PREVIOUS PATCH:\n" + str({
            k: patch[k] for k in ("summary", "technical_skills", "top_bullets")})
            + "\n\nLINT REJECTED IT FOR:\n- " + "\n- ".join(lint["issues"])
            + "\n\nReturn a corrected patch that fixes every issue.")
        patch = brain.structured("tailor", system=_tailor_system(), user=fix_user,
                                 schema=PATCH_SCHEMA, cache_blocks=cache_blocks)
        if _validate_patch(patch):
            raise RuntimeError("Corrective patch still invalid; aborting this job.")
        # The corrective patch is a fresh brain object: re-stamp the role-family
        # title or the lint pass silently reverts the block title to the master's.
        patch = dict(patch)
        patch["employer_title"] = role_cache.amazon_title(role)
        resume.apply_patch(dict(patch), profile=profile, company=company,
                           role=role, url=url, jd_text=jd_text)
    return patch


def _review_and_revise(brain, *, patch: dict, jd_text: str, profile: str,
                       company: str, role: str, url: str,
                       verbose: bool) -> tuple[dict, list]:
    """Brain call 2  REVIEW the tailored resume (repeated bullets? does the experience
    actually fit the JD? does the summary cohere?) and apply at most one correction.

    No cache_blocks here on purpose: everything in this prompt (JD, tailored resume)
    is unique per job, and Anthropic cache hits need an identical prefix including the
    system prompt  so the JD from the tailor call can never hit from a review call.
    Only the system prompt is cacheable, and llm.structured always marks it.
    Returns (patch, review_issues); the patch is re-applied to disk when a revision is
    adopted, so the caller can re-read the tailored Markdown afterwards."""
    tailored_md = _read_tailored_md()
    numbered = "\n".join(f"{n}. {b}" for n, b in enumerate(patch["top_bullets"], 1))
    claimed = ""
    if patch.get("jd_priorities"):
        claimed = ("\n\nWRITER'S CLAIMED JD PRIORITIES (ranked):\n- "
                   + "\n- ".join(patch["jd_priorities"])
                   + "\nBULLET MAPPING: " + json.dumps(patch.get("bullet_mapping") or {}))
    review_user = (
        f"JOB DESCRIPTION:\n{jd_text.strip()}\n\n"
        f"TAILORED RESUME (Markdown  full document):\n{tailored_md.strip()}\n\n"
        f"The tailored experience block is index {patch.get('experience_section_index', 0)} "
        f"(0 = most recent). Its rewritten bullets (most relevant first) are:\n{numbered}"
        + claimed)
    review = brain.structured("review", system=prompts.REVIEW_SYSTEM, user=review_user,
                             schema=REVIEW_SCHEMA)
    review_issues = list(review.get("issues") or [])
    merged, changed = _merge_review(patch, review)
    if changed and not _validate_patch(merged):  # only adopt a structurally valid revision
        patch = merged
        resume.apply_patch(dict(patch), profile=profile, company=company,
                           role=role, url=url, jd_text=jd_text)
        resume.lint(focus_bullets=patch["top_bullets"])
    if verbose:
        print(f"    review: revised ({len(review_issues)} issue(s))" if changed
              else "    review: clean (no repeats, experience fits, summary ok)")
    return patch, review_issues


def _score_tier(brain, *, patch: dict, jd_text: str, tailored_md: str,
                master: str) -> tuple[dict, int | None, bool]:
    """Two-tier scoring of the TAILORED resume. Returns (verdict, tailored_ats, scored_fully).

    Every job already carries a self-score from the patch call (STEP 3)  the default
    verdict. A real senior-reviewer SCORE brain call runs only for jobs that clear the
    keyword gate, so the extra rigor is spent where it can change a go/no-go call, not on
    every job."""
    kw = ats.ats_score(jd_text, tailored_md or master)["score"]
    score_gate = config.int_setting("score_gate_keyword_pct", 80)
    scored_fully = kw is not None and kw >= score_gate
    if scored_fully:
        score_user = ("JOB DESCRIPTION:\n" + jd_text.strip()
                      + "\n\nTAILORED RESUME (Markdown):\n" + tailored_md.strip())
        verdict = brain.structured("score", system=scorer._SCORER_SYSTEM, user=score_user,
                                   schema=scorer.SCORE_SCHEMA, max_tokens=2000)
    else:
        verdict = {
            "overall_score": patch.get("self_score"),
            "verdict": patch.get("self_verdict"),
            "match_pct": patch.get("self_match_pct"),
            "gaps": patch.get("self_gaps") or [],
            "missing_must_haves": [],
        }
    return verdict, kw, scored_fully


def tailor_job(url: str, *, brain, profile: str | None = None,
               company: str = "", role: str = "", posted_date: str | None = None,
               source: str | None = None, jd_text: str | None = None,
               verbose: bool = True) -> dict:
    """Run the full pipeline for one job URL. Returns the saved record (or raises
    BrainPending in manual mode when a packet awaits its response).

    Orchestration only  the three judgment steps live in independently-callable
    helpers: `_patch_and_lint` (call 1), `_review_and_revise` (call 2), `_score_tier`
    (call 3 + its two-tier gate). Everything between them is deterministic."""
    comp = company or "Unknown"
    rol = role or "Unknown"

    # 0. Removed-row gate  the dashboard's "remove" (−) button sets removed=True to
    # hide a job the user has already decided isn't worth pursuing (never deletes the
    # row, so restore stays possible). Honor that decision here too: don't spend any
    # tailoring effort re-processing something the user explicitly dismissed. Match by
    # URL first (the specific posting this call is for); fall back to company+role only
    # if this exact URL isn't tracked yet. Checked before the JD fetch  a removed row
    # shouldn't cost anything, not even a fetch.
    _norm = tracker._norm_url(url)
    existing_row = next((r for r in reversed(tracker.list_applications())
                         if tracker._norm_url(r.get("url", "")) == _norm), None)
    if existing_row is None:
        existing_row = tracker.find_advanced_duplicate(comp, rol, min_status="found")
    if existing_row is not None and existing_row.get("removed"):
        if verbose:
            print("    ⛔ removed from dashboard; skipping (restore it there to re-enable)")
        return existing_row
    # 0b. Stale-row gate  a row ticked "stale" (dead/expired link) has no live posting to
    # apply to, so spending a fetch/tailor/score on it is wasted. Skip it entirely, exactly
    # like a removed row; untick it on the dashboard to re-enable.
    if existing_row is not None and existing_row.get("stale"):
        if verbose:
            print("    ⛔ marked stale (dead link); skipping (untick it to re-enable)")
        return existing_row

    # 1. JD ---------------------------------------------------------------------
    if not jd_text:
        fetched = jd_fetch.fetch_jd(url)
        jd_text = fetched["text"]

    # 1a. JD validity gate  the JD we're about to tailor against must be REAL posting
    # text, whether it was freshly fetched above or pre-supplied from the tracker. A
    # login-wall shell (a logged-out LinkedIn page renders its nav/auth chrome as body
    # text) or a too-thin capture must never become a resume  the bullets would be
    # tailored to nothing. This check sits BEFORE any brain spend and covers BOTH
    # sources of jd_text, because stored junk bypasses the fetch path entirely. We do
    # not persist the bad text back (so a later clean re-capture can still fill it).
    if len(jd_text or "") < jd_fetch.MIN_COMPLETE_CHARS or jd_fetch._looks_like_login_wall(jd_text):
        reason = ("unusable JD (login wall or too thin) — no clean posting text to "
                  "tailor against; capture the JD from the company careers page")
        rec = tracker.save_application(
            company=comp, role=rol, url=url, status="skipped", source=source,
            posted_date=posted_date, profile=profile, notes=reason)
        if verbose:
            print(f"    ⛔ {reason}")
        return rec

    # 1b. Hard gates  don't spend tailoring effort on a role we can't be hired for.
    if _requires_sponsorship():
        m = _NO_SPONSOR.search(jd_text)
        if m:
            reason = f"hard gate: JD states \"{m.group(0).strip()}\" and profile requires sponsorship"
            rec = tracker.save_application(
                company=comp, role=rol, url=url, status="skipped", source=source,
                posted_date=posted_date, profile=profile, notes=reason, jd_text=jd_text)
            if verbose:
                print(f"    ⛔ {reason}")
            return rec

    # 1b2. Applied-row protection  once a resume has been SENT, it is a record of what
    # the employer received; never regenerate or overwrite it. Re-running the pipeline
    # over an applied row is always accidental (re-sweep, backlog pass), so return the
    # existing record untouched.
    existing = tracker.find_advanced_duplicate(comp, rol, min_status="applied")
    if existing is not None and tracker._norm_url(existing.get("url")) == tracker._norm_url(url):
        if verbose:
            print(f"    ⛔ already applied on {str(existing.get('applied_date') or existing.get('date'))[:10]}; resume left untouched")
        return existing

    # 1c. Duplicate gate  the same underlying job can resurface under a different URL
    # (a LinkedIn repost mints a new job id for a requisition already applied to via
    # another board/source). Re-tailoring wastes effort; re-applying risks a bounced
    # "we already have your application" email. Skip without touching the original row.
    dup = tracker.find_advanced_duplicate(comp, rol)
    if dup is not None:
        reason = (f"duplicate of an already-{dup.get('status')} application "
                  f"({dup.get('url')}) found on {dup.get('date','?')[:10]}")
        rec = tracker.save_application(
            company=comp, role=rol, url=url, status="skipped", source=source,
            posted_date=posted_date, profile=profile, notes=reason, jd_text=jd_text)
        if verbose:
            print(f"    ⛔ {reason}")
        return rec

    # 2. Profile + master --------------------------------------------------------
    if not profile:
        profile, _scores = profiles.auto_pick(jd_text)
    master = profiles.read_master_for(profile)
    if master.startswith("No master resume"):
        raise RuntimeError(master)

    # 2b. Cheap keyword pre-gate  decide if this JD is worth spending LLM tokens on.
    #     Score the JD's skills against the MASTER resume (no LLM). This master-vs-JD
    #     number is also the pre-tailor BASELINE we persist on every scored row, so the
    #     dashboard can show the lift tailoring adds (master_ats -> match_score). Below
    #     the bar we skip the whole tailor/review/score path and record why.
    min_kw = config.int_setting("min_keyword_match", 30)
    master_ats = ats.ats_score(jd_text, master)["score"]
    if master_ats is not None and master_ats < min_kw:
        reason = (f"keyword pre-gate: master-vs-JD ATS {master_ats}% < {min_kw}% "
                  f"threshold, skipped LLM tailoring to save cost")
        rec = tracker.save_application(
            company=comp, role=rol, url=url, status="skipped", source=source,
            posted_date=posted_date, profile=profile, master_ats=master_ats,
            notes=reason, jd_text=jd_text)
        if verbose:
            print(f"    ⏭ {reason}")
        return rec

    # 3. Brain call 1: patch + apply + lint (one corrective pass) ------------------
    patch = _patch_and_lint(brain, master=master, jd_text=jd_text, profile=profile,
                            company=comp, role=rol, url=url)

    # 4. Brain call 2: REVIEW + one revision pass ---------------------------------
    patch, review_issues = _review_and_revise(brain, patch=patch, jd_text=jd_text,
                                              profile=profile, company=comp, role=rol,
                                              url=url, verbose=verbose)

    # 5. Render + final check ------------------------------------------------------
    resume.render_pdf(company=comp, role=rol, url=url, profile=profile,
                      patch=patch, jd_text=jd_text)
    # Both render paths copy the PDF into the per-application folder under this name.
    pdf_file = artifacts.folder(comp, rol, url) / config.resume_pdf_name()
    pdf_path = str(pdf_file) if pdf_file.exists() else None
    tailored_md = _read_tailored_md()
    check = final_check.check_resume(tailored_md=tailored_md, pdf_path=pdf_path,
                                     jd_text=jd_text, focus_bullets=patch["top_bullets"])

    # 6. Brain call 3: two-tier scoring of the TAILORED resume --------------------
    verdict, kw, scored_fully = _score_tier(brain, patch=patch, jd_text=jd_text,
                                            tailored_md=tailored_md, master=master)

    # 7. Record ---------------------------------------------------------------------
    # The honest path to a higher match: JD asks the resume couldn't claim. The
    # masters are themselves tailored subsets, so an unclaimed ask may be something
    # the candidate HAS done but never documented  surfacing it lets them confirm
    # true items into resume/achievements.md (the grounding corpus) and re-run.
    # What it is NOT: permission to claim JD items nobody verified.
    unclaimed = [u for u in (verdict.get("missing_must_haves") or []) if u][:6]
    if unclaimed and verbose:
        print("    unclaimed JD asks  if any are TRUE for you, add them to "
              "resume/achievements.md and re-run:")
        for u in unclaimed:
            print(f"      · {u}")
    notes = "; ".join(check["problems"] + [f"review: {i}" for i in review_issues])
    if unclaimed:
        extra = "unclaimed asks (add to achievements.md if true): " + "; ".join(unclaimed)
        notes = f"{notes}; {extra}" if notes else extra
    if not scored_fully:
        gate = config.int_setting("score_gate_keyword_pct", 80)
        extra = f"self-scored (tailored-resume keyword match {kw}% < {gate}% gate)"
        notes = f"{notes}; {extra}" if notes else extra
    rec = tracker.save_application(
        company=comp, role=rol, url=url, status="scored",
        match_score=kw, master_ats=master_ats, resume_score=verdict.get("overall_score"),
        match_pct=verdict.get("match_pct"), scorer_verdict=verdict.get("verdict"),
        scorer_gaps=verdict.get("gaps"), resume_diff={
            "summary": patch.get("summary"),
            "technical_skills": patch.get("technical_skills"),
            "top_bullets": patch.get("top_bullets"),
            "experience_section_index": patch.get("experience_section_index"),
            "jd_priorities": patch.get("jd_priorities"),
            "bullet_mapping": patch.get("bullet_mapping"),
        },
        source=source, posted_date=posted_date, profile=profile,
        tailored_pdf=pdf_path,
        notes=notes,
        jd_text=jd_text,  # persist so a re-run (re-score, re-tailor) never re-fetches
    )
    if verbose:
        flag = "" if check["ok"] else f"  ⚠ final_check: {len(check['problems'])} problem(s)"
        tier = "self-score" if not scored_fully else "scored"
        print(f"    {tier} {verdict.get('overall_score')}/10 "
              f"({verdict.get('verdict')}), must-haves {verdict.get('match_pct')}%{flag}")
    return rec


def _is_auth_error(e: Exception) -> bool:
    """Provider failures that hit EVERY job identically (bad key, exhausted quota)
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
    errors abort the whole run immediately  they can never succeed job-by-job."""
    done, pending, failed = [], [], []
    for i, j in enumerate(jobs, 1):
        label = f"{j.get('company', '?')}  {j.get('role', '?')}"
        if verbose:
            print(f"\n[{i}/{len(jobs)}] {label}")
        try:
            rec = tailor_job(j["url"], brain=brain, profile=j.get("profile"),
                             company=j.get("company", ""), role=j.get("role", ""),
                             posted_date=j.get("posted_date"), source=j.get("source"),
                             jd_text=j.get("jd_text"), verbose=verbose)
            done.append(rec)
        except BrainPending as bp:
            pending.append({"job": label, "packet": str(bp.packet_path)})
            if verbose:
                print(f"    ⏸ {bp}")
        except Exception as e:
            if _is_auth_error(e):
                raise SystemExit(
                    f"\n✗ API authentication failed: {e}\n\n"
                    "Aborting the run  every remaining job would hit the same error.\n"
                    "Check which key/provider is in use:\n"
                    "  - .env: ANTHROPIC_API_KEY / OPENAI_API_KEY and JOB_AGENT_PROVIDER\n"
                    "  - a stale exported key in your shell overrides .env "
                    "(`env | grep -E 'OPENAI|ANTHROPIC'`)\n"
                    "  - or run with no key at all: `pipeline --brain manual`")
            failed.append({"job": label, "error": str(e)})
            if verbose:
                print(f"    ✗ {e}")
    return {"done": done, "pending": pending, "failed": failed}
