"""Unit tests for the deterministic tool logic (no API, no browser)."""

from src.tools import ats, feeds, final_check, finder, jd_fetch, latex, portals, usage as usage_mod
from src.sources import linkedin


def test_login_wall_detected():
    # A logged-out LinkedIn job page renders its auth/nav shell as body text; it is long
    # but contains no JD. It must be recognized so it never becomes a resume.
    shell = ("Machine Learning Engineer in Seattle, WA Expand search This button "
             "displays the currently selected search type. Jobs People Learning "
             "Sign in Join now " * 20)
    assert jd_fetch._looks_like_login_wall(shell)


def test_real_jd_not_flagged_as_login_wall():
    # A genuine JD that happens to mention "sign in" once must NOT be flagged (needs 2+
    # distinct login-shell markers).
    jd = ("We are hiring a backend engineer to build authentication and sign in flows "
          "for our platform, working with Python, PostgreSQL, and distributed systems. " * 10)
    assert not jd_fetch._looks_like_login_wall(jd)


def test_linkedin_dedupe_near_duplicates_same_company():
    jobs = [
        {"company": "Acme", "role": "Backend Engineer", "jd_text": "We build scalable APIs " * 20},
        {"company": "Acme", "role": "Backend Developer", "jd_text": "We build scalable APIs " * 20},
        {"company": "Other Co", "role": "Backend Engineer", "jd_text": "We build scalable APIs " * 20},
    ]
    out = linkedin._dedupe_near_duplicates(jobs)
    assert len(out) == 2   # the Acme duplicate collapses; Other Co (different company) survives
    assert [j["company"] for j in out] == ["Acme", "Other Co"]


def test_linkedin_dedupe_keeps_distinct_same_company_roles():
    jobs = [
        {"company": "Acme", "role": "Backend Engineer", "jd_text": "distributed systems and kafka pipelines"},
        {"company": "Acme", "role": "Frontend Engineer", "jd_text": "react typescript accessibility design systems"},
    ]
    out = linkedin._dedupe_near_duplicates(jobs)
    assert len(out) == 2   # low word-overlap -> genuinely different roles, both kept


def test_linkedin_dedupe_survives_missing_jd_text():
    # A same-company card with no captured JD must not poison later comparisons
    # (regression: empty word-set in the bucket caused ZeroDivisionError).
    jobs = [
        {"company": "Acme", "role": "Backend Engineer", "jd_text": ""},
        {"company": "Acme", "role": "Platform Engineer", "jd_text": "kubernetes go microservices"},
    ]
    out = linkedin._dedupe_near_duplicates(jobs)
    assert len(out) == 2


# --- ATS scoring ---------------------------------------------------------------

def test_ats_score_basic():
    # kafka (data-pipeline) is in the JD but nowhere in the resume's concept space.
    r = ats.ats_score("python aws kafka streaming pipelines",
                      "python developer with aws experience")
    assert 0 <= r["score"] <= 100
    assert "python" in r["matched_keywords"]
    assert "data-pipeline" in r["missing_keywords"]


def test_ats_score_empty_jd():
    assert ats.ats_score("", "anything")["score"] == 0


def test_ontology_matches_synonyms_at_concept_level():
    # JD wording and resume wording share NO literal skill word, yet match via concepts:
    # "vector database" + "model serving" (JD) <-> "FAISS" + "SageMaker inference" (resume).
    jd = "experience with vector database and model serving for recommendations"
    resume = "built FAISS index and SageMaker inference endpoint for a recommender system"
    r = ats.ats_score(jd, resume)
    assert "vector-search" in r["matched_keywords"]
    assert "model-serving" in r["matched_keywords"]
    assert "recommendation" in r["matched_keywords"]


def test_ontology_no_restacking_or_false_positives():
    # concept tokens must not re-trigger sub-rules, and generic words stay literal
    assert ats._normalize("model serving infrastructure") == "model-serving infrastructure"
    assert "model-model" not in ats._normalize("machine learning model serving")
    assert ats._normalize("serving customers coffee") == "serving customers coffee"


