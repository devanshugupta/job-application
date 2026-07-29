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

import json
import math
import re
from collections import Counter
from functools import lru_cache

from .. import config

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
    "about", "above", "below", "after", "before", "again", "once", "here", "off",
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
    # benefits / comp / application-chrome boilerplate (pollutes keyword extraction on
    # portal-scraped JDs — e.g. Apple's "employee stock", "submit resume", "learn about")
    "stock", "equity", "employee", "employees", "benefits", "benefit", "submit",
    "resume", "apply", "application", "applications", "program", "programs", "learn",
    "results", "result", "subject", "area", "relevant", "industry", "contribute",
    "devices", "device", "profile", "sign", "login", "careers", "career",
    "footer", "window", "opens", "wallet", "shop", "gift", "cards", "card",
    # weak prose words that ride along in bigrams
    "every", "single", "one", "two", "three", "want", "wants", "someone", "take",
    "takes", "put", "need", "needs", "get", "gets", "see", "really", "just", "only",
    "even", "way", "place", "part", "right", "thing", "things", "stuff", "like",
    "people", "everything", "own", "owned", "beyond", "means", "come", "comes",
    "don", "doesn", "isn", "aren", "didn", "won", "small", "full", "fast", "key",
    "many", "much", "very", "still", "here",
    # page chrome from scraped careers pages (nav / legal / cookie / EEO footers) — these
    # dominate the "prominent terms" of a whole-page scrape and crush the real match, so
    # they must be treated as anti-signal (see the JD-cleaning diagnostic).
    "cookie", "cookies", "privacy", "policy", "policies", "terms", "agreement", "consent",
    "linkedin", "login", "password", "continue", "clicking", "outline", "noogler", "hat",
    "press", "blog", "investor", "relations", "newsroom", "affirmative", "eeo",
    "discrimination", "harassment", "criminal", "histories", "conviction", "ordinance",
    "protected", "veterans", "reasonable", "accommodation", "accommodations",
    "background", "check", "chance", "genetic", "ancestry", "citizenship", "sexual",
    "manage", "cookie", "preferences", "settings", "notice", "copyright", "reserved",
    "rights", "learn", "more", "read", "click", "menu", "search", "share", "save",
    "posted", "ago", "today", "yesterday", "week", "weeks", "month", "months", "hour",
    "hours", "minute", "minutes", "date", "life", "follow", "outline", "open", "close",
    # location chrome (city/state fragments that ride in as bigrams on scraped pages)
    "san", "francisco", "jose", "mateo", "diego", "angeles", "county", "mountain",
    "view", "palo", "alto", "bay", "seattle", "york", "boston", "austin", "chicago",
    "atlanta", "denver", "remote", "hybrid", "onsite", "usa", "united", "states",
}

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]{1,}")

DEFAULT_TOP_N = 30   # evaluate the JD's 30 most prominent terms (Jobscan-style)


@lru_cache(maxsize=1)
def _ontology() -> tuple[re.Pattern | None, dict[str, str]]:
    """A single alternation regex + {surface form -> concept token} from the ontology.

    This is how JD wording matches resume wording at the CONCEPT level: a JD's "model
    serving" and a resume's "SageMaker inference endpoint" both rewrite to the token
    `model-serving`, so they match with no shared literal word. ONE regex (alternatives
    ordered longest-first) rewrites all forms in a single left-to-right pass, so a
    concept token is never re-scanned — e.g. `model-serving` can't re-trigger the bare
    `serving` rule. Missing/empty file -> (None, {}) = pure literal matching, unchanged."""
    path = config.CONFIG_DIR / "skill_synonyms.json"
    if not path.exists():
        return None, {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None, {}
    forms: dict[str, str] = {}
    for concept, surface in data.items():
        if concept.startswith("_") or not isinstance(surface, list):
            continue
        for form in surface:
            f = str(form).strip().lower()
            if f:
                forms.setdefault(f, concept.strip().lower())
    if not forms:
        return None, {}
    ordered = sorted(forms, key=len, reverse=True)   # longest match wins at each position
    pattern = re.compile(r"\b(" + "|".join(re.escape(f) for f in ordered) + r")\b")
    return pattern, forms


def _normalize(text: str) -> str:
    t = text.lower()
    t = t.replace("ci/cd", "cicd")
    # Rewrite every known skill surface form to its canonical concept token so all
    # downstream tokenizing, weighting, and matching happens in concept space.
    pattern, forms = _ontology()
    if pattern is not None:
        t = pattern.sub(lambda m: forms[m.group(1)], t)
    return t


def _tokens(text: str) -> list[str]:
    out = []
    for t in _TOKEN.findall(_normalize(text)):
        t = t.strip(".-")
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
            if (len(a) > 2 and len(b) > 2
                    and a not in _STOPWORDS and b not in _STOPWORDS):
                phrase_counts[f"{a} {b}"] += 1
    for p, c in phrase_counts.items():
        if c >= 2:                       # a phrase the JD repeats is a real ask
            weights[p] = min(c, 3) * 2
    return weights


def bm25_scores(resume_text: str, jd_corpus: list[str],
                k1: float = 1.5, b: float = 0.75) -> list[float]:
    r"""Rank a corpus of JDs by relevance to one resume using Okapi BM25.

    Per-pair keyword coverage (``ats_score``) weights every matched term the same, so
    a generic JD matching "engineer/python" can tie a genuine match sharing "faiss".
    BM25 fixes that: it needs a CORPUS, and its IDF term down-weights words common
    across the JDs and rewards rare, discriminating skills. That is exactly the
    discovery-ranking problem — score many JDs against the candidate — where per-pair
    coverage is weakest. (For a single resume↔JD pair the corpus is size 1 and IDF is
    degenerate, which is why we keep ``ats_score`` as the Jobscan-style per-resume %.)

    The resume is the query; each JD is a document. Returns one score per JD, aligned
    to ``jd_corpus`` order (higher = better fit). Empty corpus → [].
    """
    if not jd_corpus:
        return []
    docs = [_tokens(jd) for jd in jd_corpus]
    dfs: Counter = Counter()
    for toks in docs:
        dfs.update(set(toks))
    n = len(docs)
    avgdl = sum(len(d) for d in docs) / n or 1.0
    # IDF with the standard BM25 +0.5 smoothing (non-negative floor for stability).
    idf = {t: max(0.0, math.log((n - df + 0.5) / (df + 0.5) + 1.0))
           for t, df in dfs.items()}
    query = set(_tokens(resume_text))       # candidate's own terms drive relevance
    scores = []
    for toks in docs:
        tf = Counter(toks)
        dl = len(toks)
        s = 0.0
        for t in query:
            f = tf.get(t, 0)
            if not f:
                continue
            s += idf.get(t, 0.0) * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
        scores.append(round(s, 4))
    return scores


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
