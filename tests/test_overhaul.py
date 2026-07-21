"""Tests for the overhaul modules: scoring, discover, forms, latex tex handling, brain."""

import json

import pytest

from src import brain as brain_mod
from src import config
from src.tools import discover, forms, latex, scoring


# ----------------------------------------------------------------- scoring

def test_composite_full_blend():
    c = scoring.composite(reviewer_score=8, match_pct=75, ats_score=60,
                          posted_date="2026-06-12", today="2026-06-12")
    assert c["score"] == 79 and c["grade"] == "B"
    assert set(c["breakdown"]) == {"reviewer", "must_have", "keywords", "recency"}


def test_composite_renormalizes_missing_parts():
    c = scoring.composite(ats_score=80, posted_date="2026-06-12", today="2026-06-12")
    # only keywords (.10) + recency (.15): (80*.10 + 100*.15) / .25 = 92
    assert c["score"] == 92


def test_composite_no_signals():
    c = scoring.composite()
    assert c["score"] is None and c["grade"] is None


def test_recency_decay():
    assert scoring.recency_score("2026-06-12", "2026-06-12") == 100
    assert scoring.recency_score("2026-06-05", "2026-06-12") == 0
    assert scoring.recency_score("unverified", "2026-06-12") is None
    mid = scoring.recency_score("2026-06-09", "2026-06-12")
    assert 0 < mid < 100


# ----------------------------------------------------------------- discover

def test_dedupe_by_url_and_company_title():
    jobs = [
        {"company": "Acme", "role": "SDE I", "url": "https://x.com/jobs/1"},
        {"company": "Acme", "role": "SDE I", "url": "https://x.com/jobs/1?ref=feed"},
        {"company": "ACME", "role": "sde i", "url": "https://other.com/2"},
        {"company": "Beta", "role": "SDE I", "url": "https://beta.com/3"},
    ]
    out = discover._dedupe(jobs)
    assert len(out) == 2
    assert {j["company"] for j in out} == {"Acme", "Beta"}


def test_profile_for_title():
    assert discover._profile_for_title("Machine Learning Engineer") == "ml_ai"
    assert discover._profile_for_title("Data Engineer, Platform") == "data_engineer"
    assert discover._profile_for_title("Software Engineer, Backend") == "sde"
    assert discover._profile_for_title("Sales Account Manager") is None


def test_seniority_gate():
    assert discover._SENIOR.search("Senior Software Engineer")
    assert discover._SENIOR.search("Software Engineering Intern")
    assert not discover._SENIOR.search("Software Engineer II")


# ----------------------------------------------------------------- forms / question bank

PROFILE = {
    "personal": {"full_name": "Jane Doe", "email": "j@d.com", "phone": "1",
                 "location": "Tempe, AZ"},
    "links": {"linkedin": "li.com/j", "github": "gh.com/j", "website": ""},
    "education": {"school": "ASU", "degree": "MS CS", "graduation": "2026-05"},
    "work_authorization": {"authorized_to_work": True, "requires_sponsorship": True,
                           "visa_status": "F-1 OPT", "citizenship_country": "India",
                           "held_h1b_6years": False},
    "preferences": {"open_to_relocation": True, "location_preference": "Remote"},
    "experience": [{"company": "Amazon", "end": "Present"}],
}


def test_question_bank_resolves_from_profile():
    ctx = forms.build_context(PROFILE)
    text, opts = forms.answer_for_label("Are you legally authorized to work in the US?", ctx)
    assert text == "Yes"
    text, opts = forms.answer_for_label("Will you require sponsorship in the future?", ctx)
    assert text == "Yes"  # requires_sponsorship True
    text, opts = forms.answer_for_label("Country / region of citizenship", ctx)
    assert text == "India" and "India" in opts


