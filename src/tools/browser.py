"""Browser tool  a thin wrapper around Playwright.

This is the "hands" of the agent. Claude can't touch a webpage directly; it emits
tool calls like ``click(ref="...")`` and this module performs them in a real
Chromium instance.

Design choice: we expose the page to Claude as an **accessibility snapshot** (a
text outline of the interactive elements, each tagged with a stable ``ref`` id),
not as a screenshot. This is the same approach Microsoft's Playwright MCP uses
it's cheaper (no vision tokens), more reliable for forms, and gives Claude stable
handles to click/type into. See ``snapshot()`` below.
"""

from __future__ import annotations

import os
import pathlib
import random
import re
import time
from datetime import datetime, timedelta
from typing import Any

from playwright.sync_api import Page, sync_playwright

from .. import config

# Anti-flagging: pace actions like a human and present a real browser identity.
# Tunable via env so unattended runs can go slower/faster.
MIN_ACTION_DELAY = float(os.environ.get("JOB_AGENT_MIN_DELAY", "0.6"))
MAX_ACTION_DELAY = float(os.environ.get("JOB_AGENT_MAX_DELAY", "1.8"))
MAX_ACTIONS_PER_SESSION = int(os.environ.get("JOB_AGENT_MAX_ACTIONS", "120"))
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}


def _to_iso(text: str) -> str | None:
    """Parse a date string to ISO 'YYYY-MM-DD', or None. Handles already-ISO inputs
    and 'Month DD, YYYY' (e.g. 'October 31, 2025'). Avoids datetime.strptime locale
    issues and never uses the current clock."""
    if not text:
        return None
    text = text.strip()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", text)
    if m:
        mon = _MONTHS.get(m.group(1).lower())
        if mon:
            return f"{int(m.group(3)):04d}-{mon:02d}-{int(m.group(2)):02d}"
    return None


def _resolve_relative(text: str, today: str | None) -> str | None:
    """Resolve a relative date like '5 days ago' / '2 weeks ago' to ISO, using the
    caller-supplied ``today`` (ISO). Returns None if not relative or today unknown.
    Never reads the system clock (keeps date sourcing in one place)."""
    if not today:
        return None
    m = re.search(r"(\d+)\s+(day|week|month|hour|minute)s?\s+ago", text, re.I)
    if not m:
        return None

    n, unit = int(m.group(1)), m.group(2).lower()
    try:
        ref = datetime.strptime(today, "%Y-%m-%d")
    except ValueError:
        return None
    delta = {
        "minute": timedelta(0), "hour": timedelta(0), "day": timedelta(days=n),
        "week": timedelta(weeks=n), "month": timedelta(days=30 * n),
    }[unit]
    return (ref - delta).strftime("%Y-%m-%d")


