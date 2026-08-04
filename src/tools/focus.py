"""Focus UI: the official interface. One story, one action, rows behind it.

Design laws (decided 2026-08-03, reference test: "would Apple / The Browser
Company / IDEO have done this?"):
  - One story per screen, centered. Radical word economy.
  - Exactly one saturated CTA per view; cream + ink + one blue.
  - Color semantics, one meaning each: GREEN = act now / good to send.
    AMBER = waiting / held, do nothing yet. BLUE = information + navigation
    (fit bars, links, nav pills). RED = stopped / dead only. GRAY = identity
    and neutral states. A color never decorates; it always means.
  - 3-5 rows per section, best first, counts visible, "show all" expands.
  - No emojis, no em dashes, no icon where a word fits.
  - Ambient drifting background, slow enough to never catch moving.

Pages, ONE purpose each (a page never does another page's job):
  /                ROUTE me: state of the pipeline + two doors. Never a task.
  /apply           DO applications: ready rows + fresh finds.
  /network         DO outreach: its hero names today's top send.
  /company/<slug>  DECIDE about one company: the one move, people, roles.
Old dashboards stay at /classic and /network-classic.
"""

from __future__ import annotations

import html as _html
import json
import pathlib
import random
import re
from collections import Counter
from datetime import date, datetime, timedelta
from urllib.parse import quote_plus

from .. import config
from . import dashboard as _dash  # reuse _has_resume + _SUBMITTED semantics
from . import tracker

def _net_dir() -> pathlib.Path:
    # resolved per call, not at import, so tests and settings overrides that
    # repoint DATA_DIR are always respected
    return config.DATA_DIR / "network"


def esc(s) -> str:
    return _html.escape(str(s if s is not None else ""))


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")


def _monogram(name: str) -> str:
    words = [w for w in re.split(r"[\s\-.]+", name.strip()) if w]
    return (words[0][:1] + (words[1][:1] if len(words) > 1 else "")).upper() or "?"


# ------------------------------------------------------------------ data

HEAT_PILL = {"HOT": "p-go", "WARM": "p-hold", "COOL": "p-mut", "DEAD": "p-dead"}


def _heat_rows() -> dict:
    """hiring_heat.json rows keyed by company slug (empty if no sweep yet)."""
    try:
        data = json.loads((_net_dir() / "hiring_heat.json").read_text())
        return {slugify(r["company"]): r for r in data.get("companies", [])}
    except Exception:
        return {}


def _open_actions(c: dict) -> list[str]:
    """Unchecked next-action boxes from the company dossier."""
    return [m.strip() for m in re.findall(r"\s*- \[ \] (.+)", _dossier_text(c))]


def _net_companies() -> list[dict]:
    try:
        return json.loads((_net_dir() / "companies.json").read_text()).get("companies", [])
    except Exception:
        return []


def _dossier_text(c: dict) -> str:
    p = _net_dir() / c.get("dossier", "")
    try:
        return p.read_text() if c.get("dossier") and p.exists() else ""
    except Exception:
        return ""


def _first_draft(c: dict) -> str:
    """First blockquote in the dossier = the primary outreach draft."""
    md = _dossier_text(c)
    block = []
    for line in md.splitlines():
        if line.lstrip().startswith(">"):
            block.append(re.sub(r"^\s*>\s?", "", line))
        elif block:
            break
    return " ".join(block).strip()


def _person_draft(c: dict, p: dict) -> str:
    """The blockquote under this person's ### heading in the dossier."""
    first = p["name"].split("[")[0].strip().split()[0].lower()
    for chunk in re.split(r"^### ", _dossier_text(c), flags=re.M)[1:]:
        lines = chunk.splitlines()
        if first not in lines[0].lower():
            continue
        block = []
        for line in lines[1:]:
            if line.lstrip().startswith(">"):
                block.append(re.sub(r"^\s*>\s?", "", line))
            elif block:
                break
        return " ".join(block).strip()
    return ""


def _sources(c: dict) -> list[str]:
    """Bullet lines under the dossier's ## Sources heading."""
    m = re.search(r"^## Sources\s*\n(.*?)(?=^## |\Z)", _dossier_text(c), flags=re.M | re.S)
    if not m:
        return []
    return [ln.strip()[2:].strip() for ln in m.group(1).splitlines()
            if ln.strip().startswith("- ")]


def _touches(p: dict) -> list[dict]:
    return p.get("outreach") or []


def _person_state(c: dict, p: dict) -> tuple[str, str, str, str]:
    """(pill text, row class, pill class, why) for one person, same rules as the buckets."""
    t = _touches(p)
    today = date.today()
    if t and t[-1].get("outcome") in ("replied", "referred"):
        return "reply", "go", "p-go", "they answered, respond today"
    if not t:
        if c.get("status") in ("outreach_drafted", "contacted"):
            return "send", "go", "p-go", ""
        return "waiting", "", "p-mut", ""
    try:
        last = datetime.strptime(t[-1].get("date", ""), "%Y-%m-%d").date()
    except ValueError:
        last = today
    if len(t) < 3 and today - last >= timedelta(days=4):
        return "nudge", "hold", "p-hold", f"follow-up due, touch {len(t) + 1} of 3"
    return "waiting", "hold", "p-hold", f"contacted {t[-1].get('date', '')}, give it time"


def _people_actions(companies: list[dict]) -> dict:
    """Classify every mapped person into reply / send / due / waiting buckets."""
    replies, sends, due, waiting = [], [], [], []
    today = date.today()
    for c in companies:
        for p in c.get("people", []):
            t = _touches(p)
            item = {"company": c, "person": p}
            if t and t[-1].get("outcome") in ("replied", "referred"):
                replies.append(item)
            elif not t:
                if c.get("status") in ("outreach_drafted", "contacted"):
                    sends.append(item)
                else:
                    waiting.append(item)
            else:
                try:
                    last = datetime.strptime(t[-1].get("date", ""), "%Y-%m-%d").date()
                except ValueError:
                    last = today
                if len(t) < 3 and today - last >= timedelta(days=4):
                    due.append(item)
                else:
                    waiting.append(item)
    # highest warmth first within each bucket
    key = lambda i: -sum((i["person"].get("rwl") or [0, 0, 0])[:2])
    for bucket in (replies, sends, due):
        bucket.sort(key=key)
    return {"replies": replies, "sends": sends, "due": due, "waiting": waiting}


def _app_rows() -> dict:
    apps = [a for a in tracker.list_applications() if not a.get("removed")]
    ready, holds, fresh = [], [], []
    held_cos = {c["name"].lower() for c in _net_companies()
                if any(not _touches(p) or _touches(p)[-1].get("outcome")
                       not in ("declined",) for p in c.get("people", []))
                and c.get("status") in ("outreach_drafted", "contacted")}
    today = date.today().isoformat()
    for a in apps:
        stale = bool(a.get("stale"))
        if _dash._has_resume(a) and a.get("status") not in _dash._SUBMITTED and not stale:
            (holds if a.get("company", "").lower() in held_cos else ready).append(a)
        elif (a.get("status") == "found" and not stale
              and (a.get("date") or "")[:10] == today and (a.get("master_ats") or 0) >= 70):
            fresh.append(a)
    ready.sort(key=lambda a: -(a.get("master_ats") or 0))
    fresh.sort(key=lambda a: -(a.get("master_ats") or 0))
    return {"ready": ready, "holds": holds, "fresh": fresh}


