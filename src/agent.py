"""The agent loop.

This is the core of the project and the part worth understanding. We give Claude a
set of *tools* (functions it can ask to run). Each turn, Claude either replies with
text or asks to call a tool. We execute the tool, hand the result back, and loop
until Claude stops asking for tools (``stop_reason == "end_turn"``).

This is the standard Anthropic "manual agentic loop". We keep it manual (rather than
using the SDK's auto tool-runner) precisely so every step is visible and hackable.

Multi-model note: ``model`` is a parameter on ``run_agent``. The CLI uses this to
run cheap tasks (scoring) on a smaller/faster model and the full apply flow on the
most capable one. See cli.py and CLAUDE.md.
"""

from __future__ import annotations

import json
import os

from . import config
from .tools import ats, final_check, llm, portals, qa, resume, scorer, tracker, usage
from .tools.browser import Browser

DEFAULT_MODEL = config.smart_model()
# Per-run output-token budget guard (anti-flagging / cost). 0 = unlimited.
TOKEN_BUDGET = config.token_budget()
# QA self-check is a TEMPORARY debugging aid. It's deterministic (no LLM cost itself),
# but the agent calling it spends a little reasoning per step. Off by default to keep
# end-to-end cost minimal; enable with JOB_AGENT_QA=1 when you want the audit trail.
QA_ENABLED = os.environ.get("JOB_AGENT_QA", "") == "1"

