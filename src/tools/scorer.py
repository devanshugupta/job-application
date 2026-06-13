"""Resume scorer — a strict senior-reviewer agent.

This is a single Claude call that role-plays an experienced hiring manager / Sr. SDE
reviewing a tailored resume against a specific JD. It is NOT an ATS keyword counter —
it judges what a *human* reviewer cares about: do the bullets make sense, show real
impact, and read well in a 20-second skim? Keyword/ATS coverage is only one (smaller)
input.

It returns a structured verdict (via the Messages API structured-output format) so the
caller gets machine-readable fields — no prose parsing. A genuinely low score is allowed
but should be rare: reserved for a true role mismatch or fabricated content.

Rubric is grounded in widely-repeated hiring-manager advice:
- bullets show achievements/impact, not duties; quantify where possible
- resume is skimmable (~20s), 1-2 pages, no filler adjectives ("strong leader")
- tools named in context (in bullets), not just a keyword dump
- everything must be defensible in an interview (honesty)

Design intent: the GOAL is that tailoring is good enough on the FIRST pass that we
rarely iterate. When the score is low, fix the specific gaps once and re-score; do not
loop endlessly — instead feed recurring gaps back into resume/formatting_rules.md so
first-pass quality keeps rising.
"""

from __future__ import annotations

import os

# Judgment-heavy task → default to the most capable model. Override per call
# (resolved through the llm shim; JOB_AGENT_SCORER_MODEL kept for back-compat).
SCORER_MODEL = os.environ.get("JOB_AGENT_SCORER_MODEL", "claude-opus-4-8")

# Structured output schema the scorer must return.
SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_score": {"type": "integer"},  # 0-10
        "verdict": {
            "type": "string",
            "enum": ["strong", "borderline", "weak", "true_mismatch"],
        },
        "dimensions": {
            "type": "object",
            "properties": {
                "bullet_quality": {"type": "integer"},
                "jd_alignment": {"type": "integer"},
                "impact_metrics": {"type": "integer"},
                "readability": {"type": "integer"},
                "keyword_coverage": {"type": "integer"},
                "honesty_defensibility": {"type": "integer"},
            },
            "required": [
                "bullet_quality",
                "jd_alignment",
                "impact_metrics",
                "readability",
                "keyword_coverage",
                "honesty_defensibility",
            ],
            "additionalProperties": False,
        },
        # JD must-have analysis (replaces the old keyword-overlap ATS for scored roles).
        # The model extracts the role-DEFINING skills (not generic words), then checks the
        # resume for each — counting EXACT and SIMILAR/synonym matches (k8s=Kubernetes,
        # FAISS=vector search, RAG=retrieval-augmented, etc.).
        "must_haves": {"type": "array", "items": {"type": "string"}},
        "matched_must_haves": {"type": "array", "items": {"type": "string"}},
        "missing_must_haves": {"type": "array", "items": {"type": "string"}},
        "match_pct": {"type": "integer"},  # 0-100 = % of must_haves the resume satisfies
        "gaps": {"type": "array", "items": {"type": "string"}},
        "top_fixes": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
    "required": [
        "overall_score",
        "verdict",
        "dimensions",
        "must_haves",
        "matched_must_haves",
        "missing_must_haves",
        "match_pct",
        "gaps",
        "top_fixes",
        "summary",
    ],
    "additionalProperties": False,
}

_SCORER_SYSTEM = """You are a strict but fair SENIOR reviewer of engineering resumes — \
the combined eye of an experienced hiring manager, an HR screener, and a Sr. SDE on the \
interview loop. You are reviewing one tailored resume against one specific job \
description.

You are NOT an ATS keyword counter. Judge what a HUMAN reviewer cares about, weighted:
- bullet_quality (HIGHEST weight): does each bullet describe real, sensible, impactful \
work that a Sr. SDE would respect? Achievements, not duties. Lead with impact.
- jd_alignment: do the top-2 bullets and the skills line hit what THIS role actually \
demands (the real technical asks, not the JD's marketing fluff)?
- impact_metrics: are results quantified where reasonable (%, scale, latency, $)?
- readability: passes a ~20-second skim; 1-2 pages; no filler adjectives ("strong \
leader", "team player"); varied strong verbs; one-line bullets.
- keyword_coverage (SMALLER weight): are the role's real tools/skills present, named in \
context within bullets — not a meaningless keyword dump?
- honesty_defensibility: is every claim something the candidate could defend in an \
interview? Penalize anything that reads as fabricated or implausibly inflated.

Scoring discipline (overall_score is OUT OF 10, integer):
- Most genuinely-tailored resumes for a reasonable-fit role should land 7-9.
- Reserve <5 and verdict "true_mismatch" for a REAL mismatch (candidate clearly lacks \
the core of the role) or fabricated content. These should be RARE.
- "weak" (5-6) means fixable gaps; "borderline" 7; "strong" 8+.
- Per-dimension scores are ALSO out of 10.
- Always return concrete, specific gaps and AT MOST 3 top_fixes that would most raise \
the score. Fixes must be actionable and must NOT suggest fabricating anything.

JD MUST-HAVE MATCH (this replaces dumb keyword counting — be domain-agnostic):
- must_haves: extract the 6-12 ROLE-DEFINING requirements from THIS JD — the specific \
skills/tools/experience that distinguish this role. EXCLUDE generic words any engineer \
has ("services", "data", "systems", "production", "design", "team"). Work for ANY field \
(software, ML, data, biotech, finance) — derive them from the JD, don't assume software.
- matched_must_haves / missing_must_haves: for each must-have, decide if the resume \
satisfies it, counting EXACT and SIMILAR/synonym evidence (e.g. k8s≈Kubernetes, \
FAISS≈vector search, RAG≈retrieval-augmented generation, LLM≈large language model, \
PyTorch implies deep learning). Use your understanding of equivalence — don't require \
the literal string.
- match_pct = round(100 * matched / total must_haves). This should DISCRIMINATE: an ML \
resume against an ML JD scores high; the SAME resume against an SDE JD scores LOW because \
the role-defining must-haves (Java, microservices, system design, on-call) are missing — \
generic overlap must NOT inflate it.

Return ONLY the structured object."""


def score_resume(
    jd_text: str,
    resume_md: str,
    *,
    model: str | None = None,
) -> dict:
    """Score a tailored resume against a JD. Returns the validated verdict dict.

    Routed via the LLM shim — the scorer runs on whichever provider JOB_AGENT_SCORE_PROVIDER
    (or JOB_AGENT_PROVIDER) selects, so it can use OpenAI even when tailoring uses Claude.
    """
    from . import llm
    provider = llm.provider_for("score")
    model = model or llm.model_for(provider)
    user = (
        "JOB DESCRIPTION:\n" + jd_text.strip() + "\n\n"
        "TAILORED RESUME (Markdown):\n" + resume_md.strip()
    )
    parsed, _usage = llm.structured(
        provider=provider, model=model, system=_SCORER_SYSTEM, user=user,
        schema=SCORE_SCHEMA, max_tokens=2000)
    return parsed
