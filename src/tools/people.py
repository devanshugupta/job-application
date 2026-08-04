"""Free-signal people finder: hiring manager + recruiter per company, no LinkedIn login.

Design (Aug 2026): search-engine scraping is dead from servers and every search API
free tier is capped, so the default path uses only free signals:
  1. the company's own site (team/about/contact pages): emails + name/title lines,
  2. reporting lines leaked in stored JD text ("you will report to the Head of X"),
  3. pattern-guessed emails, small companies only, always labeled guessed.
Optional providers behind the same seam, active only when a key is in the env:
  - SERPER_API_KEY  -> Google results for site:linkedin.com/in people snippets,
  - HUNTER_API_KEY  -> confirms a domain's email pattern (one call per domain).
One brain call per company picks up to 3 people and drafts outreach; results are
cached on the company record for 30 days (people_scouted).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from .. import config
from ..prompts import PEOPLE_SYSTEM

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126 Safari/537.36")
_TTL_DAYS = 30
COMPANIES_PATH = config.ROOT / "data" / "network" / "companies.json"

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_EMAIL_JUNK = re.compile(r"(noreply|no-reply|sentry|example\.|\.png$|\.jpg$|\.jpeg$|"
                         r"\.gif$|\.svg$|\.webp$|@2x|wixpress|schema\.org)", re.I)
_TEAM_SLUGS = ("about", "team", "company", "people", "contact", "careers", "leadership")
_TITLE_KW = re.compile(r"(founder|co-founder|ceo|cto|coo|chief |head of|vp |vice president|"
                       r"director|engineering manager|eng manager|recruit|talent|hiring|"
                       r"people ops|staff engineer|principal engineer|lead)", re.I)
_REPORT_RE = re.compile(
    r"report(?:s|ing)?\s+(?:directly\s+)?(?:in)?to\s+(?:the\s+|our\s+|an?\s+)?"
    r"([A-Za-z][A-Za-z /&,-]{2,60})")
_TAG_RE = re.compile(r"<script.*?</script>|<style.*?</style>|<[^>]+>", re.S | re.I)

PEOPLE_SCHEMA = {
    "type": "object",
    "required": ["company_size", "people", "notes"],
    "properties": {
        "company_size": {"type": "string", "enum": ["small", "large"]},
        "people": {"type": "array", "items": {
            "type": "object",
            "required": ["name", "title", "kind", "linkedin", "email", "email_source",
                         "rwl", "hook", "message"],
            "properties": {
                "name": {"type": "string"},
                "title": {"type": "string"},
                "kind": {"type": "string",
                         "enum": ["hiring_manager", "recruiter", "founder",
                                  "senior_ic", "warm"]},
                "linkedin": {"type": "string"},
                "email": {"type": "string"},
                "email_source": {"type": "string", "enum": ["site", "guessed", "none"]},
                "rwl": {"type": "array", "items": {"type": "integer"}},
                "hook": {"type": "string"},
                "message": {"type": "string"},
            },
        }},
        "notes": {"type": "string"},
    },
}


# ------------------------------------------------------------------ fetching

def fetch(url: str, timeout: int = 12) -> str:
    """GET a page as text; every failure returns '' (signals are best-effort)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(600_000).decode("utf-8", "replace")
    except Exception:
        return ""


def _strip_html(html: str) -> str:
    # block-level closes become newlines so name/title line structure survives
    text = re.sub(r"</(p|div|li|h[1-6]|tr|section|article)>|<br[^>]*>", "\n", html, flags=re.I)
    text = _TAG_RE.sub(" ", text)
    text = re.sub(r"&(amp|nbsp|#39|quot|lt|gt);", " ", text)
    return re.sub(r"[ \t]+", " ", text)


# ------------------------------------------------------------------ free signals

def extract_emails(html: str) -> list[str]:
    seen, out = set(), []
    for m in EMAIL_RE.findall(html):
        low = m.lower()
        if _EMAIL_JUNK.search(low) or low in seen:
            continue
        seen.add(low)
        out.append(low)
    return out[:10]


def team_links(base_url: str, html: str) -> list[str]:
    """Same-host links that look like team/about/contact pages, from the homepage."""
    host = urllib.parse.urlparse(base_url).netloc
    out, seen = [], set()
    for href in re.findall(r'href=["\']([^"\'#?]+)', html):
        full = urllib.parse.urljoin(base_url, href)
        p = urllib.parse.urlparse(full)
        if p.netloc != host:
            continue
        path = p.path.rstrip("/").lower()
        if any(path.endswith("/" + s) or path == "/" + s for s in _TEAM_SLUGS):
            if full not in seen:
                seen.add(full)
                out.append(full)
    return out[:4]


_NAME_LINE = re.compile(r"^[A-Z][a-z'’.-]+(?: [A-Z][a-z'’.-]+){1,2}$")
_NOT_A_NAME = re.compile(r"^(senior|chief|vice|head|general|executive|principal|staff|"
                         r"global|worldwide|managing|apple|about|meet|our|the)\b", re.I)