TEASERS = {
    # entry-page sub-lines: generic on purpose (the entry routes, lanes hold the details).
    # one is picked at random per visit so the door always sounds fresh.
    "reply": ["Someone replied. Answer them today.",
              "A door opened overnight. Walk through it.",
              "There is a reply waiting. That is rare, use it."],
    "send": ["So, what are we doing today? One message, then the rest.",
             "A referral ask is written and ready to send.",
             "One send today could skip the whole resume pile."],
    "due": ["A follow-up is due today. Gentle, short, done.",
            "Four days of silence somewhere. One nudge fixes it.",
            "Today's plan starts with a follow-up."],
    "ready": ["A tailored application is ready. Two clicks.",
              "Today's plan: send what is already tailored.",
              "Everything is prepped. Just press send."],
    "clear": ["Nothing is waiting on you right now.",
              "All threads are moving. Rest is allowed."],
}


def _story(people: dict, apps: dict) -> dict:
    """The one thing that matters most today, as headline / line / cta / href."""
    if people["replies"]:
        i = people["replies"][0]
        n = i["person"]["name"].split("[")[0].strip().split()[0]
        return {"h": f"{esc(n)} said yes. <em>Answer today.</em>",
                "p": f"A warm door at {esc(i['company']['name'])} is open right now. Momentum decays in days, not weeks.",
                "cta": "Open the thread", "href": f"/company/{slugify(i['company']['name'])}",
                "teaser": random.choice(TEASERS["reply"]),
                "lane": "/network", "lane_name": "Networking"}
    if people["sends"]:
        i = people["sends"][0]
        n = i["person"]["name"].split("[")[0].strip().split()[0]
        co = i["company"]["name"]
        return {"h": f"{esc(n)} can open the door at {esc(co)}. <em>Ask.</em>",
                "p": "The draft is written. One message, referral before application, always.",
                "cta": "Show me the message", "href": f"/company/{slugify(co)}",
                "teaser": random.choice(TEASERS["send"]),
                "lane": "/network", "lane_name": "Networking"}
    if people["due"]:
        i = people["due"][0]
        n = i["person"]["name"].split("[")[0].strip().split()[0]
        return {"h": f"{esc(n)} went quiet. <em>One gentle nudge.</em>",
                "p": f"Touch {len(_touches(i['person'])) + 1} of 3 at {esc(i['company']['name'])}. Most replies come from the follow-up.",
                "cta": "Show me the nudge", "href": f"/company/{slugify(i['company']['name'])}",
                "teaser": random.choice(TEASERS["due"]),
                "lane": "/network", "lane_name": "Networking"}
    if apps["ready"]:
        a = apps["ready"][0]
        return {"h": f"{esc(a.get('company'))} is ready. <em>Two clicks.</em>",
                "p": f"{esc(a.get('role'))}. Resume tailored and verified, posting live.",
                "cta": "Open the posting", "href": "/apply",
                "teaser": random.choice(TEASERS["ready"]),
                "lane": "/apply", "lane_name": "Applications"}
    return {"h": "You're clear. <em>Well done.</em>",
            "p": "Every thread is moving. Come back after the next discovery sweep.",
            "cta": "See the pipeline", "href": "/apply",
            "teaser": random.choice(TEASERS["clear"]),
            "lane": "/apply", "lane_name": "Applications"}


# ------------------------------------------------------------------ html