# ---------------------------------------------------------------------------
# Tool schemas  what Claude sees. Each maps to a Python function in _dispatch.
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "open_page",
        "description": "Navigate the browser to a URL and return an accessibility "
        "snapshot of the page's interactive elements.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "read_page",
        "description": "Re-read the current page and return a fresh snapshot. Call "
        "this after a click changes the page, or if refs go stale.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "click",
        "description": "Click an element by its ref id (e.g. 'e7') from the latest snapshot.",
        "input_schema": {
            "type": "object",
            "properties": {"ref": {"type": "string"}},
            "required": ["ref"],
        },
    },
    {
        "name": "type_text",
        "description": "Type text into an input/textarea by ref. Set submit=true to press Enter.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ref": {"type": "string"},
                "text": {"type": "string"},
                "submit": {"type": "boolean"},
            },
            "required": ["ref", "text"],
        },
    },
    {
        "name": "fill_form",
        "description": "Fill multiple fields at once.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fields": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ref": {"type": "string"},
                            "value": {"type": "string"},
                        },
                        "required": ["ref", "value"],
                    },
                }
            },
            "required": ["fields"],
        },
    },
    {
        "name": "upload_file",
        "description": "Upload a file (e.g. the resume PDF) to a file input by ref.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ref": {"type": "string"},
                "file_path": {"type": "string"},
            },
            "required": ["ref", "file_path"],
        },
    },
    {
        "name": "screenshot",
        "description": "Save a full-page screenshot (proof of submission).",
        "input_schema": {
            "type": "object",
            "properties": {"label": {"type": "string"}},
        },
    },
    {
        "name": "ats_score",
        "description": "Keyword-match a job description against resume text. Returns "
        "a 0-100 score plus matched/missing keywords.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_description": {"type": "string"},
                "resume_text": {"type": "string"},
            },
            "required": ["job_description", "resume_text"],
        },
    },
    {
        "name": "read_profile",
        "description": "Load the user's profile (personal info, skills, experience, "
        "preferences) for filling forms and tailoring materials.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_resume_rules",
        "description": "Load the mandatory resume-rewriting rules. Call this before "
        "tailoring the resume or writing bullets, and follow the rules exactly.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_master_resume",
        "description": "Load the user's master resume as Markdown (the cheap, "
        "structured source format) to tailor from.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "apply_resume_patch",
        "description": "Apply a minimal tailoring patch to the master resume. Provide "
        "ONLY the pieces that change: summary (<=2 lines), technical_skills (one tight "
        "line), and top_bullets (the first two bullets of the chosen experience block, "
        "which must hit the JD's top asks). Most of the resume stays untouched.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "technical_skills": {"type": "string"},
                "top_bullets": {"type": "array", "items": {"type": "string"}},
                "experience_section_index": {"type": "integer"},
                "company": {"type": "string"},
                "role": {"type": "string"},
                "url": {"type": "string"},
            },
        },
    },
    {
        "name": "lint_resume",
        "description": "Check the tailored resume against section budgets (summary "
        "length, technical-skills length, bullet word counts, repeated verbs, filler "
        "words). Pass the top_bullets you just wrote as focus_bullets so blocking "
        "'issues' cover what you changed and untouched master bullets show as "
        "'advisory'. Fix all 'issues', then lint again before rendering.",
        "input_schema": {
            "type": "object",
            "properties": {
                "focus_bullets": {"type": "array", "items": {"type": "string"}}
            },
        },
    },
    {
        "name": "render_resume_pdf",
        "description": "Render the tailored resume to a PDF for upload. If the profile has "
        "a LaTeX (.tex) master and pdflatex is installed, pass the same `patch` you used "
        "for apply_resume_patch and it renders the polished LaTeX version; otherwise it "
        "falls back to Markdown. Pass company/role/url so the PDF saves into the "
        "per-application folder and links on the dashboard.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "role": {"type": "string"},
                "url": {"type": "string"},
                "patch": {"type": "object"},
            },
        },
    },
    {
        "name": "score_resume",
        "description": "Have a strict SENIOR reviewer (hiring manager / Sr. SDE, not an "
        "ATS) score the tailored resume against the JD. Returns overall_score (0-100), "
        "verdict, per-dimension scores, gaps, and top_fixes. Call after tailoring; if "
        "verdict isn't 'strong', apply top_fixes and re-score ONCE (max 2 passes).",
        "input_schema": {
            "type": "object",
            "properties": {
                "jd_text": {"type": "string"},
                "resume_md": {"type": "string"},
            },
            "required": ["jd_text", "resume_md"],
        },
    },
    {
        "name": "classify_portal",
        "description": "Identify the application portal (Greenhouse/Lever/Ashby/Workday/"
        "generic) and the right fill strategy, plus whether login is needed or fields are "
        "already prefilled from a prior application. Call after opening an apply page.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "get_page_text",
        "description": "Return the visible text of the current page (e.g. to read a job "
        "description or a posted date)  cheaper than a full snapshot for prose.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "extract_job_links",
        "description": "Return the unique job-posting links on the CURRENT search-results "
        "page. Use the portal's own 'sort by most recent' URL param first, then call this "
        "per page, advancing the offset/page param, until dates fall outside the window.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "find_posted_date",
        "description": "Best-effort extract the posting date from the CURRENT (real "
        "company) page. Returns an ISO date or 'unverified'. Never trust LinkedIn/"
        "aggregator dates  only the real company page counts.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "save_application",
        "description": "Record an application/finding to the tracking file (feeds the "
        "dashboard). match_score = ATS keyword overlap 0-100 (from find). resume_score = "
        "the senior-reviewer overall_score 0-10 (from score_resume). Also include "
        "scorer_verdict, scorer_gaps, resume_diff (summary/technical_skills/top_bullets), "
        "source, posted_date, profile, and tailored_pdf when available.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "role": {"type": "string"},
                "url": {"type": "string"},
                "status": {"type": "string"},
                "fit_score": {"type": "number"},
                "ats_score": {"type": "integer"},
                "match_score": {"type": "integer"},
                "resume_score": {"type": "integer"},
                "scorer_verdict": {"type": "string"},
                "scorer_gaps": {"type": "array", "items": {"type": "string"}},
                "resume_diff": {"type": "object"},
                "source": {"type": "string"},
                "posted_date": {"type": "string"},
                "profile": {"type": "string"},
                "tailored_pdf": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["company", "role", "url", "status"],
        },
    },
    {
        "name": "final_check_resume",
        "description": "MANDATORY before declaring a tailored resume done or uploading it. "
        "Runs the final pre-flight checker on the tailored resume + rendered PDF: catches "
        "leftover template placeholders, fragment/short bullets, thin summary, filler, and "
        "broken/empty PDFs. If it returns ok=false, FIX the listed problems and re-render "
        "before continuing  never ship a resume with problems.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tailored_md": {"type": "string"},
                "pdf_path": {"type": "string"},
                "jd_text": {"type": "string"},
                "focus_bullets": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "qa_check",
        "description": "Self-check that a step did a good job; logs pass/fail + concrete "
        "issues to the run log (transparency). Call after each meaningful step (open_page, "
        "classify_portal, tailor, lint, score, find, fill_form, submit). If it returns "
        "ok=false, fix the issues before moving on.",
        "input_schema": {
            "type": "object",
            "properties": {
                "step": {"type": "string"},
                "context": {"type": "object"},
            },
            "required": ["step", "context"],
        },
    },
    {
        "name": "ask_human",
        "description": "Pause and ask the human operator a question. ALWAYS use this "
        "before submitting an application, sending a message, or any other "
        "irreversible action, and wait for their answer.",
        "input_schema": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
    },
]

