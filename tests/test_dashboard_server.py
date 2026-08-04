"""Component tests for the live dashboard backend  a real HTTP server on a real port.

These drive the exact requests the dashboard's buttons make, so a broken endpoint fails
here instead of in the browser. Every response must be JSON: the buttons parse with
`fetch().json()`, so an HTML error page surfaces as "Unexpected token '<'".
"""

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import HTTPServer

import pytest

from src.tools import artifacts, dashboard_server, tracker


@pytest.fixture
def revealed(monkeypatch):
    """Capture what the server would open in Finder instead of spawning it."""
    seen = []
    monkeypatch.setattr(dashboard_server, "reveal", seen.append)
    return seen


@pytest.fixture
def server(tmp_data, monkeypatch):
    """Live server bound to an ephemeral port, serving files out of tmp_data."""
    monkeypatch.setattr(dashboard_server.config, "DATA_DIR", tmp_data)
    monkeypatch.setattr(dashboard_server.config, "DASHBOARD_PATH", tmp_data / "d.html")
    monkeypatch.setattr(dashboard_server.dashboard, "OUT_PATH", tmp_data / "d.html")
    httpd = HTTPServer(("127.0.0.1", 0), dashboard_server._Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()


def _post(base, path, url):
    """Returns (status, parsed-JSON body). Fails loudly if the body is not JSON."""
    req = urllib.request.Request(base + path, data=json.dumps({"url": url}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read()
        assert not body.lstrip().startswith(b"<"), f"HTML error page, not JSON: {body[:80]}"
        return e.code, json.loads(body)


@pytest.fixture
def job(tmp_data):
    """One tracked, tailored job  filed under a company name containing a space, the
    case that broke the un-encoded href."""
    url = "https://boards.greenhouse.io/acme/jobs/4951814008"
    pdf = artifacts.folder("Acme Inc", "ML Engineer", url) / "Devanshu_Gupta_Resume.pdf"
    pdf.write_bytes(b"%PDF-1.4 x")
    tracker.save_application(company="Acme Inc", role="ML Engineer", url=url,
                             status="scored", tailored_pdf=str(pdf))
    return url


def test_get_root_serves_focus_entry(server, job):
    # "/" is the official focus UI (story + doors); the old dashboard moved to /classic
    body = urllib.request.urlopen(server + "/").read().decode()
    assert "vouch." in body and 'class="door"' in body


def test_get_classic_serves_freshly_rendered_dashboard(server, job):
    body = urllib.request.urlopen(server + "/classic").read().decode()
    assert "Acme Inc" in body and "applyJob(this)" in body


def test_applied_marks_the_tracker(server, job):
    status, body = _post(server, "/api/applied", job)
    assert status == 200 and body["status"] == "applied"
    rec = tracker.list_applications()[0]
    assert rec["status"] == "applied" and rec["applied_date"]


def test_reveal_opens_only_the_clicked_jobs_folder(server, job, revealed):
    """One click reveals exactly one resume  never the whole tracker."""
    other = "https://boards.greenhouse.io/other/jobs/1111111"
    other_pdf = artifacts.folder("Other Co", "SDE", other) / "Devanshu_Gupta_Resume.pdf"
    other_pdf.write_bytes(b"%PDF")
    tracker.save_application(company="Other Co", role="SDE", url=other,
                             status="scored", tailored_pdf=str(other_pdf))
    status, body = _post(server, "/api/reveal", job)
    assert status == 200
    assert body["dir"].endswith("Acme Inc/ml-engineer-4951814008")
    assert revealed == [artifacts.BASE / "Acme Inc" / "ml-engineer-4951814008"
                        / "Devanshu_Gupta_Resume.pdf"]


def test_resume_is_downloadable_from_the_dashboard_href(server, job):
    """The button only renders when the PDF exists, and its href (which contains a
    space) must resolve  percent-encoded on the wire, decoded by the server."""
    href = ("applications/Acme%20Inc/ml-engineer-4951814008/"
            "Devanshu_Gupta_Resume.pdf")
    r = urllib.request.urlopen(f"{server}/{href}")
    assert r.status == 200 and r.headers["Content-Type"] == "application/pdf"
    assert r.read() == b"%PDF-1.4 x"


def test_errors_are_json_not_html(server, job, tmp_data):
    assert _post(server, "/api/applied", "https://nope")[0] == 404      # unknown job
    assert _post(server, "/api/nonsense", job)[0] == 404                # bad endpoint
    tracker.update_application(job, tailored_pdf=str(tmp_data / "gone.pdf"))
    status, body = _post(server, "/api/reveal", job)                    # missing file
    assert status == 500 and "gone.pdf" in body["error"]


def test_ping_identifies_the_backend(server):
    body = json.loads(urllib.request.urlopen(server + "/api/ping").read())
    assert body == {"ok": True}


def test_remove_and_restore_flag_without_deleting(server, job):
    # remove sets removed=True but keeps the record; restore clears it. Nothing is deleted.
    status, body = _post(server, "/api/remove", job)
    assert status == 200 and body["removed"] is True
    rec = tracker.list_applications()[0]
    assert rec["removed"] is True and rec["url"] == job    # still present, just flagged
    assert _post(server, "/api/restore", job)[1]["removed"] is False
    assert tracker.list_applications()[0]["removed"] is False


def test_removed_rows_hidden_and_excluded_from_stats(tmp_data):
    from src.tools import dashboard
    tracker.save_application(company="Keep", role="SDE", url="u1", status="scored",
                             resume_score=8, match_pct=80)
    tracker.save_application(company="Drop", role="SDE", url="u2", status="scored",
                             resume_score=9, match_pct=90)
    tracker.update_application("u2", removed=True)
    dashboard.render(tmp_data / "d.html")
    h = (tmp_data / "d.html").read_text()
    assert "Keep" in h and "Drop" in h            # removed row still RENDERED (for restore)
    assert "data-removed='1'" in h                 # but flagged hidden
    assert "🗑 removed (1)" in h                    # and offered via the toggle


def test_reveal_failure_is_reported_json_not_swallowed(server, job, monkeypatch):
    # A Finder/open failure must reach the client as a JSON 500, not a silent no-op.
    def boom(_path):
        raise OSError("open -R failed (1): no such file")
    monkeypatch.setattr(dashboard_server, "reveal", boom)
    status, body = _post(server, "/api/reveal", job)
    assert status == 500 and "open -R failed" in body["error"]


def test_run_pipeline_launches_and_status_is_json(server, monkeypatch):
    # run-pipeline must not require a job url and must launch via start_pipeline (mocked
    # so no real subprocess); the status endpoint always returns JSON with a progress tail.
    calls = []
    monkeypatch.setattr(dashboard_server, "start_pipeline",
                        lambda: calls.append(1) or {"status": "running"})
    status, body = _post(server, "/api/run-pipeline", "")
    assert status == 200 and body["status"] == "running" and calls == [1]
    st = json.loads(urllib.request.urlopen(server + "/api/pipeline-status").read())
    assert "status" in st and "progress" in st and isinstance(st["progress"], list)


def test_recompile_rebuilds_pdf_from_tex_without_existing_pdf(server, job, monkeypatch):
    # Deleting the PDF must NOT block recompile  it rebuilds from tailored_resume.tex.
    from src.tools import artifacts, latex
    folder = artifacts.folder("Acme Inc", "ML Engineer",
                              "https://boards.greenhouse.io/acme/jobs/4951814008")
    (folder / "tailored_resume.tex").write_text("dummy tex source")
    (folder / "Devanshu_Gupta_Resume.pdf").unlink()          # user deleted the PDF
    def fake_compile(src, out):
        out.write_bytes(b"%PDF-1.4 rebuilt"); return True, "ok"
    monkeypatch.setattr(latex, "compile_pdf", fake_compile)
    status, body = _post(server, "/api/recompile", job)
    assert status == 200, body
    assert (folder / "Devanshu_Gupta_Resume.pdf").read_bytes() == b"%PDF-1.4 rebuilt"


def test_path_traversal_is_refused(server, job):
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(server + "/../config/profile.json")
    assert e.value.code == 404


def test_assets_served_and_traversal_refused(server):
    r = urllib.request.urlopen(server + "/assets/trail/b1.jpg")
    assert r.status == 200 and r.headers["Content-Type"] == "image/jpeg"
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(server + "/assets/..%2Ffocus.py")
    assert e.value.code == 404


def test_about_page_served(server):
    body = urllib.request.urlopen(server + "/about").read().decode()
    assert "Interviews come from" in body and 'id="contact"' in body


def test_tracker_save_is_atomic(tmp_data):
    """_save_db must never leave a partial main file or stray tmp files behind."""
    tracker.save_application(company="X", role="Y", url="https://x/1", status="found")
    files = list(tracker.APPLICATIONS_PATH.parent.glob("*.tmp"))
    assert files == []
    json.loads(tracker.APPLICATIONS_PATH.read_text())  # valid JSON on disk


def test_touch_logs_outreach(server, tmp_data):
    net = tmp_data / "network"
    net.mkdir(exist_ok=True)
    (net / "companies.json").write_text(json.dumps({"companies": [
        {"name": "Acme", "status": "outreach_drafted",
         "people": [{"name": "Jane Roe", "outreach": []}]}]}))
    req = urllib.request.Request(server + "/api/touch",
                                 data=json.dumps({"company": "Acme", "person": "Jane Roe",
                                                  "outcome": "sent"}).encode(),
                                 headers={"Content-Type": "application/json"})
    r = urllib.request.urlopen(req)
    assert r.status == 200 and json.loads(r.read())["logged"] == "sent"
    db = json.loads((net / "companies.json").read_text())
    assert db["companies"][0]["people"][0]["outreach"][0]["outcome"] == "sent"
    assert db["companies"][0]["status"] == "contacted"
    status, body = _post(server, "/api/touch", "")
    assert status == 400


def test_add_job_queues_background_tailor(server, monkeypatch):
    spawned = []
    monkeypatch.setattr(dashboard_server.subprocess, "Popen",
                        lambda *a, **k: spawned.append(a[0]))
    status, body = _post(server, "/api/add-job", "https://boards.greenhouse.io/x/jobs/1")
    assert status == 200 and body["queued"] is True
    assert spawned and spawned[0][-2:] == ["add", "https://boards.greenhouse.io/x/jobs/1"]
    status, body = _post(server, "/api/add-job", "not-a-url")
    assert status == 400


def test_add_company_tracks_and_queues_people_scout(server, tmp_path, monkeypatch):
    from src.tools import people
    monkeypatch.setattr(people, "COMPANIES_PATH", tmp_path / "companies.json")
    spawned = []
    monkeypatch.setattr(dashboard_server.subprocess, "Popen",
                        lambda *a, **k: spawned.append(a[0]))
    status, body = _post(server, "/api/add-company", "https://www.acme.ai/about")
    assert status == 200 and body["queued"] is True and body["company"] == "Acme"
    assert spawned and spawned[0][-2:] == ["--company", "Acme"]
    assert people.load_companies()["companies"][0]["website"] == "https://www.acme.ai"
    # pasting it again dedupes instead of double-tracking
    status, body = _post(server, "/api/add-company", "https://acme.ai")
    assert status == 200 and body["already"] is True and len(spawned) == 1
    status, body = _post(server, "/api/add-company", "https://www.linkedin.com/in/person/")
    assert status == 400


def test_job_status_and_row_endpoints(server, job):
    url = "https://boards.greenhouse.io/acme/jobs/4951814008"
    r = urllib.request.urlopen(server + "/api/job-status?url=" + urllib.parse.quote(url, safe=""))
    st = json.loads(r.read())
    assert st["found"] and st["company"] == "Acme Inc" and st["has_resume"] is True
    r = urllib.request.urlopen(server + "/api/job-row?url=" + urllib.parse.quote(url, safe=""))
    assert "Acme Inc" in json.loads(r.read())["html"]
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(server + "/api/job-status?url=https%3A%2F%2Fnope")
    assert e.value.code == 404


def test_settings_candidate_save(server, tmp_data, monkeypatch):
    root = tmp_data / "root"
    (root / "config").mkdir(parents=True)
    (root / "config" / "network.json").write_text('{"candidate": {"first_name": "Old"}, "keywords": []}')
    monkeypatch.setattr(dashboard_server.config, "ROOT", root)
    req = urllib.request.Request(server + "/api/settings",
                                 data=json.dumps({"section": "candidate",
                                                  "data": {"first_name": "New", "schools": "ASU, RGPV",
                                                           "keywords": "robotics, slam"}}).encode(),
                                 headers={"Content-Type": "application/json"})
    assert urllib.request.urlopen(req).status == 200
    cfg = json.loads((root / "config" / "network.json").read_text())
    assert cfg["candidate"]["first_name"] == "New"
    assert cfg["candidate"]["schools"] == ["ASU", "RGPV"]
    assert cfg["keywords"] == ["robotics", "slam"]


def test_settings_brain_and_keys(server, tmp_data, monkeypatch):
    root = tmp_data / "root2"
    (root / "config").mkdir(parents=True)
    monkeypatch.setattr(dashboard_server.config, "ROOT", root)
    req = urllib.request.Request(server + "/api/settings",
                                 data=json.dumps({"section": "brain",
                                                  "data": {"brain": "api", "ANTHROPIC_API_KEY": "sk-test-123",
                                                           "OPENAI_API_KEY": "",
                                                           "SERPER_API_KEY": "serp-456",
                                                           "HUNTER_API_KEY": ""}}).encode(),
                                 headers={"Content-Type": "application/json"})
    assert urllib.request.urlopen(req).status == 200
    assert json.loads((root / "config" / "settings.json").read_text())["brain"] == "api"
    env = (root / ".env").read_text()
    assert "ANTHROPIC_API_KEY=sk-test-123" in env and "OPENAI_API_KEY" not in env
    # people-finder provider keys ride the same save; blank still means keep/absent
    assert "SERPER_API_KEY=serp-456" in env and "HUNTER_API_KEY" not in env


def test_deadcheck_ready_marks_api_backed_dead_rows(tmp_data, monkeypatch, job):
    # the tracked Acme job is greenhouse; simulate its API saying the posting is gone
    monkeypatch.setattr(dashboard_server.jd_fetch, "fetch_jd",
                        lambda url, allow_browser=True: {"text": "", "source": "greenhouse-api",
                                                         "looks_complete": False})
    out = dashboard_server._deadcheck_ready_sync()
    assert out["checked"] == 1 and out["marked_stale"] == 1
    rec = tracker.list_applications()[-1]
    assert rec["stale"] is True and rec["deadcheck"]["status"] == "dead"


def test_deadcheck_ready_skips_non_api_sources(tmp_data, monkeypatch, job):
    monkeypatch.setattr(dashboard_server.jd_fetch, "fetch_jd",
                        lambda url, allow_browser=True: {"text": "", "source": "http",
                                                         "looks_complete": False})
    out = dashboard_server._deadcheck_ready_sync()
    assert out["checked"] == 0 and out["marked_stale"] == 0
    assert not tracker.list_applications()[-1].get("stale")


def test_deadcheck_ready_endpoint_throttles(server, tmp_data, monkeypatch):
    monkeypatch.setattr(dashboard_server, "_deadcheck_ready_sync", lambda: {"checked": 0})
    r = json.loads(urllib.request.urlopen(server + "/api/deadcheck-ready").read())
    assert r["started"] is True
    r2 = json.loads(urllib.request.urlopen(server + "/api/deadcheck-ready").read())
    assert r2["started"] is False
