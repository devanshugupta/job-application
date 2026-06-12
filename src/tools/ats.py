"""ATS keyword scoring — fully dynamic, no hardcoded skill list.

Real Applicant Tracking Systems rank resumes partly on keyword overlap with the job
description. We approximate that, domain-agnostically: extract the JD's own meaningful
terms (drop generic stopwords / boilerplate), take the most prominent ones, and measure
how many appear in the master resume. Nothing is hardcoded to software — the same logic
works for a biotech, finance, or design JD because importance is derived from the JD text.

`score` = percentage of the evaluated JD keywords the resume contains. The evaluated set
is ALL the JD's meaningful keywords by default (count varies by JD — a short JD yields
~12, a long one 40+); pass `top_n` only if you want an optional cap. "100" is the
percentage scale, never a word count.
"""

from __future__ import annotations

import re
from collections import Counter

# Generic, domain-neutral stopwords + hiring/JD boilerplate that carries no matching
# signal. This is the ONLY word list, and it's anti-signal (words to ignore), not a
# domain skill list — so the matcher stays general across any field.
_STOPWORDS = {
    # function words
    "the", "and", "for", "with", "you", "your", "our", "are", "will", "have", "has",
    "this", "that", "from", "they", "their", "them", "out", "who", "via", "per",
    "to", "of", "in", "on", "or", "as", "is", "be", "we", "at", "by", "it", "an", "a",
    "into", "across", "within", "while", "than", "then", "but", "not", "all", "any",
    "can", "may", "should", "would", "could", "must", "such", "also", "more", "most",
    "using", "use", "used", "able", "well", "both", "each", "other", "over", "under",
    # hiring / JD boilerplate
    "experience", "experienced", "years", "year", "strong", "including", "etc", "role",
    "job", "team", "teams", "work", "working", "ability", "skills", "knowledge",
    "responsibilities", "qualifications", "requirements", "preferred", "required",
    "candidate", "candidates", "looking", "join", "help", "build", "building", "develop",
    "developing", "support", "supporting", "ensure", "drive", "deliver", "company",
    "opportunity", "passionate", "excellent", "good", "great", "plus", "nice", "must-have",
    "us", "we're", "you'll", "you're", "new", "across", "high", "highly", "world",
    "best", "across", "deep", "real", "make", "making", "impact", "scale", "scalable",
}

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]{1,}")


def _keywords(text: str) -> Counter:
    """Tokenize to meaningful lowercased terms (len>2, not a stopword)."""
    tokens = [t.lower().strip(".-") for t in _TOKEN.findall(text)]
    return Counter(t for t in tokens if len(t) > 2 and t not in _STOPWORDS)


def ats_score(job_description: str, resume_text: str, top_n: int | None = None) -> dict:
    """Match the JD's important keywords against the resume. Domain-agnostic.

    Args:
        job_description: raw JD text.
        resume_text: the master resume text (Markdown or stripped LaTeX).
        top_n: OPTIONAL cap on how many of the JD's top keywords to evaluate. Default
            None = evaluate ALL distinct meaningful JD keywords (count varies by JD).
    """
    jd = _keywords(job_description)
    resume = set(_keywords(resume_text))
    # The JD's own meaningful non-stopword terms ARE the important keywords. Size varies
    # by JD; only clip if the caller passed an explicit cap.
    ranked = [w for w, _ in jd.most_common()]
    important = ranked[:top_n] if top_n else ranked
    matched = [w for w in important if w in resume]
    missing = [w for w in important if w not in resume]
    score = round(100 * len(matched) / len(important)) if important else 0
    return {
        "score": score,  # 0-100 = % of the evaluated JD keywords matched
        "evaluated_count": len(important),
        "matched_keywords": matched,
        "missing_keywords": missing,
        "advice": (
            "Strong keyword match."
            if score >= 75
            else "Consider naturally incorporating the missing keywords IF they are "
            "truthful for your background — never fabricate."
        ),
    }
