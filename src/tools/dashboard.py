"""BI dashboard — a single static HTML file summarizing every application.

Reads ``data/applications.json`` and writes a self-contained ``data/dashboard.html``
(inline CSS + a little vanilla JS for client-side sort/filter). No server, no external
deps, zero attack surface — open it with ``open data/dashboard.html``.

For transparency it surfaces, per application: date, company, role, source/URL, the
match score (color-coded), the senior-reviewer verdict, WHAT CHANGED in the resume
(summary / skills / top-bullets from the tailoring patch), posted date, and a link to
the tailored PDF.
"""

from __future__ import annotations

import html
import json
import pathlib

from . import tracker

OUT_PATH = pathlib.Path("data/dashboard.html")


def _score_color(score) -> str:
    if not isinstance(score, (int, float)):
        return "#9ca3af"  # gray / unknown
    # Scale-aware: scorer overall_score is /10, ATS match_score is /100. Normalize.
    frac = score / 10 if score <= 10 else score / 100
    if frac >= 0.75:
        return "#16a34a"  # green
    if frac >= 0.6:
        return "#65a30d"  # lime
    if frac >= 0.45:
        return "#d97706"  # amber
    return "#dc2626"  # red


def _diff_html(diff) -> str:
    if not diff:
        return "<span class='muted'>—</span>"
    if isinstance(diff, str):  # tolerate a free-text diff summary
        return html.escape(diff)
    parts = []
    if diff.get("summary"):
        parts.append(f"<b>Summary:</b> {html.escape(str(diff['summary']))}")
    if diff.get("technical_skills"):
        parts.append(f"<b>Skills:</b> {html.escape(str(diff['technical_skills']))}")
    for i, b in enumerate(diff.get("top_bullets", []) or [], 1):
        parts.append(f"<b>Bullet {i}:</b> {html.escape(str(b))}")
    return "<br>".join(parts) if parts else "<span class='muted'>—</span>"


