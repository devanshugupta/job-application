"""ATS keyword scoring — fully dynamic, no hardcoded skill list.

Real Applicant Tracking Systems (and match tools like Jobscan) rank resumes on
coverage of the JD's PROMINENT keywords, not every word in the posting. We
approximate that, domain-agnostically:

  1. extract the JD's own meaningful terms (drop stopwords/boilerplate) plus its
     repeated two-word phrases ("machine learning", "distributed systems"),
  2. weight each by prominence (frequency, capped; phrases count double),
  3. evaluate the TOP-N weighted terms (default 30) against the resume, after
     normalizing common aliases (k8s≈kubernetes, postgres≈postgresql).

`score` = weighted % of the evaluated JD keywords the resume contains, 0-100.
Nothing is hardcoded to software — importance is derived from the JD text, so the
same logic works for a biotech or finance JD. The anti-signal stopword list below
is the ONLY word list.

Evaluated against a capped, weighted set, 95%+ is an achievable target for a
well-tailored resume on a genuinely matching role — which makes the number
actionable instead of noise. (Compared for this purpose against
itslovepatel/Resume-ATS — JD-independent fixed domain lists — and
interviewstreet/hiring-agent — employer-side LLM rubric for one fixed role;
neither measures JD↔resume match, so this JD-derived matcher is kept.)
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
    "what", "when", "where", "how", "there", "these", "those", "its", "it's", "if",
    # hiring / JD boilerplate
    "experience", "experienced", "years", "year", "strong", "including", "etc", "role",
    "job", "team", "teams", "work", "working", "ability", "skills", "knowledge",
    "responsibilities", "qualifications", "requirements", "preferred", "required",
    "candidate", "candidates", "looking", "join", "help", "build", "building", "develop",
    "developing", "support", "supporting", "ensure", "drive", "deliver", "company",
    "opportunity", "passionate", "excellent", "good", "great", "plus", "nice", "must-have",
    "us", "we're", "you'll", "you're", "new", "across", "high", "highly", "world",
    "best", "across", "deep", "real", "make", "making", "impact", "scale", "scalable",
    "benefits", "salary", "equity", "bonus", "employer", "employment", "applicants",
    "applicant", "status", "equal", "diverse", "diversity", "inclusion", "belonging",
    "mission", "culture", "location", "remote", "hybrid", "onsite", "office", "please",
    "apply", "application", "degree", "bachelor", "bachelor's", "master", "master's",
    "related", "field", "minimum", "qualification", "responsibility", "day", "days",
    "range", "compensation", "pay", "verification", "orientation", "gender", "race",
    "veteran", "disability", "religion", "national", "origin", "legally", "authorized",
    # weak prose words that ride along in bigrams
    "every", "single", "one", "two", "three", "want", "wants", "someone", "take",
    "takes", "put", "need", "needs", "get", "gets", "see", "really", "just", "only",
    "even", "way", "place", "part", "right", "thing", "things", "stuff", "like",
    "people", "everything", "own", "owned", "beyond", "means", "come", "comes",
    "don", "doesn", "isn", "aren", "didn", "won", "small", "full", "fast", "key",
    "many", "much", "very", "still", "here",
}

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]{1,}")

# Tiny alias map so the SAME skill spelled differently still matches. Deliberately
# minimal + unambiguous (deeper synonym judgment is the LLM scorer's job).
_ALIASES = {
    "k8s": "kubernetes",
    "postgres": "postgresql",
    "js": "javascript",
    "ts": "typescript",
    "golang": "go",
    "ci/cd": "cicd", "ci-cd": "cicd", "cicd": "cicd",
    "ml": "machine-learning", "machine-learning": "machine-learning",
    "nlp": "natural-language-processing",
}

DEFAULT_TOP_N = 30   # evaluate the JD's 30 most prominent terms (Jobscan-style)


def _normalize(text: str) -> str:
    t = text.lower()
    t = t.replace("ci/cd", "cicd")
    t = re.sub(r"\bmachine learning\b", "machine-learning", t)
    t = re.sub(r"\bnatural language processing\b", "natural-language-processing", t)
    return t


def _tokens(text: str) -> list[str]:
    out = []
    for t in _TOKEN.findall(_normalize(text)):
        t = t.strip(".-")
        t = _ALIASES.get(t, t)
        if len(t) > 2 and t not in _STOPWORDS:
            out.append(t)
    return out


def _keywords(text: str) -> Counter:
    """Meaningful unigrams (kept for compatibility with older callers/tests)."""
    return Counter(_tokens(text))


def _weighted_terms(jd_text: str) -> Counter:
    """JD terms weighted by prominence: unigram weight = min(freq, 3); repeated
    two-word phrases (both words meaningful) weigh double their capped frequency."""
    weights = Counter()
    for t, c in Counter(_tokens(jd_text)).items():
        weights[t] = min(c, 3)
    # phrases: adjacent meaningful tokens within a punctuation-delimited segment —
    # commas/periods break phrases so "detection, segmentation" never fuses, and
    # dropping a stopword can't glue two distant words together.
    phrase_counts = Counter()
    for segment in re.split(r"[,.;:()!?/\n]", _normalize(jd_text)):
        raw = [t.strip(".-") for t in _TOKEN.findall(segment)]
        for a, b in zip(raw, raw[1:]):
            a, b = _ALIASES.get(a, a), _ALIASES.get(b, b)
            if (len(a) > 2 and len(b) > 2
                    and a not in _STOPWORDS and b not in _STOPWORDS):
                phrase_counts[f"{a} {b}"] += 1
    for p, c in phrase_counts.items():
        if c >= 2:                       # a phrase the JD repeats is a real ask
            weights[p] = min(c, 3) * 2
    return weights


def ats_score(job_description: str, resume_text: str,
              top_n: int | None = DEFAULT_TOP_N) -> dict:
    """Match the JD's most prominent keywords against the resume. Domain-agnostic.

    Args:
        job_description: raw JD text.
        resume_text: resume text (tailored Markdown or stripped LaTeX) — score the
            TAILORED resume when judging an application, the master when pre-filtering.
        top_n: how many of the JD's top weighted terms to evaluate (default 30);
            pass None to evaluate every meaningful term (strict, mostly diagnostic).
    """
    weights = _weighted_terms(job_description)
    ranked = [w for w, _ in weights.most_common()]
    important = ranked[:top_n] if top_n else ranked
    resume_norm = _normalize(resume_text)
    resume_uni = set(_tokens(resume_text))

    def _hit(term: str) -> bool:
        return (term in resume_norm) if " " in term else (term in resume_uni)

    matched = [w for w in important if _hit(w)]
    missing = [w for w in important if not _hit(w)]
    total_w = sum(weights[w] for w in important)
    match_w = sum(weights[w] for w in matched)
    score = round(100 * match_w / total_w) if total_w else 0
    return {
        "score": score,  # 0-100 = weighted % of the evaluated JD keywords matched
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
