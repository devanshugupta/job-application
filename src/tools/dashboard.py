"""Scores dashboard — one static HTML file that answers "how good are my applications?"

Built around the **Application Quality Score** (AQS, 0-100 — see scoring.py): every
row gets one headline number with a grade and a hover breakdown of its components
(reviewer /10, JD must-have %, ATS keywords, recency). Around the table:

  - KPI cards: tracked, found today, tailored, applied, average AQS, A-grades
  - pipeline funnel: found -> scored -> ready -> applied
  - AQS distribution histogram
  - filter chips (status), profile filter, text search, sortable columns
  - per-row "what changed" expander + apply / find-resume action buttons

Self-contained (inline CSS/JS): `open data/dashboard.html` works read-only; the action
buttons need the backend (`dashboard --serve`, see dashboard_server.py).
"""

from __future__ import annotations

import html
import re
import pathlib
from datetime import date

from .. import config
from . import scoring, tracker

OUT_PATH = config.DASHBOARD_PATH

_SUBMITTED = {"submitted", "applied", "ready_to_submit", "skipped_submit"}



_JOB_ID_PATTERNS = [
    re.compile(r"JobDetail/(\d+)", re.I),               # Siemens/Avature
    re.compile(r"[_-](R\d{6,})", re.I),                  # Workday requisition
    re.compile(r"gh_jid=(\d+)"),                          # embedded Greenhouse
    re.compile(r"greenhouse\.io/.+/jobs/(\d+)"),        # Greenhouse
    re.compile(r"/jobs?/(\d{5,})"),                       # amazon.jobs etc.
    re.compile(r"/([0-9a-f]{8})-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I),  # Ashby/Lever UUID (short)
]


def _job_id(url: str) -> str:
    """Best-effort requisition/job id from a posting URL ('' if none)."""
    for pat in _JOB_ID_PATTERNS:
        m = pat.search(url or "")
        if m:
            return m.group(1)
    return ""

def _grade_color(score) -> str:
    if not isinstance(score, (int, float)):
        return "var(--mut)"
    if score >= 80:
        return "var(--ok)"
    if score >= 65:
        return "var(--good)"
    if score >= 50:
        return "var(--warn)"
    return "var(--bad)"


def _breakdown_title(comp: dict) -> str:
    names = {"reviewer": "Reviewer", "must_have": "Must-haves",
             "keywords": "Keywords", "recency": "Recency"}
    parts = [f"{names[k]} {v}" for k, v in comp.get("breakdown", {}).items()]
    return f"{comp.get('meaning', '')} · " + " · ".join(parts) if parts else ""


def _diff_html(diff) -> str:
    if not diff:
        return ""
    if isinstance(diff, str):
        return html.escape(diff)
    parts = []
    if diff.get("summary"):
        parts.append(f"<b>Summary</b> {html.escape(str(diff['summary']))}")
    if diff.get("technical_skills"):
        parts.append(f"<b>Skills</b> {html.escape(str(diff['technical_skills']))}")
    for i, b in enumerate(diff.get("top_bullets", []) or [], 1):
        parts.append(f"<b>Bullet {i}</b> {html.escape(str(b))}")
    return "<br>".join(parts)


def render(out_path: str | pathlib.Path = OUT_PATH) -> str:
    apps = tracker.list_applications()
    today = date.today().isoformat()

    # Default order: most recently touched first (a job's `date` is bumped on every
    # upsert, so the job you just worked on leads). Columns stay click-sortable.
    ordered = sorted(apps, key=lambda r: (r.get("date") or "", r.get("id", 0)),
                     reverse=True)

    rows = []
    aqs_values = []
    statuses: dict[str, int] = {}
    profiles_seen: set[str] = set()
    for a in ordered:
        comp = scoring.score_record(a, today)
        aqs = comp["score"]
        if aqs is not None and a.get("status") != "found":
            aqs_values.append(aqs)
        statuses[a.get("status") or "?"] = statuses.get(a.get("status") or "?", 0) + 1
        prof = a.get("profile") or ""
        if prof:
            profiles_seen.add(prof)

        # The color already conveys the grade, so the badge shows just the number.
        aqs_cell = (
            f"<span class='aqs' style='background:{_grade_color(aqs)}' "
            f"title='{html.escape(_breakdown_title(comp))}'>{aqs}</span>"
            if aqs is not None else "<span class='mut'>—</span>"
        )
        url = a.get("url") or ""
        pdf = a.get("tailored_pdf") or ""
        diff = _diff_html(a.get("resume_diff") or {})
        diff_cell = (f"<details><summary>diff</summary><div class='diff'>{diff}</div>"
                     f"</details>") if diff else "<span class='mut'>—</span>"
        # Actions. Under `dashboard --serve` these POST back (mark applied / file the
        # PDF into the save folder); opened as a plain file:// page they degrade to
        # ordinary links, so the static dashboard keeps working.
        applied = a.get("status") in _SUBMITTED
        links = []
        if url:
            u = html.escape(url, quote=True)
            links.append(
                f"<button class='btn btn-apply{' done' if applied else ''}' "
                f"data-url=\"{u}\" onclick='applyJob(this)'>"
                f"{'applied ✓' if applied else 'apply ↗'}</button>")
        # Show "find resume" only when the tailored PDF actually exists on disk (guard on
        # the file, not on resume_diff). Clicking asks the backend to reveal it in Finder.
        if pdf:
            pdf_abs = pathlib.Path(pdf)
            if not pdf_abs.is_absolute():
                pdf_abs = config.ROOT / pdf
            if pdf_abs.exists():
                links.append(
                    f"<button class='btn' data-url=\"{html.escape(url, quote=True)}\" "
                    f"onclick='findResume(this)'>find resume</button>")

        def cell(v, dash="—"):
            return html.escape(str(v)) if v not in (None, "") else f"<span class='mut'>{dash}</span>"

        rows.append(
            f"<tr data-status='{html.escape(str(a.get('status') or ''))}' "
            f"data-profile='{html.escape(prof)}'>"
            f"<td>{cell(a.get('date'))}</td>"
            f"<td class='co'>{cell(a.get('company'))}</td>"
            f"<td>{cell(a.get('role'))}</td>"
            f"<td class='mut'>{cell(_job_id(a.get('url') or ''))}</td>"
            f"<td>{cell(prof)}</td>"
            f"<td><span class='tag tag-{html.escape(str(a.get('status') or ''))}'>"
            f"{cell(a.get('status'))}</span></td>"
            f"<td data-v='{aqs if aqs is not None else -1}'>{aqs_cell}</td>"
            f"<td data-v='{a.get('resume_score') if a.get('resume_score') is not None else -1}'>"
            f"{cell(a.get('resume_score'))}</td>"
            f"<td data-v='{a.get('match_pct') if a.get('match_pct') is not None else -1}'>"
            f"{cell(a.get('match_pct'))}</td>"
            f"<td data-v='{a.get('match_score') if a.get('match_score') is not None else -1}'>"
            f"{cell(a.get('match_score'))}</td>"
            f"<td>{cell(a.get('posted_date'))}</td>"
            f"<td>{diff_cell}</td>"
            f"<td>{' · '.join(links) or '—'}</td>"
            "</tr>"
        )

    total = len(apps)
    found_today = sum(1 for a in apps if a.get("status") == "found"
                      and a.get("date") == today)
    tailored = sum(1 for a in apps if a.get("resume_diff") or a.get("status") == "tailored")
    applied = sum(1 for a in apps if a.get("status") in _SUBMITTED)
    scored = sum(1 for a in apps if a.get("resume_score") is not None)
    avg_aqs = round(sum(aqs_values) / len(aqs_values)) if aqs_values else "—"
    a_grades = sum(1 for v in aqs_values if v >= 80)

    # funnel widths (relative to the largest stage)
    funnel = [("found", statuses.get("found", 0)), ("scored", scored),
              ("tailored", tailored), ("applied", applied)]
    fmax = max((n for _, n in funnel), default=0) or 1
    funnel_html = "".join(
        f"<div class='frow'><span class='flab'>{name}</span>"
        f"<div class='fbar' style='width:{max(2, round(100 * n / fmax))}%'></div>"
        f"<span class='fnum'>{n}</span></div>"
        for name, n in funnel)

    # AQS histogram, 10 buckets
    buckets = [0] * 10
    for v in aqs_values:
        buckets[min(9, v // 10)] += 1
    bmax = max(buckets) or 1
    hist_html = "".join(
        f"<div class='hcol' title='{i * 10}-{i * 10 + 9}: {n}'>"
        f"<div class='hbar' style='height:{round(100 * n / bmax)}%'></div>"
        f"<span>{i * 10}</span></div>"
        for i, n in enumerate(buckets))

    status_chips = "".join(
        f"<button class='chip' data-status='{html.escape(s)}' onclick='chip(this)'>"
        f"{html.escape(s)} ({n})</button>"
        for s, n in sorted(statuses.items(), key=lambda kv: -kv[1]))
    profile_opts = "".join(f"<option>{html.escape(p)}</option>"
                           for p in sorted(profiles_seen))

    page = _TEMPLATE.format(
        generated=today, total=total, found_today=found_today, tailored=tailored,
        applied=applied, avg_aqs=avg_aqs, a_grades=a_grades,
        funnel=funnel_html, hist=hist_html, chips=status_chips,
        profile_opts=profile_opts,
        rows="\n".join(rows) or "<tr><td colspan='13' class='mut'>No applications yet — "
                                "run <code>python -m src.cli pipeline</code>.</td></tr>",
    )
    dest = pathlib.Path(out_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(page)
    return f"Wrote dashboard to {dest}"


_TEMPLATE = """<!doctype html><html><head><meta charset="utf-8">
<title>Job Pipeline — Scores Dashboard</title>
<style>
  :root {{ --bg:#0f1117; --panel:#171a23; --line:#262b38; --txt:#e6e8ee; --mut:#7c8497;
          --ok:#22c55e; --good:#84cc16; --warn:#f59e0b; --bad:#ef4444; --acc:#6366f1; }}
  * {{ box-sizing:border-box; }}
  body {{ font:14px/1.45 -apple-system,'Segoe UI',Roboto,sans-serif; margin:0;
         background:var(--bg); color:var(--txt); padding:28px; }}
  h1 {{ font-size:19px; margin:0 0 2px; }} .sub {{ color:var(--mut); font-size:12px; }}
  .grid {{ display:grid; grid-template-columns:repeat(6,1fr); gap:12px; margin:18px 0; }}
  .card {{ background:var(--panel); border:1px solid var(--line); border-radius:10px;
          padding:12px 16px; }}
  .card b {{ display:block; font-size:24px; margin-bottom:2px; }}
  .card span {{ color:var(--mut); font-size:11.5px; text-transform:uppercase;
               letter-spacing:.5px; }}
  .panels {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:18px; }}
  .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:10px;
           padding:14px 16px; }}
  .panel h3 {{ margin:0 0 10px; font-size:12px; color:var(--mut);
              text-transform:uppercase; letter-spacing:.5px; }}
  .frow {{ display:flex; align-items:center; gap:10px; margin:7px 0; }}
  .flab {{ width:64px; color:var(--mut); font-size:12px; }}
  .fbar {{ height:14px; background:linear-gradient(90deg,var(--acc),#8b5cf6);
          border-radius:4px; }}
  .fnum {{ font-size:12px; }}
  .hist {{ display:flex; align-items:flex-end; gap:6px; height:90px; }}
  .hcol {{ flex:1; display:flex; flex-direction:column; justify-content:flex-end;
          align-items:center; height:100%; font-size:9px; color:var(--mut); }}
  .hbar {{ width:100%; background:var(--acc); border-radius:3px 3px 0 0; min-height:1px; }}
  .bar {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:12px; }}
  input,select {{ background:var(--panel); color:var(--txt); border:1px solid var(--line);
          border-radius:8px; padding:7px 10px; font-size:13px; }}
  input {{ width:260px; }}
  .chip {{ background:var(--panel); color:var(--mut); border:1px solid var(--line);
          border-radius:999px; padding:4px 12px; font-size:12px; cursor:pointer; }}
  .chip.on {{ color:#fff; border-color:var(--acc); background:#23264a; }}
  table {{ border-collapse:collapse; width:100%; font-size:13px; background:var(--panel);
          border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
  th,td {{ border-bottom:1px solid var(--line); padding:8px 10px; text-align:left;
          vertical-align:top; }}
  th {{ cursor:pointer; background:#1c2030; font-size:11px; text-transform:uppercase;
       letter-spacing:.4px; color:var(--mut); position:sticky; top:0; user-select:none; }}
  tr:hover td {{ background:#1b1f2c; }}
  .co {{ font-weight:600; }}
  .aqs {{ color:#fff; padding:2px 9px; border-radius:10px; font-weight:700;
         font-size:12px; white-space:nowrap; cursor:help; }}
  .tag {{ padding:1px 8px; border-radius:8px; font-size:11.5px; border:1px solid var(--line);
         color:var(--mut); }}
  .tag-applied,.tag-submitted,.tag-ready_to_submit {{ color:var(--ok); border-color:var(--ok); }}
  .tag-scored {{ color:var(--warn); border-color:var(--warn); }}
  .mut {{ color:var(--mut); }}
  details summary {{ cursor:pointer; color:var(--acc); font-size:12px; }}
  .diff {{ max-width:420px; font-size:12px; color:var(--mut); padding-top:6px; }}
  .diff b {{ color:var(--txt); }}
  a {{ color:var(--acc); text-decoration:none; }} a:hover {{ text-decoration:underline; }}
  .btn {{ background:#23264a; color:var(--txt); border:1px solid var(--acc);
         border-radius:7px; padding:3px 10px; font-size:12px; cursor:pointer;
         white-space:nowrap; margin-right:4px; }}
  .btn:hover {{ background:var(--acc); }}
  .btn.done {{ background:transparent; color:var(--ok); border-color:var(--ok);
              cursor:default; }}
  #toast {{ position:fixed; bottom:20px; right:20px; background:var(--panel);
           border:1px solid var(--acc); border-radius:8px; padding:10px 14px;
           font-size:12.5px; max-width:520px; display:none; z-index:9; }}
  .legend {{ color:var(--mut); font-size:11.5px; margin:10px 0 24px; }}
</style></head><body>
<h1>Job Pipeline — Scores Dashboard</h1>
<div class="sub">generated {generated} · AQS = 0.40·reviewer + 0.35·must-haves + 0.10·keywords + 0.15·recency (renormalized when a part is missing) · hover a score for its breakdown</div>

<div class="grid">
  <div class="card"><b>{total}</b><span>tracked</span></div>
  <div class="card"><b>{found_today}</b><span>found today</span></div>
  <div class="card"><b>{tailored}</b><span>tailored</span></div>
  <div class="card"><b>{applied}</b><span>applied / ready</span></div>
  <div class="card"><b>{avg_aqs}</b><span>avg AQS</span></div>
  <div class="card"><b>{a_grades}</b><span>A-grade (80+)</span></div>
</div>

<div class="panels">
  <div class="panel"><h3>Pipeline funnel</h3>{funnel}</div>
  <div class="panel"><h3>AQS distribution (scored rows)</h3><div class="hist">{hist}</div></div>
</div>

<div class="bar">
  <input id="q" placeholder="Search company / role / verdict…" onkeyup="apply()">
  <select id="prof" onchange="apply()"><option value="">all profiles</option>{profile_opts}</select>
  {chips}
</div>

<table id="t"><thead><tr>
  <th onclick="sortBy(0)">Date</th><th onclick="sortBy(1)">Company</th>
  <th onclick="sortBy(2)">Role</th><th onclick="sortBy(3)">Job ID</th>
  <th onclick="sortBy(4)">Profile</th>
  <th onclick="sortBy(5)">Status</th><th onclick="sortBy(6)">AQS</th>
  <th onclick="sortBy(7)">Reviewer /10</th><th onclick="sortBy(8)">Must-have %</th>
  <th onclick="sortBy(9)">ATS /100</th>
  <th onclick="sortBy(10)">Posted</th><th>What changed</th><th>Actions</th>
</tr></thead><tbody>{rows}</tbody></table>

<p class="legend">AQS color: <b style="color:var(--ok)">green</b> 80+ apply now ·
<b style="color:var(--good)">lime</b> 65+ strong · <b style="color:var(--warn)">amber</b> 50+ decent ·
<b style="color:var(--bad)">red</b> below 50 weak/mismatch. Reviewer = senior hiring-manager score /10.
Must-have % = share of the JD's role-defining requirements the resume satisfies.
ATS = raw keyword overlap. Tailored files live in <code>data/applications/&lt;Company&gt;/&lt;role-id&gt;/</code>.</p>

<div id="toast"></div>
<script>
// The action buttons POST back to `dashboard --serve`. The page can also be opened as a
// plain file or served by some OTHER web server (an IDE preview) with no such backend —
// so we don't guess up front: each click just TRIES the POST and, only if it fails,
// falls back to opening the link/file. That removes any load-time race.
var HINT = 'Start the backend with <code>python -m src.cli dashboard --serve</code> ' +
           'and open <code>http://localhost:8765</code> (not the file or an IDE preview).';
function toast(msg, bad) {{
  var t = document.getElementById('toast');
  t.innerHTML = msg; t.style.borderColor = bad ? 'var(--bad)' : 'var(--acc)';
  t.style.display = 'block';
  clearTimeout(t._h); t._h = setTimeout(function() {{ t.style.display = 'none'; }}, 7000);
}}
// Resolve to parsed JSON on success; reject with a flag distinguishing a reachable
// backend that refused (has JSON error) from no-backend-at-all (network / HTML page).
function post(path, url) {{
  return fetch(path, {{method: 'POST', headers: {{'Content-Type': 'application/json'}},
                      body: JSON.stringify({{url: url}})}})
    .then(function(r) {{
      return r.text().then(function(txt) {{
        var j; try {{ j = JSON.parse(txt); }} catch (e) {{
          var err = new Error('no dashboard backend here'); err.noBackend = true; throw err;
        }}
        if (!r.ok) throw new Error(j.error || r.status);
        return j;
      }});
    }}, function() {{
      var err = new Error('backend not reachable'); err.noBackend = true; throw err;
    }});
}}
function applyJob(btn) {{
  var url = btn.dataset.url;
  window.open(url, '_blank');
  if (btn.classList.contains('done')) return;
  post('/api/applied', url).then(function() {{
    btn.classList.add('done'); btn.textContent = 'applied ✓';
    var tr = btn.closest('tr'), tag = tr.querySelector('.tag');
    tr.dataset.status = 'applied';
    if (tag) {{ tag.textContent = 'applied'; tag.className = 'tag tag-applied'; }}
    toast('Marked applied.');
  }}).catch(function(e) {{
    toast(e.noBackend ? 'Opened the posting, but could NOT mark it applied. ' + HINT
                      : 'Could not mark applied: ' + e.message, true);
  }});
}}
function findResume(btn) {{
  // Only the backend can open Finder — a web page can't. So on no-backend we do NOT
  // open the PDF in a tab (that just dumps it in the browser); we point you at --serve.
  post('/api/reveal', btn.dataset.url).then(function(j) {{
    toast('Revealed <code>' + j.dir + '</code> in Finder.');
  }}).catch(function(e) {{
    toast(e.noBackend ? 'Cannot open Finder from a static page. ' + HINT
                      : 'Could not open the folder: ' + e.message, true);
  }});
}}
var activeStatus = null;
function chip(el) {{
  var on = el.classList.contains('on');
  document.querySelectorAll('.chip').forEach(function(c) {{ c.classList.remove('on'); }});
  activeStatus = on ? null : el.dataset.status;
  if (!on) el.classList.add('on');
  apply();
}}
function apply() {{
  var q = document.getElementById('q').value.toLowerCase();
  var p = document.getElementById('prof').value;
  document.querySelectorAll('#t tbody tr').forEach(function(tr) {{
    var okQ = !q || tr.innerText.toLowerCase().indexOf(q) > -1;
    var okS = !activeStatus || tr.dataset.status === activeStatus;
    var okP = !p || tr.dataset.profile === p;
    tr.style.display = (okQ && okS && okP) ? '' : 'none';
  }});
}}
var dir = {{}};
function sortBy(col) {{
  var tb = document.querySelector('#t tbody');
  var rows = Array.prototype.slice.call(tb.querySelectorAll('tr'));
  dir[col] = !dir[col];
  rows.sort(function(a, b) {{
    var ca = a.cells[col], cb = b.cells[col];
    var x = ca.dataset.v !== undefined ? parseFloat(ca.dataset.v) : ca.innerText;
    var y = cb.dataset.v !== undefined ? parseFloat(cb.dataset.v) : cb.innerText;
    var r = (typeof x === 'number' && typeof y === 'number' && !isNaN(x) && !isNaN(y))
            ? y - x : String(x).localeCompare(String(y));
    return dir[col] ? r : -r;
  }});
  rows.forEach(function(r) {{ tb.appendChild(r); }});
}}
</script>
</body></html>"""
