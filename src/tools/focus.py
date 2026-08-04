"""Focus UI: the official interface. One story, one action, rows behind it.

Design laws (decided 2026-08-03, reference test: "would Apple / The Browser
Company / IDEO have done this?"):
  - One story per screen, centered. Radical word economy.
  - Exactly one saturated CTA per view; cream + ink + one blue.
  - Green appears ONLY on do-now rows, amber ONLY on waiting rows.
  - 3-5 rows per section, best first, counts visible, "show all" expands.
  - No emojis, no em dashes, no icon where a word fits.
  - Ambient drifting background, slow enough to never catch moving.

Pages (rendered on demand by dashboard_server):
  /                entry: greeting, story of the day, two doors, scroll funnel
  /apply           applications lane (ready rows + fresh finds + cross-door)
  /network         networking lane (send today + waiting + companies + cross-door)
  /company/<slug>  one company: the one move, people, roles
Old dashboards stay at /classic and /network-classic.
"""

from __future__ import annotations

import html as _html
import json
import pathlib
import re
from datetime import date, datetime, timedelta

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


def _touches(p: dict) -> list[dict]:
    return p.get("outreach") or []


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


def _story(people: dict, apps: dict) -> dict:
    """The one thing that matters most today, as headline / line / cta / href."""
    if people["replies"]:
        i = people["replies"][0]
        n = i["person"]["name"].split("[")[0].strip().split()[0]
        return {"h": f"{esc(n)} said yes. <em>Answer today.</em>",
                "p": f"A warm door at {esc(i['company']['name'])} is open right now. Momentum decays in days, not weeks.",
                "cta": "Open the thread", "href": f"/company/{slugify(i['company']['name'])}"}
    if people["sends"]:
        i = people["sends"][0]
        n = i["person"]["name"].split("[")[0].strip().split()[0]
        co = i["company"]["name"]
        return {"h": f"{esc(n)} can open the door at {esc(co)}. <em>Ask.</em>",
                "p": "The draft is written. One message, referral before application, always.",
                "cta": "Show me the message", "href": f"/company/{slugify(co)}"}
    if people["due"]:
        i = people["due"][0]
        n = i["person"]["name"].split("[")[0].strip().split()[0]
        return {"h": f"{esc(n)} went quiet. <em>One gentle nudge.</em>",
                "p": f"Touch {len(_touches(i['person'])) + 1} of 3 at {esc(i['company']['name'])}. Most replies come from the follow-up.",
                "cta": "Show me the nudge", "href": f"/company/{slugify(i['company']['name'])}"}
    if apps["ready"]:
        a = apps["ready"][0]
        return {"h": f"{esc(a.get('company'))} is ready. <em>Two clicks.</em>",
                "p": f"{esc(a.get('role'))}. Resume tailored and verified, posting live.",
                "cta": "Open the posting", "href": "/apply"}
    return {"h": "You're clear. <em>Well done.</em>",
            "p": "Every thread is moving. Come back after the next discovery sweep.",
            "cta": "See the pipeline", "href": "/apply"}


# ------------------------------------------------------------------ html

