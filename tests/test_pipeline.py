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


def test_dashboard_pdf_only_when_tailored(tmp_data):
    # tailored row (has resume_diff) -> pdf link; found row (no diff) -> no link
    tracker.save_application(company="A", role="SDE", url="u1", status="scored",
                             resume_diff={"summary": "s"}, tailored_pdf="p.pdf")
    tracker.save_application(company="B", role="SDE", url="u2", status="found",
                             tailored_pdf="q.pdf")  # path but no diff
    dashboard.render(tmp_data / "dash.html")
    html = (tmp_data / "dash.html").read_text()
    assert html.count(">pdf</a>") == 1


def test_dashboard_renders_score_columns(tmp_data):
    tracker.save_application(company="A", role="SDE", url="u", status="scored",
                             match_score=40, resume_score=8, match_pct=70,
                             posted_date="2026-06-10")
    dashboard.render(tmp_data / "dash.html")
    html = (tmp_data / "dash.html").read_text()
    # composite AQS column + component columns all present
    assert "AQS" in html and "Reviewer /10" in html and "Must-have %" in html
    assert "class='aqs'" in html  # the scored row got a composite badge
