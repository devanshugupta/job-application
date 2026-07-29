"""Live dashboard server — makes the dashboard *actionable* instead of read-only.

A static `file://` page can neither write `data/applications.json` nor copy a PDF
anywhere, so the two buttons in the table need a tiny local backend:

  GET  /             re-render the dashboard from the tracker and serve it
  POST /api/applied  {"url": …}  mark that job applied (tracker upsert)
  POST /api/remove   {"url": …}  hide a job you don't want (removed=True; never deletes)
  POST /api/restore  {"url": …}  un-hide it (removed=False)
  POST /api/reveal   {"url": …}  open the folder holding its tailored PDF in Finder
  GET  /<rel>        any file under data/ (serves the PDF itself)

Run with `python -m src.cli dashboard --serve`. Stdlib only, localhost only.
"""

from __future__ import annotations

import json
import mimetypes
import pathlib
import subprocess
import sys
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
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
    return tracker.update_application(
        url, status="applied", applied_date=date.today().isoformat())


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
        if not path:
            dashboard.render(config.DASHBOARD_PATH)
            return self._send(200, config.DASHBOARD_PATH.read_bytes(), "text/html")
        target = (config.DATA_DIR / path).resolve()
        if config.DATA_DIR.resolve() in target.parents and target.is_file():
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            return self._send(200, target.read_bytes(), ctype)
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            n = int(self.headers.get("Content-Length") or 0)
            try:
                url = (json.loads(self.rfile.read(n) or b"{}").get("url") or "").strip()
            except json.JSONDecodeError:
                return self._json(400, {"error": "bad JSON"})
            key = tracker._norm_url(url)
            rec = next((r for r in tracker.list_applications()
                        if tracker._norm_url(r.get("url", "")) == key), None)
            if rec is None:
                return self._json(404, {"error": "unknown job"})
            if self.path.startswith("/api/applied"):
                mark_applied(url)
                return self._json(200, {"status": "applied"})
            if self.path.startswith("/api/remove"):
                tracker.update_application(url, removed=True)
                return self._json(200, {"removed": True})
            if self.path.startswith("/api/restore"):
                tracker.update_application(url, removed=False)
                return self._json(200, {"removed": False})
            if self.path.startswith("/api/reveal"):
                pdf = resume_path(rec)
                reveal(pdf)
                return self._json(200, {"dir": artifacts.rel_to_root(pdf.parent)})
        except Exception as e:  # never let an HTML error page reach the fetch() caller
            return self._json(500, {"error": f"{type(e).__name__}: {e}"})
        self._json(404, {"error": "unknown endpoint"})

    def log_message(self, fmt: str, *args) -> None:
        print(f"  {self.command} {self.path} -> {fmt % args}".rstrip())


def serve(port: int = 8765, open_browser: bool = True) -> None:
    # No initial render needed — GET "/" renders on demand (see do_GET).
    url = f"http://localhost:{port}"
    print(f"Dashboard live at {url}  (Ctrl-C to stop)")
    print(f"Resumes filed under {config.APPLICATIONS_DIR}/<Company>/<job-id>/")
    server = HTTPServer(("127.0.0.1", port), _Handler)
    # Open the RIGHT page automatically so the buttons reach this backend — landing on
    # the file:// page or an IDE preview instead is exactly what breaks apply/reveal.
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