def render(out_path: str | pathlib.Path = OUT_PATH) -> str:
    apps = tracker.list_applications()
    rows = []
    for a in apps:
        # Two DISTINCT metrics, never mixed in one column:
        #  - ATS match: keyword overlap, 0-100 (from `find`)
        #  - Resume score: senior-reviewer quality, 0-10 (from `score`/`apply`)
        ats = a.get("match_score") if a.get("match_score") is not None else a.get("ats_score")
        rscore = a.get("resume_score")
        ats_cell = (
            f"<span class='score' style='background:{_score_color(ats)}'>{ats}</span>"
            if ats is not None else "<span class='muted'>—</span>"
        )
        rscore_cell = (
            f"<span class='score' style='background:{_score_color(rscore)}'>{rscore}</span>"
            if rscore is not None else "<span class='muted'>—</span>"
        )
        url = a.get("url") or ""
        url_cell = (
            f"<a href='{html.escape(url)}' target='_blank'>link</a>" if url else "—"
        )
        # Show a PDF link ONLY when real tailoring happened (a resume_diff exists). A PDF
        # rendered from the master verbatim (no diff) is not a tailored application, so we
        # don't advertise it — avoids implying tailoring that didn't occur.
        pdf = a.get("tailored_pdf")
        pdf_cell = (
            f"<a href='{html.escape(pdf)}' target='_blank'>PDF</a>"
            if pdf and a.get("resume_diff") else "—"
        )
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(a.get('date') or ''))}</td>"
            f"<td>{html.escape(str(a.get('company') or ''))}</td>"
            f"<td>{html.escape(str(a.get('role') or ''))}</td>"
            f"<td>{html.escape(str(a.get('profile') or '—'))}</td>"
            f"<td>{html.escape(str(a.get('status') or ''))}</td>"
            f"<td>{ats_cell}</td>"
            f"<td>{rscore_cell}</td>"
            f"<td>{html.escape(str(a.get('scorer_verdict') or '—'))}</td>"
            f"<td>{html.escape(str(a.get('posted_date') or '—'))}</td>"
            f"<td class='diff'>{_diff_html(a.get('resume_diff') or {})}</td>"
            f"<td>{url_cell}</td>"
            f"<td>{pdf_cell}</td>"
            "</tr>"
        )

    total = len(apps)
    _submitted_statuses = {"submitted", "applied", "ready_to_submit", "skipped_submit"}
    submitted = sum(1 for a in apps if a.get("status") in _submitted_statuses)
    avg = [a.get("match_score") for a in apps if isinstance(a.get("match_score"), (int, float))]
    avg_score = round(sum(avg) / len(avg)) if avg else "—"

    page = _TEMPLATE.format(
        total=total,
        submitted=submitted,
        avg_score=avg_score,
        rows="\n".join(rows) or "<tr><td colspan='11' class='muted'>No applications yet.</td></tr>",
        data_json=html.escape(json.dumps(apps)),
    )
    dest = pathlib.Path(out_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(page)
    return f"Wrote dashboard to {dest}"


_TEMPLATE = """<!doctype html><html><head><meta charset="utf-8">
<title>Job Applier — Dashboard</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 24px; color: #111; }}
  h1 {{ font-size: 20px; }}
  .cards {{ display: flex; gap: 16px; margin: 12px 0 20px; }}
  .card {{ background: #f3f4f6; border-radius: 8px; padding: 12px 18px; }}
  .card b {{ font-size: 22px; display: block; }}
  input {{ padding: 6px 10px; width: 280px; margin-bottom: 12px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th, td {{ border-bottom: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; vertical-align: top; }}
  th {{ cursor: pointer; background: #fafafa; position: sticky; top: 0; }}
  .score {{ color: #fff; padding: 2px 8px; border-radius: 10px; font-weight: 600; }}
  .diff {{ max-width: 380px; font-size: 12px; }}
  .muted {{ color: #9ca3af; }}
</style></head><body>
<h1>Job Applier — Dashboard</h1>
<div class="cards">
  <div class="card"><b>{total}</b>applications</div>
  <div class="card"><b>{submitted}</b>filled / submitted</div>
  <div class="card"><b>{avg_score}</b>avg match score</div>
</div>
<input id="q" placeholder="Filter by company / role / status..." onkeyup="filt()">
<p class="muted" style="font-size:12px">
  <b>ATS</b> = keyword-overlap match, 0–100 (from <b>find</b>). <b>Score</b> =
  senior-reviewer resume quality, 0–10 (from <b>score</b>/<b>apply</b>). They are
  different metrics on different scales — don't compare across columns.
  "What changed" + "PDF" populate only after tailoring (score/apply); <b>find</b> rows
  show "—". Tailored files live in <code>data/applications/&lt;company-role-jobid&gt;/</code>.
</p>
<table id="t">
  <thead><tr>
    <th onclick="sortBy(0)">Date</th><th onclick="sortBy(1)">Company</th>
    <th onclick="sortBy(2)">Role</th><th onclick="sortBy(3)">Profile</th>
    <th onclick="sortBy(4)">Status</th><th onclick="sortBy(5)">ATS /100</th>
    <th onclick="sortBy(6)">Score /10</th><th onclick="sortBy(7)">Verdict</th>
    <th onclick="sortBy(8)">Posted</th>
    <th>What changed</th><th>URL</th><th>PDF</th>
  </tr></thead>
  <tbody>{rows}</tbody>
</table>
<script>
function filt() {{
  var q = document.getElementById('q').value.toLowerCase();
  document.querySelectorAll('#t tbody tr').forEach(function(tr) {{
    tr.style.display = tr.innerText.toLowerCase().indexOf(q) > -1 ? '' : 'none';
  }});
}}
function sortBy(col) {{
  var tb = document.querySelector('#t tbody');
  var rows = Array.prototype.slice.call(tb.querySelectorAll('tr'));
  rows.sort(function(a, b) {{
    var x = a.cells[col].innerText, y = b.cells[col].innerText;
    var nx = parseFloat(x), ny = parseFloat(y);
    if (!isNaN(nx) && !isNaN(ny)) return ny - nx;
    return x.localeCompare(y);
  }});
  rows.forEach(function(r) {{ tb.appendChild(r); }});
}}
</script>
</body></html>"""