def test_ats_scores_skill_coverage_not_word_overlap():
    # An ML resume covers an ML JD's skills even though the JD is full of company noise
    # the resume can't (and shouldn't) contain.
    jd = ("Build retrieval and ranking with FAISS vector search, RAG, PyTorch, and "
          "recommendation systems on AWS. Perks: free lunch, dog-friendly campus, "
          "quarterly offsites, generous parental leave, phishing awareness training.")
    resume = ("ML engineer: FAISS retrieval, XGBoost ranking, RAG, PyTorch, "
              "recommender systems, AWS SageMaker.")
    r = ats.ats_score(jd, resume)
    assert r["score"] >= 80                             # skills covered -> high
    assert "parental" not in " ".join(r["missing_keywords"])   # noise never a "gap"


def test_ats_discriminates_by_skill_fit():
    ml_resume = "ML engineer: FAISS retrieval, ranking, RAG, PyTorch, AWS, recommendation"
    ml_jd = "vector search retrieval ranking recommendation LLM PyTorch AWS model serving"
    rust_jd = "Rust systems programmer, embedded firmware, RTOS, drivers, PCB, CAN bus, soldering"
    assert ats.ats_score(ml_jd, ml_resume)["score"] > 70
    assert ats.ats_score(rust_jd, ml_resume)["score"] < 25   # wrong domain -> low


# --- finder freshness + ranking ------------------------------------------------

def test_is_fresh_within_window():
    assert finder.is_fresh("2026-06-05", 7, "2026-06-07") is True

def test_is_fresh_too_old():
    assert finder.is_fresh("2026-05-01", 7, "2026-06-07") is False

def test_is_fresh_unverified_excluded():
    assert finder.is_fresh("unverified", 7, "2026-06-07") is False
    assert finder.is_fresh(None, 7, "2026-06-07") is False

def test_is_fresh_caps_at_max_days():
    # request 30 days but MAX_DAYS=7 caps it
    assert finder.is_fresh("2026-05-20", 30, "2026-06-07") is False

def test_rank_recency_first():
    rows = [
        {"posted_date": "2026-06-01", "is_fresh": True, "match_score": 5},
        {"posted_date": "2026-06-06", "is_fresh": True, "match_score": 1},
        {"posted_date": "2025-10-31", "is_fresh": False, "match_score": 9},
    ]
    ranked = finder.rank(rows)
    assert ranked[0]["posted_date"] == "2026-06-06"   # freshest first
    assert ranked[-1]["is_fresh"] is False             # stale last


def test_finder_cache_roundtrip(tmp_data):
    finder.put_cache("q", "sde", "2026-06-07", [{"role": "x"}])
    assert finder.get_cached("q", "sde", "2026-06-07") == [{"role": "x"}]
    # different day -> miss
    assert finder.get_cached("q", "sde", "2026-06-08") is None


# --- portal classifier ---------------------------------------------------------

def test_portal_greenhouse():
    assert portals.classify("https://boards.greenhouse.io/acme/jobs/1")["strategy"] == "simple_form"

def test_portal_workday_needs_login():
    r = portals.classify("https://acme.wd1.myworkdayjobs.com/x")
    assert r["portal"] == "workday"
    assert r["needs_login"] is True

def test_portal_captcha_handoff():
    r = portals.classify("https://x.com/apply", page_text="please complete the reCAPTCHA")
    assert r["captcha"] is True
    assert r["strategy"] == "handoff_captcha"

def test_portal_prefilled_detection():
    r = portals.classify("https://x.com", snapshot="[e1] <input> name (current value: 'Jane')")
    assert r["prefilled"] is True


# --- feeds filtering -----------------------------------------------------------

def test_feeds_profile_for_drops_hardware():
    assert feeds._profile_for({"category": "Hardware", "title": "FPGA Engineer"}) is None

def test_feeds_profile_for_drops_nonenq_titles():
    assert feeds._profile_for({"category": "Software", "title": "Sales Technician"}) is None

def test_feeds_data_eng_split():
    assert feeds._profile_for({"category": "AI/ML/Data", "title": "Data Engineer"}) == "data_engineer"
    assert feeds._profile_for({"category": "AI/ML/Data", "title": "Machine Learning Engineer"}) == "ml_ai"