class Browser:
    """Owns a single Playwright browser + page and exposes simple actions.

    One instance per agent run. ``ref`` ids handed to Claude in snapshots are
    resolved back to elements via a small in-memory map we rebuild on each
    snapshot.
    """

    def __init__(self, headless: bool = False, user_data_dir: str | None = None):
        self._pw = sync_playwright().start()
        if user_data_dir:
            # Persistent context = you stay logged into job sites across runs.
            self._ctx = self._pw.chromium.launch_persistent_context(
                user_data_dir, headless=headless, user_agent=_USER_AGENT
            )
            self.page: Page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        else:
            self._browser = self._pw.chromium.launch(headless=headless)
            self._ctx = self._browser.new_context(user_agent=_USER_AGENT)
            self.page = self._ctx.new_page()
        self._refs: dict[str, Any] = {}
        self._action_count = 0

    # --- anti-flagging pacing ----------------------------------------------------

    def _pace(self) -> None:
        """Sleep a randomized human-like interval and enforce a per-session action cap.

        Keeps us from hammering a site (which trips bot defenses) and bounds total
        activity per run. Raises if the cap is exceeded so the agent stops politely.
        """
        self._action_count += 1
        if self._action_count > MAX_ACTIONS_PER_SESSION:
            raise RuntimeError(
                f"Hit per-session action cap ({MAX_ACTIONS_PER_SESSION}). Stopping to "
                "avoid looking like a bot. Re-run later or raise JOB_AGENT_MAX_ACTIONS."
            )
        time.sleep(random.uniform(MIN_ACTION_DELAY, MAX_ACTION_DELAY))

    # --- actions Claude can call -------------------------------------------------

    def open_page(self, url: str) -> str:
        self._pace()
        self.page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        # settle dynamic content politely without hammering
        try:
            self.page.wait_for_load_state("networkidle", timeout=8_000)
        except Exception:
            pass
        return f"Navigated to {self.page.url}\n\n{self.snapshot()}"

    def extract_job_links(self, base: str = "") -> str:
        """Return the unique job-posting links on the CURRENT search-results page.

        Reads real <a href> elements (browser-resolved to absolute URLs) and keeps those
        whose path looks like a job DETAIL page across common ATS shapes  Amazon
        (/jobs/<id>/...), Greenhouse (/jobs/<id>), Lever/Ashby (uuid), Apple
        (/details/<id>/...), Workday (/job/...). Reading anchors (not regex on raw HTML)
        avoids relative-vs-absolute bugs and generalizes across portals. Use it to walk a
        board's pages: load the search sorted-recent, call this, advance the page param,
        repeat  stop once dates fall outside the freshness window."""
        hrefs = self.page.eval_on_selector_all(
            "a[href]", "els => els.map(e => e.href)"  # .href is browser-resolved absolute
        )
        detail = re.compile(
            r"(/jobs?/\d+)"                      # amazon / greenhouse: /jobs/<id>
            r"|(/details/\d+/)"                  # apple: /details/<id>/slug
            r"|(/[A-Za-z0-9_\-]+/[0-9a-f]{8}-[0-9a-f\-]{27,})"  # lever / ashby uuid
            r"|(/job/)",                         # workday
            re.I,
        )
        seen: list[str] = []
        for h in hrefs:
            if h and detail.search(h) and h not in seen:
                seen.append(h)
        return "\n".join(seen[:40]) if seen else "No job links found on this page."

    def get_page_text(self, max_chars: int = 8000) -> str:
        """Return the visible page text (for reading a JD or a posted date).

        Cheaper than asking the model to parse a full snapshot when we just need prose.
        """
        txt = self.page.inner_text("body")
        return txt[:max_chars]

    def find_posted_date(self, today: str | None = None) -> str:
        """Extract the posting date from the CURRENT (real company) page, portal-agnostic.

        Strategy is ordered MOST-STANDARD → least, so it generalizes across ATS platforms
        (Greenhouse, Lever, Ashby, Workday, company sites) rather than hardcoding any one:

          1. schema.org JobPosting `datePosted`  the WEB STANDARD for job pages; most
             ATS emit it in JSON-LD or as an itemprop/meta. This is the reliable signal.
          2. <time datetime="...">  the HTML standard for machine-readable dates.
          3. A generic "posted/listed <date>" phrase near the TOP of the page (header
             region only, to avoid a "related jobs" sidebar contaminating the result),
             accepting absolute dates and relative ones ("5 days ago") resolved vs `today`.

        Returns ISO 'YYYY-MM-DD', or 'unverified' if nothing trustworthy is found. The
        agent must confirm this is the REAL company page, never an aggregator/LinkedIn.
        """
        # 1) schema.org JobPosting datePosted (JSON-LD or microdata)  the standard.
        html_txt = self.page.content()
        m = re.search(r'"datePosted"\s*:\s*"([^"]+)"', html_txt)
        if m:
            iso = _to_iso(m.group(1))
            if iso:
                return iso
        for sel in ("[itemprop=datePosted]", "meta[itemprop=datePosted]"):
            el = self.page.query_selector(sel)
            if el:
                iso = _to_iso(el.get_attribute("content") or el.get_attribute("datetime")
                              or el.inner_text() or "")
                if iso:
                    return iso
        # 2) HTML <time datetime="..."> standard.
        el = self.page.query_selector("time[datetime]")
        if el:
            iso = _to_iso(el.get_attribute("datetime") or "")
            if iso:
                return iso
        # 3) Generic visible phrase, restricted to the header region (first ~1500 chars)
        #    so a "related jobs" list lower on the page can't contaminate the date.
        head = self.page.inner_text("body")[:1500]
        m = re.search(
            r"(?:posted|listed|date posted)[:\s]*"
            r"([A-Za-z]+ \d{1,2},? \d{4}|\d{4}-\d{2}-\d{2}|\d+\s+\w+\s+ago)",
            head, re.I,
        )
        if m:
            iso = _resolve_relative(m.group(1), today) or _to_iso(m.group(1))
            if iso:
                return iso
        return "unverified"

    def read_page(self) -> str:
        """Re-read the current page (after a click changed it, etc.)."""
        return self.snapshot()

    def click(self, ref: str) -> str:
        self._pace()
        el = self._resolve(ref)
        el.click(timeout=15_000)
        self.page.wait_for_timeout(800)  # let the DOM settle
        return f"Clicked {ref}.\n\n{self.snapshot()}"

    def type_text(self, ref: str, text: str, submit: bool = False) -> str:
        self._pace()
        el = self._resolve(ref)
        el.fill(text)
        if submit:
            el.press("Enter")
            self.page.wait_for_timeout(800)
        return f"Typed into {ref}.\n\n{self.snapshot()}"

    def fill_form(self, fields: list[dict[str, str]]) -> str:
        """Fill several fields at once. Each field: {"ref": "...", "value": "..."}."""
        for f in fields:
            self._pace()
            self._resolve(f["ref"]).fill(f["value"])
        return f"Filled {len(fields)} field(s).\n\n{self.snapshot()}"

    def upload_file(self, ref: str, file_path: str) -> str:
        self._pace()
        path = pathlib.Path(file_path).expanduser().resolve()
        if not path.exists():
            return f"ERROR: file not found at {path}"
        self._resolve(ref).set_input_files(str(path))
        return f"Uploaded {path.name} to {ref}.\n\n{self.snapshot()}"

    def screenshot(self, label: str = "screenshot") -> str:
        out_dir = config.SCREENSHOTS_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)
        dest = out_dir / f"{safe}.png"
        self.page.screenshot(path=str(dest), full_page=True)
        return f"Saved screenshot to {dest}"

    # --- internals ---------------------------------------------------------------

    def snapshot(self, max_chars: int = 6000) -> str:
        """Produce a compact, ref-tagged outline of interactive elements.

        We assign each candidate element a ``ref`` (e1, e2, ...) and store the
        Playwright locator so ``_resolve`` can find it later. We surface the
        element role, accessible name, and current value so Claude knows what's
        on the page and what's already filled.
        """
        self._refs.clear()
        selector = "a, button, input, textarea, select, [role=button], [role=link]"
        handles = self.page.query_selector_all(selector)
        lines: list[str] = [f"PAGE TITLE: {self.page.title()}", "INTERACTIVE ELEMENTS:"]
        for i, h in enumerate(handles, start=1):
            ref = f"e{i}"
            self._refs[ref] = h
            tag = h.evaluate("el => el.tagName.toLowerCase()")
            name = (
                h.get_attribute("aria-label")
                or h.get_attribute("placeholder")
                or h.get_attribute("name")
                or (h.inner_text() or "").strip()[:60]
                or h.get_attribute("value")
                or ""
            )
            value = h.get_attribute("value") or ""
            etype = h.get_attribute("type") or ""
            descr = f"  [{ref}] <{tag}{':' + etype if etype else ''}> {name!r}"
            if value:
                descr += f"  (current value: {value!r})"
            lines.append(descr)
        text = "\n".join(lines)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n... (truncated; call read_page after narrowing)"
        return text

    def _resolve(self, ref: str):
        if ref not in self._refs:
            raise ValueError(
                f"Unknown ref {ref!r}. Call read_page to get a fresh snapshot first."
            )
        return self._refs[ref]

    def close(self) -> None:
        try:
            self._ctx.close()
        finally:
            self._pw.stop()
