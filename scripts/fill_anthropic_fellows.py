"""Pre-fill the objective fields of the Anthropic Fellows Application (Airtable form).

Airtable form inputs have opaque hashed ids and no labels, so every field is located by
its visible QUESTION TEXT: find the label leaf, climb to the field container, fill the
input/textarea inside. Opens a visible browser and fills only the objective fields —
name, email, links, and the ML Systems stream. It deliberately leaves the resume upload,
references, essays, and Submit to you (those are yours to write and click). Never submits.

Run:  python scripts/fill_anthropic_fellows.py
"""
import sys
from playwright.sync_api import sync_playwright

URL = "https://airtable.com/appCHLjgoTUCJMLct/pagUhpiBE5KxoU3lX/form"

# --- your details -----------------------------------------------------------------
TEXT_FIELDS = {
    "First Name": "Devanshu",
    "Last Name": "Gupta",
    "Email": "dgupta77@asu.edu",
    "LinkedIn": "https://www.linkedin.com/in/devanshu0gupta",
    "GitHub": "https://github.com/devanshugupta",
}
TOP_STREAM = "ML Systems & Performance"   # your top-choice team


def log(m): print(m); sys.stdout.flush()


def fill_by_label(page, label, value):
    """Fill the input/textarea belonging to the field whose label is exactly `label`."""
    # locate the label leaf, climb to its NEAREST ancestor holding a field, fill that
    # input/textarea. `[1]` on the ancestor axis = nearest-first (not the outer wrapper).
    field = page.locator(
        f'xpath=//*[normalize-space(text())={label!r}]'
        f'/ancestor::*[.//input or .//textarea][1]'
        f'//*[self::input or self::textarea]'
    ).first
    field.fill(value)


def click_option(page, text):
    """Click a choice button/label by its visible text (streams, Yes/No)."""
    page.get_by_text(text, exact=True).first.click()


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False)
    page = browser.new_context().new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3500)

    # decline non-essential cookies if the banner is present
    try:
        page.get_by_text("Reject All, Except Strictly Necessary", exact=False).first.click(timeout=3000)
    except Exception:
        pass

    for label, value in TEXT_FIELDS.items():
        try:
            fill_by_label(page, label, value)
            log(f"  filled: {label}")
        except Exception as e:
            log(f"  MANUAL: {label} ({type(e).__name__})")

    try:
        click_option(page, TOP_STREAM)
        log(f"  selected top stream: {TOP_STREAM}")
    except Exception as e:
        log(f"  MANUAL: top stream ({type(e).__name__})")

    log("\nFILLED the objective fields. LEFT FOR YOU (must do these yourself):")
    log("  - Resume PDF: drop your file in (automation can't attach local files).")
    log("  - 'Applied to Anthropic in the past year?' -> pick Yes/No.")
    log("  - 'Confirm AI policy understanding' -> select Yes after reading it.")
    log("  - References (3): names, emails, background, relationship.")
    log("  - Essays: why Fellows, research areas, the two likelihood % questions.")
    log("  - REVIEW everything, then click Submit yourself. This script never submits.")
    log("\n(Window stays open ~40 min.)")
    try:
        page.wait_for_url("**submitted**", timeout=40 * 60 * 1000)
        log("Submitted — confirmation reached.")
    except Exception:
        log("Window session ended.")
    browser.close()
