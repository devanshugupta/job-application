"""Question bank — data-driven answers for application-form questions.

The old form filler hardcoded employer-specific question patterns (Amazon, Twitch)
and the answer logic in Python. All of that now lives in ``config/question_bank.json``
— regex label patterns mapped to answer templates — so adding a new question type
is a config edit, not a code change. This module resolves an entry against the
user's profile and hands (text_value, dropdown_keywords) to whichever portal
filler matched a label (Greenhouse today; Lever/Ashby can reuse it).
"""

from __future__ import annotations

import json
import re

from .. import config


def load_bank() -> list[dict]:
    if not config.QUESTION_BANK_PATH.exists():
        return []
    return json.loads(config.QUESTION_BANK_PATH.read_text()).get("questions", [])


def build_context(profile: dict) -> dict:
    """Flatten profile.json into the placeholder/bool context the bank references."""
    personal = profile.get("personal", {})
    links = profile.get("links", {})
    work = profile.get("work_authorization", {})
    edu = profile.get("education", {})
    prefs = profile.get("preferences", {})
    experience = profile.get("experience") or [{}]

    full = (personal.get("full_name") or "").split(" ", 1)
    location = personal.get("location", "")
    current = next(
        (e for e in experience
         if (e.get("end") or "").lower() in ("present", "current", "")), experience[0])

    amazon_employee = "amazon" in (current.get("company") or "").lower()

    return {
        "placeholders": {
            "first_name": full[0] if full else "",
            "last_name": full[1] if len(full) > 1 else "",
            "email": personal.get("email", ""),
            "phone": personal.get("phone", ""),
            "city": location.split(",")[0].strip() if location else "",
            "state": location.split(",")[0].strip() if location else "",
            "linkedin": links.get("linkedin", ""),
            "github": links.get("github", ""),
            "website": links.get("website", "") or links.get("github", ""),
            "school": edu.get("school", ""),
            "degree": edu.get("degree", ""),
            "citizenship": work.get("citizenship_country", ""),
            "visa_status": work.get("visa_status", ""),
            "current_employer": current.get("company", ""),
            "location_preference": prefs.get("location_preference", "Remote"),
            "decline": "I don't wish to answer",
        },
        "bools": {
            "authorized": bool(work.get("authorized_to_work")),
            "sponsorship": bool(work.get("requires_sponsorship")),
            "held_h1b": bool(work.get("held_h1b_6years")),
            "amazon_employee": amazon_employee,
            "open_to_relocation": bool(prefs.get("open_to_relocation", True)),
        },
    }


def _fill_placeholders(value: str, ctx: dict) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: str(ctx["placeholders"].get(m.group(1), "")),
                  value)


def resolve(entry: dict, ctx: dict) -> tuple[str, list[str]] | None:
    """Resolve one bank entry to (text_value, dropdown_keywords). None = skip field."""
    if entry.get("skip"):
        return None
    if "bool" in entry:
        val = ctx["bools"].get(entry["bool"], False)
        opts = ["Yes", "yes", "true"] if val else ["No", "no", "false"]
        text = opts[0]
        extra = [_fill_placeholders(o, ctx) for o in entry.get("extra_options", [])]
        # extra options only make sense on the affirmative side (e.g. relocation cities)
        return text, (opts + [e for e in extra if e]) if val else opts
    text = _fill_placeholders(entry.get("text", ""), ctx)
    opts = [_fill_placeholders(o, ctx) for o in entry.get("options", [])]
    return text, [o for o in opts if o]


def answer_for_label(label_text: str, ctx: dict,
                     bank: list[dict] | None = None) -> tuple[str, list[str]] | None:
    """Match a form label against the bank. Returns (text, options) or None.

    None means either no entry matched OR the matched entry says 'skip' — in both
    cases the filler must leave the field to the human.
    """
    label = label_text.strip().lower()
    if not label:
        return None
    for entry in (bank if bank is not None else load_bank()):
        if any(re.search(p, label, re.I) for p in entry.get("match", [])):
            return resolve(entry, ctx)
    return None