def looks_like_name(text: str) -> bool:
    t = text.strip()
    return bool(_NAME_LINE.match(t)) and not _NOT_A_NAME.match(t)


def people_chunks(html: str, cap_chars: int = 4000) -> list[str]:
    """Lines of page text that mention a title keyword; the brain's raw material.

    Team pages often put the name on its own line right above the title, so a
    name-looking previous line is glued on ("Jane Doe :: CEO")."""
    out, total, prev = [], 0, ""
    for raw in _strip_html(html).splitlines():
        line = raw.strip()
        if not line:
            continue
        if 8 < len(line) < 240 and _TITLE_KW.search(line):
            if looks_like_name(prev):
                line = f"{prev} :: {line}"
            out.append(line)
            total += len(line)
            if total > cap_chars:
                break
        prev = line
    return out[:40]


def jd_hints(jd_text: str) -> list[str]:
    """Reporting lines that actually name a role ('report to the Head of Search')."""
    hints = []
    for m in _REPORT_RE.finditer(jd_text or ""):
        target = m.group(1).strip(" ,")
        if _TITLE_KW.search(target):
            hints.append(f"reports to {target}")
    return list(dict.fromkeys(hints))[:3]


def guess_emails(name: str, domain: str) -> list[str]:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    parts = [p for p in re.sub(r"[^a-z ]", "", ascii_name.lower()).split() if p]
    if not parts or not domain:
        return []
    first, last = parts[0], parts[-1]
    guesses = [f"{first}@{domain}", f"{first}.{last}@{domain}", f"{first[0]}{last}@{domain}"]
    return list(dict.fromkeys(guesses)) if last != first else [guesses[0]]


# ------------------------------------------------------------------ optional providers

def search_provider() -> str:
    return "serper" if os.environ.get("SERPER_API_KEY") else "none"