CSS = """
* { box-sizing:border-box; margin:0 }
:root { --ink:#1c1b18; --mut:#8d8a80; --line:#eee7d9; --accent:#2a78d6;
  --go:#0ca30c; --go-bg:#f0faf0; --hold:#b98a00; --hold-bg:#fbf6e7; --cream:#faf7f1 }
html { scroll-behavior:smooth }
body { background:var(--cream); color:var(--ink); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; min-height:100vh }
body::before, body::after { content:""; position:fixed; inset:-20%; pointer-events:none; z-index:-1 }
body::before { background:radial-gradient(640px 420px at 50% 8%, rgba(42,120,214,.08), transparent 70%); animation:d1 38s ease-in-out infinite alternate }
body::after { background:radial-gradient(520px 380px at 82% 92%, rgba(201,133,0,.05), transparent 70%); animation:d2 47s ease-in-out infinite alternate }
@keyframes d1 { to { transform:translate(4%,3%) scale(1.06) } }
@keyframes d2 { to { transform:translate(-5%,-4%) scale(1.08) } }
@media (prefers-reduced-motion: reduce) { body::before, body::after { animation:none } }
.bar { position:sticky; top:0; display:flex; align-items:center; gap:20px; padding:14px 28px; font-size:13px;
  background:rgba(250,247,241,.9); backdrop-filter:blur(8px); z-index:5 }
.bar b a { color:var(--ink); text-decoration:none; font-weight:650 }
.bar a { color:var(--mut); text-decoration:none } .bar a.on, .bar a:hover { color:var(--ink) }
.bar .right { margin-left:auto } .bar .right a { font-size:12px }
.wrap { max-width:820px; margin:0 auto; padding:26px 24px 60px }
.serif { font-family:Georgia,serif; font-weight:600; letter-spacing:-.5px }
.heroblock { min-height:calc(88vh - 50px); display:flex; flex-direction:column; align-items:center;
  justify-content:center; text-align:center; padding:20px; margin:0 auto; max-width:760px }
.heroblock h1 { font-family:Georgia,serif; font-weight:600; font-size:42px; line-height:1.14; letter-spacing:-.5px; margin-bottom:12px }
.heroblock h1 em { font-style:italic; color:var(--accent) }
.heroblock .sub { color:var(--mut); font-size:16px; margin-bottom:30px; max-width:460px }
.cta { display:inline-flex; background:var(--accent); color:#fff; font-size:15px; font-weight:650; padding:12px 28px;
  border-radius:999px; cursor:pointer; border:none; text-decoration:none; box-shadow:0 6px 20px rgba(42,120,214,.25) }
.cta:hover { transform:translateY(-2px) }
.doors { display:flex; gap:16px; justify-content:center; margin-top:34px; flex-wrap:wrap }
.door { width:250px; background:#fff; border:1px solid var(--line); border-radius:18px; padding:24px; cursor:pointer;
  text-align:left; transition:.15s; box-shadow:0 4px 18px rgba(30,20,0,.04); text-decoration:none; color:var(--ink); display:block }
.door:hover { transform:translateY(-3px); border-color:var(--accent) }
.door h3 { font-family:Georgia,serif; font-size:19px; font-weight:600; margin-bottom:3px }
.door p { color:var(--mut); font-size:13px }
.door .cue { margin-top:14px; font-size:12.5px; font-weight:700; color:var(--accent) }
.hint { text-align:center; color:var(--mut); font-size:14px; padding-bottom:20px; animation:bob 2.2s infinite }
@keyframes bob { 50% { transform:translateY(4px) } }
.rows { background:#fff; border:1px solid var(--line); border-radius:14px; overflow:hidden; box-shadow:0 4px 18px rgba(30,20,0,.04) }
.row { display:flex; align-items:center; gap:14px; padding:12px 18px; border-bottom:1px solid #f5f0e6; color:inherit; text-decoration:none }
.row:last-child { border-bottom:none }
a.row:hover, .row.click:hover { background:#fdfbf6; cursor:pointer }
.row.go { box-shadow:inset 3px 0 0 var(--go) } .row.hold { box-shadow:inset 3px 0 0 var(--hold) }
.mono { width:34px; height:34px; border-radius:9px; background:#eef2f7; color:#5a6b80; font-weight:750; font-size:12.5px;
  display:grid; place-items:center; flex-shrink:0 }
.who { width:230px; flex-shrink:0 } .who b { font-size:14px }
.who .r { color:var(--mut); font-size:12.5px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:215px }
.fit { display:flex; align-items:center; gap:8px; width:105px; flex-shrink:0 }
.fit .t { height:5px; border-radius:3px; background:#efe9db; width:56px; overflow:hidden }
.fit .t i { display:block; height:100%; background:var(--accent) }
.fit b { font-size:12.5px; font-variant-numeric:tabular-nums }
.why { flex:1; color:var(--mut); font-size:13px; min-width:0 }
.pill { font-size:11px; font-weight:750; padding:3px 11px; border-radius:999px; flex-shrink:0 }
.p-go { background:var(--go-bg); color:var(--go) } .p-hold { background:var(--hold-bg); color:var(--hold) }
.p-mut { background:#f1ede3; color:var(--mut) }
.sech { display:flex; align-items:baseline; gap:10px; margin:26px 0 10px }
.sech h2 { font-family:Georgia,serif; font-size:20px; font-weight:600 }
.sech .n { color:var(--mut); font-size:13px }
.more { text-align:center; padding:12px; color:var(--accent); font-size:13px; cursor:pointer; border-top:1px solid #f5f0e6 }
.hidden { display:none }
.storyline { color:var(--mut); font-size:14.5px; margin:4px 0 8px } .storyline b { color:var(--ink) }
.glance { max-width:680px; margin:0 auto; padding:26px 24px }
.glance h2 { font-family:Georgia,serif; font-size:22px; font-weight:600; text-align:center; margin-bottom:4px }
.glance .gs { color:var(--mut); font-size:13.5px; text-align:center; margin-bottom:16px }
.momentum { display:flex; justify-content:center; gap:44px; padding:30px 0 6px; text-align:center }
.momentum b { font-size:26px; font-weight:700; display:block } .momentum span { color:var(--mut); font-size:12.5px }
.lastcall { text-align:center; padding:34px 0 60px }
.cohead { display:flex; align-items:center; gap:14px; margin-bottom:4px }
.cohead .mono { width:44px; height:44px; font-size:15px }
.cohead h1 { font-size:30px }
.meta { color:var(--mut); font-size:13.5px; margin-bottom:20px } .meta b { color:var(--ink) }
.draftbox { background:#fff; border:1px solid var(--line); border-left:3px solid var(--accent);
  border-radius:0 12px 12px 0; padding:14px 18px; margin:10px 0; font-size:14px }
.draftbox .lab { font-size:12px; color:var(--mut); margin-bottom:6px }
.copybtn { font:inherit; font-size:12.5px; font-weight:650; border:none; border-radius:8px; padding:6px 14px;
  cursor:pointer; background:var(--ink); color:#fff; margin-top:10px }
"""