CSS = """
* { box-sizing:border-box; margin:0 }
:root { --ink:#1c1b18; --mut:#8d8a80; --line:#eee7d9; --accent:#2a78d6;
  --go:#0ca30c; --go-bg:#f0faf0; --hold:#b98a00; --hold-bg:#fbf6e7; --cream:#faf7f1;
  --panel:#ffffff; --panel-hov:#fdfbf6 }
[data-theme="dark"] { --ink:#f2f1ec; --mut:#98968c; --line:#2c2c2a; --accent:#3987e5;
  --go:#3fbf3f; --go-bg:rgba(12,163,12,.14); --hold:#d9a520; --hold-bg:rgba(201,133,0,.13);
  --cream:#141413; --panel:#1c1c1b; --panel-hov:#232322 }
html { scroll-behavior:smooth }
body { background:var(--cream); transition:background .4s; color:var(--ink); font:16.5px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; min-height:100vh }
body::before, body::after { content:""; position:fixed; inset:-20%; pointer-events:none; z-index:-1 }
body::before { background:radial-gradient(640px 420px at 50% 8%, rgba(42,120,214,.08), transparent 70%); animation:d1 38s ease-in-out infinite alternate }
body::after { background:radial-gradient(520px 380px at 82% 92%, rgba(201,133,0,.05), transparent 70%); animation:d2 47s ease-in-out infinite alternate }
@keyframes d1 { to { transform:translate(4%,3%) scale(1.06) } }
@keyframes d2 { to { transform:translate(-5%,-4%) scale(1.08) } }
@media (prefers-reduced-motion: reduce) { body::before, body::after { animation:none } }
.bar { position:sticky; top:0; display:flex; align-items:center; gap:20px; padding:14px 28px; font-size:14.5px;
  background:color-mix(in srgb, var(--cream) 88%, transparent); backdrop-filter:blur(8px); z-index:5 }
.bar b a { color:var(--ink); text-decoration:none; font-weight:650 }
.bar a { color:var(--mut); text-decoration:none } .bar a.on, .bar a:hover { color:var(--ink) }
.bar .right { margin-left:auto } .bar .right a { font-size:13.5px }
.wrap { max-width:1440px; margin:0 auto; padding:26px 40px 60px }
.serif { font-family:Georgia,serif; font-weight:600; letter-spacing:-.5px }
.heroblock { min-height:calc(88vh - 50px); display:flex; flex-direction:column; align-items:center;
  justify-content:center; text-align:center; padding:20px; margin:0 auto; max-width:760px; position:relative }
.aurora { position:absolute; top:50%; left:50%; width:520px; height:380px; transform:translate(-50%,-58%);
  background:conic-gradient(from 0deg, rgba(42,120,214,.16), rgba(201,133,0,.10), rgba(27,175,122,.10), rgba(42,120,214,.16));
  border-radius:48% 52% 55% 45% / 55% 45% 52% 48%; filter:blur(64px); z-index:-1;
  animation:aur 22s ease-in-out infinite alternate }
@keyframes aur { to { transform:translate(-48%,-54%) rotate(50deg) scale(1.12) } }
@media (prefers-reduced-motion: reduce) { .aurora { animation:none } }
.count { font-size:14px; font-weight:700; letter-spacing:1.5px; color:var(--mut); text-transform:uppercase; margin-bottom:16px }
.count b { color:var(--accent) }
.progress { margin-top:16px; font-size:15px; color:var(--mut) }
.progress b { color:var(--ink) }
.heroblock h1 { font-family:Georgia,serif; font-weight:600; font-size:54px; line-height:1.14; letter-spacing:-.5px; margin-bottom:12px }
.heroblock h1 em { font-style:italic; color:var(--accent) }
.heroblock .sub { color:var(--mut); font-size:19px; margin-bottom:30px; max-width:580px }
.cta { display:inline-flex; background:var(--accent); color:#fff; font-size:17px; font-weight:650; padding:14px 34px;
  border-radius:999px; cursor:pointer; border:none; text-decoration:none; box-shadow:0 6px 20px rgba(42,120,214,.25) }
.cta:hover { transform:translateY(-2px) }
.doors { display:flex; gap:20px; justify-content:center; margin-top:34px; flex-wrap:wrap }
.door { width:330px; background:var(--panel); border:1px solid var(--line); border-radius:20px; padding:34px 32px; cursor:pointer;
  text-align:left; transition:.15s; box-shadow:0 4px 18px rgba(30,20,0,.04); text-decoration:none; color:var(--ink); display:block }
.door:hover { transform:translateY(-3px); box-shadow:0 12px 30px rgba(30,20,0,.09) }
.door h3 { font-family:Georgia,serif; font-size:25px; font-weight:600; margin-bottom:3px }
.door p { color:var(--mut); font-size:15.5px }
.door .cue { margin-top:18px; font-size:14.5px; font-weight:700; color:var(--accent) }
.hint { text-align:center; color:var(--mut); padding-bottom:20px; animation:bob 2.2s infinite }
.hint svg { display:inline-block }
a:focus:not(:focus-visible), button:focus:not(:focus-visible) { outline:none }
body:not([data-lane]) { cursor:url('data:image/svg+xml;utf8,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2222%22 height=%2228%22 viewBox=%220 0 22 28%22%3E%3Crect x=%221%22 y=%221%22 width=%2220%22 height=%2226%22 rx=%223%22 fill=%22white%22 stroke=%22%231c1b18%22 stroke-width=%221.6%22/%3E%3Ccircle cx=%227%22 cy=%228%22 r=%222.2%22 fill=%22%238d8a80%22/%3E%3Crect x=%2211%22 y=%226.2%22 width=%226%22 height=%221.6%22 rx=%22.8%22 fill=%22%238d8a80%22/%3E%3Crect x=%2211%22 y=%229.2%22 width=%225%22 height=%221.6%22 rx=%22.8%22 fill=%22%23c8c4ba%22/%3E%3Crect x=%224.5%22 y=%2214.5%22 width=%2213%22 height=%221.6%22 rx=%22.8%22 fill=%22%23b5b0a4%22/%3E%3Crect x=%224.5%22 y=%2218%22 width=%2213%22 height=%221.6%22 rx=%22.8%22 fill=%22%23b5b0a4%22/%3E%3Crect x=%224.5%22 y=%2221.5%22 width=%229%22 height=%221.6%22 rx=%22.8%22 fill=%22%23b5b0a4%22/%3E%3C/svg%3E') 3 2, auto }
@keyframes bob { 50% { transform:translateY(4px) } }
.rows { background:var(--panel); border:1px solid var(--line); border-radius:14px; overflow:hidden; box-shadow:0 4px 18px rgba(30,20,0,.04) }
.row { display:flex; align-items:center; gap:14px; padding:14px 20px; border-bottom:1px solid var(--line); color:inherit; text-decoration:none }
.row:last-child { border-bottom:none }
a.row:hover, .row.click:hover { background:var(--panel-hov); cursor:pointer }
.row.go { box-shadow:inset 3px 0 0 var(--go) } .row.hold { box-shadow:inset 3px 0 0 var(--hold) }
.mono { width:38px; height:38px; border-radius:10px; background:rgba(90,107,128,.14); color:#7a8aa0; font-weight:750; font-size:13.5px;
  display:grid; place-items:center; flex-shrink:0 }
.who { width:265px; flex-shrink:0 } .who b { font-size:15.5px }
.who .r { color:var(--mut); font-size:13.5px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:250px }
.fit { display:flex; align-items:center; gap:8px; width:105px; flex-shrink:0 }
.fit .t { height:5px; border-radius:3px; background:rgba(140,130,100,.2); width:56px; overflow:hidden }
.fit .t i { display:block; height:100%; background:var(--accent) }
.fit b { font-size:13.5px; font-variant-numeric:tabular-nums }
.why { flex:1; color:var(--mut); font-size:14.5px; min-width:0 }
.pill { font-size:12px; font-weight:750; padding:3px 11px; border-radius:999px; flex-shrink:0 }
.p-go { background:var(--go-bg); color:var(--go) } .p-hold { background:var(--hold-bg); color:var(--hold) }
.p-mut { background:rgba(140,130,100,.14); color:var(--mut) }
.p-nav { background:rgba(42,120,214,.12); color:var(--accent) }
.p-dead { background:rgba(208,59,59,.12); color:#d03b3b }
.thead { display:flex; gap:14px; padding:9px 20px 7px; font-size:11.5px; font-weight:700;
  letter-spacing:.6px; text-transform:uppercase; color:var(--mut); border-bottom:1px solid var(--line) }
.thead .h-who { width:265px } .thead .h-fit { width:105px } .thead .h-date { width:66px }
.thead .h-prof { width:74px } .thead .h-tats { width:64px } .thead .h-score { width:58px }
.thead .h-why { flex:1 } .thead .h-st { width:70px; text-align:right }
.c-tats { width:64px } .c-score { width:58px; font-weight:650; color:var(--ink) }
.cell { flex-shrink:0; font-size:13.5px; color:var(--mut); font-variant-numeric:tabular-nums }
.c-date { width:66px } .c-prof { width:74px; overflow:hidden; text-overflow:ellipsis }
.ract { display:inline-flex; gap:6px; flex-shrink:0; opacity:.55 }
a.row:hover .ract { opacity:1 }
.ract button { font:inherit; font-size:12.5px; font-weight:650; border:1px solid var(--line);
  border-radius:7px; padding:3px 10px; cursor:pointer; background:var(--panel); color:var(--mut) }
.ract button:hover { color:var(--accent); border-color:var(--accent) }
.row.rowdone { opacity:.45 }
.runbtn { font:inherit; font-size:13.5px; font-weight:650; color:var(--accent); background:none;
  border:1px solid var(--accent); border-radius:999px; padding:3px 14px; cursor:pointer; margin-left:auto }
.sortable { cursor:pointer } .sortable:hover { color:var(--ink) }
.sortable.asc::after { content:" \2191" } .sortable.desc::after { content:" \2193" }
.sech { display:flex; align-items:baseline; gap:10px; margin:26px 0 10px }
.sech h2 { font-family:Georgia,serif; font-size:24px; font-weight:600 }
.sech .n { color:var(--mut); font-size:14.5px }
.more { text-align:center; padding:12px; color:var(--accent); font-size:14.5px; cursor:pointer; border-top:1px solid var(--line) }
.hidden { display:none }
.storyline { color:var(--mut); font-size:16.5px; margin:4px 0 8px } .storyline b { color:var(--ink) }
.glance { max-width:780px; margin:0 auto; padding:26px 24px }
.glance h2 { font-family:Georgia,serif; font-size:27px; font-weight:600; text-align:center; margin-bottom:4px }
.glance .gs { color:var(--mut); font-size:15.5px; text-align:center; margin-bottom:16px }
.momentum { display:flex; justify-content:center; gap:44px; padding:30px 0 6px; text-align:center }
.momentum b { font-size:32px; font-weight:700; display:block } .momentum span { color:var(--mut); font-size:14px }
.lastcall { text-align:center; padding:34px 0 60px }
.cohead { display:flex; align-items:center; gap:14px; margin-bottom:4px }
.cohead .mono { width:44px; height:44px; font-size:15px }
.cohead h1 { font-size:37px }
.meta { color:var(--mut); font-size:15.5px; margin-bottom:20px } .meta b { color:var(--ink) }
.draftbox { background:var(--panel); border:1px solid var(--line); border-left:3px solid var(--accent);
  border-radius:0 12px 12px 0; padding:14px 18px; margin:10px 0; font-size:14px }
.draftbox .lab { font-size:13.5px; color:var(--mut); margin-bottom:6px }
.theme { margin-left:14px; cursor:pointer; border:none; background:none; font-size:15px; line-height:1 }
.copybtn { font:inherit; font-size:14px; font-weight:650; border:none; border-radius:8px; padding:6px 14px;
  cursor:pointer; background:var(--ink); color:#fff; margin-top:10px }
.copybtn.sm { margin-top:0; padding:4px 12px; font-size:12.5px; border-radius:7px }
.pbtn { font-size:12.5px; font-weight:650; border:1px solid var(--line); border-radius:7px; padding:3px 10px;
  background:var(--panel); color:var(--mut); text-decoration:none; flex-shrink:0 }
.pbtn:hover { color:var(--accent); border-color:var(--accent) }
.scene { position:fixed; inset:0; z-index:-1; pointer-events:none; overflow:hidden }
.scene svg { position:absolute; bottom:-8vh; left:-5%; width:110%; height:54vh; will-change:transform }
[data-theme="dark"] .scene { opacity:.4 }
.metapills { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin:0 0 10px }
.v-hi { color:var(--go) !important } .v-mid { color:var(--hold) !important } .v-lo { color:var(--mut) !important }
.charts { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:14px }
.panel { background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:16px 18px;
  box-shadow:0 4px 18px rgba(30,20,0,.04); margin-bottom:14px }
.charts .panel { margin-bottom:0 }
.panel h3 { font-family:Georgia,serif; font-size:17.5px; font-weight:600; margin-bottom:10px }
.frow { display:flex; align-items:center; gap:8px; margin:7px 0; font-size:14px }
.flab { width:116px; color:var(--mut); flex-shrink:0; text-align:right; overflow:hidden; text-overflow:ellipsis; white-space:nowrap }
.ftrack { flex:1 } .fbar { display:block; height:10px; border-radius:5px; background:var(--accent); opacity:.85; position:relative; overflow:hidden }
.fbar i { position:absolute; inset:0; background:var(--go); border-radius:5px }
.fnum { color:var(--mut); font-variant-numeric:tabular-nums; flex-shrink:0; min-width:34px; text-align:right }
.hgrid { display:flex; align-items:flex-end; gap:4px; height:104px }
.hcol { flex:1; display:flex; flex-direction:column; justify-content:flex-end; align-items:center; gap:3px; height:100% }
.hcol .hbar { width:100%; background:var(--accent); border-radius:3px 3px 0 0; min-height:1px; opacity:.85 }
.hcol .hx, .hcol .hn { font-size:10px; color:var(--mut) }
.cal { display:flex; gap:4px; padding:6px 0 2px; flex-wrap:wrap }
.cal i { width:23px; height:23px; border-radius:4px; background:var(--line); display:block; position:relative }
.cal i:hover::after { content:attr(data-tip); position:absolute; bottom:135%; left:50%; transform:translateX(-50%);
  background:var(--ink); color:var(--cream); font-size:11.5px; font-weight:650; font-style:normal;
  padding:3px 9px; border-radius:6px; white-space:nowrap; z-index:3 }
.cal .l1 { background:#cdeccd } .cal .l2 { background:#8fd48f } .cal .l3 { background:#3fae3f } .cal .l4 { background:#0b7a0b }
[data-theme="dark"] .cal i { background:#252523 }
[data-theme="dark"] .cal .l1 { background:#1e3b1e } [data-theme="dark"] .cal .l2 { background:#2c5c2c }
[data-theme="dark"] .cal .l3 { background:#3f8a3f } [data-theme="dark"] .cal .l4 { background:#57c957 }
.sech .coname { text-decoration:none; color:inherit } .sech .coname:hover h2 { color:var(--accent) }
.rise { opacity:0; transform:translateY(44px);
  transition:opacity .8s ease, transform 1.6s cubic-bezier(.28,1.9,.42,1) }
.rise.up { opacity:1; transform:none }
@media (prefers-reduced-motion: reduce) { .rise { opacity:1; transform:none; transition:none } }
"""

