"""Deterministic Greenhouse form filler  no LLM required.

Greenhouse has a consistent form structure across all companies that use it.
This module fills the form directly from profile.json + a tailored PDF.

Handles:
- Standard fields: first/last name, email, phone, location
- Links: LinkedIn, website/portfolio, GitHub
- Resume upload
- Work authorisation radio buttons
- EEO/demographic dropdowns (defaults to "Decline" / "Prefer not to say")
- Human confirmation before submit
"""

from __future__ import annotations

import json
import pathlib
import shutil
import time

from .browser import Browser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_profile(path: str | None = None) -> dict:
    from .. import config
    return json.loads(pathlib.Path(path or config.PROFILE_PATH).read_text())


def _fill(page, selector: str, value: str, skip_if_filled: bool = True) -> bool:
    """Fill one field. Returns True on success. Skips if already has a value."""
    if not value:
        return False
    try:
        el = page.query_selector(selector)
        if el and el.is_visible():
            if skip_if_filled:
                existing = (el.get_attribute("value") or "").strip()
                if existing:
                    return True   # already filled  don't overwrite
            el.fill(value)
            time.sleep(0.25)
            return True
    except Exception:
        pass
    return False


def _fill_any(page, selectors: list[str], value: str) -> bool:
    for sel in selectors:
        if _fill(page, sel, value):
            return True
    return False


def _select_option(page, selector: str, keywords: list[str]) -> bool:
    """Pick the first <option> whose text contains any of the keywords (case-insensitive)."""
    try:
        el = page.query_selector(selector)
        if not el or not el.is_visible():
            return False
        options = el.query_selector_all("option")
        for kw in keywords:
            for opt in options:
                text = opt.inner_text().strip().lower()
                if kw.lower() in text:
                    val = opt.get_attribute("value") or text
                    page.select_option(selector, value=val)
                    time.sleep(0.2)
                    return True
    except Exception:
        pass
    return False


def _open_and_pick(page, clickable, keywords: list[str]) -> bool:
    """Click one candidate control, poll for [role=option]s, click the first keyword match.
    Returns True only if an option was actually selected. Never raises."""
    try:
        clickable.scroll_into_view_if_needed(timeout=1000)
    except Exception:
        pass
    for _ in range(2):
        try:
            clickable.click(timeout=2000)
        except Exception:
            return False
        opts: list = []
        for _ in range(10):                      # poll up to ~3 s for the menu to open
            opts = page.query_selector_all('[role="option"]') or page.query_selector_all(
                '[class*="__option"], [class*="-option"], li[role="option"], [role="menuitem"]')
            if opts:
                break
            time.sleep(0.3)
        if opts:
            for kw in keywords:
                for opt in opts:
                    try:
                        text = opt.inner_text().strip()
                        if text and kw.lower() in text.lower():
                            opt.click()
                            time.sleep(0.8)
                            return True
                    except Exception:
                        continue
            try:                                  # options opened but none matched  close
                page.keyboard.press("Escape")
            except Exception:
                pass
            return False
        time.sleep(0.4)                           # nothing opened  retry the click once
    return False


def _select_react_dropdown(page, input_id: str, keywords: list[str]) -> bool:
    """Pick an option from a react-select / Ashby / custom combobox by keyword.

    The clickable that OPENS the menu isn't always the labeled input  for Ashby it's a
    wrapper div/button. So we try several candidates (the element, then its combobox /
    select-control / dropdown ancestor) until one actually opens a [role=option] list.
    Works across Greenhouse, Ashby, and custom themes via ARIA roles. Never raises."""
    try:
        el = page.query_selector(f"[id='{input_id}']")
        if not el:
            return False
        candidates = [el]
        try:
            wrap = el.evaluate_handle(
                "e => e.closest('[role=combobox],[class*=select__control],[class*=Select],"
                "[class*=dropdown],[class*=combobox],[data-ashby-field-container]') "
                "|| e.parentElement")
            node = wrap.as_element() if wrap else None
            if node:
                candidates.append(node)
        except Exception:
            pass
        for c in candidates:
            if _open_and_pick(page, c, keywords):
                return True
    except Exception:
        pass
    return False