JS = """
function copyText(btn, txt) { navigator.clipboard.writeText(txt).then(() => {
  btn.textContent = 'Copied'; setTimeout(() => btn.textContent = 'Copy message', 1400); }); }
document.querySelectorAll('.more[data-for]').forEach(m => m.addEventListener('click', () => {
  document.querySelectorAll('.hidden[data-grp="' + m.dataset.for + '"]').forEach(r => r.classList.remove('hidden'));
  m.remove(); }));
"""


def _page(title: str, body: str, active: str = "") -> str:
    nav = "".join(
        f'<a href="{h}" class="{"on" if active == k else ""}">{t}</a>'
        for k, h, t in [("apply", "/apply", "Applications"), ("net", "/network", "Networking")])
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)}</title><style>{CSS}</style></head><body>'
            f'<div class="bar"><b><a href="/">pipeline.</a></b>{nav}'
            f'<span class="right"><a href="/classic">classic view</a></span></div>'
            f'{body}<script>{JS}</script></body></html>')


def _app_row(a: dict, cls: str, pill: str, pill_cls: str, why: str, cap: bool) -> str:
    mats = a.get("master_ats")
    fit = (f'<span class="fit"><span class="t"><i style="width:{min(int(mats), 100)}%"></i></span>'
           f'<b>{mats}</b></span>') if isinstance(mats, (int, float)) else '<span class="fit"></span>'
    hidden = ' hidden" data-grp="' + cap if cap else '"'
    url = esc(a.get("url") or "#")
    return (f'<a class="row {cls}{hidden} href="{url}" target="_blank">'
            f'<span class="mono">{esc(_monogram(a.get("company", "?")))}</span>'
            f'<span class="who"><b>{esc(a.get("company"))}</b><div class="r">{esc(a.get("role"))}</div></span>'
            f'{fit}<span class="why">{esc(why)}</span>'
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

    body = f"""
<div class="heroblock">
  <h1>{story['h']}</h1>
  <div class="sub">{esc(story['p'])}</div>
  <a class="cta" href="{esc(story['href'])}">{esc(story['cta'])}</a>
  <div class="doors">
    <a class="door" href="/network"><h3>Networking</h3>
      <p>people who can open doors for you</p><div class="cue">{n_send} waiting</div></a>
    <a class="door" href="/apply"><h3>Applications</h3>
      <p>tailored, verified, ready to send</p><div class="cue">{n_ready} ready</div></a>
  </div>
</div>
<div class="hint">v</div>
<div class="glance">
  <h2>Here is the whole day.</h2>
  <div class="gs">A few minutes of honest work.</div>
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
<div class="lastcall"><a class="cta" href="{esc(story['href'])}">{esc(story['cta'])}</a></div>"""
    return _page("Pipeline", body)


def render_apply() -> str:
    apps = _app_rows()
    ready, holds, fresh = apps["ready"], apps["holds"], apps["fresh"]
    story = (f"<b>{esc(ready[0].get('company'))} first.</b> " if ready else "")
    rows = ""
    for i, a in enumerate(ready):
        rows += _app_row(a, "go", "apply", "p-go", "tailored and verified, posting live",
                         "ready" if i >= 5 else "")
    for a in holds:
        rows += _app_row(a, "hold", "hold", "p-hold",
                         "outreach in flight, applying now burns the referral", "")
    if len(ready) > 5:
        rows += f'<div class="more" data-for="ready">show all {len(ready)} ready</div>'
    frows = ""
    for i, a in enumerate(fresh[:20]):
        frows += _app_row(a, "", "tailor", "p-mut", "fresh today, strong keyword fit",
                          "fresh" if i >= 5 else "")
    if len(fresh) > 5:
        frows += f'<div class="more" data-for="fresh">show all {min(len(fresh), 20)} fresh</div>'

    body = f"""<div class="wrap">
  <h1 class="serif" style="font-size:30px">Applications</h1>
  <div class="storyline">{story}Referral holds are marked. Everything green is safe to send.</div>
  <div class="sech"><h2>Ready</h2><span class="n">{min(len(ready),5)} of {len(ready)} shown, best first</span></div>
  <div class="rows">{rows or '<div class="row"><span class="why">Nothing tailored yet. Run the pipeline.</span></div>'}</div>
  <div class="sech"><h2>Fresh finds</h2><span class="n">today's sweep, 70+ fit only</span></div>
  <div class="rows">{frows or '<div class="row"><span class="why">No fresh high-fit roles today.</span></div>'}</div>
  <div class="rows" style="margin-top:26px"><a class="row" href="/network" style="justify-content:space-between">
    <span class="who" style="width:auto"><b>Done applying?</b><div class="r">people are waiting in Networking</div></span>
    <span class="pill p-mut">Networking</span></a></div>
</div>"""
    return _page("Applications", body, "apply")


def render_network() -> str:
    companies = _net_companies()
    people = _people_actions(companies)
    rows = ""
    for item in people["replies"]:
        rows += _person_row(item, "go", "reply", "p-go", "they answered, respond today")
    for item in people["sends"][:5 - min(len(people["replies"]), 5)]:
        rows += _person_row(item, "go", "send", "p-go", "draft ready, copy and send")
    wrows = ""
    for item in people["due"]:
        wrows += _person_row(item, "hold", "nudge", "p-hold", "follow-up is due")
    for item in people["waiting"][:5]:
        wrows += _person_row(item, "hold", "waiting", "p-hold", "nothing to do yet")
    crows = ""
    for c in sorted(companies, key=lambda c: c.get("last_scouted", ""), reverse=True)[:6]:
        n = len(c.get("people", []))
        crows += (f'<a class="row" href="/company/{slugify(c["name"])}">'
                  f'<span class="mono">{esc(_monogram(c["name"]))}</span>'
                  f'<span class="who"><b>{esc(c["name"])}</b><div class="r">{n} people mapped</div></span>'
                  f'<span class="why">{esc(c.get("fit", ""))[:70]}</span>'
                  f'<span class="pill p-mut">{esc((c.get("status") or "").replace("_", " "))}</span></a>')

    body = f"""<div class="wrap">
  <h1 class="serif" style="font-size:30px">Networking</h1>
  <div class="storyline">Referral before application, always. Green means send.</div>
  <div class="sech"><h2>Send today</h2><span class="n">{len(people['replies']) + len(people['sends'])}</span></div>
  <div class="rows">{rows or '<div class="row"><span class="why">Nothing to send. Scout a company.</span></div>'}</div>
  <div class="sech"><h2>Waiting</h2><span class="n">{len(people['due']) + len(people['waiting'])}, nothing to do unless marked</span></div>
  <div class="rows">{wrows or '<div class="row"><span class="why">No open threads.</span></div>'}</div>
  <div class="sech"><h2>Companies</h2><span class="n">{len(companies)} in flight, click any for its page</span></div>
  <div class="rows">{crows}</div>
  <div class="rows" style="margin-top:26px"><a class="row" href="/apply" style="justify-content:space-between">
    <span class="who" style="width:auto"><b>Messages sent?</b><div class="r">roles are ready in Applications</div></span>
    <span class="pill p-mut">Applications</span></a></div>
</div>"""
    return _page("Networking", body, "net")


def render_company(slug: str) -> str | None:
    companies = _net_companies()
    c = next((x for x in companies if slugify(x["name"]) == slug), None)
    if not c:
        return None
    draft = _first_draft(c)
    draft_html = ""
    if draft:
        draft_js = draft.replace("\\", "\\\\").replace("'", "\\'")
        draft_html = (f'<div class="sech"><h2>The one move</h2></div>'
                      f'<div class="draftbox"><div class="lab">Primary draft from the dossier</div>'
                      f'{esc(draft)}'
                      f'<div><button class="copybtn" onclick="copyText(this, \'{esc(draft_js)}\')">Copy message</button></div></div>')
    prows = ""
    for p in sorted(c.get("people", []), key=lambda p: -sum((p.get("rwl") or [0, 0, 0])[:2])):
        name = p["name"].split("[")[0].strip()
        t = _touches(p)
        state = ("replied" if t and t[-1].get("outcome") in ("replied", "referred")
                 else "contacted" if t else "send")
        cls, pcls = ("go", "p-go") if state != "contacted" else ("hold", "p-hold")
        from urllib.parse import quote_plus
        url = p.get("linkedin") or ("https://www.linkedin.com/search/results/people/?keywords="
                                    + quote_plus(f"{name} {c['name']}"))
        prows += (f'<a class="row {cls}" href="{esc(url)}" target="_blank">'
                  f'<span class="mono">{esc(_monogram(name))}</span>'
                  f'<span class="who"><b>{esc(name)}</b><div class="r">{esc(p.get("title", ""))}</div></span>'
                  f'<span class="why">{esc(p.get("hook", ""))[:80]}</span>'
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
  <div class="meta">{esc(c.get("fit", ""))} · heat <b>{esc(c.get("heat", "?"))}</b>
    · scouted {esc(c.get("last_scouted", "?"))}
    {f' · <a class="lnk" href="{esc(c.get("website"))}" style="color:var(--accent)">website</a>' if c.get("website") else ''}</div>
  {draft_html}
  <div class="sech"><h2>People</h2><span class="n">ranked by reachability</span></div>
  <div class="rows">{prows or '<div class="row"><span class="why">none mapped yet</span></div>'}</div>
  <div class="sech"><h2>Roles here</h2></div>
  <div class="rows">{arows}</div>
</div>"""
    return _page(c["name"], body, "net")
