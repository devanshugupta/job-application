"""Deterministic Ashby application-form fill  no LLM, no API key.

Mirrors tools/greenhouse.py for Ashby-hosted postings (jobs.ashbyhq.com/<org>/<uuid>).
Ashby renders a React form, so we wait for it, fill the standard fields (name / email /
phone / links / resume) plus any labeled questions resolved against the profile
(forms.py), then STOP for the human to review and submit. Nothing is submitted
automatically  the human confirms and clicks Submit in the browser, exactly like the
Greenhouse flow.

Reuses greenhouse.py's field-fill primitives (`_fill_any`, `_click_radio`,
`_fill_labeled_questions`, `_load_profile`) so there's one implementation of the
profile-to-field logic; only the Ashby-specific selectors + React-render waits live here.
"""

from __future__ import annotations

import pathlib
import shutil
import time

from . import forms, greenhouse as gh
from .browser import Browser


def fill_ashby_form(browser: Browser, url: str, pdf_path: str,
                    profile_path: str | None = None) -> dict:
    """Navigate to an Ashby application URL and fill the form (no submit).

    Returns {"filled": [...], "skipped": [...], "final_url": str}. Raises RuntimeError if
    the page doesn't look like an Ashby form.
    """
    profile = gh._load_profile(profile_path)
    personal = profile.get("personal", {})
    links = profile.get("links", {})
    work_auth = profile.get("work_authorization", {})
    full_name = personal.get("full_name", "")

    print("\nOpening application page …")
    browser.open_page(url)
    page = browser.page

    content = page.content().lower()
    if "ashbyhq.com" not in page.url.lower() and "ashby" not in content[:8000]:
        raise RuntimeError(
            f"Page doesn't look like an Ashby form.\nURL: {page.url}\n"
            "Use `fill` for Greenhouse, or `apply` for other portals.")

    # Ashby often shows the JD first with an "Apply"/"Application" button that reveals
    # the form; click it if present, then wait for the React form to render.
    for sel in ("a:has-text('Apply for this Job')", "button:has-text('Apply for this Job')",
                "button:has-text('Apply')", "a:has-text('Application')"):
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                page.wait_for_timeout(1500)
                break
        except Exception:
            pass
    try:
        page.wait_for_selector("input[type='email'], input[name*='email' i], form",
                               timeout=20_000)
    except Exception:
        pass

    filled: list[str] = []
    skipped: list[str] = []

    def rec(name: str, ok: bool) -> None:
        (filled if ok else skipped).append(name)

    # Ashby uses a single Name field (system field _systemfield_name), not first/last.
    rec("name", gh._fill_any(page, [
        "input[name='_systemfield_name']", "input[name*='name' i]",
        "input[id*='name' i]", "input[aria-label*='name' i]"], full_name))
    rec("email", gh._fill_any(page, [
        "input[name='_systemfield_email']", "input[type='email']",
        "input[name*='email' i]", "input[id*='email' i]"], personal.get("email", "")))
    if personal.get("phone"):
        rec("phone", gh._fill_any(page, [
            "input[type='tel']", "input[name*='phone' i]", "input[id*='phone' i]"],
            personal["phone"]))
    for key in ("linkedin", "github"):
        if links.get(key):
            gh._fill_any(page, [f"input[name*='{key}' i]", f"input[id*='{key}' i]",
                                f"input[aria-label*='{key}' i]"], links[key])

    # Resume upload  rename to "First_Last_Resume.pdf" first (like greenhouse) so the
    # recruiter sees a proper filename.
    name_slug = (full_name.replace(" ", "_") or "Resume")
    pdf_orig = pathlib.Path(pdf_path).resolve()
    pdf = pdf_orig.parent / f"{name_slug}_Resume.pdf"
    if pdf_orig.exists() and pdf_orig != pdf:
        shutil.copy2(pdf_orig, pdf)
    uploaded = False
    if pdf.exists():
        for sel in ("input[type='file'][name*='resume' i]",
                    "input[type='file'][id*='resume' i]", "input[type='file']"):
            try:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    loc.set_input_files(str(pdf))
                    time.sleep(1.0)
                    uploaded = True
                    break
            except Exception:
                pass
    rec("resume PDF", uploaded)

    # Custom questions  Ashby renders single-select choices as Yes/No <button> pairs
    # (and multi-choice as radios), associated to their <label> by DOM proximity, not
    # label[for]. Consent/agreement checkboxes are deliberately left for the human.
    answered = _fill_ashby_questions(page, profile)
    filled.extend(answered)

    return {"filled": filled, "skipped": skipped, "final_url": page.url}


