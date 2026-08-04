"""Live dashboard server  makes the dashboard *actionable* instead of read-only.

A static `file://` page can neither write `data/applications.json` nor copy a PDF
anywhere, so the two buttons in the table need a tiny local backend:

  GET  /             re-render the dashboard from the tracker and serve it
  POST /api/applied  {"url": …}  mark that job applied (tracker upsert)
  POST /api/remove   {"url": …}  hide a job you don't want (removed=True; never deletes)
  POST /api/restore  {"url": …}  un-hide it (removed=False)
  POST /api/reveal   {"url": …}  open the folder holding its tailored PDF in Finder
  POST /api/recompile {"url": …}  re-render tailored_resume.tex -> PDF (pick up tex edits)
  POST /api/run-pipeline         launch the full pipeline (find → score → tailor >70) in
                                 the background
  GET  /api/pipeline-status      state + progress of the current/last pipeline run
  GET  /<rel>        any file under data/ (serves the PDF itself)

Run with `python -m src.cli dashboard --serve`. Stdlib only, localhost only.
"""

from __future__ import annotations

import json
import mimetypes
import os
import pathlib
import subprocess
import sys
import webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

from .. import config
from . import artifacts, dashboard, tracker


def resume_path(rec: dict) -> pathlib.Path:
    """Absolute path of this job's tailored PDF (stored paths may be relative)."""
    src = pathlib.Path(rec.get("tailored_pdf") or "")
    if not src.name:
        raise FileNotFoundError("no tailored resume for this job")
    if not src.is_absolute():
        src = config.ROOT / src
    if not src.exists():
        raise FileNotFoundError(f"missing file: {src}")
    return src


def reveal(path: pathlib.Path) -> None:
    """Show the file in the OS file manager (Finder on macOS), selected if possible."""
    cmd = ({"darwin": ["open", "-R", str(path)],
            "win32": ["explorer", f"/select,{path}"]}
           .get(sys.platform, ["xdg-open", str(path.parent)]))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:   # surfaced to the toast rather than silently doing nothing
        raise OSError(f"{cmd[0]} failed ({r.returncode}): {r.stderr.strip() or 'no output'}")


def mark_applied(url: str) -> dict | None:
    # Remember the status we're leaving, so a second click can undo cleanly.
    rec = tracker._find_by_url(tracker.list_applications(), url)
    prev = rec.get("status") if rec and rec.get("status") != "applied" else None
    return tracker.update_application(
        url, status="applied", applied_date=date.today().isoformat(),
        prev_status=prev)


def unmark_applied(url: str) -> str:
    """Undo an 'applied' mark (the even-numbered click). Restores the status the row
    had before it was marked applied (or a sensible fallback), clears applied_date, and
    returns the restored status so the UI can re-render the row's tag."""
    rec = tracker._find_by_url(tracker.list_applications(), url)
    prev = (rec or {}).get("prev_status")
    if not prev:  # no stored prior status  infer from how far the row got
        prev = ("tailored" if (rec or {}).get("tailored_pdf")
                else "scored" if (rec or {}).get("resume_score") is not None
                else "found")
    tracker.update_application(url, status=prev, applied_date="", prev_status="")
    return prev


def recompile_resume(rec: dict) -> pathlib.Path:
    """Re-render this job's tailored_resume.tex into its PDF, overwriting it  so editing
    the .tex and clicking 'recompile' picks up the changes. Returns the PDF path."""
    from . import latex
    # Derive the folder/PDF name from the stored path WITHOUT requiring the PDF to exist
    # yet  recompiling is exactly how a missing/edited PDF gets (re)generated.
    stored = pathlib.Path(rec["tailored_pdf"]) if rec.get("tailored_pdf") else None
    if stored is not None and not stored.is_absolute():
        stored = config.ROOT / stored
    folder = (stored.parent if stored else
              artifacts.folder(rec.get("company", ""), rec.get("role", ""), rec.get("url")))
    tex = folder / "tailored_resume.tex"
    if not tex.exists():
        raise FileNotFoundError(f"no tailored_resume.tex in {folder}")
    out = folder / (stored.name if stored else "Devanshu_Gupta_Resume.pdf")
    ok, msg = latex.compile_pdf(tex.read_text(), out)
    if not ok:
        raise RuntimeError(f"compile failed: {msg[:200]}")
    # compile_pdf drops a .tex sidecar named after the PDF; remove it so `tailored_
    # resume.tex` stays the single editable source (never delete that source itself).
    sidecar = out.with_suffix(".tex")
    if sidecar.exists() and sidecar != tex:
        sidecar.unlink()
    if not rec.get("tailored_pdf"):
        tracker.update_application(rec.get("url", ""),
                                   tailored_pdf=artifacts.rel_to_root(out))
    return out