# qa_check is a temporary, opt-in debugging aid  exclude it from the tool set (and the
# prompt's self-check step) unless JOB_AGENT_QA=1, to keep end-to-end cost minimal.
if not QA_ENABLED:
    TOOLS = [t for t in TOOLS if t["name"] != "qa_check"]


def _dispatch(
    name: str, args: dict, browser: Browser | None, profile: str | None,
    today: str | None = None,
) -> str:
    """Run a tool by name and return a string result for Claude.

    ``profile`` selects which master resume the resume tools operate on.
    ``today`` (ISO) lets date-aware tools resolve relative dates without a clock.
    """
    if name == "find_posted_date" and browser is not None:
        return browser.find_posted_date(today=today)
    if name == "final_check_resume":
        return json.dumps(final_check.check_resume(
            tailored_md=args.get("tailored_md"), pdf_path=args.get("pdf_path"),
            jd_text=args.get("jd_text", ""), focus_bullets=args.get("focus_bullets")))
    if name == "qa_check":
        return json.dumps(qa.qa_check(args["step"], args.get("context", {})))
    if name == "ask_human":
        print(f"\n🤖 Agent asks: {args['question']}")
        answer = input("👤 You: ").strip()
        return f"Human answered: {answer}"

    if name == "ats_score":
        return json.dumps(ats.ats_score(args["job_description"], args["resume_text"]))
    if name == "read_profile":
        return json.dumps(tracker.read_profile())
    if name == "read_resume_rules":
        return tracker.read_resume_rules()
    if name == "read_master_resume":
        return resume.read_master(profile)
    if name == "apply_resume_patch":
        return resume.apply_patch(
            {k: v for k, v in args.items() if k not in ("company", "role", "url")},
            profile=profile, company=args.get("company"), role=args.get("role"),
            url=args.get("url"),
        )
    if name == "lint_resume":
        return json.dumps(resume.lint(focus_bullets=args.get("focus_bullets")))
    if name == "render_resume_pdf":
        return resume.render_pdf(company=args.get("company"), role=args.get("role"),
                                 url=args.get("url"), profile=profile,
                                 patch=args.get("patch"))
    if name == "score_resume":
        return json.dumps(scorer.score_resume(args["jd_text"], args["resume_md"]))
    if name == "classify_portal":
        text = browser.get_page_text() if browser else ""
        snap = browser.read_page() if browser else ""
        result = portals.classify(args["url"], page_text=text, snapshot=snap)
        result["guidance"] = portals.STRATEGY_GUIDANCE.get(result["strategy"], "")
        return json.dumps(result)
    if name == "save_application":
        return json.dumps(tracker.save_application(**args))

    # Everything else is a browser action.
    if browser is None:
        return "ERROR: browser not available for this run."
    method = getattr(browser, name, None)
    if method is None:
        return f"ERROR: unknown tool {name}"
    return method(**args)


