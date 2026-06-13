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


def test_config_paths_are_root_anchored():
    assert config.APPLICATIONS_PATH.is_absolute()
    assert str(config.APPLICATIONS_PATH).endswith("data/applications.json")
    assert config.resume_pdf_name().endswith("_Resume.pdf") or \
        config.resume_pdf_name() == "Tailored_Resume.pdf"
