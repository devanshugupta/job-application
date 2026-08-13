"""Fetch a job description as plain text over HTTP  no browser, no LLM.

ATS-hosted postings (Greenhouse, Lever, Ashby, SmartRecruiters, Workable) are
server-rendered, so a single GET + tag-strip yields the JD. Where the URL maps to
a known ATS JSON API we use that first (cleaner text). JS-only pages (Workday)
return little text; callers should fall back to the browser agent when the result
is too short (`looks_complete` is False).
"""

from __future__ import annotations

import functools
import html as _html
import json
import re
import urllib.request

from . import boards

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
TIMEOUT = 25
MIN_COMPLETE_CHARS = 600  # below this, the page was probably JS-rendered

# A logged-out LinkedIn job page renders its full nav/auth shell ("Sign in", "Join now",
# the search-type-selector button copy) as body text when the real posting requires a
# session  long enough to clear MIN_COMPLETE_CHARS despite containing zero JD content.
# Length alone can't tell them apart; this phrase cluster can. Two-of-three keeps a real
# JD that happens to mention "sign in" once (rare) from being falsely rejected.
_LOGIN_WALL_MARKERS = (
    "sign in", "join now", "currently selected search type",
)


def _looks_like_login_wall(text: str) -> bool:
    low = text.lower()
    return sum(m in low for m in _LOGIN_WALL_MARKERS) >= 2


# The signal that a page carries a REAL posting body (not just company boilerplate) is a
# JD-STRUCTURE marker: the phrases that introduce an actual job's sections. This set is
# DATA-DRIVEN: over our corpus of 402 captured JDs, 99.8% contain at least ONE of these,
# while a dead/expired posting that degrades to a company-blurb / careers-nav page (e.g.
# Genentech's expired page: title + "Who we are… invested in R&D… join our talent
# network", but no responsibilities/qualifications) contains NONE. Generic words like
# "experience/team/apply" were rejected  they also appear in that boilerplate.
_JD_SIGNAL_MARKERS = (
    "responsibilit", "qualificat", "requirement", "what you", "you will", "you'll",
    "minimum", "preferred", "in this role", "who you are", "you have", "you bring",
    "the role", "your role", "we're looking", "we are looking", "day-to-day",
    "what we look", "basic qualif", "proficien",
)
MIN_JD_MARKERS = 1  # 99.8% of real JDs clear >=1; dead/boilerplate pages have 0.


def has_jd_content(text: str, min_hits: int = MIN_JD_MARKERS) -> bool:
    """True if `text` carries a real job-description BODY, i.e. contains >= min_hits
    JD-structure markers (responsibilities / qualifications / requirements / "you will"…).
    Catches long-but-empty pages that clear the length bar: careers-nav shells and
    dead/expired postings that degrade to company boilerplate. Calibrated from our JD
    corpus (see _JD_SIGNAL_MARKERS)."""
    low = (text or "").lower()
    return sum(m in low for m in _JD_SIGNAL_MARKERS) >= min_hits


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310
        return r.read().decode("utf-8", errors="replace")