JS = """
function copyText(btn, txt) { navigator.clipboard.writeText(txt).then(() => {
  btn.textContent = 'Copied'; setTimeout(() => btn.textContent = 'Copy message', 1400); }); }
document.querySelectorAll('.more[data-for]').forEach(m => m.addEventListener('click', () => {
  const hid = [...document.querySelectorAll('.hidden[data-grp="' + m.dataset.for + '"]')];
  hid.slice(0, 20).forEach(r => r.classList.remove('hidden'));
  const left = Math.max(hid.length - 20, 0);
  if (left) m.textContent = 'show 20 more (' + left + ' hidden)'; else m.remove(); }));
document.querySelectorAll('.ract button').forEach(b => b.addEventListener('click', e => {
  e.preventDefault(); e.stopPropagation();
  const row = b.closest('a.row'), api = b.dataset.api;
  const undo = api === 'applied' && row.classList.contains('rowdone');
  const path = undo ? '/api/unapplied' : '/api/' + api;
  fetch(path, { method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ url: row.href }) })
  .then(r => { if (!r.ok) throw 0;
    if (api === 'applied' && !undo) {
      window.open(row.href, '_blank');
      row.classList.add('rowdone'); row.querySelector('.pill').textContent = 'applied';
      b.textContent = 'undo';
    } else if (undo) {
      row.classList.remove('rowdone'); row.querySelector('.pill').textContent = 'ready';
      b.textContent = 'apply';
    }
    if (api === 'remove') row.style.display = 'none';
    if (api === 'reveal') { b.textContent = 'opened'; setTimeout(() => b.textContent = 'resume', 1500); } })
  .catch(() => { b.textContent = 'needs server'; setTimeout(() => b.textContent = api, 1500); });
}));
document.querySelectorAll('.sortable').forEach(hcell => hcell.addEventListener('click', () => {
  const box = hcell.closest('.rows'), key = hcell.dataset.key;
  const dir = hcell.classList.contains('asc') ? -1 : 1;
  box.querySelectorAll('.sortable').forEach(x => x.classList.remove('asc', 'desc'));
  hcell.classList.add(dir === 1 ? 'asc' : 'desc');
  const rows = [...box.querySelectorAll('a.row')];
  const visible = rows.filter(r => !r.classList.contains('hidden')).length;
  rows.sort((a, b) => {
    const av = a.dataset[key] || '', bv = b.dataset[key] || '';
    const an = parseFloat(av), bn = parseFloat(bv);
    return (!isNaN(an) && !isNaN(bn)) ? (an - bn) * dir : av.localeCompare(bv) * dir;
  });
  const more = box.querySelector('.more[data-for]');
  rows.forEach((r, i) => { r.classList.toggle('hidden', i >= visible);
    if (more) box.insertBefore(r, more); else box.appendChild(r); });
}));
const saved = localStorage.getItem('theme');
if (saved === 'dark') document.documentElement.dataset.theme = 'dark';
const tbtn = document.querySelector('.theme');
function paintTheme() { tbtn.textContent = document.documentElement.dataset.theme === 'dark' ? '☀️' : '🌙'; }
if (tbtn) { paintTheme(); tbtn.addEventListener('click', () => {
  const d = document.documentElement.dataset.theme === 'dark';
  if (d) delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = 'dark';
  localStorage.setItem('theme', d ? 'light' : 'dark'); paintTheme(); }); }
if (document.body.dataset.lane && document.documentElement.dataset.theme !== 'dark') {
  const from = [250, 247, 241], to = [255, 255, 255];
  addEventListener('scroll', () => {
    const k = Math.min(scrollY / 260, 1);
    document.body.style.background = 'rgb(' + from.map((f, i) => Math.round(f + (to[i] - f) * k)).join(',') + ')';
  }, { passive: true });
}
if (!matchMedia('(prefers-reduced-motion: reduce)').matches) {
  const ob = new IntersectionObserver(es => es.forEach(e => {
    if (e.isIntersecting) { e.target.classList.add('up'); ob.unobserve(e.target); }
  }), { rootMargin: '0px 0px -10% 0px' });
  document.querySelectorAll('.sech, .rows, .panel, .glance, .lastcall, .draftbox, .doors, .momentum, .storyline, .metapills').forEach(el => {
    if (el.getBoundingClientRect().top > innerHeight * 0.92) { el.classList.add('rise'); ob.observe(el); }
  });
}
const scene = document.querySelector('.scene');
if (scene && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
  const layers = scene.querySelectorAll('svg');
  addEventListener('scroll', () => {
    layers.forEach((l, i) => l.style.transform = 'translateY(' + scrollY * (0.10 + i * 0.10) + 'px)');
    scene.style.opacity = Math.max(1 - scrollY / 900, 0.12);
  }, { passive: true });
}
"""