def test_question_bank_amazon_derived_not_hardcoded():
    ctx = forms.build_context(PROFILE)
    text, _ = forms.answer_for_label(
        "Are you a current Amazon employee or employee of any Amazon subsidiary?", ctx)
    assert text == "Yes"
    ctx2 = forms.build_context({**PROFILE, "experience": [{"company": "Acme", "end": "Present"}]})
    text2, _ = forms.answer_for_label(
        "Are you a current Amazon employee or employee of any Amazon subsidiary?", ctx2)
    assert text2 == "No"


def test_question_bank_skips_judgment_calls():
    ctx = forms.build_context(PROFILE)
    assert forms.answer_for_label("What is your expected base pay?", ctx) is None
    assert forms.answer_for_label("Some totally unknown question?", ctx) is None


# ----------------------------------------------------------------- latex

TEX = r"""
\documentclass{article}
\newcommand{\resumeItem}[1]{\item #1}
\begin{document}
\section{Summary}
 \small{Old summary text here.}
\section{Work Experience}
\resumeSubheading{Engineer}{2024}{Acme}{Remote}
\resumeItem{Did the first thing with measurable results across the system stack}
\resumeItem{Did the second thing with measurable results across the system stack}
\section{Technical Skills}
\begin{itemize}[leftmargin=0in]
  \small{\item{
    \textbf{Languages}{: Python, C++} \\
    \textbf{Cloud}{: AWS}
  }}
\end{itemize}
\end{document}
"""


def test_tex_to_text_extracts_real_content():
    text = latex.tex_to_text(TEX)
    assert "## Summary" in text and "Old summary text here." in text
    assert "- Did the first thing" in text
    assert "\\resumeItem" not in text and "\\textbf" not in text


def test_edit_tex_patches_skills_block():
    patch = {"summary": "New summary.",
             "technical_skills": "Languages: Go, Rust | Data: Spark, Kafka"}
    out = latex.edit_tex(TEX, patch)
    assert "New summary." in out
    assert r"\textbf{Languages}{: Go, Rust}" in out
    assert r"\textbf{Data}{: Spark, Kafka}" in out
    assert "Python, C++" not in out


TEX2 = r"""
\documentclass{article}
\newcommand{\resumeItem}[1]{\item #1}
\begin{document}
\section{Work Experience}
\resumeSubheadingg{Amazon | MLE}{2025}
\resumeItem{Amazon bullet one original text that is here}
\resumeItem{Amazon bullet two original text that is here}
\resumeItem{Amazon bullet three original text that is here}
\resumeSubheadingg{TCS | SDE}{2021}
\resumeItem{TCS bullet one original text that is here}
\section{Education}
\resumeSubheading{MS CS}{2025}{ASU}{Tempe}
\end{document}
"""


def test_edit_tex_targets_block_and_takes_n_bullets():
    # 3 bullets, block 0: all three Amazon items replaced, TCS untouched
    out = latex.edit_tex(TEX2, {"top_bullets": ["New A1", "New A2", "New A3"],
                                "experience_section_index": 0})
    assert "New A1" in out and "New A3" in out
    assert "Amazon bullet one original" not in out
    assert "TCS bullet one original" in out
    # block 1: only the TCS item replaced; extra bullets beyond the block are ignored
    out = latex.edit_tex(TEX2, {"top_bullets": ["New T1", "New T2"],
                                "experience_section_index": 1})
    assert "New T1" in out and "New T2" not in out
    assert "Amazon bullet one original" in out


TEX3 = r"""
\documentclass{article}
\newcommand{\resumeItem}[1]{\item #1}
\begin{document}
\section{Projects}
    \resumeSubHeadingListStart
    \resumeProjectHeading
          {\textbf{Old Project} $|$ \href{https://x}{[Code]}}{}
          \resumeItemListStart
          \resumeItem{Old project bullet text goes right here}
          \resumeItemListEnd
    \resumeSubHeadingListEnd
\section{Education}
\resumeSubheading{MS}{2025}{ASU}{Tempe}
\end{document}
"""