def test_feeds_software_is_sde():
    assert feeds._profile_for({"category": "Software", "title": "Software Engineer"}) == "sde"

def test_fresh_roles_filters_and_sorts():
    listings = [
        {"active": True, "is_visible": True, "date_posted": 1000, "category": "Software",
         "title": "Software Engineer", "company_name": "A", "url": "u1"},
        {"active": True, "is_visible": True, "date_posted": 2000, "category": "Software",
         "title": "Backend Developer", "company_name": "B", "url": "u2"},
        {"active": True, "is_visible": True, "date_posted": 1500, "category": "Hardware",
         "title": "FPGA Engineer", "company_name": "C", "url": "u3"},  # dropped
        {"active": False, "is_visible": True, "date_posted": 2000, "category": "Software",
         "title": "Software Engineer", "company_name": "D", "url": "u4"},  # inactive
    ]
    # window huge so all active+relevant pass; anchor at newest (2000)
    out = feeds.fresh_roles(listings, days=7, today_ts=2000 + 1)
    titles = [r["role"] for r in out]
    assert "FPGA Engineer" not in titles      # hardware dropped
    assert "D" not in [r["company"] for r in out]  # inactive dropped
    assert out[0]["company"] == "B"           # recency-first (ts 2000)


# --- LaTeX escaping + fill -----------------------------------------------------

def test_latex_escape_specials():
    out = latex.latex_escape("cost 40% & C_x #2 $x")
    assert r"\%" in out and r"\&" in out and r"\_" in out and r"\#" in out and r"\$" in out

def test_latex_escape_none():
    assert latex.latex_escape(None) == ""


# --- usage meter ---------------------------------------------------------------

def test_usage_meter_totals_and_cost():
    m = usage_mod.UsageMeter("claude-opus-4-8")
    m.add({"input_tokens": 1_000_000, "output_tokens": 0})
    assert m.total == 1_000_000
    assert m.cost_usd() == 5.0  # opus input rate

def test_usage_meter_budget_guard():
    m = usage_mod.UsageMeter("claude-sonnet-4-6", max_total_tokens=100)
    m.add({"input_tokens": 200, "output_tokens": 0})
    import pytest
    with pytest.raises(usage_mod.BudgetExceeded):
        m.check()

def test_usage_meter_no_ceiling_ok():
    m = usage_mod.UsageMeter("claude-haiku-4-5", max_total_tokens=0)
    m.add({"input_tokens": 9_999_999, "output_tokens": 0})
    m.check()  # 0 = unlimited, no raise


# --- final resume checker ------------------------------------------------------

def test_final_check_catches_placeholders_and_fragments():
    bad = ("# Your Name\nyour@email.com\n\n## Summary\nML engineer.\n\n"
           "## Experience\n### E\n- Built FAISS retrieval serving users.\n")
    r = final_check.check_resume(tailored_md=bad,
                                 focus_bullets=["Built FAISS retrieval serving users."])
    assert r["ok"] is False
    blob = " ".join(r["problems"]).lower()
    assert "placeholder" in blob and "fragment" in blob and "summary too short" in blob

def test_final_check_passes_clean_resume():
    good = (
        "# Jane Doe\njane@real.com\n\n"
        "## Summary\nMachine learning engineer building production retrieval, ranking, and "
        "evaluation systems serving millions of users, with first-author published research "
        "in model evaluation methodology and search relevance.\n\n"
        "## Experience\n### MLE  RealCo\n"
        "- Built an embedding retrieval and ranking pipeline serving one million users at "
        "sub-second latency, lifting click-through sixteen percent through online evaluation.\n"
        "- Designed an automated evaluation harness over fifty thousand daily conversations, "
        "raising defect discovery sixty percent across production model launches.\n"
    )
    r = final_check.check_resume(tailored_md=good, focus_bullets=[
        "Built an embedding retrieval and ranking pipeline serving one million users at "
        "sub-second latency, lifting click-through sixteen percent through online evaluation.",
        "Designed an automated evaluation harness over fifty thousand daily conversations, "
        "raising defect discovery sixty percent across production model launches.",
    ])
    assert r["ok"] is True, r["problems"]