def _fill_education(target, profile: dict) -> bool:
    """Fill the Greenhouse education section.

    Greenhouse education HTML:
      - School name: react-select where the CONTAINER has id=education_school_name_0.
        The <input> inside has a generated ID unrelated to 'school', so we find the
        container and type into whichever <input> lives inside it.
      - Degree / Discipline: native <select> elements (id=education_degree_0 / _discipline_0).
      - End year: plain text <input> (NOT a <select>  _select_option would miss it).
      - End month: native <select>.
    """
    edu         = profile.get("education", {})
    school_name = edu.get("school", "")
    degree_str  = edu.get("degree", "")
    graduation  = edu.get("graduation", "")
    grad_year   = graduation[:4] if graduation else ""
    grad_month  = int(graduation[5:7]) if len(graduation) >= 7 else 0
    _months     = ["January","February","March","April","May","June",
                   "July","August","September","October","November","December"]
    grad_month_name = _months[grad_month - 1] if 0 < grad_month <= 12 else ""
    degree_kws  = (
        ["Master", "M.S.", "MS"] if "master" in degree_str.lower()
        else ["Bachelor", "B.S.", "BS"] if "bachelor" in degree_str.lower()
        else []
    )

    filled_any = False

    # --- School: container has the meaningful ID; input inside has a generated one ---
    if school_name:
        container = target.query_selector(
            "[id*='school_name'], [id*='education_school']"
        )
        if container:
            inp = container.query_selector("input")
            if inp:
                inp.fill(school_name)
                # Poll for react-select options
                opts = []
                for _ in range(10):
                    opts = target.query_selector_all('[role="option"]')
                    if opts:
                        break
                    time.sleep(0.3)
                for opt in opts:
                    try:
                        if school_name[:6].lower() in opt.inner_text().lower():
                            opt.click()
                            time.sleep(0.5)
                            filled_any = True
                            break
                    except Exception:
                        continue
                if not filled_any:
                    try:
                        inp.press("Escape")
                    except Exception:
                        pass

    # --- Degree: native <select> ---
    if degree_kws:
        for sel in ["select[id*='degree']", "select[name*='degree']"]:
            if _select_option(target, sel, degree_kws):
                filled_any = True
                break

    # --- Discipline: native <select> ---
    for sel in ["select[id*='discipline']", "select[name*='discipline']"]:
        if _select_option(target, sel, ["Computer Science", "Computer"]):
            filled_any = True
            break

    # --- End year: TEXT INPUT (not a select) ---
    if grad_year:
        for sel in ["input[id*='end_year']", "input[name*='end_year']"]:
            if _fill(target, sel, grad_year, skip_if_filled=False):
                filled_any = True
                break

    # --- End month: native <select> ---
    if grad_month_name:
        for sel in ["select[id*='end_month']", "select[name*='end_month']"]:
            if _select_option(target, sel, [grad_month_name, grad_month_name[:3]]):
                filled_any = True
                break

    return filled_any


def _click_radio(page, name: str, keywords: list[str]) -> bool:
    """Click a radio button whose label contains any keyword."""
    try:
        radios = page.query_selector_all(f"input[type='radio'][name*='{name}']")
        for kw in keywords:
            for r in radios:
                label_for = r.get_attribute("id") or ""
                label_el = page.query_selector(f"label[for='{label_for}']")
                label_text = (label_el.inner_text() if label_el else "").lower()
                if kw.lower() in label_text or kw.lower() in (r.get_attribute("value") or "").lower():
                    r.click()
                    time.sleep(0.2)
                    return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Label-based question filler (handles custom question_XXXXX fields)
# ---------------------------------------------------------------------------

def _fill_labeled_questions(target, profile: dict) -> None:
    """Fill labeled inputs/dropdowns by matching label text against the question bank.

    All question patterns + answers live in config/question_bank.json (resolved
    against the profile by forms.py)  nothing employer-specific is hardcoded here.
    Unmatched and "skip" questions are left for the human to review.
    """
    from . import forms

    bank = forms.load_bank()
    ctx = forms.build_context(profile)

    try:
        labels = target.query_selector_all("label[for]")
        for lbl in labels:
            for_id = lbl.get_attribute("for") or ""
            lbl_txt = lbl.inner_text().strip()
            if not for_id or not lbl_txt:
                continue
            answer = forms.answer_for_label(lbl_txt, ctx, bank)
            if answer is None:
                continue
            text_val, opts = answer

            el = target.query_selector(f"[id='{for_id}']")
            if not el:
                continue
            tag = el.evaluate("e => e.tagName.toLowerCase()")
            cls = el.get_attribute("class") or ""
            role = el.get_attribute("role") or ""
            haspopup = el.get_attribute("aria-haspopup") or ""
            # A field is a DROPDOWN if it's a native <select>, a react-select/combobox, or
            # simply if the answer is a set of choice-options (opts). In ALL those cases we
            # must click-and-pick  NEVER el.fill(), which throws/garbles on a combobox
            # (the bug that "breaks on dropdowns"). Text fill is only for real text inputs.
            is_dropdown = (
                tag == "select" or role in ("combobox", "listbox") or haspopup
                or "select__input" in cls or "select__control" in cls
                or ("select" in cls.lower() and tag != "input") or bool(opts))
            if is_dropdown:
                if tag == "select":
                    _select_option(target, f"[id='{for_id}']", opts or ([text_val] if text_val else []))
                else:
                    _select_react_dropdown(target, for_id, opts or ([text_val] if text_val else []))
            elif tag in ("input", "textarea") and text_val:
                existing = (el.get_attribute("value") or "").strip()
                if not existing:
                    try:
                        el.fill(text_val)
                        time.sleep(0.2)
                    except Exception:
                        pass  # not a fillable field after all  leave for the human
    except Exception as e:
        print(f"  Warning: labeled question fill error: {e}")