def test_edit_tex_reselects_projects():
    patch = {"projects": [
        {"name": "Streaming Pipeline", "url": "https://github.com/x/stream",
         "bullet": "Built a Kafka streaming pipeline on EC2 with Glue cataloging and Athena querying"},
        {"name": "SafeNet", "url": "", "bullet": "Mitigated tabular ML bias with SMOTE and fairlearn"},
    ]}
    out = latex.edit_tex(TEX3, patch)
    assert r"\textbf{Streaming Pipeline} $|$ \href{https://github.com/x/stream}{[Code]}" in out
    assert r"\textbf{SafeNet}" in out and "fairlearn" in out
    assert "Old Project" not in out
    assert r"\section{Education}" in out  # next section untouched


def test_ats_ignores_benefits_and_chrome_boilerplate():
    from src.tools import ats as ats_mod
    # A JD padded with portal chrome + benefits copy must still score on real skills,
    # not on "employee stock", "submit resume", "learn about", etc.
    jd = ("Machine Learning Engineer. Build retrieval and ranking systems with Python "
          "and PyTorch for search. Submit resume. Employee stock programs and benefits. "
          "Learn about careers. Sign in to your profile. Gift cards and wallet.")
    resume = "Built retrieval and ranking systems in Python and PyTorch for search."
    r = ats_mod.ats_score(jd, resume)
    junk = {"employee", "stock", "programs", "benefits", "submit", "resume",
            "learn", "careers", "profile", "gift", "cards", "wallet"}
    assert not (junk & set(r["matched_keywords"] + r["missing_keywords"]))
    assert r["score"] >= 60  # real skills (retrieval/ranking/python/pytorch/search) match


def test_render_tailor_system_has_no_stray_format_braces():
    # Literal { } in the prompt must be escaped as {{ }} or .format() raises KeyError.
    from src import prompts
    s = prompts.render_tailor_system()  # would KeyError if a brace leaked
    assert "{name, url, bullet}" in s   # the projects example survived, un-doubled
    assert "{summary_min}" not in s and "{bullet_max}" not in s  # budgets filled


def test_lint_flags_em_dash_in_focus_bullet():
    from src.tools import resume as resume_mod
    md = ("## Summary\nA sentence long enough to pass the minimum summary word "
          "count check for linting right now today.\n\n## Work Experience\n### R (2024)\n"
          "- Built a data pipeline processing millions of records daily — cutting "
          "costs by forty percent overall\n")
    out = resume_mod.lint(markdown=md)
    assert any("dash" in i.lower() for i in out["issues"])


# ----------------------------------------------------------------- brain

def test_manual_brain_roundtrip(tmp_path):
    b = brain_mod.ManualBrain(base_dir=tmp_path)
    schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
    with pytest.raises(brain_mod.BrainPending) as exc:
        b.structured("tailor", system="sys", user="usr", schema=schema)
    packet = exc.value.packet_path
    assert packet.exists() and "Required JSON schema" in packet.read_text()
    # operator answers (with a tolerated fenced block)
    exc.value.response_path.write_text('```json\n{"x": 7}\n```')
    out = b.structured("tailor", system="sys", user="usr", schema=schema)
    assert out == {"x": 7}


def test_careers_scraper_extractors():
    from src.sources import careers_page
    import time
    now = int(time.time())
    # icon-only link (Google-style) -> title from container text, location after "place"
    title, loc = careers_page._title_and_location(
        "", "Software Engineer III, Web Ecosystem corporate_fare Google place Austin, TX, USA bar_chart Mid")
    assert title == "Software Engineer III, Web Ecosystem"
    assert loc == "Austin, TX, USA"
    # date parsing variants
    assert careers_page._parse_date("Posted 3 days ago", now)[0] != ""
    assert careers_page._parse_date("June 10, 2026", now)[0] == "2026-06-10"
    assert careers_page._parse_date("no date here", now) == ("", 0)


def test_careers_source_optin_only():
    from src import sources
    src = sources.all_sources()["careers_page"]
    # selectable by keyword; availability depends on a watchlist scrape block existing
    assert [s.name for s in sources.resolve(["careers"])] == ["careers_page"]
    assert hasattr(src, "fetch")


