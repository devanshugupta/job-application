"""Application-portal awareness.

Job applications live on very different portals, and the right strategy differs:
- Greenhouse / Lever / Ashby: usually a single public form, no login  easiest.
- Workday: almost always needs an account/login, multi-step, JS-heavy.
- Generic company form: best-effort field mapping.
- Unknown / CAPTCHA / SSO / login wall: stop and hand to the human.

This module gives a cheap, deterministic first guess from the URL + page snapshot so the
agent can pick a fill strategy (or back off) without spending a model call. The agent can
always override based on what it actually sees.

It also flags two things the user called out:
- needs_login: portals that gate the form behind auth (don't try to fill; hand off).
- prefilled: when a logged-in portal already populated fields from a PRIOR application
  in that case we should NOT rewrite them, only fill blanks / update the resume.

Credentials are NEVER handled here. Login happens in a human-authenticated persistent
browser profile (JOB_AGENT_USER_DATA_DIR).
"""

from __future__ import annotations

import re

# URL host fragments → portal id.
_HOST_SIGNATURES = {
    "greenhouse.io": "greenhouse",
    "boards.greenhouse": "greenhouse",
    "lever.co": "lever",
    "ashbyhq.com": "ashby",
    "myworkdayjobs.com": "workday",
    "wd1.myworkday": "workday",
    "wd5.myworkday": "workday",
    "icims.com": "icims",
    "taleo.net": "taleo",
    "smartrecruiters.com": "smartrecruiters",
    "workable.com": "workable",
}

# Portals that effectively require an account/login to apply.
_NEEDS_LOGIN = {"workday", "icims", "taleo"}

# Page-text signals for a login/auth wall.
_LOGIN_WALL = re.compile(
    r"\b(sign in|log in|create account|create an account|password|forgot password)\b",
    re.I,
)
# Only treat as a CAPTCHA WALL on signals of a VISIBLE challenge  human-facing prompt
# text, or an actual widget container/iframe. NOT a hidden token field like
# `h-captcha-response` / `g-recaptcha-response`, which ATS forms (Lever, Greenhouse)
# embed in every page and only activate on suspicion. Matching the hidden field made the
# agent wrongly bail on every Lever application.
_CAPTCHA = re.compile(
    r"are you a robot|verify you are human|please complete the (captcha|recaptcha)|"
    r"recaptcha-checkbox|g-recaptcha\b(?!-response)|h-captcha\b(?!-response)|"
    r"class=[\"']?[^\"'>]*captcha-(widget|container|challenge)",
    re.I,
)


def classify(url: str, page_text: str = "", snapshot: str = "") -> dict:
    """Classify the portal and recommend a strategy.

    Returns: {portal, needs_login, captcha, login_wall, prefilled, strategy, confidence}.
    """
    host = url.lower()
    portal = "unknown"
    confidence = 0.4
    for frag, pid in _HOST_SIGNATURES.items():
        if frag in host:
            portal = pid
            confidence = 0.9
            break

    text = f"{page_text}\n{snapshot}"
    captcha = bool(_CAPTCHA.search(text))
    login_wall = bool(_LOGIN_WALL.search(text))
    needs_login = portal in _NEEDS_LOGIN or login_wall

    # Returning-applicant heuristic: the snapshot shows inputs that already carry a
    # current value (we render "(current value: ...)" in browser snapshots).
    prefilled = "current value:" in snapshot

    if captcha:
        strategy = "handoff_captcha"
    elif portal in ("greenhouse", "lever", "ashby", "smartrecruiters", "workable"):
        strategy = "simple_form"
    elif portal == "workday":
        strategy = "workday_login_required"
    elif login_wall:
        strategy = "handoff_login"
    elif portal == "unknown":
        strategy = "generic_form"
    else:
        strategy = "generic_form"

    return {
        "portal": portal,
        "needs_login": needs_login,
        "captcha": captcha,
        "login_wall": login_wall,
        "prefilled": prefilled,
        "strategy": strategy,
        "confidence": confidence,
    }


# Human-readable guidance per strategy, surfaced to the agent.
STRATEGY_GUIDANCE = {
    "simple_form": "Public single-page form (Greenhouse/Lever/Ashby). Fill directly from "
    "the profile; upload the tailored resume PDF; confirm with the human before submit.",
    "workday_login_required": "Workday  needs a logged-in account. If the persistent "
    "browser profile is already logged in, proceed but CHECK for pre-filled fields from a "
    "prior application and DO NOT overwrite them  only fill blanks/update. If not logged "
    "in, open the page and hand to the human to log in, then resume.",
    "handoff_login": "A login wall is present. Hand to the human to authenticate in the "
    "persistent profile, then resume. Never enter credentials yourself.",
    "handoff_captcha": "CAPTCHA detected. Stop, screenshot, and hand to the human.",
    "generic_form": "Unknown/custom company form. Map profile fields to inputs best-effort; "
    "if structure is unclear or an account is required, ask the human.",
}