# --- full-pipeline runner ---------------------------------------------------------
# The funnel's "Run pipeline" button launches `src.cli pipeline` (discover → score →
# tailor >70) as ONE background subprocess, streaming its output to a log so the
# dashboard can show live + last-run progress. State persists to a file so the progress
# survives a page reload. (No API key -> the pipeline runs its manual-brain path: it
# discovers and scores what it can and stops at packets, which the progress line shows.)
_RUN_LOG = config.DATA_DIR / "pipeline_run.log"
_RUN_STATE = config.DATA_DIR / "pipeline_run.json"
_proc: subprocess.Popen | None = None


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _read_run_state() -> dict:
    try:
        return json.loads(_RUN_STATE.read_text())
    except (OSError, json.JSONDecodeError):
        return {"status": "idle"}


def _write_run_state(d: dict) -> None:
    _RUN_STATE.parent.mkdir(parents=True, exist_ok=True)
    _RUN_STATE.write_text(json.dumps(d, indent=2))


def start_pipeline(hours: int = 24, top: int = 20) -> dict:
    """Launch the pipeline in the background unless one is already running."""
    global _proc
    if _proc is not None and _proc.poll() is None:
        return {"status": "running", "already": True}
    # -u / PYTHONUNBUFFERED so the child flushes each print to the log line-by-line;
    # otherwise a file-redirected Python subprocess block-buffers and the progress line
    # stays empty for the whole run, which looks stuck even though it's working.
    cmd = [sys.executable, "-u", "-m", "src.cli", "pipeline",
           "--hours", str(hours), "--top", str(top)]
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    _RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    logf = _RUN_LOG.open("w")
    _proc = subprocess.Popen(cmd, cwd=str(config.ROOT), stdout=logf,
                             stderr=subprocess.STDOUT, text=True, env=env)
    _write_run_state({"status": "running", "started_at": _now(),
                      "pid": _proc.pid, "cmd": " ".join(cmd[2:])})
    return {"status": "running"}


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)          # signal 0 = liveness probe, doesn't touch the process
        return True
    except (ProcessLookupError, PermissionError, OverflowError, TypeError):
        return False


# Log markers the pipeline prints when it finishes cleanly (incl. manual-brain, which
# ends at packets). Presence of any => the run completed rather than crashed.
_DONE_MARKERS = ("PIPELINE DONE", "Submit a chosen role", "No fresh roles",
                 "packets awaiting")


