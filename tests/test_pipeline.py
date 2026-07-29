"""Tests for stateful pipeline pieces: tracker, resume patch/lint, dashboard, profiles."""

from src.tools import dashboard, profiles, resume, tracker


def test_tracker_roundtrip_new_fields(tmp_data):
    rec = tracker.save_application(
        company="Acme", role="SDE", url="http://x/1", status="scored",
        match_score=70, resume_score=8, scorer_verdict="strong",
        resume_diff={"summary": "s"}, source="acme.com", posted_date="2026-06-05",
        profile="sde",
    )
    assert rec["id"] == 1
    apps = tracker.list_applications()
    assert apps[0]["resume_score"] == 8
    assert apps[0]["match_score"] == 70
    assert apps[0]["profile"] == "sde"


def test_save_application_upserts_by_url(tmp_data):
    # Same job across lifecycle stages -> ONE row, status advances, fields merge.
    tracker.save_application(company="Acme", role="SDE", url="http://x/1?ref=feed",
                             status="found", source="feed", posted_date="2026-07-01")
    tracker.save_application(company="Acme", role="SDE", url="http://x/1",  # query differs
                             status="scored", resume_score=8, match_pct=80,
                             tailored_pdf="/p.pdf")
    apps = tracker.list_applications()
    assert len(apps) == 1                          # not duplicated
    row = apps[0]
    assert row["status"] == "scored"               # advanced
    assert row["resume_score"] == 8 and row["match_pct"] == 80
    assert row["tailored_pdf"] == "/p.pdf"
    assert row["source"] == "feed"                 # discovery value preserved (not clobbered)
    assert row["posted_date"] == "2026-07-01"


def test_save_application_empty_url_always_appends(tmp_data):
    tracker.save_application(company="A", role="R", url="", status="found")
    tracker.save_application(company="B", role="R", url="", status="found")
    assert len(tracker.list_applications()) == 2


def test_dedupe_applications_merges_same_job(tmp_data):
    # A found row (real URL, no PDF) + a tailored row (placeholder URL, PDF) for the
    # same job collapse into one row with the real URL, the PDF, and 'tailored' status.
    tracker.save_application(company="Cohort AI Inc.", role="Associate Data Engineer",
                             url="https://ats/cohort/abc", status="found", source="ats")
    tracker.save_application(company="Cohort AI", role="Associate Data Engineer",
                             url="manual:cohort", status="tailored", resume_score=8,
                             tailored_pdf="/r.pdf")
    assert len(tracker.list_applications()) == 2    # distinct URLs -> two rows for now
    removed = tracker.dedupe_applications()
    apps = tracker.list_applications()
    assert removed == 1 and len(apps) == 1
    row = apps[0]
    assert row["status"] == "tailored"
    assert row["tailored_pdf"] == "/r.pdf"
    assert row["url"] == "https://ats/cohort/abc"   # real URL beat the placeholder
    assert row["source"] == "ats"


def test_profiles_auto_pick():
    # profiles are configured in the repo (resume/masters/index.json)
    if not profiles.have_profiles():
        return
    pid, scores = profiles.auto_pick(
        "data engineer etl kafka spark airflow dbt snowflake streaming")
    assert pid == "data_engineer"
    pid2, _ = profiles.auto_pick(
        "machine learning pytorch rag embeddings faiss ranking model serving")
    assert pid2 == "ml_ai"


def test_resume_patch_and_lint(tmp_data, monkeypatch):
    # use a minimal in-memory master via the legacy path
    master = (
        "# Me\nx@y.com\n\n## Summary\nold summary\n\n## Technical Skills\nold skills\n\n"
        "## Experience\n\n### Engineer — Co\nCity · 2024\n"
        "- old bullet one here that is reasonably long enough\n"
        "- old bullet two here that is reasonably long enough\n"
    )
    mpath = tmp_data / "master_resume.md"
    mpath.write_text(master)
    monkeypatch.setattr(resume, "MASTER_PATH", mpath)
    monkeypatch.setattr(resume.profiles, "have_profiles", lambda: False)
    # also redirect the tailored output
    monkeypatch.chdir(tmp_data)
    (tmp_data / "data").mkdir(exist_ok=True)

    patch = {
        "summary": "New tailored summary for the role.",
        "technical_skills": "Python, AWS, Kubernetes, Go",
        "top_bullets": [
            "Scaled a distributed service on AWS to fifty thousand requests per second.",
            "Owned on-call for twelve microservices and cut paging sixty percent overall.",
        ],
        "experience_section_index": 0,
    }
    out = resume.apply_patch(patch)
    assert "New tailored summary" in out
    assert "Scaled a distributed service" in out
    lint = resume.lint(out, focus_bullets=patch["top_bullets"])
    assert "ok" in lint and "issues" in lint


def test_dashboard_pdf_links_when_file_exists(tmp_data):
    # A tailored PDF is linked when the file actually exists on disk (regardless of
    # whether resume_diff was recorded); a stored path with no file is not linked.
    real_pdf = tmp_data / "real_resume.pdf"
    real_pdf.write_bytes(b"%PDF-1.4 test")
    tracker.save_application(company="A", role="SDE", url="u1", status="tailored",
                             tailored_pdf=str(real_pdf))               # file exists -> link
    tracker.save_application(company="B", role="SDE", url="u2", status="found",
                             tailored_pdf=str(tmp_data / "missing.pdf"))  # no file -> no link
    dashboard.render(tmp_data / "dash.html")
    html = (tmp_data / "dash.html").read_text()
    assert html.count("findResume(this)") == 1


def test_dashboard_apply_button_reflects_status(tmp_data):
    tracker.save_application(company="A", role="SDE", url="u1", status="scored")
    tracker.save_application(company="B", role="SDE", url="u2", status="applied")
    dashboard.render(tmp_data / "dash.html")
    html = (tmp_data / "dash.html").read_text()
    assert "apply ↗" in html and "applied ✓" in html
    assert html.count("applyJob(this)") == 2   # both rows get a button


def test_migrate_layout_refiles_and_repoints(tmp_data):
    from src.tools import artifacts

    url = "https://boards.greenhouse.io/acme/jobs/4951814008"
    old = artifacts.BASE / artifacts.slug("Acme Inc", "ML Engineer", url)
    old.mkdir(parents=True)
    (old / "Resume.pdf").write_bytes(b"%PDF")
    tracker.save_application(company="Acme Inc", role="ML Engineer", url=url,
                             status="tailored",
                             tailored_pdf=str(old / "Resume.pdf"))
    moves = artifacts.migrate_layout()
    assert moves == [(old.name, "Acme Inc/ml-engineer-4951814008")]
    new = artifacts.BASE / "Acme Inc" / "ml-engineer-4951814008" / "Resume.pdf"
    assert new.exists() and not old.exists()
    assert tracker.list_applications()[0]["tailored_pdf"].endswith(
        "Acme Inc/ml-engineer-4951814008/Resume.pdf")
    assert artifacts.migrate_layout() == []    # idempotent


def test_dashboard_renders_score_columns(tmp_data):
    tracker.save_application(company="A", role="SDE", url="u", status="scored",
                             match_score=40, resume_score=8, match_pct=70,
                             posted_date="2026-06-10")
    dashboard.render(tmp_data / "dash.html")
    html = (tmp_data / "dash.html").read_text()
    # composite AQS column + component columns all present
    assert "AQS" in html and "Reviewer /10" in html and "Must-have %" in html
    assert "class='aqs'" in html  # the scored row got a composite badge
