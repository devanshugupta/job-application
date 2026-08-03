"""Scores dashboard  one static HTML file that answers "how good are my applications?"

Three DISTINCT, never-blended fit signals per row  no composite score hides how a
number was reached:

  - **Master ATS** (0-100): deterministic keyword match of the JD against your
    unmodified MASTER resume. Free, no LLM, available the moment a JD is captured
    (even at 'found'). THE primary "is this worth tailoring for" signal and what
    the ATS/score filter and 'high fit' KPI key on.
  - **Tailored ATS** (0-100): same deterministic keyword match, but against the
    resume actually tailored+sent for this job. Shows what tailoring achieved.
  - **Reviewer /10**: senior-hiring-manager LLM judgment of the tailored resume.
    Only exists once a job has actually been scored by the brain  never folded
    into the ATS numbers above.

Around the table: KPI cards, a pipeline funnel (found -> high fit -> tailored ->
applied), a Master ATS distribution histogram, filter chips (status + high-fit +
tailored + ready), profile filter, text search, sortable columns, per-row "what
changed" expander + apply/find-resume action buttons.

Self-contained (inline CSS/JS): `open data/dashboard.html` works read-only; the action
buttons need the backend (`dashboard --serve`, see dashboard_server.py).
"""

from __future__ import annotations

import html
import re
import pathlib
from datetime import date, datetime

from .. import config
from . import artifacts, tracker

# A row is "tailored" (has a real resume) if a recompilable artifact exists on disk  a
# tailored .tex or a PDF  NOT the flaky tailored_pdf field, which past runs often left
# unset. A .tex counts because it recompiles to a PDF on demand.
def _canon_source(s: str | None) -> str:
    """Collapse a source label to its FAMILY so the 'by source' list has one row per real
    source. The tracker holds drift across code versions  'greenhouse' vs 'greenhouse-api',
    'github:simplify-newgrad' vs 'SimplifyJobs/New-Grad-Positions', 'careers:google' vs
    'google-careers'  all the same source. Maps every variant to a single canonical name."""
    s = (s or "").strip().lower()
    if not s or s in ("?", "user", "pipeline", "manual", "feed"):
        return "manual"
    if "scout" in s:
        return "scoutbetter"
    if "linkedin" in s:
        return "linkedin"
    if "simplify" in s or "new-grad" in s or "newgrad" in s:
        return "simplify"
    if "chrome" in s:
        return "chrome-tabs"
    if "careers" in s or s.endswith("-careers"):
        return "careers"
    for fam in ("greenhouse", "ashby", "lever", "workday", "smartrecruiters", "workable"):
        if fam in s:
            return fam
    return s[:-4] if s.endswith("-api") else s   # merge stray 'x-api' with 'x'


def _has_resume(a: dict) -> bool:
    pdf = a.get("tailored_pdf")
    if pdf and pathlib.Path(pdf).exists():
        return True
    try:
        d = artifacts.BASE / artifacts.company_dir(a.get("company", "")) / \
            artifacts.job_dir(a.get("role", ""), a.get("url"))
        return d.exists() and (any(d.glob("*.tex")) or any(d.glob("*.pdf")))
    except Exception:
        return False

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

def _fmt_date(iso: str | None) -> tuple[str, str]:
    """('29 Jul 26, 18:20', '202607291820')  human display + a numeric sort key. Shows
    the time when the stored value carries one (rows are stamped 'YYYY-MM-DD HH:MM'), so
    you can see WHEN a job was found; falls back to date-only for legacy values."""
    if not iso:
        return "", ""
    s = str(iso)
    has_time = False
    try:
        d = datetime.strptime(s[:16], "%Y-%m-%d %H:%M")
        has_time = True
    except ValueError:
        try:
            d = datetime.strptime(s[:10], "%Y-%m-%d")
        except ValueError:
            return s, ""
    disp = f"{d.day} {d.strftime('%b %y')}"
    if has_time:
        disp += f", {d.strftime('%H:%M')}"
    return disp, d.strftime("%Y%m%d%H%M")


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


