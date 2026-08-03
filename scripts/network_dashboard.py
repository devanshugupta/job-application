"""Networking dashboard generator — ZERO LLM tokens.

Reads  data/network/companies.json   (pipeline tracker, maintained by company-scout)
       data/network/hiring_heat.json (posting-velocity sweep from hiring_heat.py)
       data/network/dossiers/*.md    (per-company dossiers)
Writes data/network/dashboard.html            (searchable index)
       data/network/companies/<slug>.html     (per-company page, rendered dossier)

Usage:  python scripts/network_dashboard.py [--open]
Re-run any time; safe with missing inputs. Never edit the HTML by hand.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NET = ROOT / "data" / "network"
OUT = NET / "dashboard.html"
CO_DIR = NET / "companies"

HEAT_COLORS = {
    "HOT": "#d03b3b", "WARM": "#ec835a", "COOL": "#2a78d6", "DEAD": "#898781",
}
STATUS_FLOW = ["scouted", "outreach_drafted", "contacted", "replied",
               "call_booked", "referred", "interviewing", "closed"]

CSS = """
:root { color-scheme: light;
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --mut:#898781;
  --grid:#e1e0d9; --border:rgba(11,11,11,.10); --bar:#2a78d6; --wash:rgba(42,120,214,.08); }
@media (prefers-color-scheme: dark) { :root { color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7; --mut:#898781;
  --grid:#2c2c2a; --border:rgba(255,255,255,.10); --bar:#3987e5; --wash:rgba(57,135,229,.12); } }
* { box-sizing:border-box; margin:0 }
body { background:var(--page); color:var(--ink);
  font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; padding:24px; max-width:1080px; margin:auto }
h1 { font-size:20px; margin-bottom:2px } h2 { font-size:15px; margin:26px 0 10px }
h3 { font-size:13.5px; margin:16px 0 6px }
.mut { color:var(--mut); font-size:12.5px; text-decoration:none }
a { color:inherit } a.mut:hover, .lnk:hover { color:var(--bar) }
.lnk { color:var(--bar); text-decoration:none } .lnk:hover { text-decoration:underline }
.chip { display:inline-flex; align-items:center; gap:5px; font-size:11.5px; font-weight:600;
  padding:1px 8px; border-radius:999px; border:1px solid var(--chip); color:var(--chip); vertical-align:1px }
.chip .dot { width:7px; height:7px; border-radius:50%; background:var(--chip) }
.date { font-size:11.5px; color:var(--mut); border:1px solid var(--border); border-radius:5px; padding:0 6px }
table { width:100%; border-collapse:collapse; background:var(--surface);
  border:1px solid var(--border); border-radius:10px; overflow:hidden }
th,td { padding:7px 10px; text-align:left; border-bottom:1px solid var(--grid); font-size:13px }
th { color:var(--ink2); font-weight:600; font-size:12px }
td.n,th.n { text-align:right; font-variant-numeric:tabular-nums }
tr:last-child td { border-bottom:none }
details summary { cursor:pointer; color:var(--bar); font-variant-numeric:tabular-nums }
.fresh { margin:6px 0 2px 16px; font-size:12.5px }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:10px; margin-top:14px }
.tile { background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:12px 14px }
.tile .v { font-size:26px; font-weight:650 } .tile .k { color:var(--ink2); font-size:12px }
.search { width:100%; margin:18px 0 4px; padding:9px 14px; font:inherit; color:var(--ink);
  background:var(--surface); border:1px solid var(--border); border-radius:10px; outline:none }
.search:focus { border-color:var(--bar) }
.bchart { background:var(--surface); border:1px solid var(--border); border-radius:10px;
  padding:14px 16px; margin-bottom:14px }
.brow { display:grid; grid-template-columns:150px 1fr 34px; gap:10px; align-items:center; margin:5px 0 }
.blab { font-size:12.5px; color:var(--ink2); overflow:hidden; text-overflow:ellipsis; white-space:nowrap }
.bar { display:block; height:14px; background:var(--bar); border-radius:0 4px 4px 0 }
.bval { font-size:12.5px; text-align:right; font-variant-numeric:tabular-nums }
.card { background:var(--surface); border:1px solid var(--border); border-radius:10px;
  padding:14px 16px; margin-bottom:12px }
.card:hover { border-color:var(--bar) }
.chead { display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap }
.flow { display:flex; align-items:center; gap:3px }
.step { width:14px; height:6px; border-radius:3px; background:var(--grid) }
.step.on { background:var(--bar) }
.fit { font-size:13px; color:var(--ink2); margin:4px 0 }
.person { border-top:1px solid var(--grid); margin-top:10px; padding-top:8px }
.rwl { display:inline-flex; gap:4px; margin:3px 0 }
.rwl span { font-size:11px; font-weight:650; border:1px solid var(--border); border-radius:5px;
  padding:0 5px; color:var(--ink2); font-variant-numeric:tabular-nums }
.hook { font-size:12.5px; color:var(--ink2) }
.log { margin:6px 0 0 16px; font-size:12.5px; color:var(--ink2) }
ul { margin-left:18px } li { margin:2px 0 }
.crumb { margin-bottom:14px; font-size:12.5px }
.stats { display:flex; gap:18px; flex-wrap:wrap; background:var(--surface); border:1px solid var(--border);
  border-radius:10px; padding:10px 16px; margin:12px 0; font-variant-numeric:tabular-nums }
.stats b { font-size:16px } .stats span { color:var(--ink2); font-size:12px }
.doss { background:var(--surface); border:1px solid var(--border); border-radius:10px;
  padding:6px 18px 14px; margin-top:12px }
.doss h1 { font-size:16px; margin:12px 0 4px } .doss h2 { font-size:14px; margin:16px 0 6px }
.doss h3 { font-size:13px; margin:12px 0 4px }
.doss p { margin:6px 0 } .doss li { font-size:13px }
.draft { position:relative; background:var(--wash); border-left:3px solid var(--bar);
  border-radius:0 8px 8px 0; padding:10px 14px; margin:8px 0; font-size:13px }
.copy { position:absolute; top:6px; right:6px; font-size:11px; padding:2px 8px; cursor:pointer;
  color:var(--ink2); background:var(--surface); border:1px solid var(--border); border-radius:6px }
.copy:hover { color:var(--bar); border-color:var(--bar) }
.hidden { display:none }
th[data-col] { cursor:pointer; user-select:none } th[data-col]:hover { color:var(--bar) }
.fchips { display:flex; gap:6px; margin:8px 0 10px }
.fchip { font:inherit; font-size:11.5px; font-weight:600; padding:2px 10px; cursor:pointer;
  color:var(--ink2); background:var(--surface); border:1px solid var(--border); border-radius:999px }
.fchip.on { color:var(--bar); border-color:var(--bar); background:var(--wash) }
.acts { background:var(--surface); border:1px solid var(--border); border-radius:10px;
  padding:10px 16px; margin:12px 0 }
.acts li { font-size:13px; margin:4px 0 }
"""

SEARCH_JS = """
const q = document.getElementById('q');
let heatFilter = '';
function applyFilters() {
  const t = q.value.trim().toLowerCase();
  document.querySelectorAll('[data-search]').forEach(el => {
    const miss = (t && !el.dataset.search.includes(t)) ||
                 (heatFilter && el.dataset.heat !== undefined && el.dataset.heat !== heatFilter);
    el.classList.toggle('hidden', miss);
  });
}
q.addEventListener('input', applyFilters);
document.querySelectorAll('.fchip').forEach(b => b.addEventListener('click', () => {
  heatFilter = (heatFilter === b.dataset.f) ? '' : b.dataset.f;
  document.querySelectorAll('.fchip').forEach(x =>
    x.classList.toggle('on', x.dataset.f === heatFilter));
  applyFilters();
}));
// sortable columns: click a header to sort, click again to flip
document.querySelectorAll('th[data-col]').forEach(th => th.addEventListener('click', () => {
  const table = th.closest('table');
  const idx = [...th.parentNode.children].indexOf(th);
  const dir = th.dataset.dir === 'asc' ? -1 : 1;
  table.querySelectorAll('th').forEach(h => { delete h.dataset.dir;
    h.textContent = h.textContent.replace(/ [\\u25B4\\u25BE]$/, ''); });
  th.dataset.dir = dir === 1 ? 'asc' : 'desc';
  th.textContent += dir === 1 ? ' \\u25B4' : ' \\u25BE';
  const rows = [...table.querySelectorAll('tr')].slice(1);
  rows.sort((a, b) => {
    const av = a.children[idx].textContent.trim(), bv = b.children[idx].textContent.trim();
    const an = parseFloat(av.replace('%','')), bn = parseFloat(bv.replace('%',''));
    return (!isNaN(an) && !isNaN(bn)) ? (an - bn) * dir : av.localeCompare(bv) * dir;
  });
  rows.forEach(r => r.parentNode.appendChild(r));
}));
"""

COPY_JS = """
document.querySelectorAll('.draft').forEach(d => {
  const b = document.createElement('button'); b.className = 'copy'; b.textContent = 'copy';
  b.onclick = () => { navigator.clipboard.writeText(d.dataset.raw)
    .then(() => { b.textContent = 'copied!'; setTimeout(() => b.textContent = 'copy', 1200); }); };
  d.appendChild(b);
});
"""


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def heat_chip(heat: str) -> str:
    c = HEAT_COLORS.get(heat, "#898781")
    return (f'<span class="chip" style="--chip:{c}">'
            f'<span class="dot"></span>{esc(heat or "?")}</span>')


def page(title: str, body: str, script: str = "") -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)}</title><style>{CSS}</style></head>'
            f'<body>{body}<script>{script}</script></body></html>')


# --------------------------------------------------------- markdown (minimal)

def _inline(t: str) -> str:
    t = esc(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)",
               r'<a class="lnk" href="\2" target="_blank">\1</a>', t)
    t = re.sub(r"(?<![\"'>=])(https?://[^\s<)]+)",
               r'<a class="lnk" href="\1" target="_blank">\1</a>', t)
    return t


def md_to_html(md: str) -> str:
    out, i, lines = [], 0, md.splitlines()
    while i < len(lines):
        ln = lines[i]
        if m := re.match(r"(#{1,3}) (.+)", ln):
            out.append(f"<h{len(m[1])}>{_inline(m[2])}</h{len(m[1])}>")
        elif ln.lstrip().startswith(">"):
            block = []
            while i < len(lines) and (lines[i].lstrip().startswith(">") or lines[i].strip() == ""):
                if lines[i].strip():
                    block.append(re.sub(r"^\s*>\s?", "", lines[i]))
                elif block and i + 1 < len(lines) and lines[i + 1].lstrip().startswith(">"):
                    block.append("")
                else:
                    break
                i += 1
            i -= 1
            raw = "\n".join(block)
            out.append(f'<div class="draft" data-raw="{esc(raw)}">'
                       + "<br>".join(_inline(b) for b in block) + "</div>")
        elif re.match(r"\s*- \[[ x]\] ", ln):
            items = []
            while i < len(lines) and (m := re.match(r"\s*- \[([ x])\] (.+)", lines[i])):
                mark = "✅" if m[1] == "x" else "⬜"
                items.append(f"<li>{mark} {_inline(m[2])}</li>")
                i += 1
            i -= 1
            out.append("<ul>" + "".join(items) + "</ul>")
        elif re.match(r"\s*[-*] ", ln):
            items = []
            while i < len(lines) and re.match(r"\s*[-*] ", lines[i]):
                items.append(f"<li>{_inline(re.sub(r'^\\s*[-*] ', '', lines[i]))}</li>")
                i += 1
            i -= 1
            out.append("<ul>" + "".join(items) + "</ul>")
        elif ln.strip().startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    tag = "th" if not rows else "td"
                    rows.append("<tr>" + "".join(f"<{tag}>{_inline(c)}</{tag}>" for c in cells) + "</tr>")
                i += 1
            i -= 1
            out.append("<table>" + "".join(rows) + "</table>")
        elif ln.strip():
            out.append(f"<p>{_inline(ln)}</p>")
        i += 1
    return "\n".join(out)


# --------------------------------------------------------------- company page

def people_html(c: dict) -> str:
    out = ""
    for p in c.get("people", []):
        r_, w_, l_ = (p.get("rwl") or [0, 0, 0])[:3]
        log = "".join(
            f'<li>{esc(o.get("date",""))}: {esc(o.get("channel",""))}, mode {esc(o.get("mode",""))},'
            f' touch {esc(o.get("touch_n",""))}, outcome <b>{esc(o.get("outcome","none"))}</b></li>'
            for o in p.get("outreach", []))
        out += (f'<div class="person"><div><b>{esc(p["name"])}</b>'
                f' <span class="mut">{esc(p.get("title",""))}</span></div>'
                f'<div class="rwl"><span title="response likelihood">R{r_}</span>'
                f'<span title="warmth">W{w_}</span><span title="leverage">L{l_}</span></div>'
                f'<div class="hook">{esc(p.get("hook",""))}</div>'
                f'{f"<ul class=log>{log}</ul>" if log else ""}</div>')
    return out


def company_page(c: dict, heat_row: dict | None) -> str:
    name, slug = c["name"], slugify(c["name"])
    stage = c.get("status", "scouted")
    steps = "".join(
        f'<span class="step{" on" if STATUS_FLOW.index(stage) >= i else ""}" title="{esc(s)}"></span>'
        for i, s in enumerate(STATUS_FLOW))
    links = [f'<a class="lnk" href="{esc(c["website"])}" target="_blank">website</a>'] \
        if c.get("website") else []
    links.append(f'<a class="lnk" href="https://www.linkedin.com/company/{slug}/people/"'
                 f' target="_blank">linkedin people</a>')
    stats = ""
    if heat_row:
        stats = ('<div class="stats">'
                 + "".join(f"<div><b>{v}</b><br><span>{k}</span></div>" for v, k in [
                     (heat_row["open_roles"], "open roles"),
                     (heat_row["new_30d"], "new (30d)"),
                     (f'{heat_row["accel"]:.1f}x', "speeding up"),
                     (f'{heat_row["ghost_share"]:.0%}', "stale posts"),
                     (heat_row["match_new_30d"], "for you (30d)")])
                 + "</div>")
        fresh = "".join(
            f'<li><a class="lnk" href="{esc(j["url"])}" target="_blank">{esc(j["role"])}</a>'
            f' <span class="mut">{esc(j["posted"])}</span></li>'
            for j in heat_row.get("freshest_matches", []))
        if fresh:
            stats += f'<h2>Freshest matching roles</h2><ul class="fresh">{fresh}</ul>'
    dossier_html, acts_html = "", ""
    md_path = NET / c.get("dossier", "")
    if c.get("dossier") and md_path.exists():
        md = md_path.read_text()
        acts = re.findall(r"\s*- \[ \] (.+)", md)
        if acts:
            acts_html = ('<h2>Next actions</h2><div class="acts"><ul>'
                         + "".join(f"<li>⬜ {_inline(a.strip())}</li>" for a in acts)
                         + "</ul></div>")
        dossier_html = f'<div class="doss">{md_to_html(md)}</div>'
    body = (f'<div class="crumb"><a class="lnk" href="../dashboard.html">← Back to pipeline</a></div>'
            f'<h1>{esc(name)} {heat_chip(c.get("heat",""))}'
            f' <span class="date">scouted {esc(c.get("last_scouted","?"))}</span></h1>'
            f'<div class="mut" style="display:flex;gap:14px">{"".join(links)}</div>'
            f'<div class="flow" style="margin-top:8px">{steps}'
            f'<span class="mut">&nbsp;{esc(stage)}</span></div>'
            f'{acts_html}{stats}'
            f'<h2>People ({len(c.get("people", []))})</h2>'
            f'<div class="card">{people_html(c) or "<span class=mut>none mapped</span>"}</div>'
            f'{dossier_html}')
    return page(f"{name} scout report", body, COPY_JS)


# ---------------------------------------------------------------------- index

def build_index(tracker: list[dict], heat: dict) -> str:
    heat_rows = heat.get("companies", [])
    computed = (heat.get("computed_at") or "")[:16].replace("T", " ")
    by_slug = {slugify(c["name"]): c for c in tracker}

    n_hot = sum(1 for r in heat_rows if r["heat"] == "HOT")
    match30 = sum(r.get("match_new_30d", 0) for r in heat_rows)
    n_people = sum(len(c.get("people", [])) for c in tracker)
    touches = [o for c in tracker for p in c.get("people", []) for o in p.get("outreach", [])]
    n_replies = sum(1 for o in touches if o.get("outcome") in ("replied", "referred"))

    tiles = "".join(
        f'<div class="tile"><div class="v">{v}</div><div class="k">{k}</div></div>'
        for v, k in [(len(tracker), "companies scouted"), (n_hot, "hot right now"),
                     (match30, "matching roles (30d)"), (n_people, "people mapped"),
                     (len(touches), "messages sent"), (n_replies, "replies")])

    top = [r for r in heat_rows if r.get("match_new_30d", 0) > 0][:10]
    mx = max((r["match_new_30d"] for r in top), default=1)
    bars = "".join(
        f'<div class="brow"><span class="blab">{esc(r["company"])}</span>'
        f'<span><span class="bar" style="width:{max(r["match_new_30d"]/mx*100,2):.0f}%"></span></span>'
        f'<span class="bval">{r["match_new_30d"]}</span></div>' for r in top)

    cards = ""
    for c in sorted(tracker, key=lambda c: c.get("last_scouted", ""), reverse=True):
        slug = slugify(c["name"])
        stage = c.get("status", "scouted")
        steps = "".join(
            f'<span class="step{" on" if STATUS_FLOW.index(stage) >= i else ""}"></span>'
            for i, s in enumerate(STATUS_FLOW))
        ppl = ", ".join(p["name"] for p in c.get("people", [])) or "—"
        blob = " ".join([c["name"], c.get("fit", ""), c.get("funding", ""), stage, ppl]).lower()
        cards += (
            f'<a class="card" style="display:block;text-decoration:none" data-search="{esc(blob)}"'
            f' href="companies/{slug}.html"><div class="chead">'
            f'<div><b>{esc(c["name"])}</b> {heat_chip(c.get("heat",""))}'
            f' <span class="date">{esc(c.get("last_scouted","?"))}</span></div>'
            f'<div class="flow">{steps}<span class="mut">&nbsp;{esc(stage)}</span></div></div>'
            f'<div class="fit">{esc(c.get("fit",""))}</div>'
            f'<div class="mut">people: {esc(ppl)}</div></a>')
    if not cards:
        cards = '<div class="mut">No companies scouted yet — run /scout &lt;company&gt;.</div>'

    heat_trs = ""
    for r in heat_rows:
        slug = slugify(r["company"])
        name_cell = (f'<a class="lnk" href="companies/{slug}.html">{esc(r["company"])}</a>'
                     if slug in by_slug else esc(r["company"]))
        fresh = "".join(
            f'<li><a class="lnk" href="{esc(j["url"])}" target="_blank">{esc(j["role"])}</a>'
            f' <span class="mut">{esc(j["posted"])}</span></li>'
            for j in r.get("freshest_matches", []))
        details = (f'<details><summary>{r["match_new_30d"]}</summary><ul class="fresh">{fresh}</ul></details>'
                   if fresh else str(r.get("match_new_30d", 0)))
        heat_trs += (
            f'<tr data-search="{esc(r["company"].lower())} {r["heat"].lower()}"'
            f' data-heat="{esc(r["heat"])}">'
            f'<td>{name_cell}</td><td>{heat_chip(r["heat"])}</td>'
            f'<td class="n">{r["open_roles"]}</td><td class="n">{r["new_30d"]}</td>'
            f'<td class="n">{r["accel"]:.1f}x</td><td class="n">{r["ghost_share"]:.0%}</td>'
            f'<td class="n">{details}</td></tr>')

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body = (f'<h1>Networking Pipeline</h1>'
            f'<div class="mut">Updated {now}. Heat sweep: {esc(computed) or "not run yet"}. '
            f'Refresh with <code>python scripts/network_dashboard.py</code></div>'
            f'<div class="tiles">{tiles}</div>'
            f'<input id="q" class="search" type="search"'
            f' placeholder="Search companies, people, or status">'
            f'<h2>Companies in Pipeline</h2>'
            f'<div class="mut" style="margin-bottom:8px">Newest first. Click a card for the full page.</div>'
            f'{cards}'
            f'<h2>Matching Roles Opened in the Last 30 Days</h2>'
            f'<div class="bchart">{bars or "<span class=mut>run scripts/hiring_heat.py first</span>"}</div>'
            f'<h2>Hiring Heat ({len(heat_rows)} companies)</h2>'
            f'<div class="mut" style="margin-bottom:4px">How actively each company is hiring, '
            f'from real posting dates. Click a column to sort, a chip to filter.</div>'
            f'<div class="fchips">'
            + "".join(f'<button class="fchip" data-f="{h}">{h}</button>'
                      for h in ("HOT", "WARM", "COOL", "DEAD"))
            + f'</div>'
            f'<table><tr><th data-col>Company</th><th data-col>Heat</th>'
            f'<th class="n" data-col>Open roles</th><th class="n" data-col>New (30d)</th>'
            f'<th class="n" data-col>Speeding up</th><th class="n" data-col>Stale posts</th>'
            f'<th class="n" data-col>For you (30d)</th></tr>'
            f'{heat_trs}</table>')
    return page("Networking Pipeline — Devanshu", body, SEARCH_JS)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()
    tracker = load_json(NET / "companies.json").get("companies", [])
    heat = load_json(NET / "hiring_heat.json")
    heat_by_name = {slugify(r["company"]): r for r in heat.get("companies", [])}

    CO_DIR.mkdir(parents=True, exist_ok=True)
    for c in tracker:
        slug = slugify(c["name"])
        (CO_DIR / f"{slug}.html").write_text(company_page(c, heat_by_name.get(slug)))
    OUT.write_text(build_index(tracker, heat))
    print(f"-> {OUT}  (+{len(tracker)} company pages in {CO_DIR})")
    if args.open:
        webbrowser.open(OUT.as_uri())


if __name__ == "__main__":
    main()