SCENE = """<div class="scene">
<svg viewBox="0 0 1440 420" preserveAspectRatio="none">
  <circle cx="1150" cy="80" r="58" fill="rgba(201,133,0,.10)"/>
  <path d="M0,300 C240,258 430,342 720,310 C1010,278 1210,332 1440,288 L1440,420 L0,420 Z" fill="rgba(42,120,214,.06)"/>
</svg>
<svg viewBox="0 0 1440 420" preserveAspectRatio="none">
  <path d="M0,338 C210,298 480,382 780,344 C1080,308 1270,372 1440,330 L1440,420 L0,420 Z" fill="rgba(42,120,214,.09)"/>
  <path d="M0,388 C260,358 560,410 860,384 C1130,361 1310,402 1440,376 L1440,420 L0,420 Z" fill="rgba(201,133,0,.06)"/>
</svg>
</div>"""


# ------------------------------------------------------------------ charts

def _applied_panel() -> str:
    """Top-of-page strip: one square per day, last 20 days; hover for the count."""
    counts = Counter((a.get("applied_date") or "")[:10]
                     for a in tracker.list_applications()
                     if a.get("applied_date") and not a.get("removed"))
    today = date.today()
    cells = ""
    for i in range(19, -1, -1):
        day = today - timedelta(days=i)
        n = counts.get(day.isoformat(), 0)
        lvl = "l4" if n >= 50 else "l3" if n >= 30 else "l2" if n >= 10 else "l1" if n else ""
        cells += f'<i class="{lvl}" data-tip="{day.strftime("%b %d")}: {n}"></i>'
    today_n = counts.get(today.isoformat(), 0)
    week = sum(counts.get((today - timedelta(days=i)).isoformat(), 0) for i in range(7))
    if week > 150:
        line = f"{week} this week. Nobody is outworking you."
    elif today_n == 0:
        line = "Zero today. The squares do not fill themselves."
    else:
        line = f"{today_n} today, {week} this week."
    return (f'<div class="panel"><h3>Applications per day</h3>'
            f'<div class="storyline" style="margin:0 0 4px">{line}</div>'
            f'<div class="cal">{cells}</div></div>')


def _bar_rows(items: list[tuple[str, int, int | None]]) -> str:
    """Label / bar / number rows. Optional third value renders as a green share."""
    mx = max((n for _, n, _ in items), default=0) or 1
    out = ""
    for label, n, part in items:
        inner = f'<i style="width:{round(100 * part / n) if n else 0}%"></i>' if part is not None else ""
        num = f"{part}/{n}" if part is not None else str(n)
        out += (f'<div class="frow"><span class="flab">{esc(label)}</span>'
                f'<span class="ftrack"><span class="fbar" style="width:{max(2, round(100 * n / mx))}%">{inner}</span></span>'
                f'<span class="fnum">{num}</span></div>')
    return out or '<div class="frow"><span class="flab"></span><span class="fnum">no data yet</span></div>'