def search_people(company: str, keywords: list[str], _post=None) -> list[str]:
    """LinkedIn-profile snippets via Google, only when a Serper key exists.

    Never touches LinkedIn itself (logged in or out), so zero flag risk.
    """
    if search_provider() == "none":
        return []
    snippets = []
    for kw in keywords[:2]:
        q = f'site:linkedin.com/in "{company}" {kw}'
        body = json.dumps({"q": q, "num": 5}).encode()
        try:
            if _post is not None:
                data = _post(q)
            else:
                req = urllib.request.Request(
                    "https://google.serper.dev/search", data=body,
                    headers={"X-API-KEY": os.environ["SERPER_API_KEY"],
                             "Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    data = json.loads(r.read().decode())
        except Exception:
            continue
        for item in (data or {}).get("organic", [])[:5]:
            snippets.append(f'{item.get("title", "")} | {item.get("link", "")} | '
                            f'{item.get("snippet", "")}')
    return snippets


def hunter_pattern(domain: str, _get=None) -> str:
    """The domain's confirmed email pattern from Hunter, '' without a key."""
    if not os.environ.get("HUNTER_API_KEY"):
        return ""
    try:
        if _get is not None:
            data = _get(domain)
        else:
            url = ("https://api.hunter.io/v2/domain-search?domain=" + domain
                   + "&api_key=" + os.environ["HUNTER_API_KEY"])
            with urllib.request.urlopen(url, timeout=15) as r:
                data = json.loads(r.read().decode())
        return (data.get("data") or {}).get("pattern") or ""
    except Exception:
        return ""


# ------------------------------------------------------------------ tracker io

def company_from_url(url: str) -> dict | None:
    """A fresh tracker entry from a pasted company website or LinkedIn company URL."""
    p = urllib.parse.urlparse(url)
    host = p.netloc.lower().removeprefix("www.")
    if not host:
        return None
    if host.endswith("linkedin.com"):
        m = re.match(r"/company/([^/]+)", p.path)
        if not m:
            return None  # a profile or post URL names a person, not a company
        slug = urllib.parse.unquote(m.group(1))
        name = re.sub(r"[-_]+", " ", slug).strip().title()
        return {"name": name, "website": "", "linkedin": f"https://www.linkedin.com/company/{slug}/",
                "heat": "?", "fit": "pasted on /network, not yet scouted", "people": []}
    name = host.split(".")[0].replace("-", " ").title()
    return {"name": name, "website": f"{p.scheme}://{p.netloc}",
            "heat": "?", "fit": "pasted on /network, not yet scouted", "people": []}

def load_companies() -> dict:
    try:
        return json.loads(COMPANIES_PATH.read_text())
    except Exception:
        return {"companies": []}


def save_companies(db: dict) -> None:
    f = COMPANIES_PATH
    f.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=f.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(db, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, f)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _candidate_block() -> str:
    try:
        cfg = json.loads((config.ROOT / "config" / "network.json").read_text())
    except Exception:
        return "(candidate config missing)"
    cand = cfg.get("candidate", {})
    keep = ("first_name", "headline", "one_liner", "schools", "past_employers",
            "stack", "role_families", "visa_note")
    return json.dumps({k: cand[k] for k in keep if k in cand})


def _achievements_excerpt(cap: int = 2500) -> str:
    try:
        return (config.ROOT / "resume" / "achievements.md").read_text()[:cap]
    except OSError:
        return "(no achievements file)"


# ------------------------------------------------------------------ main

def is_fresh(company: dict, today: date | None = None) -> bool:
    stamp = company.get("people_scouted") or ""
    try:
        return (today or date.today()) - date.fromisoformat(stamp) < timedelta(days=_TTL_DAYS)
    except ValueError:
        return False


def gather_signals(company: dict, jobs: list[dict], fetch_fn=fetch) -> dict:
    website = company.get("website") or ""
    home = fetch_fn(website) if website else ""
    emails, chunks = extract_emails(home), people_chunks(home)
    for link in team_links(website, home):
        page = fetch_fn(link)
        emails += [e for e in extract_emails(page) if e not in emails]
        chunks += people_chunks(page)
    hints = []
    for j in jobs:
        for h in jd_hints(j.get("jd_text") or ""):
            hints.append(f'{j.get("role", "?")}: {h}')
    domain = urllib.parse.urlparse(website).netloc.removeprefix("www.")
    kw = [j.get("role", "") for j in jobs][:1] + ["recruiter OR talent"]
    return {
        "domain": domain,
        "emails": emails[:10],
        "chunks": chunks[:40],
        "jd_hints": hints[:6],
        "snippets": search_people(company.get("name", ""), kw),
        "hunter_pattern": hunter_pattern(domain) if domain else "",
    }


def find_people(company: dict, jobs: list[dict], brain,
                fetch_fn=fetch, force: bool = False, today: date | None = None) -> dict:
    """Scout one company in place: merge up to 3 people onto the company dict.

    Raises BrainPending in manual mode; safe to re-run (30-day cache, keyed merge).
    """
    today = today or date.today()
    if not force and is_fresh(company, today):
        return {"company": company.get("name"), "skipped": "fresh"}

    sig = gather_signals(company, jobs, fetch_fn)
    roles = [{"role": j.get("role"), "url": j.get("url")} for j in jobs[:6]]
    existing = [p.get("name") for p in company.get("people", [])]
    guesses = {}
    for line in sig["chunks"][:12]:
        m = re.match(r"([A-Z][a-z'’.-]+ [A-Z][a-z'’.-]+)", line.strip())
        if m and sig["domain"] and looks_like_name(m.group(1)):
            guesses[m.group(1)] = guess_emails(m.group(1), sig["domain"])

    # candidate + achievements are byte-identical for every company in a run, so they
    # ride as cache blocks: in API mode only the first company pays for them (prompt
    # caching); later companies read them from cache at a fraction of the input price.
    cache_blocks = [f"CANDIDATE:\n{_candidate_block()}",
                    f"ACHIEVEMENTS (ground every draft claim here):\n{_achievements_excerpt()}"]
    user = json.dumps({
        "company": {"name": company.get("name"), "website": company.get("website"),
                    "heat": company.get("heat"), "funding": company.get("funding"),
                    "fit": company.get("fit")},
        "open_roles": roles,
        "site_emails": sig["emails"],
        "site_text_lines": sig["chunks"],
        "jd_reporting_hints": sig["jd_hints"],
        "linkedin_search_snippets": sig["snippets"],
        "email_pattern_confirmed": sig["hunter_pattern"],
        "email_pattern_guesses": guesses,
        "already_tracked_people": existing,
    }, indent=1)

    out = brain.structured("people", system=PEOPLE_SYSTEM, user=user,
                           schema=PEOPLE_SCHEMA, max_tokens=2500,
                           cache_blocks=cache_blocks)

    by_name = {p.get("name", "").lower(): p for p in company.setdefault("people", [])}
    added = 0
    for p in out.get("people", [])[:3]:
        key = (p.get("name") or "").lower()
        if not key:
            continue
        rec = by_name.get(key)
        if rec is None:
            rec = {"name": p["name"], "outreach": []}
            company["people"].append(rec)
            by_name[key] = rec
            added += 1
        rec.update({
            "title": p.get("title") or rec.get("title", ""),
            "kind": p.get("kind", ""),
            "linkedin": p.get("linkedin") or rec.get("linkedin", ""),
            "email": p.get("email", ""),
            "email_source": p.get("email_source", "none"),
            "rwl": p.get("rwl") or rec.get("rwl"),
            "hook": p.get("hook") or rec.get("hook", ""),
            "draft": p.get("message", ""),
            "source": "people-scout",
            "found": today.isoformat(),
        })
    company["people_scouted"] = today.isoformat()
    company["company_size"] = out.get("company_size", company.get("company_size", ""))
    # a hello@/support@ inbox only matters where a human reads it: small companies
    if sig["emails"] and company["company_size"] == "small" and not company.get("generic_inbox"):
        company["generic_inbox"] = sig["emails"][0]
    return {"company": company.get("name"), "added": added,
            "total": len(company["people"]), "size": company.get("company_size"),
            "notes": out.get("notes", "")}
