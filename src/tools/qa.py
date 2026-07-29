"""QA self-check — verifies each pipeline step did a good job, and writes down issues.

The agent calls `qa_check(step, context)` after each meaningful step. We run cheap,
deterministic checks per step type (no extra LLM call), decide pass/fail, list concrete
issues, and append the verdict to the run log (runlog.py). The agent should react to a
failed check (fix and retry) and the issues become a written record on the dashboard.

This is intentionally rule-based so it's free and predictable. For judgment-heavy quality
(does a bullet actually read well?) we already have the LLM `score_resume` tool — qa here
catches the mechanical "did this step even work" failures that should never slip through.
"""

from __future__ import annotations

from . import runlog


def qa_check(step: str, context: dict) -> dict:
    """Check one step. Returns {ok, issues, step}. Also appends to the run log.

    context keys vary by step (all optional; checks degrade gracefully):
      open_page:       {url, final_url, page_text}
      classify_portal: {portal, strategy, needs_login, captcha}
      tailor:          {patch}  (the applied resume patch)
      lint:            {lint_result}  (output of resume.lint)
      score:           {score_result}  (output of scorer.score_resume)
      find:            {posted_date, is_fresh, match_score}
      fill_form:       {filled, total}
      submit:          {confirmed, screenshot}
    """
    issues: list[str] = []
    target = context.get("url") or context.get("target") or ""

    if step == "open_page":
        final = context.get("final_url", "")
        txt = context.get("page_text", "") or ""
        if "login" in final.lower() or "sign-in" in final.lower():
            issues.append("Redirected to a login page — content may be gated.")
        if len(txt) < 200:
            issues.append("Very little page text extracted — page may not have loaded.")

    elif step == "classify_portal":
        if context.get("captcha"):
            issues.append("CAPTCHA present — must hand off to human.")
        if context.get("needs_login"):
            issues.append("Portal needs login — ensure the persistent profile is signed in.")
        if context.get("portal") == "unknown":
            issues.append("Portal type unknown — using generic form mapping (verify fields).")

    elif step == "tailor":
        patch = context.get("patch", {}) or {}
        if not patch.get("top_bullets"):
            issues.append("No top_bullets in patch — the two key JD-aligned bullets are missing.")
        elif len(patch.get("top_bullets", [])) < 2:
            issues.append("Fewer than 2 top bullets — both first bullets must hit the JD.")
        if not patch.get("technical_skills"):
            issues.append("No technical_skills line tailored.")

    elif step == "lint":
        lint = context.get("lint_result", {}) or {}
        if not lint.get("ok", True):
            for i in lint.get("issues", []):
                issues.append(f"lint: {i}")

    elif step == "score":
        sc = context.get("score_result", {}) or {}
        verdict = sc.get("verdict")
        score = sc.get("overall_score")
        if verdict in ("weak", "true_mismatch"):
            issues.append(f"Score verdict '{verdict}' (score {score}/10) — apply top_fixes.")
            for f in sc.get("top_fixes", [])[:3]:
                issues.append(f"fix: {f}")

    elif step == "find":
        if not context.get("is_fresh", False):
            issues.append(f"Role not fresh (posted {context.get('posted_date')}) — excluded.")
        if (context.get("match_score") or 0) < 3:
            issues.append("Very low resume match — likely wrong role family.")

    elif step == "fill_form":
        filled, total = context.get("filled", 0), context.get("total", 0)
        if total and filled < total:
            issues.append(f"Only filled {filled}/{total} fields — some may be blank/unmapped.")

    elif step == "submit":
        if not context.get("confirmed"):
            issues.append("Submission not confirmed by human — did NOT submit.")
        if not context.get("screenshot"):
            issues.append("No confirmation screenshot captured.")

    ok = not issues
    runlog.log_step(step, ok, target=target, issues=issues,
                    detail=context.get("detail", ""))
    return {"ok": ok, "issues": issues, "step": step}