def _apply_charts() -> str:
    live = [a for a in tracker.list_applications() if not a.get("removed")]
    mats = [int(a["master_ats"]) for a in live if isinstance(a.get("master_ats"), (int, float))]
    funnel = [("found", sum(1 for a in live if a.get("status") == "found"), None),
              ("high fit 70+", sum(1 for v in mats if v >= 70), None),
              ("tailored", sum(1 for a in live if _dash._has_resume(a)), None),
              ("applied", sum(1 for a in live if a.get("status") in _dash._SUBMITTED), None)]
    buckets = [0] * 10
    for v in mats:
        buckets[min(9, v // 10)] += 1
    bmax = max(buckets) or 1
    hist = "".join(
        f'<div class="hcol" title="fit {i * 10} to {i * 10 + 9}: {n} roles">'
        f'<span class="hn">{n or ""}</span><div class="hbar" style="height:{round(84 * n / bmax)}%"></div>'
        f'<span class="hx">{i * 10}</span></div>' for i, n in enumerate(buckets))
    prof_t, prof_a = Counter(), Counter()
    for a in live:
        if not a.get("profile"):
            continue
        prof_t[a["profile"]] += 1
        if a.get("status") in _dash._SUBMITTED:
            prof_a[a["profile"]] += 1
    tracks = [(p.replace("_", " "), prof_t[p], prof_a.get(p, 0))
              for p in sorted(prof_t, key=lambda p: -prof_t[p])]
    return (f'<div class="sech"><h2>The numbers</h2><span class="n">the whole tracker at a glance</span></div>'
            f'<div class="charts">'
            f'<div class="panel"><h3>Pipeline funnel</h3>{_bar_rows(funnel)}</div>'
            f'<div class="panel"><h3>Fit distribution</h3><div class="hgrid">{hist}</div></div>'
            f'<div class="panel"><h3>Tracks, applied of total</h3>{_bar_rows(tracks)}</div>'
            f'</div>')


def _network_charts(companies: list[dict]) -> str:
    touches = [o for c in companies for p in c.get("people", []) for o in _touches(p)]
    replies = sum(1 for o in touches if o.get("outcome") in ("replied", "referred"))
    tiles = "".join(f"<div><b>{v}</b><span>{k}</span></div>" for v, k in [
        (len(companies), "companies"),
        (sum(len(c.get("people", [])) for c in companies), "people mapped"),
        (len(touches), "messages sent"), (replies, "replies")])
    top = sorted((r for r in _heat_rows().values() if r.get("match_new_30d", 0) > 0),
                 key=lambda r: -r["match_new_30d"])[:8]
    bars = _bar_rows([(r["company"], r["match_new_30d"], None) for r in top])
    return (f'<div class="sech"><h2>The numbers</h2><span class="n">is the outreach paying off</span></div>'
            f'<div class="charts">'
            f'<div class="panel"><h3>Outreach so far</h3><div class="momentum" style="padding:14px 0 4px">{tiles}</div></div>'
            f'<div class="panel"><h3>Matching roles opened, last 30 days</h3>{bars}</div>'
            f'</div>')


def _page(title: str, body: str, active: str = "") -> str:
    nav = "".join(
        f'<a href="{h}" class="{"on" if active == k else ""}">{t}</a>'
        for k, h, t in [("apply", "/apply", "Applications"), ("net", "/network", "Networking")])
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)}</title><style>{CSS}</style></head>'
            f'<body{" data-lane=1" if active else ""}>'
            f'<div class="bar"><b><a href="/">pipeline.</a></b>{nav}'
            f'<span class="right"><a href="/classic">classic view</a>'
            f'<button class="theme" title="theme"></button></span></div>'
            f'{body}<script>{JS}</script></body></html>')


def _app_row(a: dict, cls: str, pill: str, pill_cls: str, why: str, cap: bool) -> str:
    mats = a.get("master_ats")
    fit = (f'<span class="fit"><span class="t"><i style="width:{min(int(mats), 100)}%"></i></span>'
           f'<b>{mats}</b></span>') if isinstance(mats, (int, float)) else '<span class="fit"></span>'
    grp = f' data-grp="{cap}"' if cap else ""
    hide = " hidden" if cap else ""
    url = esc(a.get("url") or "#")
    posted_full = esc((a.get("posted_date") or a.get("date") or "")[:10])
    posted = posted_full[5:]  # MM-DD display
    tats = a.get("match_score") if _dash._has_resume(a) else None
    score = a.get("resume_score")
    data = (f' data-co="{esc(a.get("company", ""))}"'
            f' data-fit="{mats if isinstance(mats, (int, float)) else -1}"'
            f' data-tats="{tats if isinstance(tats, (int, float)) else -1}"'
            f' data-score="{score if isinstance(score, (int, float)) else -1}"'
            f' data-posted="{posted_full}" data-prof="{esc(a.get("profile") or "")}"')
    prof = esc((a.get("profile") or "").replace("_", " "))
    tats_cls = ("" if not isinstance(tats, (int, float))
                else " v-hi" if tats >= 85 else " v-mid" if tats >= 70 else " v-lo")
    score_cls = ("" if not isinstance(score, (int, float))
                 else " v-hi" if score >= 8 else " v-mid" if score >= 6 else " v-lo")
    return (f'<a class="row {cls}{hide}"{grp}{data} href="{url}" target="_blank">'
            f'<span class="mono">{esc(_monogram(a.get("company", "?")))}</span>'
            f'<span class="who"><b>{esc(a.get("company"))}</b><div class="r">{esc(a.get("role"))}</div></span>'
            f'{fit}<span class="cell c-tats{tats_cls}">{tats if tats is not None else ""}</span>'
            f'<span class="cell c-score{score_cls}">{f"{score}/10" if score is not None else ""}</span>'
            f'<span class="cell c-date">{posted}</span>'
            f'<span class="cell c-prof">{prof}</span>'
            f'<span class="why">{esc(why)}</span>'
            f'<span class="ract"><button data-api="applied">apply</button>'
            f'<button data-api="reveal">resume</button>'
            f'<button data-api="remove">hide</button></span>'
            f'<span class="pill {pill_cls}">{esc(pill)}</span></a>')


def _person_row(item: dict, cls: str, pill: str, pill_cls: str, why: str) -> str:
    p, c = item["person"], item["company"]
    name = p["name"].split("[")[0].strip()
    slug = slugify(c["name"])
    return (f'<a class="row {cls}" href="/company/{slug}">'
            f'<span class="mono">{esc(_monogram(name))}</span>'
            f'<span class="who"><b>{esc(name)}</b><div class="r">{esc(c["name"])} · {esc(p.get("title", ""))}</div></span>'
            f'<span class="why">{esc(why)}</span>'
            f'<span class="pill {pill_cls}">{esc(pill)}</span></a>')


# ------------------------------------------------------------------ pages