def run_agent(
    task: str,
    *,
    model: str = DEFAULT_MODEL,
    browser: Browser | None = None,
    max_turns: int = 40,
    verbose: bool = True,
    profile: str | None = None,
    system: str | None = None,
    token_budget: int = TOKEN_BUDGET,
    today: str | None = None,
    usage_label: str = "",
    task_kind: str = "tailor",
) -> str:
    """Run the agent loop for a single task and return Claude's final text.

    Args:
        task: the instruction (built by the CLI per command).
        model: which Claude model to use  lets callers pick cheap vs. capable.
        browser: a live Browser, or None for tasks that need no web access.
        max_turns: safety cap on the loop.
        profile: which master-resume profile the resume tools operate on.
        system: override system prompt (e.g. the finder prompt); defaults to apply prompt.
        token_budget: abort if cumulative OUTPUT tokens exceed this (0 = unlimited).
            Cost / anti-flagging guard.
        today: exact current date (ISO 'YYYY-MM-DD'), injected so freshness math is
            correct  the model has no reliable clock.
    """
    # Route this run to a provider (Claude or OpenAI) based on the task kind. The caller's
    # `model` is used only when it matches the resolved provider; otherwise we use that
    # provider's configured model. This lets tailoring run on Claude while find/score can
    # run on OpenAI (or any mix)  see tools/llm.py.
    prov = llm.provider_for(task_kind)
    if model == DEFAULT_MODEL or (prov == "openai" and model.startswith("claude")):
        model = llm.model_for(prov)
    if today:
        task = f"TODAY'S DATE is {today}. Use it for all recency/freshness math.\n\n{task}"
    # Mark the big stable block with cache_control so repeat turns read it from cache
    # (~0.1x) instead of full price  the single biggest token win in a multi-turn loop.
    sys_text = system or _SYSTEM_PROMPT
    if not QA_ENABLED:
        # Drop self-check instructions so the agent doesn't try to call a tool that
        # isn't in its set (and to save the per-step reasoning). Lines mentioning qa.
        sys_text = "\n".join(
            ln for ln in sys_text.splitlines()
            if "qa_check" not in ln and not ln.strip().startswith("- SELF-CHECK")
        )
    messages = [{"role": "user", "content": task}]
    # Track input/output/cache tokens + cost for THIS run (one application). The per-run
    # ceiling (token_budget) stops a single application from burning the whole budget.
    meter = usage.UsageMeter(model=model, label=f"[{prov}] {usage_label}".strip(),
                             max_total_tokens=token_budget)

    def _finish(result: str) -> str:
        meter.record()  # persist this application's usage to data/usage_log.jsonl
        if verbose:
            print(f"\n💸 {meter.summary()}")
        return result

    for turn in range(max_turns):
        resp = llm.run_turn(provider=prov, model=model, system=sys_text,
                            messages=messages, tools=TOOLS, max_tokens=8000)
        meter.add(resp["usage"])  # dict usage from the shim
        messages.append(resp["raw_assistant"])  # provider-native assistant turn

        if resp["stop"] != "tool_use":
            final = resp["text"]
            if verbose and final:
                print(f"\n✅ {final}")
            return _finish(final)

        # Per-run token-budget guard: stop politely before runaway cost on ONE application.
        try:
            meter.check()
        except usage.BudgetExceeded as e:
            return _finish(f"Stopped: {e}")

        # Execute every tool the model requested this turn.
        results = []
        for call in resp["tool_calls"]:
            if verbose:
                print(f"  ⚙️  {call['name']}({_short(call['input'])})")
            try:
                out = _dispatch(call["name"], call["input"], browser, profile, today)
            except Exception as e:  # surface errors to the model so it can recover
                out = f"ERROR running {call['name']}: {e}"
            results.append(
                {"type": "tool_result", "tool_use_id": call["id"], "content": out}
                )
        messages.append({"role": "user", "content": results})

    return _finish("Reached max turns without finishing. Inspect the transcript above.")


def _short(d: dict, n: int = 80) -> str:
    s = json.dumps(d)
    return s if len(s) <= n else s[:n] + "..."