def test_final_check_flags_near_duplicate_bullets():
    dup = (
        "# X\nx@y.com\n\n## Experience\n### E\n"
        "- Designed a multi-turn LLM evaluation framework over fifty thousand conversations daily raising defect discovery sixty percent.\n"
        "- Designed a multi turn LLM evaluation framework over fifty thousand conversations per day increasing defect discovery sixty percent.\n"
    )
    r = final_check.check_resume(tailored_md=dup)
    assert any("duplicate" in p.lower() for p in r["problems"])

def test_final_check_skips_commented_latex_items():
    # commented \resumeItem must NOT count as a duplicate
    tex = (r"\newcommand{\resumeItem}[1]{\item #1}" "\n" r"\begin{document}" "\n"
           r"\resumeItem{Built a real and active bullet about distributed systems work here.}" "\n"
           r"% \resumeItem{Built a real and active bullet about distributed systems work here.}" "\n"
           r"\end{document}")
    r = final_check.check_resume(tailored_md=tex)
    assert not any("duplicate" in p.lower() for p in r["problems"])

def test_edit_tex_replaces_bullets_and_summary_only():
    tex = (
        r"\newcommand{\resumeItem}[1]{\item #1}" "\n"
        r"\begin{document}" "\n"
        r"\section{Summary}" "\n"
        r"\small{old summary}" "\n"
        r"\section{Work Experience}" "\n"
        r"\resumeItem{old bullet one}" "\n"
        r"\resumeItem{old bullet two}" "\n"
        r"% \resumeItem{commented out}" "\n"
        r"\resumeItem{old bullet three}" "\n"
        r"\end{document}" "\n"
    )
    out = latex.edit_tex(tex, {"summary": "NEW SUMMARY",
                               "top_bullets": ["NEW ONE", "NEW TWO"]})
    # macro definition in preamble untouched
    assert r"\newcommand{\resumeItem}[1]{\item #1}" in out
    # summary replaced, old gone
    assert "NEW SUMMARY" in out and "old summary" not in out
    # first two ACTIVE bullets replaced; commented one + third untouched
    assert "NEW ONE" in out and "NEW TWO" in out
    assert "old bullet one" not in out and "old bullet two" not in out
    assert "old bullet three" in out          # only first 2 replaced
    assert "commented out" in out             # comment line skipped

def test_edit_tex_auto_removes_near_duplicate():
    # An existing bullet near-duplicates a freshly tailored top bullet -> auto-commented.
    tex = (
        r"\newcommand{\resumeItem}[1]{\item #1}" "\n" r"\begin{document}" "\n"
        r"\resumeItem{old placeholder bullet one to be replaced by tailoring step here now}" "\n"
        r"\resumeItem{second old bullet that will also be replaced by the tailoring step}" "\n"
        r"\resumeItem{Designed a multi turn LLM evaluation framework over fifty thousand conversations daily raising defect discovery sixty percent}" "\n"
        r"\end{document}"
    )
    patch = {"top_bullets": [
        "Built an embedding retrieval and ranking pipeline serving one million users at sub second latency lifting click through sixteen percent",
        "Designed a multi-turn LLM-as-judge evaluation framework over fifty thousand conversations per day increasing defect discovery sixty percent",
    ]}
    out = latex.edit_tex(tex, patch)
    # the pre-existing near-duplicate eval bullet should now be commented out
    active = [l for l in out.split("\n")
              if "\\resumeItem" in l and not l.strip().startswith("%")]
    eval_bullets = [l for l in active if "evaluation framework" in l]
    assert len(eval_bullets) == 1  # only the tailored one remains active


def test_edit_tex_escapes_bullet_specials():
    tex = (r"\begin{document}" "\n" r"\resumeItem{x}" "\n" r"\end{document}")
    out = latex.edit_tex(tex, {"top_bullets": ["cut cost 40% & more"]})
    assert r"40\%" in out and r"\&" in out
