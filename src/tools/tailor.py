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

from .. import config
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

TAILOR_SYSTEM = """You tailor ONE resume to ONE job description. You change exactly three \
things — the Summary, the Technical Skills line, and the first two bullets of one \
experience section — and nothing else. Return only the JSON patch.

HONESTY (overrides everything): use only true content from the master resume. Never \
invent skills, employers, tools, metrics, or activities. Tailoring = re-framing and \
re-emphasizing real work in the role's language.

METHOD — understand the role before touching words:
1. Ignore JD fluff (mission, benefits, "are you passionate..."). Extract the real \
technical demands from responsibilities + qualifications.
2. Build the practitioner's toolkit: adjacent tech a strong candidate in this role \
would have touched even if the JD doesn't name it (e.g. "ETL" implies Kafka/S3/\
Airflow/Spark; "search relevance" implies embeddings/FAISS/ranking).
3. List the expected WORK-TYPES as activities a reviewer wants to see described \
(e.g. data eng -> ran a migration, designed schemas, owned pipeline SLAs).
4. Intersect all of that with what the candidate GENUINELY has. Survivors drive the \
skills line and the re-framing of the two bullets. Cut anything the candidate lacks.

OUTPUT CONSTRAINTS (lint will reject violations):
- summary: 2 full lines, {summary_min}-{summary_max} words. Role + domain + scale + a \
credential. Mirror the JD's role title where truthful.
- technical_skills: one tight grouped line, <= {skills_max} words, only relevant \
skills the candidate has. Keep the master's grouping style (e.g. "Languages: ... | \
ML: ...") if it has one.
- top_bullets: EXACTLY 2 bullets for the most relevant experience section. Each is one \
full sentence of {bullet_min}-{bullet_max} words following XYZ ("Accomplished X by \
doing Y, measured by Z") — lead with impact, keep real metrics. They MUST hit the \
JD's top two asks in the JD's own wording (truthfully) — even for weak-match jobs.
- Do not start both bullets with the same verb; avoid filler ("responsible for", \
"helped", "successfully", "various", "in order to").
- experience_section_index: 0-based index of the experience block the bullets \
replace (0 = most recent).
- reasoning: 1-2 sentences — which JD asks the patch targets (for the audit trail).

Skim test: a reviewer reading only the summary and those two bullets should think \
"this is the right person for THIS role"."""


def _tailor_system() -> str:
    b = resume.BUDGETS
    return TAILOR_SYSTEM.format(
        summary_min=b["summary_min_words"], summary_max=b["summary_max_words"],
        skills_max=b["technical_skills_max_words"],
        bullet_min=b["bullet_min_words"], bullet_max=b["bullet_max_words"])


def _validate_patch(patch: dict) -> list[str]:
    problems = []
    bullets = patch.get("top_bullets") or []
    if len(bullets) != 2:
        problems.append(f"top_bullets must have exactly 2 entries (got {len(bullets)}).")
    for key in ("summary", "technical_skills"):
        if not (patch.get(key) or "").strip():
            problems.append(f"{key} is empty.")
    return problems


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

    # 5. Render + final check ------------------------------------------------------
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

    # 6. Brain call 2: senior-reviewer score ---------------------------------------
    score_user = ("JOB DESCRIPTION:\n" + jd_text.strip()
                  + "\n\nTAILORED RESUME (Markdown):\n" + tailored_md.strip())
    verdict = brain.structured("score", system=scorer._SCORER_SYSTEM, user=score_user,
                               schema=scorer.SCORE_SCHEMA, max_tokens=2000)

    # 7. Record ---------------------------------------------------------------------
    kw = ats.ats_score(jd_text, master)["score"]
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
        notes="; ".join(check["problems"]) if check["problems"] else "",
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
