"""Fetch a job description as plain text over HTTP — no browser, no LLM.

ATS-hosted postings (Greenhouse, Lever, Ashby, SmartRecruiters, Workable) are
server-rendered, so a single GET + tag-strip yields the JD. Where the URL maps to
a known ATS JSON API we use that first (cleaner text). JS-only pages (Workday)
return little text; callers should fall back to the browser agent when the result
is too short (`looks_complete` is False).
"""

from __future__ import annotations

import html as _html
import json
import re
import urllib.request

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
TIMEOUT = 25
MIN_COMPLETE_CHARS = 600  # below this, the page was probably JS-rendered


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


def _greenhouse_api(url: str) -> str | None:
    """boards.greenhouse.io/<token>/jobs/<id> or job-boards.greenhouse.io — clean JSON content."""
    m = re.search(r"greenhouse\.io/(?:embed/job_app\?[^ ]*token=)?([A-Za-z0-9_-]+)/jobs/(\d+)",
                  url)
    if not m:
        return None
    token, jid = m.group(1), m.group(2)
    try:
        data = json.loads(_get(
            f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{jid}"))
        body = _strip_html(_html.unescape(data.get("content", "")))
        head = f"{data.get('title', '')}\n{(data.get('location') or {}).get('name', '')}\n\n"
        return (head + body).strip() or None
    except Exception:
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


def fetch_jd(url: str, max_chars: int = 12000) -> dict:
    """Return {text, source, looks_complete}. Never raises on fetch errors."""
    for api_fn, src in ((_greenhouse_api, "greenhouse-api"), (_lever_api, "lever-api")):
        text = api_fn(url)
        if text:
            return {"text": text[:max_chars], "source": src,
                    "looks_complete": len(text) >= MIN_COMPLETE_CHARS}
    try:
        text = _strip_html(_get(url))
    except Exception as e:
        return {"text": "", "source": f"error: {e}", "looks_complete": False}
    return {"text": text[:max_chars], "source": "http",
            "looks_complete": len(text) >= MIN_COMPLETE_CHARS}