_SKIP_BTN = {"upload file", "submit application", "submit", "back", "add", "remove"}


def _radio_label(radio) -> str:
    """Text of the label associated with a radio (aria-label, wrapping/adjacent label)."""
    try:
        t = radio.get_attribute("aria-label") or ""
        if t.strip():
            return t
        return radio.evaluate(
            "e => { const l = e.closest('label') || (e.parentElement && "
            "e.parentElement.querySelector('label')) || e.nextElementSibling; "
            "return l ? (l.innerText || l.textContent || '') : ''; }") or ""
    except Exception:
        return ""


def _answer_choice(page, label_el, keywords: list[str], text_val: str) -> bool:
    """Answer ONE Ashby question by clicking the matching Yes/No button, radio, or by
    typing into a type-ahead combobox. Scoped to the label's field container so we never
    touch a neighbouring question. Returns True if answered. Never raises."""
    kws = [k for k in keywords if k]
    try:
        container = label_el.evaluate_handle(
            "el => { let n = el.parentElement;"
            "  for (let i=0;i<5 && n;i++){"
            "    if (n.querySelector('button, input, [role=combobox], [role=radio]')) return n;"
            "    n = n.parentElement; } return el.parentElement; }").as_element()
    except Exception:
        container = None
    if not container:
        return False

    # 1) Yes/No or labelled option BUTTONS (Ashby's default for single-select).
    for b in container.query_selector_all("button"):
        try:
            t = (b.inner_text() or "").strip()
        except Exception:
            continue
        if not t or t.lower() in _SKIP_BTN:
            continue
        tl = t.lower()
        # exact match, or a short Yes/No button appearing as a word in the answer
        # ("Yes, I require sponsorship" -> the YES button).
        if any(tl == k.lower() or (len(tl) <= 4 and tl in k.lower().split())
               for k in kws):
            try:
                b.click()
                time.sleep(0.3)
                return True
            except Exception:
                pass

    # 2) RADIO options matched by their label text.
    for r in container.query_selector_all("input[type='radio']"):
        rt = _radio_label(r)
        if rt and any(k.lower() in rt.lower() for k in kws):
            try:
                r.check(timeout=1500)
                return True
            except Exception:
                try:
                    r.click(timeout=1500)
                    return True
                except Exception:
                    pass

    # 3) Type-ahead COMBOBOX (e.g. Location)  type the value, then pick the first option.
    cb = container.query_selector("[role='combobox'], input[placeholder*='Start typing' i]")
    if cb and text_val:
        try:
            cb.click()
            cb.fill(text_val)
            time.sleep(1.0)
            opt = page.query_selector("[role='option']")
            if opt:
                opt.click()
                time.sleep(0.4)
                return True
        except Exception:
            pass
    return False


def _fill_ashby_questions(page, profile: dict) -> list[str]:
    """Answer every question the profile/question-bank knows, via Ashby's real controls
    (button pairs, radios, type-ahead comboboxes, plain inputs). Unknown questions and all
    consent/agreement checkboxes are left untouched for the human. Returns answered labels."""
    bank = forms.load_bank()
    ctx = forms.build_context(profile)
    answered: list[str] = []
    try:
        labels = page.query_selector_all("label")
    except Exception:
        return answered
    for lbl in labels:
        try:
            txt = (lbl.inner_text() or "").strip()
        except Exception:
            continue
        if not txt or len(txt) < 4:
            continue
        ans = forms.answer_for_label(txt, ctx, bank)
        if ans is None:
            continue
        text_val, opts = ans
        keywords = (opts or []) + ([text_val] if text_val else [])
        # A plain text/textarea question (no options) → fill it directly if empty.
        if text_val and not opts:
            fid = lbl.get_attribute("for")
            el = page.query_selector(f"[id='{fid}']") if fid else None
            if el:
                tag = el.evaluate("e => e.tagName.toLowerCase()")
                if tag in ("input", "textarea") and not (el.get_attribute("value") or "").strip():
                    try:
                        el.fill(text_val)
                        answered.append(txt[:30])
                        continue
                    except Exception:
                        pass
        if _answer_choice(page, lbl, keywords, text_val or ""):
            answered.append(txt[:30])
    return answered