def _strip_html(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<(br|/p|/div|/li|/h[1-6]|/tr)[^>]*>", "\n", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = _html.unescape(raw)
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n\s*\n+", "\n\n", raw)
    return raw.strip()


def _greenhouse_fetch(token: str, jid: str) -> str | None:
    try:
        data = json.loads(_get(
            f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{jid}"))
        body = _strip_html(_html.unescape(data.get("content", "")))
        head = f"{data.get('title', '')}\n{(data.get('location') or {}).get('name', '')}\n\n"
        return (head + body).strip() or None
    except Exception:
        return None


def _greenhouse_api(url: str) -> str | None:
    """Greenhouse JD via the boards API. Handles both the native board URL
    (boards.greenhouse.io/<token>/jobs/<id>) and a company page that embeds Greenhouse
    via ?gh_jid=<id>  in the embed case the board token isn't in the URL, so we try
    tokens derived from the hostname and the watchlist."""
    m = re.search(r"greenhouse\.io/(?:embed/job_app\?[^ ]*token=)?([A-Za-z0-9_-]+)/jobs/(\d+)",
                  url)
    if m:
        return _greenhouse_fetch(m.group(1), m.group(2))

    jid_m = re.search(r"[?&]gh_jid=(\d+)", url)
    if not jid_m:
        return None
    jid = jid_m.group(1)
    # candidate board tokens: watchlist company whose name appears in the host, then the
    # host's main label (mongodb.com -> "mongodb"), which is the usual Greenhouse token.
    host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
    label = host.split(".")[0]
    candidates = [label]
    try:
        for c in boards.watchlist_companies():
            tok = c.get("token")
            if tok and (tok in host or c["name"].lower().replace(" ", "") in host):
                candidates.insert(0, tok)
    except Exception:
        pass
    for tok in dict.fromkeys(candidates):  # dedupe, keep order
        out = _greenhouse_fetch(tok, jid)
        if out:
            return out
    return None


def _lever_api(url: str) -> str | None:
    m = re.search(r"jobs\.lever\.co/([A-Za-z0-9_-]+)/([0-9a-f-]{36})", url)
    if not m:
        return None
    try:
        data = json.loads(_get(f"https://api.lever.co/v0/postings/{m.group(1)}/{m.group(2)}"))
        parts = [data.get("text", ""), (data.get("categories") or {}).get("location", ""),
                 _strip_html(data.get("description", ""))]
        for lst in data.get("lists", []):
            parts.append(lst.get("text", ""))
            parts.append(_strip_html(lst.get("content", "")))
        return "\n\n".join(p for p in parts if p).strip() or None
    except Exception:
        return None


def _workday_api(url: str) -> str | None:
    """Workday (<tenant>.wdN.myworkdayjobs.com/<site>/job/<path>)  fetch the JD from
    Workday's public CXS JSON API instead of the JS-rendered page. The API path mirrors
    the URL: /wday/cxs/<tenant>/<site>/job/<path>."""
    m = re.search(r"https?://([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/([^/]+)/job/(.+)",
                  url, re.I)
    if not m:
        return None
    tenant, wd, site, jobpath = m.group(1), m.group(2), m.group(3), m.group(4)
    # the site segment sometimes carries a locale prefix (e.g. en-US/Site)  strip it
    site = site.split("/")[-1]
    api = f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/job/{jobpath}"
    try:
        req = urllib.request.Request(api, headers={**_UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=25) as r:  # noqa: S310
            info = json.loads(r.read().decode()).get("jobPostingInfo", {})
        body = _strip_html(_html.unescape(info.get("jobDescription", "")))
        head = f"{info.get('title', '')}\n{info.get('location', '')}\n\n"
        return (head + body).strip() or None
    except Exception:
        return None


def _ashby_api(url: str) -> str | None:
    """jobs.ashbyhq.com/<org>/<uuid>  pull the JD from Ashby's public posting API."""
    m = re.search(r"ashbyhq\.com/([A-Za-z0-9_.-]+)/([0-9a-f-]{36})", url)
    if not m:
        return None
    org, jid = m.group(1), m.group(2)
    try:
        data = json.loads(_get(
            f"https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=false"))
        for j in data.get("jobs", []):
            if jid in (j.get("jobUrl", "") + j.get("applyUrl", "")) or j.get("id") == jid:
                body = _strip_html(j.get("descriptionHtml", "")) or j.get("descriptionPlain", "")
                head = f"{j.get('title', '')}\n{j.get('location', '')}\n\n"
                return (head + body).strip() or None
    except Exception:
        return None
    return None


def _browser_fetch(url: str) -> str:
    """Last-resort: render the page with the Chromium Playwright already installed and
    read its visible text. Handles JS-only portals (Ashby SPA, Workday, company sites
    that embed an ATS) that return almost nothing over plain HTTP. Never raises."""
    try:
        # lazy: playwright is an optional dependency
        from playwright.sync_api import sync_playwright
    except Exception:
        return ""
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_context(user_agent=_UA["User-Agent"]).new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=8_000)
                except Exception:
                    pass
                text = page.inner_text("body")
            finally:
                browser.close()
        return re.sub(r"\n\s*\n+", "\n\n", text or "").strip()
    except Exception:
        return ""


@functools.lru_cache(maxsize=256)
def _fetch_jd_cached(url: str, max_chars: int, allow_browser: bool) -> tuple[str, str, bool]:
    """Cached core of fetch_jd, keyed on the exact call args. Ensures a given URL is
    fetched over the network at most once per process/run  repeated calls (e.g. a
    batch script re-fetching the same JD for logging and then again for tailoring)
    hit this cache instead of re-hitting the network or the browser."""
    # A capture is "complete" only if it is long enough, is NOT a login-wall shell, AND
    # actually reads like a JD (has_jd_content)  the last clause is what catches a
    # dead/expired posting or careers-nav page that is long but carries no real content.
    def _complete(t: str) -> bool:
        return (len(t) >= MIN_COMPLETE_CHARS and not _looks_like_login_wall(t)
                and has_jd_content(t))

    # LinkedIn first: the full /jobs/view page is an auth wall (plain HTTP and even the
    # browser get a login shell), but the guest jobPosting endpoint returns the real JD.
    if "linkedin.com/jobs" in url:
        from ..sources.linkedin import fetch_jd_for_url as _li_jd
        text = _li_jd(url)
        if text and _complete(text):
            return text[:max_chars], "linkedin-guest", True

    for api_fn, src in ((_greenhouse_api, "greenhouse-api"), (_lever_api, "lever-api"),
                        (_ashby_api, "ashby-api"), (_workday_api, "workday-api")):
        text = api_fn(url)
        if text and _complete(text):
            return text[:max_chars], src, True
    try:
        http_text = _strip_html(_get(url))
    except Exception:
        http_text = ""
    if _complete(http_text):
        return http_text[:max_chars], "http", True

    if allow_browser:
        rendered = _browser_fetch(url)
        if _complete(rendered):
            return rendered[:max_chars], "browser", True
        http_text = rendered or http_text  # keep whatever's longer/available

    return http_text[:max_chars], "http", _complete(http_text)


def fetch_jd(url: str, max_chars: int = 12000, *, allow_browser: bool = True) -> dict:
    """Return {text, source, looks_complete}. Never raises on fetch errors.

    Order: cheap ATS JSON APIs (greenhouse/lever/ashby) → plain HTTP strip → if still
    too thin and allowed, a headless-Chromium render (covers JS-only portals).
    Memoized per (url, max_chars, allow_browser) for the life of the process, so the
    same job is never fetched twice in one run."""
    text, source, looks_complete = _fetch_jd_cached(url, max_chars, allow_browser)
    return {"text": text, "source": source, "looks_complete": looks_complete}