def render(out_path: str | pathlib.Path = OUT_PATH) -> str:
    apps = tracker.list_applications()
    today = date.today().isoformat()

    # Default order: most recently touched first (a job's `date` is bumped on every
    # upsert, so the job you just worked on leads). Columns stay click-sortable.
    ordered = sorted(apps, key=lambda r: (r.get("date") or "", r.get("id", 0)),
                     reverse=True)

    rows = []
    mats_values = []   # master ATS values (deterministic, available pre-LLM) -> histogram/avg
    statuses: dict[str, int] = {}
    profiles_seen: set[str] = set()
    prof_total: dict[str, int] = {}      # roles per profile (ml_ai / sde / data_engineer)
    prof_applied: dict[str, int] = {}    # of those, how many applied
    src_total: dict[str, int] = {}       # roles per source (scoutbetter / linkedin / ...)
    src_applied: dict[str, int] = {}     # of those, how many applied
    removed_count = 0
    for a in ordered:
        # Rows you removed are kept in the tracker (never deleted) but hidden by default
        # and excluded from every stat/KPI; a "show removed" toggle can reveal them to
        # restore. So a removed row still renders (for restore) but counts toward nothing.
        removed = bool(a.get("removed"))
        if removed:
            removed_count += 1
        # Master ATS: deterministic keyword match of THIS JD against the unmodified
        # master resume. No LLM involved, available the instant a JD is captured, and
        # never blended with the reviewer's judgment  the single number the ATS/score
        # filter and 'high fit' KPI key on.
        mats = a.get("master_ats")
        mats_cell = (f"<span class='aqs' style='background:{_grade_color(mats)}'>{mats}</span>"
                     if mats is not None else "<span class='mut'></span>")
        # Tailored ATS: same deterministic keyword match, against the resume actually
        # sent for this job  shows what tailoring achieved, kept as its own column
        # rather than folded into Master ATS. Gated on a REAL tailored resume existing
        # on disk: match_score is also written at discovery time (a cheap title/location
        # pre-rank, unrelated to any resume), so showing it here for a never-tailored
        # row would silently pass off that discovery-time number as "what tailoring
        # achieved" when no tailoring ever happened.
        is_tailored = _has_resume(a)
        tats = a.get("match_score") if is_tailored else None
        if not removed:
            if mats is not None:
                mats_values.append(mats)
            statuses[a.get("status") or "?"] = statuses.get(a.get("status") or "?", 0) + 1
        prof = a.get("profile") or ""
        if prof and not removed:
            profiles_seen.add(prof)
            prof_total[prof] = prof_total.get(prof, 0) + 1
            if a.get("status") in _SUBMITTED:
                prof_applied[prof] = prof_applied.get(prof, 0) + 1
        if not removed:
            src = _canon_source(a.get("source"))
            src_total[src] = src_total.get(src, 0) + 1
            if a.get("status") in _SUBMITTED:
                src_applied[src] = src_applied.get(src, 0) + 1

        url = a.get("url") or ""
        pdf = a.get("tailored_pdf") or ""
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
            u = html.escape(url, quote=True)
            # find-resume needs the PDF; recompile only needs the editable .tex  so it
            # stays available to REBUILD a PDF you've deleted or edited the source of.
            if pdf_abs.exists():
                links.append(
                    f"<button class='btn' data-url=\"{u}\" "
                    f"onclick='findResume(this)'>find resume</button>")
            if (pdf_abs.parent / "tailored_resume.tex").exists():
                links.append(
                    f"<button class='btn' data-url=\"{u}\" title='re-render the .tex to PDF' "
                    f"onclick='recompile(this)'>recompile</button>")
        # Remove / restore lives in a leading column (before Date), not in Actions.
        # A small icon: removed rows offer restore (↺); live rows offer "−" (confirms).
        if url:
            u = html.escape(url, quote=True)
            rm_btn = (f"<button class='ic' title='restore' data-url=\"{u}\" "
                      f"onclick='restoreJob(this)'>↺</button>" if removed else
                      f"<button class='ic ic-rm' title='remove' data-url=\"{u}\" "
                      f"onclick='removeJob(this)'>−</button>")
        else:
            rm_btn = ""

        def cell(v, dash=""):
            return html.escape(str(v)) if v not in (None, "") else f"<span class='mut'>{dash}</span>"

        def date_cell(v):
            disp, key = _fmt_date(v)
            return (f"<td data-v='{key or 0}'>{html.escape(disp)}</td>" if disp
                    else "<td class='mut'></td>")

        # is_tailored was already computed above (gates the Tailored ATS cell); reused
        # here for the "tailored only" / "ready to apply" filters.
        ready = is_tailored and a.get("status") not in _SUBMITTED
        high_fit = mats is not None and mats >= 70
        rows.append(
            f"<tr data-status='{html.escape(str(a.get('status') or ''))}' "
            f"data-profile='{html.escape(prof)}' data-removed='{1 if removed else 0}' "
            f"data-source='{html.escape(str(a.get('source') or '?'))}' "
            f"data-tailored='{1 if is_tailored else 0}' data-ready='{1 if ready else 0}' "
            f"data-highfit='{1 if high_fit else 0}'>"
            f"<td class='rmcell'>{rm_btn}</td>"
            f"{date_cell(a.get('date'))}"
            f"<td class='co'>{cell(a.get('company'))}</td>"
            f"<td>{cell(a.get('role'))}</td>"
            f"<td class='mut'>{cell(_job_id(a.get('url') or ''))}</td>"
            f"<td>{cell(prof)}</td>"
            f"<td data-v='{mats if mats is not None else -1}'>{mats_cell}</td>"
            f"<td data-v='{tats if tats is not None else -1}'>{cell(tats)}</td>"
            f"<td data-v='{a.get('resume_score') if a.get('resume_score') is not None else -1}'>"
            f"{cell(a.get('resume_score'))}</td>"
            f"{date_cell(a.get('posted_date'))}"
            f"<td class='mut'>{cell(a.get('source'))}</td>"
            f"<td>{' · '.join(links) or ''}</td>"
            "</tr>"
        )

    live = [a for a in apps if not a.get("removed")]   # removed rows count toward nothing
    total = len(live)
    found_today = sum(1 for a in live if a.get("status") == "found"
                      and (a.get("date") or "")[:10] == today)
    tailored = sum(1 for a in live if _has_resume(a))
    ready = sum(1 for a in live if _has_resume(a) and a.get("status") not in _SUBMITTED)
    applied = sum(1 for a in live if a.get("status") in _SUBMITTED)
    # "high fit" = Master ATS >= 70  the ONE deterministic, pre-LLM signal for whether
    # a role is worth spending tailoring effort on. This replaces the old blended AQS
    # 'scored'/'A-grade' concepts, which mixed in the LLM reviewer score.
    high_fit = sum(1 for a in live if (a.get("master_ats") or -1) >= 70)
    high_fit_not_applied = sum(1 for a in live if (a.get("master_ats") or -1) >= 70
                               and a.get("status") not in _SUBMITTED)
    avg_mats = round(sum(mats_values) / len(mats_values)) if mats_values else ""

    # funnel widths (relative to the largest stage)
    funnel = [("found", statuses.get("found", 0)), ("high fit (ATS 70+)", high_fit),
              ("tailored", tailored), ("applied", applied)]
    fmax = max((n for _, n in funnel), default=0) or 1
    funnel_html = "".join(
        f"<div class='frow'><span class='flab'>{name}</span>"
        f"<div class='fbar' style='width:{max(2, round(100 * n / fmax))}%'></div>"
        f"<span class='fnum'>{n}</span></div>"
        for name, n in funnel)

    # Master ATS histogram, 10 buckets  deterministic, so this reflects every row with
    # a captured JD (not just LLM-reviewed ones).
    buckets = [0] * 10
    for v in mats_values:
        buckets[min(9, v // 10)] += 1
    bmax = max(buckets) or 1
    # Count label ABOVE each bar (0 shown muted) so the histogram reads as live data, not
    # decoration  and a total so you can see it track row count as it grows.
    hist_html = "".join(
        f"<div class='hcol' title='Master ATS {i * 10}-{i * 10 + 9}: {n} role(s)'>"
        f"<span class='hn{' z' if not n else ''}'>{n}</span>"
        f"<div class='hbar' style='height:{round(100 * n / bmax)}%'></div>"
        f"<span class='hx'>{i * 10}</span></div>"
        for i, n in enumerate(buckets))

    # Role mix by profile, with the applied share highlighted (ML vs SDE vs Data + applied).
    _PROF_LABEL = {"ml_ai": "ML/AI", "sde": "SDE", "data_engineer": "Data Eng"}
    pmax = max(prof_total.values(), default=0) or 1
    prof_chart_html = "".join(
        f"<div class='frow'><span class='flab'>{html.escape(_PROF_LABEL.get(p, p))}</span>"
        f"<div class='pbar'>"
        f"<div class='pbar-tot' style='width:{max(2, round(100 * prof_total[p] / pmax))}%'>"
        f"<div class='pbar-app' style='width:{round(100 * prof_applied.get(p, 0) / prof_total[p])}%'></div>"
        f"</div></div>"
        f"<span class='fnum'>{prof_applied.get(p, 0)}/{prof_total[p]}</span></div>"
        for p in sorted(prof_total, key=lambda p: -prof_total[p])
    ) or "<div class='mut'>no scored roles yet</div>"

    # Jobs by source  one compact horizontal strip: "scoutbetter 74 · ashby 9 · …".
    # data-tot/data-app let the "applied only" switch swap the number and re-sort in place.
    src_rows_html = "".join(
        f"<span class='schip' data-tot='{src_total[s]}' data-app='{src_applied.get(s, 0)}' "
        f"title='{html.escape(s)}: {src_total[s]} role(s), {src_applied.get(s, 0)} applied'>"
        f"<span class='sl'>{html.escape(s)}</span><b>{src_total[s]}</b></span>"
        for s in sorted(src_total, key=lambda s: -src_total[s])
    ) or "<span class='mut'>no roles yet</span>"

    # Status chips: drop low-signal/duplicate statuses. 'duplicate' is noise, 'skipped'
    # is roles we already passed on. 'scored' is dropped because its meaning was
    # ambiguous (which score?)  use the "high fit" chip instead. 'tailored' status is
    # dropped because the resume-existence "✓ tailored" chip below already covers it
    # and is the more reliable signal (a tailored PDF/tex on disk, not a status string).
    _HIDE_STATUS = {"duplicate", "skipped", "scored", "tailored"}
    status_chips = "".join(
        f"<button class='chip' data-status='{html.escape(s)}' onclick='chip(this)'>"
        f"{html.escape(s)} ({n})</button>"
        for s, n in sorted(statuses.items(), key=lambda kv: -kv[1]) if s not in _HIDE_STATUS)
    if removed_count:
        status_chips += (f"<button class='chip chip-rm' onclick='toggleRemoved(this)'>"
                         f"🗑 removed ({removed_count})</button>")
    profile_opts = "".join(f"<option>{html.escape(p)}</option>"
                           for p in sorted(profiles_seen))

    page = _TEMPLATE.format(
        generated=today, total=total, found_today=found_today, tailored=tailored,
        ready=ready, applied=applied, avg_mats=avg_mats,
        high_fit_not_applied=high_fit_not_applied,
        funnel=funnel_html, hist=hist_html, mats_n=len(mats_values),
        prof_chart=prof_chart_html, src_rows=src_rows_html,
        chips=status_chips, profile_opts=profile_opts,
        rows="\n".join(rows) or "<tr><td colspan='12' class='mut'>No applications yet  "
                                "run <code>python -m src.cli pipeline</code>.</td></tr>",
    )
    dest = pathlib.Path(out_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(page)
    return f"Wrote dashboard to {dest}"


_TEMPLATE = """<!doctype html><html><head><meta charset="utf-8">
<title>Job Pipeline Dashboard</title>
<style>
  :root {{ --bg:#eef1f8; --panel:#ffffff; --line:#dde2ee; --txt:#1c2130; --mut:#6b7280;
          --ok:#16a34a; --good:#65a30d; --warn:#d97706; --bad:#dc2626; --acc:#4f46e5;
          --acc-soft:#e6e4fb; --hover:#f3f5fc; }}
  * {{ box-sizing:border-box; }}
  body {{ font:14px/1.45 -apple-system,'Segoe UI',Roboto,sans-serif; margin:0;
         background:var(--bg); color:var(--txt); padding:28px; }}
  h1 {{ font-size:19px; margin:0 0 2px; }} .sub {{ color:var(--mut); font-size:12px; }}
  .grid {{ display:grid; grid-template-columns:repeat(6,1fr); gap:12px; margin:18px 0; }}
  .card {{ background:var(--panel); border:1px solid var(--line); border-radius:10px;
          padding:12px 16px; box-shadow:0 1px 2px rgba(20,25,50,.04); }}
  .card b {{ display:block; font-size:24px; margin-bottom:2px; }}
  .card span {{ color:var(--mut); font-size:11.5px; text-transform:uppercase;
               letter-spacing:.5px; }}
  .panels {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-bottom:18px; }}
  .pbar {{ flex:1; height:14px; background:var(--bg); border-radius:4px; overflow:hidden; }}
  .pbar-tot {{ height:100%; background:var(--acc); border-radius:4px; position:relative; }}
  .pbar-app {{ height:100%; background:var(--ok); border-radius:4px; }}
  .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:10px;
           padding:14px 16px; box-shadow:0 1px 2px rgba(20,25,50,.04); }}
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
  .hn {{ font-size:10px; color:var(--txt); font-weight:600; margin-bottom:2px; }}
  .hn.z {{ color:var(--mut); opacity:.4; font-weight:400; }}
  .hx {{ margin-top:2px; }}
  .bar {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:12px; }}
  input,select {{ background:var(--panel); color:var(--txt); border:1px solid var(--line);
          border-radius:8px; padding:7px 10px; font-size:13px; }}
  input {{ width:260px; }}
  .chip {{ background:var(--panel); color:var(--mut); border:1px solid var(--line);
          border-radius:999px; padding:4px 12px; font-size:12px; cursor:pointer; }}
  .chip.on {{ color:var(--acc); border-color:var(--acc); background:var(--acc-soft); font-weight:600; }}
  .chip-tl.on {{ color:var(--ok); border-color:var(--ok); background:#dcfce7; font-weight:600; }}
  .chip-rd.on {{ color:#047857; border-color:#047857; background:#d1fae5; font-weight:600; }}
  .chip-hf.on {{ color:#b45309; border-color:#b45309; background:#fef3c7; font-weight:600; }}
  .srchdr {{ display:flex; justify-content:space-between; align-items:center;
             font-size:11px; font-weight:600; color:var(--mut); text-transform:uppercase;
             letter-spacing:.4px; border-top:1px solid var(--line); padding-top:8px; }}
  .sw {{ display:inline-flex; align-items:center; gap:5px; cursor:pointer; font-weight:500;
         text-transform:none; letter-spacing:0; }}
  .srcstrip {{ display:grid; grid-template-columns:repeat(2, 1fr); gap:6px; padding:6px 0 2px; }}
  .schip {{ display:flex; align-items:center; justify-content:space-between; gap:6px;
            box-sizing:border-box; min-width:0; background:var(--bg);
            border:1px solid var(--line); border-radius:20px; padding:3px 11px;
            font-size:12px; color:var(--mut); }}
  .schip .sl {{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap; min-width:0; }}
  .schip b {{ flex:0 0 auto; color:var(--acc); font-variant-numeric:tabular-nums; }}
  .schip.zero {{ opacity:.35; }}
  table {{ border-collapse:collapse; width:100%; font-size:13px; background:var(--panel);
          border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
  th,td {{ border-bottom:1px solid var(--line); padding:8px 10px; text-align:left;
          vertical-align:top; }}
  th {{ cursor:pointer; background:var(--bg); font-size:11px; text-transform:uppercase;
       letter-spacing:.4px; color:var(--mut); position:sticky; top:0; user-select:none; }}
  tr:hover td {{ background:var(--hover); }}
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
  .btn {{ background:var(--acc-soft); color:var(--acc); border:1px solid var(--acc);
         border-radius:7px; padding:3px 10px; font-size:12px; cursor:pointer;
         white-space:nowrap; margin-right:4px; font-weight:600; }}
  .btn:hover {{ background:var(--acc); color:#fff; }}
  .btn.done {{ background:transparent; color:var(--ok); border-color:var(--ok);
              cursor:default; }}
  .ic {{ background:transparent; color:var(--mut); border:1px solid var(--line);
        border-radius:6px; width:22px; height:22px; line-height:1; font-size:15px;
        cursor:pointer; padding:0; margin-left:4px; vertical-align:middle; }}
  .ic-rm:hover {{ color:#fff; background:var(--bad); border-color:var(--bad); }}
  .ic:hover {{ border-color:var(--acc); }}
  .rmcell {{ width:28px; text-align:center; padding-left:6px; padding-right:2px; }}
  .chip-rm.on {{ color:var(--bad); border-color:var(--bad); background:#fee2e2; font-weight:600; }}
  .runrow {{ display:flex; align-items:center; gap:10px; margin-top:12px;
            padding-top:10px; border-top:1px solid var(--line); }}
  #runstatus {{ font-size:11.5px; line-height:1.35; }}
  #runbtn.busy {{ opacity:.6; cursor:default; }}
  tr[data-removed='1'] {{ display:none; }}
  body.show-removed tr[data-removed='1'] {{ display:table-row; opacity:.55; }}
  #toast {{ position:fixed; bottom:20px; right:20px; background:var(--panel);
           border:1px solid var(--acc); border-radius:8px; padding:10px 14px;
           font-size:12.5px; max-width:520px; display:none; z-index:9; }}
  .legend {{ color:var(--mut); font-size:11.5px; margin:10px 0 24px; }}
  .pager {{ display:flex; align-items:center; gap:12px; justify-content:center;
           margin:14px 0; }}
  .pager button:disabled {{ opacity:.4; cursor:default; }}
  #pgLabel {{ font-size:12.5px; min-width:110px; text-align:center; }}
</style></head><body>
<h1>Job Pipeline Dashboard <a href="/network" style="font-size:13px;font-weight:500;margin-left:10px">Networking pipeline →</a></h1>
<div class="sub">generated {generated} · Master ATS = deterministic keyword match of the JD against your UNCHANGED master resume (no LLM, no reviewer blended in) · Tailored ATS = same match against the resume actually sent · Reviewer /10 = senior-hiring-manager LLM judgment, a separate signal</div>

<div class="grid">
  <div class="card"><b>{total}</b><span>tracked</span></div>
  <div class="card"><b>{found_today}</b><span>found today</span></div>
  <div class="card"><b>{tailored}</b><span>tailored</span></div>
  <div class="card"><b id="kpiReady">{ready}</b><span>ready to apply</span></div>
  <div class="card"><b id="kpiApplied">{applied}</b><span>applied</span></div>
  <div class="card"><b>{avg_mats}</b><span>avg master ATS</span></div>
  <div class="card" title="Master ATS 70+, not yet applied  your actionable backlog">
    <b>{high_fit_not_applied}</b><span>high fit, not applied</span></div>
</div>

<div class="panels">
  <div class="panel"><h3>Pipeline funnel</h3>{funnel}
    <div class="runrow">
      <button class="btn" id="runbtn" onclick="runPipeline()">▶ Run pipeline</button>
      <span id="runstatus" class="mut">last run: </span>
    </div>
  </div>
  <div class="panel"><h3>Master ATS distribution  {mats_n} rows</h3><div class="hist">{hist}</div></div>
  <div class="panel"><h3>Roles by profile (applied / total)</h3>{prof_chart}
    <div class="mut" style="font-size:10.5px;margin:8px 0 10px">
      <span style="color:var(--ok)">green</span> = applied ·
      <span style="color:var(--acc)">blue</span> = total</div>
    <div class="srchdr">by source
      <button class="chip" id="srcAppliedTog" onclick="toggleSrcApplied()">applied</button>
    </div>
    <div id="srcList" class="srcstrip">{src_rows}</div>
  </div>
</div>

<div class="bar">
  <input id="q" placeholder="Search company / role / verdict…" onkeyup="apply()">
  <select id="prof" onchange="apply()"><option value="">all profiles</option>{profile_opts}</select>
  <button class="chip chip-hf" data-highfit="1" onclick="toggleHighFit(this)"
          title="Master ATS score is 70 or above  worth spending tailoring effort on">🎯 high fit (ATS 70+)</button>
  <button class="chip chip-tl" data-tailored="1" onclick="toggleTailored(this)"
          title="Show only jobs that already have a tailored resume">✓ tailored ({tailored})</button>
  <button class="chip chip-rd" data-ready="1" onclick="toggleReady(this)"
          title="Resume produced (recompilable) AND not applied yet">✅ ready to apply ({ready})</button>
  {chips}
  <span class="mut" style="font-size:11px">status chips multi-select</span>
</div>

<table id="t"><thead><tr>
  <th></th><th onclick="sortBy(1)">Date</th><th onclick="sortBy(2)">Company</th>
  <th onclick="sortBy(3)">Role</th><th onclick="sortBy(4)">Job ID</th>
  <th onclick="sortBy(5)">Profile</th>
  <th onclick="sortBy(6)" title="deterministic keyword match of the JD vs your unmodified master resume">Master ATS</th>
  <th onclick="sortBy(7)" title="deterministic keyword match of the JD vs the resume actually tailored/sent">Tailored ATS</th>
  <th onclick="sortBy(8)" title="senior-hiring-manager LLM judgment of the tailored resume">Reviewer /10</th>
  <th onclick="sortBy(9)">Posted</th><th onclick="sortBy(10)">Source</th><th>Actions</th>
</tr></thead><tbody>{rows}</tbody></table>

<div class="pager" id="pager">
  <button class="btn" id="pgPrev" onclick="pgGo(-1)">‹ prev</button>
  <span id="pgLabel" class="mut"></span>
  <button class="btn" id="pgNext" onclick="pgGo(1)">next ›</button>
</div>

<p class="legend">Master ATS color: <b style="color:var(--ok)">green</b> 80+ · <b style="color:var(--good)">lime</b> 65+ ·
<b style="color:var(--warn)">amber</b> 50+ · <b style="color:var(--bad)">red</b> below 50  all deterministic keyword
match, computed against the UNCHANGED master resume, before any LLM involvement. Tailored ATS is the same
measure against the resume actually sent. Reviewer /10 is a separate senior-hiring-manager LLM judgment  never
blended into either ATS number. Tailored files live in <code>data/applications/&lt;Company&gt;/&lt;role-id&gt;/</code>.</p>

<div id="toast"></div>
<script>
// The action buttons POST back to `dashboard --serve`. The page can also be opened as a
// plain file or served by some OTHER web server (an IDE preview) with no such backend 
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
  // Toggle: odd click marks applied AND opens the posting; even click un-marks it and
  // does NOT re-open the link. So an even number of clicks leaves the row as it was.
  var url = btn.dataset.url, tr = btn.closest('tr'), tag = tr.querySelector('.tag');
  var SUBMITTED = ['submitted','applied','ready_to_submit','skipped_submit'];
  function bumpApplied(d) {{ var el = document.getElementById('kpiApplied');
    if (el) el.textContent = (parseInt(el.textContent, 10) || 0) + d; }}
  if (btn.classList.contains('done')) {{
    post('/api/unapplied', url).then(function(j) {{
      var st = j.status || 'tailored';
      btn.classList.remove('done'); btn.textContent = 'apply ↗';
      tr.dataset.status = st;
      if (tag) {{ tag.textContent = st; tag.className = 'tag tag-' + st; }}
      if (SUBMITTED.indexOf(st) < 0) bumpApplied(-1);  // left the applied/ready bucket
      toast('Unmarked applied.');
    }}).catch(function(e) {{
      toast(e.noBackend ? 'Cannot change status from a static page. ' + HINT
                        : 'Could not unmark: ' + e.message, true);
    }});
    return;
  }}
  window.open(url, '_blank');
  var wasSubmitted = SUBMITTED.indexOf(tr.dataset.status) >= 0;
  post('/api/applied', url).then(function() {{
    btn.classList.add('done'); btn.textContent = 'applied ✓';
    tr.dataset.status = 'applied';
    if (tag) {{ tag.textContent = 'applied'; tag.className = 'tag tag-applied'; }}
    if (!wasSubmitted) bumpApplied(1);  // newly entered the applied/ready bucket
    toast('Marked applied.');
  }}).catch(function(e) {{
    toast(e.noBackend ? 'Opened the posting, but could NOT mark it applied. ' + HINT
                      : 'Could not mark applied: ' + e.message, true);
  }});
}}
function findResume(btn) {{
  // Only the backend can open Finder  a web page can't. So on no-backend we do NOT
  // open the PDF in a tab (that just dumps it in the browser); we point you at --serve.
  post('/api/reveal', btn.dataset.url).then(function(j) {{
    toast('Revealed <code>' + j.dir + '</code> in Finder.');
  }}).catch(function(e) {{
    toast(e.noBackend ? 'Cannot open Finder from a static page. ' + HINT
                      : 'Could not open the folder: ' + e.message, true);
  }});
}}
function recompile(btn) {{
  // Re-render the row's edited tailored_resume.tex into its PDF (overwrites).
  post('/api/recompile', btn.dataset.url).then(function(j) {{
    toast('Recompiled <code>' + j.pdf + '</code>.');
  }}).catch(function(e) {{
    toast(e.noBackend ? 'Recompiling needs the backend. ' + HINT
                      : 'Recompile failed: ' + e.message, true);
  }});
}}
// Remove/restore. Removed rows are hidden but NEVER deleted (removed=True in the tracker).
function removeJob(btn) {{
  if (!confirm('Hide this job from the dashboard? It stays in the tracker (not deleted).')) return;
  post('/api/remove', btn.dataset.url).then(function() {{
    btn.closest('tr').dataset.removed = '1'; toast('Removed (still in the tracker).'); apply();
  }}).catch(function(e) {{ toast(e.noBackend ? 'Removing needs the backend. ' + HINT
                                             : 'Could not remove: ' + e.message, true); }});
}}
function restoreJob(btn) {{
  post('/api/restore', btn.dataset.url).then(function() {{
    btn.closest('tr').dataset.removed = '0'; toast('Restored.'); apply();
  }}).catch(function(e) {{ toast(e.noBackend ? 'Restoring needs the backend. ' + HINT
                                             : 'Could not restore: ' + e.message, true); }});
}}
function toggleRemoved(el) {{
  document.body.classList.toggle('show-removed');
  el.classList.toggle('on');
  apply();  // removed-state is now part of the filter below; re-derive the page
}}
// Run the full pipeline (find -> score -> tailor >70) via the backend, and surface the
// current/last run's progress in the funnel. State persists server-side, so the last
// run shows even after a reload.
function fmtRun(s) {{
  var label = {{idle:'', running:'running…', done:'done', failed:'failed'}}[s.status] || s.status;
  var when = s.finished_at || s.started_at || '';
  var last = (s.progress && s.progress.length) ? s.progress[s.progress.length - 1] : '';
  return 'last run: ' + label + (when ? ' (' + when + ')' : '') + (last ? '  ' + last : '');
}}
function refreshRun() {{
  return fetch('/api/pipeline-status').then(function(r) {{ return r.json(); }})
    .then(function(s) {{
      document.getElementById('runstatus').textContent = fmtRun(s);
      var busy = s.status === 'running', btn = document.getElementById('runbtn');
      btn.classList.toggle('busy', busy); btn.disabled = busy;
      return s;
    }}).catch(function() {{}});
}}
var _runPoll = null;
function pollRun() {{
  clearInterval(_runPoll);
  _runPoll = setInterval(function() {{
    refreshRun().then(function(s) {{
      if (s && s.status !== 'running') {{
        clearInterval(_runPoll); setTimeout(function() {{ location.reload(); }}, 1500);
      }}
    }});
  }}, 2500);
}}
function runPipeline() {{
  if (!LIVE) return toast('Running the pipeline needs the backend. ' + HINT, true);
  post('/api/run-pipeline', '').then(function() {{
    refreshRun(); pollRun();
    toast('Pipeline started  finding jobs, scoring, tailoring >70. Watch the funnel.');
  }}).catch(function(e) {{ toast('Could not start pipeline: ' + e.message, true); }});
}}
if (location.protocol.indexOf('http') === 0) {{
  refreshRun().then(function(s) {{ if (s && s.status === 'running') pollRun(); }});
}}
// Status chips are MULTI-select: a Set of active statuses; empty = all. Clicking toggles
// one on/off, so you can view e.g. scored + tailored together.
var activeStatuses = new Set();
var tailoredOnly = false;
var readyOnly = false;
var highFitOnly = false;
function chip(el) {{
  var s = el.dataset.status;
  if (activeStatuses.has(s)) {{ activeStatuses.delete(s); el.classList.remove('on'); }}
  else {{ activeStatuses.add(s); el.classList.add('on'); }}
  apply();
}}
function toggleTailored(el) {{
  tailoredOnly = !tailoredOnly;
  el.classList.toggle('on', tailoredOnly);
  apply();
}}
function toggleReady(el) {{
  readyOnly = !readyOnly;
  el.classList.toggle('on', readyOnly);
  apply();
}}
function toggleHighFit(el) {{
  highFitOnly = !highFitOnly;
  el.classList.toggle('on', highFitOnly);
  apply();
}}
// "by source" list: the applied-only switch swaps each row's number (total <-> applied)
// and re-sorts the list in place by that number, descending.
function toggleSrcApplied() {{
  var appliedOnly = document.getElementById('srcAppliedTog').classList.toggle('on');
  var box = document.getElementById('srcList');
  var chips = Array.prototype.slice.call(box.querySelectorAll('.schip'));
  chips.forEach(function(c) {{
    var v = appliedOnly ? +c.dataset.app : +c.dataset.tot;
    c.querySelector('b').textContent = v;
    c.classList.toggle('zero', v === 0);
  }});
  chips.sort(function(a, b) {{
    var av = appliedOnly ? +a.dataset.app : +a.dataset.tot;
    var bv = appliedOnly ? +b.dataset.app : +b.dataset.tot;
    return bv - av;
  }});
  chips.forEach(function(c) {{ box.appendChild(c); }});
}}
// Pagination: 30 rows/page over whatever currently matches the filters, in current DOM
// (sort) order. apply() recomputes which rows match and always resets to page 1; sortBy()
// re-derives the filtered set in the new order and keeps the user on page 1 too (a fresh
// sort is a fresh view). Rows failing the filter get display:none permanently (not just
// off-page) so search/status/profile/tailored all still work as before.
var PAGE_SIZE = 30;
var pgPage = 1;
var filteredRows = [];
function apply() {{
  var q = document.getElementById('q').value.toLowerCase();
  var p = document.getElementById('prof').value;
  filteredRows = [];
  document.querySelectorAll('#t tbody tr').forEach(function(tr) {{
    var okQ = !q || tr.innerText.toLowerCase().indexOf(q) > -1;
    var okS = activeStatuses.size === 0 || activeStatuses.has(tr.dataset.status);
    var okP = !p || tr.dataset.profile === p;
    var okT = !tailoredOnly || tr.dataset.tailored === '1';
    var okRd = !readyOnly || tr.dataset.ready === '1';
    var okHf = !highFitOnly || tr.dataset.highfit === '1';
    // Pagination sets inline display, which would otherwise beat the CSS rule that
    // hides removed rows by default  so "removed" has to be a filter condition too,
    // not left to that stylesheet rule, once any row has been paginated.
    var okR = document.body.classList.contains('show-removed') || tr.dataset.removed !== '1';
    if (okQ && okS && okP && okT && okRd && okHf && okR) {{ filteredRows.push(tr); }} else {{ tr.style.display = 'none'; }}
  }});
  pgPage = 1;
  renderPage();
}}
function renderPage() {{
  var pages = Math.max(1, Math.ceil(filteredRows.length / PAGE_SIZE));
  pgPage = Math.min(Math.max(1, pgPage), pages);
  var start = (pgPage - 1) * PAGE_SIZE, end = start + PAGE_SIZE;
  filteredRows.forEach(function(tr, i) {{ tr.style.display = (i >= start && i < end) ? '' : 'none'; }});
  document.getElementById('pgLabel').textContent =
    filteredRows.length ? ('page ' + pgPage + ' of ' + pages + ' (' + filteredRows.length + ')') : 'no matches';
  document.getElementById('pgPrev').disabled = pgPage <= 1;
  document.getElementById('pgNext').disabled = pgPage >= pages;
}}
function pgGo(delta) {{ pgPage += delta; renderPage(); window.scrollTo({{top: document.getElementById('t').offsetTop - 20, behavior: 'smooth'}}); }}
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
  apply();  // re-derive filteredRows in the new DOM order and reset to page 1
}}
apply();  // initial pagination on load
</script>
</body></html>"""
