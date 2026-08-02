"""Deterministic Lever application-form fill  no LLM, no API key.

Mirrors tools/ashby.py for Lever-hosted postings (jobs.lever.co/<org>/<uuid>). Lever
renders a plain HTML form with stable field names (name / email / phone / org /
urls[LinkedIn] / urls[GitHub] / resume / location), so this is the simplest of the
three ATS fillers. Standard fields fill from profile.json; labeled custom questions
resolve through greenhouse.py's shared helpers; then we STOP for the human to review
and submit  nothing is submitted automatically, exactly like the Greenhouse and
Ashby flows.
"""

from __future__ import annotations

import time

from . import greenhouse as gh
from .browser import Browser

# Lever's standard application fields, by input name  stable across orgs.
_FIELDS = {
    "name":            lambda p, l: p.get("full_name", ""),
    "email":           lambda p, l: p.get("email", ""),
    "phone":           lambda p, l: p.get("phone", ""),
    "org":             lambda p, l: p.get("current_company", ""),
    "location":        lambda p, l: p.get("location", ""),
    "urls[LinkedIn]":  lambda p, l: l.get("linkedin", ""),
    "urls[GitHub]":    lambda p, l: l.get("github", ""),
    "urls[Portfolio]": lambda p, l: l.get("portfolio", ""),
}


def fill_lever_form(browser: Browser, url: str, pdf_path: str,
                    profile_path: str | None = None) -> dict:
    """Navigate to a Lever application URL and fill the form (no submit).

    Returns {"filled": [...], "skipped": [...], "final_url": str}. Raises RuntimeError
    if the page doesn't look like a Lever form."""
    profile = gh._load_profile(profile_path)
    personal = profile.get("personal", {})
    links = profile.get("links", {})

    print("\nOpening application page …")
    # The posting page and the form differ by an /apply suffix; go straight to the form.
    form_url = url if url.rstrip("/").endswith("/apply") else url.rstrip("/") + "/apply"
    browser.open_page(form_url)
    page = browser.page

    if "lever.co" not in page.url.lower():
        raise RuntimeError(
            f"Page doesn't look like a Lever form.\nURL: {page.url}\n"
            "Use `fill` for Greenhouse/Ashby, or `apply` for other portals.")

    filled, skipped = [], []
    for name, getter in _FIELDS.items():
        value = getter(personal, links)
        if not value:
            continue
        if gh._fill_any(page, [f'input[name="{name}"]'], value):
            filled.append(name)
        else:
            skipped.append(name)

    # Resume upload (input[name="resume"] is a file input on every Lever form).
    try:
        up = page.query_selector('input[name="resume"]')
        if up:
            up.set_input_files(pdf_path)
            filled.append("resume")
            time.sleep(2)  # Lever parses the resume server-side; let it settle
    except Exception as e:
        skipped.append(f"resume ({e})")

    # Custom questions (cards)  resolve labeled questions against the profile via the
    # shared question-bank logic; anything unresolved is left for the human.
    try:
        gh._fill_labeled_questions(page, profile)
    except Exception:
        pass

    print("\nForm filled  review it in the browser and click Submit yourself.")
    return {"filled": filled, "skipped": skipped, "final_url": page.url}