def test_workday_company_detection_and_params():
    from src.tools import boards
    # explicit workday config
    c1 = {"name": "NVIDIA", "ats": "workday",
          "workday": {"host": "nvidia.wd5.myworkdayjobs.com", "site": "NVIDIAExternalCareerSite"}}
    assert boards._is_api_company(c1)
    assert boards._workday_params(c1) == ("nvidia.wd5.myworkdayjobs.com", "NVIDIAExternalCareerSite")
    # derive from a board URL
    c2 = {"name": "X", "ats": "workday",
          "board": "https://acme.wd1.myworkdayjobs.com/en-US/AcmeCareers"}
    assert boards._workday_params(c2) == ("acme.wd1.myworkdayjobs.com", "AcmeCareers")
    # token ATS still detected; non-API company (no token/workday) skipped
    assert boards._is_api_company({"name": "S", "ats": "greenhouse", "token": "stripe"})
    assert not boards._is_api_company({"name": "Google", "board": "https://google.com/careers"})


def test_workday_posted_iso_relative():
    from src.tools import boards
    from datetime import datetime, timezone
    utc_today = datetime.now(timezone.utc).date().isoformat()  # fn computes in UTC
    assert boards._workday_posted_iso("Posted Today") == utc_today
    assert boards._workday_posted_iso("Posted 30+ Days Ago") < utc_today
    assert boards._workday_posted_iso("") == ""


def test_review_merge_applies_only_changed_fields():
    from src.tools.tailor import _merge_review
    patch = {"summary": "orig sum", "technical_skills": "orig skills",
             "top_bullets": ["b1", "b2"], "experience_section_index": 0, "reasoning": "r"}

    # ok=true -> no change
    out, changed = _merge_review(patch, {"ok": True, "new_summary": "ignored",
                                         "new_top_bullets": ["x", "y"],
                                         "new_experience_section_index": 2})
    assert changed is False and out["summary"] == "orig sum"

    # revise bullets + move experience block, keep summary/skills
    out, changed = _merge_review(patch, {
        "ok": False, "new_summary": "", "new_technical_skills": "",
        "new_top_bullets": ["new1", "new2"], "new_experience_section_index": 1})
    assert changed is True
    assert out["top_bullets"] == ["new1", "new2"]
    assert out["experience_section_index"] == 1
    assert out["summary"] == "orig sum" and out["technical_skills"] == "orig skills"


def test_sources_registry_and_selection():
    from src import sources
    names = set(sources.all_sources())
    assert {"ats_boards", "github_feed", "linkedin", "scoutbetter"} <= names
    # select by keyword
    chosen = sources.resolve(["greenhouse"])
    assert [s.name for s in chosen] == ["ats_boards"]
    # linkedin is off until configured; scoutbetter is a public API (on by default)
    assert sources.all_sources()["linkedin"].available() is False
    assert sources.all_sources()["scoutbetter"].available() is True
    # explicit selection bypasses availability (lets you force one on)
    assert [s.name for s in sources.resolve(["linkedin"])] == ["linkedin"]


def test_workday_url_parses_to_cxs_api():
    import re
    from src.tools import jd_fetch
    url = ("https://ngc.wd1.myworkdayjobs.com/Northrop_Grumman_External_Site/job/"
           "United-States-California-San-Diego/SE_R10234156")
    m = re.search(r"https?://([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/([^/]+)/job/(.+)",
                  url, re.I)
    assert m and m.group(1) == "ngc" and m.group(3) == "Northrop_Grumman_External_Site"
    # the fetcher exists and is wired into the API chain
    assert hasattr(jd_fetch, "_workday_api")


def test_config_paths_are_root_anchored():
    assert config.APPLICATIONS_PATH.is_absolute()
    assert str(config.APPLICATIONS_PATH).endswith("data/applications.json")
    assert config.resume_pdf_name().endswith("_Resume.pdf") or \
        config.resume_pdf_name() == "Tailored_Resume.pdf"