def pipeline_status(tail_lines: int = 4) -> dict:
    """Current/last run + a progress tail. Completion is detected by PID liveness (works
    even if THIS server didn't launch the run, or was restarted), then confirmed by a
    log marker  so the status never sticks on 'running' after the process is gone."""
    st = _read_run_state()
    try:
        lines = [ln for ln in _RUN_LOG.read_text().splitlines() if ln.strip()]
    except OSError:
        lines = []
    if st.get("status") == "running":
        alive = _proc.poll() is None if _proc is not None else _pid_alive(st.get("pid"))
        if not alive:
            done = any(m in ln for ln in lines for m in _DONE_MARKERS)
            st["status"] = "done" if done else "failed"
            st["finished_at"] = _now()
            _write_run_state(st)
    st["progress"] = lines[-tail_lines:]
    return st


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict) -> None:
        self._send(code, json.dumps(payload).encode(), "application/json")

    def do_GET(self) -> None:  # noqa: N802
        # Company folders contain spaces, so served paths arrive percent-encoded.
        path = unquote(self.path.split("?")[0]).lstrip("/")
        if path == "api/ping":
            return self._json(200, {"ok": True})
        if path == "api/pipeline-status":
            return self._json(200, pipeline_status())
        # Focus UI (the official interface): /, /apply, /network, /company/<slug>.
        # Old dashboards remain at /classic and /network-classic.
        from . import focus
        if not path:
            return self._send(200, focus.render_entry().encode(), "text/html")
        if path == "apply":
            return self._send(200, focus.render_apply().encode(), "text/html")
        if path == "network":
            return self._send(200, focus.render_network().encode(), "text/html")
        if path.startswith("company/"):
            page = focus.render_company(path.split("/", 1)[1])
            if page:
                return self._send(200, page.encode(), "text/html")
            return self._json(404, {"error": "company not scouted"})
        if path == "classic":
            dashboard.render(config.DASHBOARD_PATH)
            return self._send(200, config.DASHBOARD_PATH.read_bytes(), "text/html")
        if path == "network-classic":
            net = config.DATA_DIR / "network" / "dashboard.html"
            if net.is_file():
                return self._send(200, net.read_bytes(), "text/html")
            return self._json(404, {"error": "no networking dashboard yet; run scripts/network_dashboard.py"})
        target = (config.DATA_DIR / path).resolve()
        if config.DATA_DIR.resolve() in target.parents and target.is_file():
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            return self._send(200, target.read_bytes(), ctype)
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            n = int(self.headers.get("Content-Length") or 0)
            try:
                payload = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                return self._json(400, {"error": "bad JSON"})
            # run-pipeline takes no job url  handle before the record lookup
            if self.path.startswith("/api/run-pipeline"):
                return self._json(200, start_pipeline())
            url = (payload.get("url") or "").strip()
            key = tracker._norm_url(url)
            rec = next((r for r in tracker.list_applications()
                        if tracker._norm_url(r.get("url", "")) == key), None)
            if rec is None:
                return self._json(404, {"error": "unknown job"})
            if self.path.startswith("/api/unapplied"):
                return self._json(200, {"status": unmark_applied(url)})
            if self.path.startswith("/api/applied"):
                mark_applied(url)
                return self._json(200, {"status": "applied"})
            if self.path.startswith("/api/remove"):
                tracker.update_application(url, removed=True)
                return self._json(200, {"removed": True})
            if self.path.startswith("/api/restore"):
                tracker.update_application(url, removed=False)
                return self._json(200, {"removed": False})
            if self.path.startswith("/api/unstale"):
                tracker.update_application(url, stale=False)
                return self._json(200, {"stale": False})
            if self.path.startswith("/api/stale"):
                tracker.update_application(url, stale=True)
                return self._json(200, {"stale": True})
            if self.path.startswith("/api/deadcheck"):
                # On-demand liveness probe: re-fetch the JD (deterministic, no LLM) and
                # decide dead = the page carries no real posting body. Persist the result
                # as `stale` so the pipeline skips it, and return it so the button updates.
                from datetime import datetime
                from . import jd_fetch
                r = jd_fetch.fetch_jd(url, allow_browser=True)
                dead = not r["looks_complete"]
                chars = len(r["text"].strip())
                # Persist the full result so the button state survives a page reload.
                tracker.update_application(url, stale=dead, deadcheck={
                    "status": "dead" if dead else "live", "chars": chars,
                    "at": datetime.now().strftime("%Y-%m-%d %H:%M")})
                return self._json(200, {"dead": dead, "chars": chars})
            if self.path.startswith("/api/reveal"):
                pdf = resume_path(rec)
                reveal(pdf)
                return self._json(200, {"dir": artifacts.rel_to_root(pdf.parent)})
            if self.path.startswith("/api/recompile"):
                out = recompile_resume(rec)
                return self._json(200, {"pdf": artifacts.rel_to_root(out)})
        except Exception as e:  # never let an HTML error page reach the fetch() caller
            return self._json(500, {"error": f"{type(e).__name__}: {e}"})
        self._json(404, {"error": "unknown endpoint"})

    def log_message(self, fmt: str, *args) -> None:
        print(f"  {self.command} {self.path} -> {fmt % args}".rstrip())


def serve(port: int = 8765, open_browser: bool = True) -> None:
    # No initial render needed  GET "/" renders on demand (see do_GET).
    url = f"http://localhost:{port}"
    print(f"Dashboard live at {url}  (Ctrl-C to stop)")
    print(f"Resumes filed under {config.APPLICATIONS_DIR}/<Company>/<job-id>/")
    # Threading: one slow/idle browser connection must never block the next
    # page load (the single-threaded HTTPServer made pages queue behind keep-alives).
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    # Open the RIGHT page automatically so the buttons reach this backend  landing on
    # the file:// page or an IDE preview instead is exactly what breaks apply/reveal.
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