def render_entry() -> str:
    companies = _net_companies()
    people = _people_actions(companies)
    apps = _app_rows()
    story = _story(people, apps)
    n_send = len(people["replies"]) + len(people["sends"]) + len(people["due"])
    n_ready = len(apps["ready"])
    applied = sum(1 for a in tracker.list_applications()
                  if a.get("status") in _dash._SUBMITTED and not a.get("removed"))
    touches = [o for c in companies for p in c.get("people", []) for o in _touches(p)]
    replies = sum(1 for o in touches if o.get("outcome") in ("replied", "referred"))
    rate = f"{round(100 * replies / len(touches))}%" if touches else "-"

    today_iso = date.today().isoformat()
    done_today = sum(1 for o in touches if o.get("date") == today_iso)
    done_today += sum(1 for a in tracker.list_applications()
                      if (a.get("applied_date") or "")[:10] == today_iso and not a.get("removed"))
    open_loops = n_send + min(n_ready, 3)
    hour = datetime.now().hour
    greet = "Morning" if hour < 12 else "Afternoon" if hour < 18 else "Evening"
    first = "there"
    try:
        net_cfg = json.loads((config.ROOT / "config" / "network.json").read_text())
        first = net_cfg.get("candidate", {}).get("first_name", first)
    except Exception:
        pass

    glance_rows = ""
    for item in (people["replies"] + people["sends"])[:2]:
        glance_rows += _person_row(item, "go", "2 min", "p-go",
                                   "one message, draft ready")
    if apps["ready"]:
        a = apps["ready"][0]
        glance_rows += _app_row(a, "go", "3 min", "p-go", "two clicks to applied", "")

    body = f"""{SCENE}
<div class="heroblock">
  <div class="aurora"></div>
  <div class="count">{esc(greet)}, {esc(first)}</div>
  <h1>{open_loops} doors are open. <em>Pick a lane.</em></h1>
  <div class="sub">{esc(story['teaser'])}</div>
  {f'<div class="progress"><b>{done_today} done today.</b> {open_loops} to go.</div>' if done_today else ''}
  <div class="doors">
    <a class="door" href="/apply"><h3>Applications</h3>
      <p>tailored, verified, ready to send</p><div class="cue">{n_ready} ready</div></a>
    <a class="door" href="/network"><h3>Networking</h3>
      <p>people who can open doors for you</p><div class="cue">{n_send} waiting</div></a>
  </div>
</div>
<div class="hint">v</div>
<div class="glance">
  <h2>Here is the whole day.</h2>
  <div class="gs">Done when this list is empty.</div>
  <div class="rows">{glance_rows or '<div class="row"><span class="why">Nothing urgent. The sweep runs tonight.</span></div>'}</div>
</div>
<div class="glance">
  <h2>It is working.</h2>
  <div class="momentum">
    <div><b>{rate}</b><span>warm replies</span></div>
    <div><b>{replies}</b><span>replies</span></div>
    <div><b>{applied}</b><span>applied</span></div>
  </div>
</div>
<div class="lastcall"><a class="cta" href="{esc(story['lane'])}">Start in {esc(story['lane_name'])}</a></div>"""
    return _page("Pipeline", body)


def render_apply() -> str:
    apps = _app_rows()
    ready, holds, fresh = apps["ready"], apps["holds"], apps["fresh"]
    story = (f"<b>{esc(ready[0].get('company'))} first.</b> " if ready else "")
    rows = ""
    for i, a in enumerate(ready):
        rows += _app_row(a, "go", "ready", "p-go", "",
                         "ready" if i >= 5 else "")
    for a in holds:
        rows += _app_row(a, "hold", "hold", "p-hold",
                         "referral in flight, apply after it lands", "")
    if len(ready) > 5:
        rows += f'<div class="more" data-for="ready">show 20 more ({len(ready) - 5} hidden)</div>'
    frows = ""
    for i, a in enumerate(fresh):
        frows += _app_row(a, "", "tailor", "p-mut", "found today",
                          "fresh" if i >= 5 else "")
    if len(fresh) > 5:
        frows += f'<div class="more" data-for="fresh">show 20 more ({len(fresh) - 5} hidden)</div>'

    body = f"""<div class="wrap">
  <h1 class="serif" style="font-size:36px">Applications</h1>
  <div class="storyline">{story}Amber rows wait on a referral.</div>
  {_applied_panel()}
  <div class="sech"><h2>Ready</h2><span class="n">{min(len(ready),5)} of {len(ready)} shown, best first</span></div>
  <div class="rows"><div class="thead"><span style="width:34px"></span><span class="h-who sortable" data-key="co">Company / Role</span><span class="h-fit sortable" data-key="fit">Fit</span><span class="h-tats sortable" data-key="tats">Tailored</span><span class="h-score sortable" data-key="score">Score</span><span class="h-date sortable" data-key="posted">Posted</span><span class="h-prof sortable" data-key="prof">Track</span><span class="h-why">Note</span><span class="h-st">Status</span></div>{rows or '<div class="row"><span class="why">Nothing tailored yet. Run the pipeline.</span></div>'}</div>
  <div class="sech"><h2>Fresh finds</h2><span class="n">today's sweep, 70+ fit only</span>
    <button class="runbtn" onclick="fetch('/api/run-pipeline').then(r => r.json()).then(d => this.textContent = 'running').catch(() => this.textContent = 'needs server')">run sweep</button></div>
  <div class="rows"><div class="thead"><span style="width:34px"></span><span class="h-who sortable" data-key="co">Company / Role</span><span class="h-fit sortable" data-key="fit">Fit</span><span class="h-tats sortable" data-key="tats">Tailored</span><span class="h-score sortable" data-key="score">Score</span><span class="h-date sortable" data-key="posted">Posted</span><span class="h-prof sortable" data-key="prof">Track</span><span class="h-why">Note</span><span class="h-st">Status</span></div>{frows or '<div class="row"><span class="why">No fresh high-fit roles today.</span></div>'}</div>
  {_apply_charts()}
  <div class="rows" style="margin-top:26px"><a class="row" href="/network" style="justify-content:space-between">
    <span class="who" style="width:auto"><b>Done applying?</b><div class="r">people are waiting in Networking</div></span>
    <span class="pill p-nav">Networking</span></a></div>
</div>"""
    return _page("Applications", body, "apply")


def render_network() -> str:
    companies = _net_companies()
    people = _people_actions(companies)
    apps = _app_rows()
    s = _story(people, apps)
    story_line = (f"<b>{s['h'].replace('<em>', '').replace('</em>', '')}</b>"
                  if s.get("lane") == "/network" else "Referral before application, always.")

    order = {"reply": 0, "send": 1, "nudge": 2, "waiting": 3}
    heat_rank = {"HOT": 0, "WARM": 1, "COOL": 2, "DEAD": 3}

    def co_key(c):
        states = [_person_state(c, p)[0] for p in c.get("people", [])]
        return (min((order[st] for st in states), default=4),
                heat_rank.get((c.get("heat") or "").upper(), 4))

    blocks = ""
    newest_first = sorted(companies, key=lambda c: c.get("last_scouted") or "", reverse=True)
    for c in sorted(newest_first, key=co_key):
        slug = slugify(c["name"])
        heat = (c.get("heat") or "?").upper()
        ppl = sorted(c.get("people", []), key=lambda p: order.get(_person_state(c, p)[0], 4))
        prows = ""
        for p in ppl:
            state, cls, pcls, why = _person_state(c, p)
            name = p["name"].split("[")[0].strip()
            hook = (p.get("hook") or "").split(";")[0].strip()
            url = p.get("linkedin") or ("https://www.linkedin.com/search/results/people/?keywords="
                                        + quote_plus(f"{name} {c['name']}"))
            copy = ""
            draft = _person_draft(c, p)
            if draft:
                js = draft.replace("\\", "\\\\").replace("'", "\\'")
                copy = ('<button class="copybtn sm" onclick="copyText(this, '
                        f"'{esc(js)}')\">Copy message</button>")
            prows += (f'<div class="row {cls}">'
                      f'<span class="mono">{esc(_monogram(name))}</span>'
                      f'<span class="who"><b>{esc(name)}</b><div class="r">{esc(p.get("title", ""))}</div></span>'
                      f'<span class="why">{esc(why or hook)}</span>'
                      f'<span class="ract" style="opacity:1">{copy}'
                      f'<a class="pbtn" href="{esc(url)}" target="_blank">profile</a></span>'
                      f'<span class="pill {pcls}">{state}</span></div>')
        if not prows:
            prows = '<div class="row"><span class="why">no people mapped yet</span></div>'
        links = []
        for src_line in _sources(c)[:3]:
            tok = src_line.split()[0].strip().rstrip(",")
            href = tok if tok.startswith("http") else "https://" + tok
            label = tok.replace("https://", "").replace("http://", "")
            label = label if len(label) <= 46 else label[:43] + "..."
            links.append(f'<a style="color:var(--accent);text-decoration:none" '
                         f'href="{esc(href)}" target="_blank">{esc(label)}</a>')
        if links:
            prows += ('<div class="row"><span class="why">sources: '
                      + ", ".join(links) + "</span></div>")
        fit_short = esc((c.get("fit") or "").split(";")[0])
        blocks += (
            f'<div class="sech"><a class="coname" href="/company/{slug}"><h2>{esc(c["name"])}</h2></a>'
            f'<span class="pill {HEAT_PILL.get(heat, "p-mut")}">{esc(heat)}</span>'
            f'<span class="n">{fit_short}</span>'
            f'<a class="pbtn" style="margin-left:auto" href="/company/{slug}">full page</a></div>'
            f'<div class="rows">{prows}</div>')
    if not blocks:
        blocks = ('<div class="sech"><h2>Companies</h2></div><div class="rows">'
                  '<div class="row"><span class="why">No companies scouted yet. '
                  'Run /scout with a company name.</span></div></div>')

    body = f"""<div class="wrap">
  <h1 class="serif" style="font-size:36px">Networking</h1>
  <div class="storyline">{story_line} Green rows have a message ready to copy.</div>
  {blocks}
  {_network_charts(companies)}
  <div class="rows" style="margin-top:26px"><a class="row" href="/apply" style="justify-content:space-between">
    <span class="who" style="width:auto"><b>Messages sent?</b><div class="r">roles are ready in Applications</div></span>
    <span class="pill p-nav">Applications</span></a></div>
</div>"""
    return _page("Networking", body, "net")