# ---------------------------------------------------------------------------
# Main filler
# ---------------------------------------------------------------------------

def fill_greenhouse_form(browser: Browser, url: str, pdf_path: str,
                         profile_path: str | None = None) -> dict:
    """Navigate to a Greenhouse application URL and fill the form.

    Returns {"filled": [...field names...], "skipped": [...], "final_url": str}.
    Raises RuntimeError if the page doesn't look like a Greenhouse form.
    """
    profile = _load_profile(profile_path)
    personal   = profile.get("personal", {})
    links      = profile.get("links", {})
    work_auth  = profile.get("work_authorization", {})
    defaults   = profile.get("application_defaults", {})

    full_name  = personal.get("full_name", "")
    name_parts = full_name.split(" ", 1)
    first_name = name_parts[0]
    last_name  = name_parts[1] if len(name_parts) > 1 else ""

    print("\nOpening application page …")
    browser.open_page(url)
    page = browser.page

    # Verify we landed on a Greenhouse form.
    # Greenhouse can be embedded on company domains  detect by URL param or page signals.
    raw_url  = page.url.lower()
    content  = page.content().lower()
    is_gh = (
        "greenhouse.io" in raw_url
        or "gh_jid=" in raw_url
        or "greenhouse" in content[:8000]
        or 'name="job_application' in content[:8000]
        or "grnh.se" in raw_url
    )
    if not is_gh:
        raise RuntimeError(
            f"Page doesn't look like a Greenhouse form.\nURL: {page.url}\n"
            "Check the URL or use `apply` for other portals."
        )

    # Greenhouse is often embedded as an iframe on company domains.
    # Prefer the iframe context if one exists, else use the main page.
    target = page
    for frame in page.frames:
        if "greenhouse" in frame.url.lower() or "grnh.se" in frame.url.lower():
            target = frame  # type: ignore[assignment]
            print(f"  (using Greenhouse iframe: {frame.url})")
            break

    filled:  list[str] = []
    skipped: list[str] = []

    def record(name: str, ok: bool) -> None:
        (filled if ok else skipped).append(name)

    # --- Personal fields -------------------------------------------------------
    record("first name",  _fill_any(target, [
        "input[name='first_name']", "input[id*='first_name']",
        "input[autocomplete='given-name']",
    ], first_name))

    record("last name", _fill_any(target, [
        "input[name='last_name']", "input[id*='last_name']",
        "input[autocomplete='family-name']",
    ], last_name))

    record("email", _fill_any(target, [
        "input[name='email']", "input[type='email']", "input[id*='email']",
    ], personal.get("email", "")))

    record("phone", _fill_any(target, [
        "input[name='phone']", "input[type='tel']", "input[id*='phone']",
    ], personal.get("phone", "")))

    # Phone country code dropdown (sits between Phone label and the number field)
    for sel in ["select[id*='phone_country']", "select[name*='phone_country']",
                "select[id*='country_code']",  "select[name*='country_code']"]:
        if _select_option(target, sel, ["United States", "us", "+1"]):
            break

    # Location (City)  Greenhouse uses an autocomplete text field
    city = personal.get("location", "New York").split(",")[0].strip()
    loc_filled = _fill_any(target, [
        "input[name='job_application[location]']",
        "input[id*='city']", "input[placeholder*='city' i]",
    ], city)
    if not loc_filled:
        for loc_sel in ["input[id*='location']", "input[placeholder*='location' i]"]:
            loc_inp = target.query_selector(loc_sel)
            if loc_inp:
                loc_inp.fill(city)
                time.sleep(1.5)
                sug = target.query_selector(
                    ".pac-item, [class*='suggestion'], [role='option']"
                )
                if sug:
                    sug.click()
                    time.sleep(0.5)
                    loc_filled = True
                break
    record("location", loc_filled)

    # --- Links -----------------------------------------------------------------
    record("LinkedIn", _fill_any(target, [
        "input[name='job_application[linkedin_url]']",
        "input[id*='linkedin']", "input[placeholder*='linkedin' i]",
    ], links.get("linkedin", "")))

    record("website", _fill_any(target, [
        "input[name='job_application[website]']",
        "input[id*='website']", "input[id*='portfolio']",
        "input[placeholder*='website' i]", "input[placeholder*='portfolio' i]",
    ], links.get("website", "")))

    record("GitHub", _fill_any(target, [
        "input[id*='github']", "input[placeholder*='github' i]",
    ], links.get("github", "")))

    # --- Education ---------------------------------------------------------------
    record("education", _fill_education(target, profile))

    # --- Fill labeled custom questions by inspecting label text ----------------
    _fill_labeled_questions(target, profile)

    # --- Resume upload ---------------------------------------------------------
    # Rename to "FirstName_LastName_Resume.pdf" before uploading so the recruiter
    # sees a proper filename instead of "zsAIEngineer.pdf".
    name_slug = personal.get("full_name", "Resume").replace(" ", "_")
    pdf_orig  = pathlib.Path(pdf_path).resolve()
    pdf       = pdf_orig.parent / f"{name_slug}_Resume.pdf"
    if pdf_orig.exists() and pdf_orig != pdf:
        shutil.copy2(pdf_orig, pdf)

    uploaded = False
    if pdf.exists():
        for sel in [
            "input[type='file'][id='resume']",
            "input[type='file'][name*='resume']",
            "input[type='file'][id*='resume']",
            "input[type='file']",
        ]:
            try:
                loc = target.locator(sel).first
                if loc.count() > 0:
                    loc.set_input_files(str(pdf))
                    time.sleep(0.8)
                    uploaded = True
                    break
            except Exception:
                pass
    record("resume PDF", uploaded)

    # --- Work authorisation & visa questions -----------------------------------
    auth_kw    = ["yes", "true"] if work_auth.get("authorized_to_work") else ["no", "false"]
    sponsor_kw = ["yes", "true"] if work_auth.get("requires_sponsorship") else ["no", "false"]

    _click_radio(target, "authoriz", auth_kw)
    _click_radio(target, "legally_authorized", auth_kw)
    for sel in ["select[id*='authoriz']", "select[name*='authoriz']",
                "select[id*='legally']", "select[name*='legally']"]:
        _select_option(target, sel, auth_kw + ["yes, i am"])

    _click_radio(target, "sponsor", sponsor_kw)
    _click_radio(target, "visa_sponsor", sponsor_kw)
    for sel in ["select[id*='sponsor']", "select[name*='sponsor']",
                "select[id*='visa']", "select[name*='visa']"]:
        _select_option(target, sel, sponsor_kw)

    # Visa/work status dropdown
    visa = work_auth.get("visa_status", "")
    if visa:
        for sel in ["select[id*='visa']", "select[name*='visa']",
                    "select[id*='work_status']", "select[name*='work_status']",
                    "select[id*='citizenship']", "select[name*='citizenship']"]:
            _select_option(target, sel, [visa, "opt", "f-1", "f1"])

    # --- EEO / demographic dropdowns (default: decline / prefer not to say) ---
    decline_kws = ["decline", "prefer not", "i don't", "i do not", "choose not"]

    gender_val = defaults.get("gender", "Prefer not to say")
    for sel in ["select[id*='gender']", "select[name*='gender']"]:
        _select_option(target, sel, [gender_val] + decline_kws)

    race_val = defaults.get("race_ethnicity", "Prefer not to say")
    for sel in ["select[id*='race']", "select[name*='race']",
                "select[id*='ethnicity']", "select[name*='ethnicity']"]:
        _select_option(target, sel, [race_val] + decline_kws)

    veteran_val = defaults.get("veteran_status", "Prefer not to say")
    for sel in ["select[id*='veteran']", "select[name*='veteran']"]:
        _select_option(target, sel, [veteran_val] + decline_kws)

    disability_val = defaults.get("disability_status", "Prefer not to say")
    for sel in ["select[id*='disability']", "select[name*='disability']"]:
        _select_option(target, sel, [disability_val] + decline_kws)

    return {"filled": filled, "skipped": skipped, "final_url": page.url}


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------

def submit_greenhouse_form(browser: Browser) -> bool:
    """Click the submit button. Returns True if the page changed (success signal)."""
    page = browser.page
    url_before = page.url
    for sel in [
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Submit Application')",
        "button:has-text('Submit')",
    ]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                page.wait_for_load_state("networkidle", timeout=15_000)
                return page.url != url_before or "thank" in page.content().lower()
        except Exception:
            pass
    return False