_SYSTEM_PROMPT = """You are a careful job-application assistant operating a real web browser.

Principles you MUST follow:
- HONESTY: Only ever use real information from the user's profile and resume. Never
  invent skills, employers, dates, or metrics. Tailoring means re-ordering and
  emphasizing true content, not fabricating it.
- HUMAN-IN-THE-LOOP: Before you submit an application, send any message, or take any
  other irreversible action, call `ask_human` and wait for explicit approval.
- TRANSPARENCY: Narrate what you're doing in short notes between tool calls.
- POLITENESS / ANTI-FLAGGING: Act like a human, not a scraper. One action at a time;
  don't bulk-fire. On a CAPTCHA, login wall, or SSO, STOP, screenshot, and ask_human 
  never try to defeat them and never enter credentials yourself.
- SELF-CHECK (only if qa_check tool is present): after each meaningful step call qa_check(step, context); if it returns ok=false, FIX the issues before continuing.

Workflow for applying to a job:
1. read_profile to load the user's details. read_master_resume to see the resume.
2. open_page on the job URL; get_page_text to read the description.
3. classify_portal to learn the portal + strategy. If it needs login or shows a
   CAPTCHA/SSO and you're not logged in, ask_human to log in (persistent profile), then
   resume. If fields are already PREFILLED from a prior application, do NOT overwrite
   them  only fill blanks / update what changed.
4. ats_score the description against the resume for a quick keyword read.
5. Judge fit. If clearly a poor fit / has dealbreakers, ask_human whether to continue.
6. If tailoring: read_resume_rules first, then apply_resume_patch (summary, technical
   skills, top-2 bullets), lint_resume (pass your top_bullets as focus_bullets), fix any
   blocking issues, then score_resume. If verdict isn't 'strong', apply its top_fixes and
   re-score ONCE (max 2 passes total  don't loop further). render_resume_pdf.
6b. MANDATORY: final_check_resume(tailored_md, pdf_path, jd_text, focus_bullets) before
   using the resume. If it returns ok=false, FIX every problem (e.g. expand fragment
   bullets, remove placeholders, re-render) and re-check until ok=true. Never upload a
   resume that failed the final check.
7. Fill the form from the profile (fill_form / type_text / upload_file for the PDF).
   Handle multi-step forms by reading the page after each step.
8. Before the final submit, ask_human to confirm. Only submit on approval.
9. screenshot the confirmation, then save_application  include match_score,
   scorer_verdict, scorer_gaps, resume_diff (what you changed), source, posted_date,
   profile, and tailored_pdf so the dashboard is complete.

Use refs (e.g. 'e7') from the most recent snapshot. If refs seem stale, call read_page.

RESUME TAILORING RULES (full version via read_resume_rules  these always apply):
- First UNDERSTAND THE ROLE, don't pattern-match words. Ignore JD fluff (mission,
  benefits, "are you passionate about..."); it contributes nothing. Then build THREE
  lists: (1) explicit demands from responsibilities+qualifications; (2) the
  practitioner's toolkit  adjacent tech a strong candidate would have touched even if
  unlisted (e.g. "ETL" implies Kafka/S3/SQS/Airflow/Spark; "search relevance" implies
  two-tower/FAISS/ranking); (3) expected WORK-TYPES as activities the reviewer expects
  to see described (e.g. data eng → ran a data migration, built BI dashboards, designed
  schemas; robotics deploy → led on-site installs, commissioned equipment). Take the
  union, then KEEP ONLY what the candidate genuinely has. Use survivors to pick the
  Technical Skills line and to reframe true bullets so they describe those work-types
  in the role's language. Never add a tool or activity the candidate hasn't done.
- The TOP TWO bullets of the most relevant role must map directly to the JD's top
  asks, in the JD's own wording. THIS HOLDS EVEN FOR WEAK-MATCH JOBS  always force
  the first two bullets to adhere to the job profile (using only true content).
- Fold the JD's exact keywords in where truthful (don't keyword-stuff, don't lie).
- Every bullet uses the XYZ rule: "Accomplished X by doing Y, measured by Z"  lead
  with impact, not the task.
- Readable, plain language. No filler words ("responsible for", "helped"). Do NOT
  repeat the same adjective or strong verb twice across the bullet set.
- Each bullet is a FULL one-line sentence of ~16-28 words (NOT a clipped fragment;
  under ~14 words is too thin  expand with the missing X/Y/Z detail). Summary = 2 full
  lines (~30-45 words). Tailoring re-frames toward the JD; it never strips metrics/detail.
- Skim test: someone reading only the top lines should feel "this is the right person."
"""


# The job-FINDER system prompt lives in src/prompts.py (FINDER_SYSTEM).
from .prompts import FINDER_SYSTEM as _FINDER_SYSTEM  # noqa: E402,F401