def render_company(slug: str) -> str | None:
    companies = _net_companies()
    c = next((x for x in companies if slugify(x["name"]) == slug), None)
    if not c:
        return None
    fit_main, _, fit_extra = (c.get("fit") or "").partition(";")
    fit_main, fit_extra = fit_main.strip(), fit_extra.strip()
    draft = _first_draft(c)
    draft_html = ""
    if draft:
        draft_js = draft.replace("\\", "\\\\").replace("'", "\\'")
        draft_html = (f'<div class="sech"><h2>The one move</h2></div>'
                      f'<div class="draftbox"><div class="lab">Primary draft from the dossier</div>'
                      f'{esc(draft)}'
                      f'<div><button class="copybtn" onclick="copyText(this, \'{esc(draft_js)}\')">Copy message</button></div></div>')
    hr = _heat_rows().get(slug, {})
    stats_html = ""
    if hr:
        fresh_links = "".join(
            f'<a class="row" href="{esc(j["url"])}" target="_blank">'
            f'<span class="mono">-</span>'
            f'<span class="who"><b>{esc(j["role"])}</b><div class="r">posted {esc(j["posted"])}</div></span>'
            f'<span class="pill p-go">open</span></a>'
            for j in hr.get("freshest_matches", [])[:5])
        stats_html = (
            f'<div class="sech"><h2>Hiring heat</h2>'
            f'<span class="n">{hr.get("open_roles", 0)} open, {hr.get("new_30d", 0)} new in 30d, '
            f'{hr.get("accel", 0):.1f}x pace, {hr.get("match_new_30d", 0)} matching you</span></div>'
            + (f'<div class="rows">{fresh_links}</div>' if fresh_links else ""))
    acts = _open_actions(c)
    acts_html = ""
    if acts:
        acts_html = ('<div class="sech"><h2>Next actions</h2></div><div class="rows">'
                     + "".join(f'<div class="row hold"><span class="why">{esc(a)}</span></div>'
                               for a in acts) + '</div>')
    prows = ""
    for p in sorted(c.get("people", []), key=lambda p: -sum((p.get("rwl") or [0, 0, 0])[:2])):
        name = p["name"].split("[")[0].strip()
        t_ = _touches(p)
        state = ("replied" if t_ and t_[-1].get("outcome") in ("replied", "referred")
                 else "contacted" if t_ else "send")
        cls, pcls = ("go", "p-go") if state != "contacted" else ("hold", "p-hold")
        from urllib.parse import quote_plus
        url = p.get("linkedin") or ("https://www.linkedin.com/search/results/people/?keywords="
                                    + quote_plus(f"{name} {c['name']}"))
        log = "; ".join(f'{o.get("date","")} {o.get("channel","")} touch {o.get("touch_n","")}'
                        f' {o.get("outcome","")}' for o in t_) if t_ else ""
        prows += (f'<a class="row {cls}" href="{esc(url)}" target="_blank">'
                  f'<span class="mono">{esc(_monogram(name))}</span>'
                  f'<span class="who"><b>{esc(name)}</b><div class="r">{esc(p.get("title", ""))}</div></span>'
                  f'<span class="why">{esc(p.get("hook", ""))[:80]}'
                  f'{f"<br><span style=\"font-size:11.5px\">{esc(log)}</span>" if log else ""}</span>'
                  f'<span class="pill {pcls}">{state}</span></a>')

    apps = [a for a in tracker.list_applications()
            if slugify(a.get("company", "")) == slug and not a.get("removed")]
    arows = ""
    for a in apps[:5]:
        tailored = _dash._has_resume(a)
        arows += _app_row(a, "go" if tailored else "", "resume ready" if tailored else a.get("status", ""),
                          "p-go" if tailored else "p-mut", "", "")
    if not arows:
        arows = ('<div class="row"><span class="mono" style="background:transparent;border:1px dashed #d8d2c4;color:#b5b0a4">-</span>'
                 '<span class="why">No open roles. Get known before the req exists.</span></div>')

    body = f"""<div class="wrap">
  <div class="cohead"><span class="mono">{esc(_monogram(c["name"]))}</span>
    <h1 class="serif">{esc(c["name"])}</h1></div>
  <div class="metapills"><span class="pill {HEAT_PILL.get((c.get("heat") or "").upper(), "p-mut")}">{esc((c.get("heat") or "?").upper())}</span>
    <span class="pill p-mut">scouted {esc(c.get("last_scouted", "?"))}</span>
    {f'<a class="pbtn" href="{esc(c.get("website"))}" target="_blank">website</a>' if c.get("website") else ''}</div>
  <div class="meta"><b>{esc(fit_main)}</b>{f' <span style="font-size:12.5px">{esc(fit_extra)}</span>' if fit_extra else ''}</div>
  {draft_html}{acts_html}{stats_html}
  <div class="sech"><h2>People</h2><span class="n">ranked by reachability</span></div>
  <div class="rows">{prows or '<div class="row"><span class="why">none mapped yet</span></div>'}</div>
  <div class="sech"><h2>Roles here</h2></div>
  <div class="rows">{arows}</div>
</div>"""
    return _page(c["name"], body, "net")
