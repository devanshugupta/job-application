"""ATS skill-match scoring  how well a resume's SKILLS cover a JD's skills.

Modern matchers (Jobscan, Eightfold, LinkedIn) score against a SKILLS TAXONOMY, not raw
word overlap  that's what makes the number track real fit. We do the same:

  1. a skill ontology (`config/skill_synonyms.json`) maps every surface form to a
     canonical concept, so "FAISS", "qdrant", "vector database" all read as
     `vector-search` and match a JD's "embeddings" or "ANN" (see `_ontology`),
  2. `_normalize` rewrites BOTH the JD and the resume into that concept space,
  3. `ats_score` takes the JD's recognized skill concepts (weighted by how much the JD
     emphasizes each) and scores what fraction the resume's concepts cover.

`score` = weighted % of the JD's SKILLS the resume has, 0-100. This is the fix for the
old "% of prominent words" approach, which penalized a resume for lacking a posting's
company jargon ("fulfillment home", "phishing coach") and so disagreed sharply with the
LLM reviewer. `missing_keywords` now lists real skill GAPS. A JD too skill-sparse for
the ontology (`_MIN_JD_CONCEPTS`) falls back to the old prominent-term coverage so
non-tech postings still get a number. The stopword list is anti-signal only  the
ontology is the skill vocabulary, extend it freely (a new alias needs no code change).
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
# domain skill list  so the matcher stays general across any field.
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
    # portal-scraped JDs  e.g. Apple's "employee stock", "submit resume", "learn about")
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
    # page chrome from scraped careers pages (nav / legal / cookie / EEO footers)  these
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
    concept token is never re-scanned  e.g. `model-serving` can't re-trigger the bare
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


@lru_cache(maxsize=1)
def _concept_names() -> frozenset[str]:
    """The ontology's canonical concept tokens (what surface forms rewrite to)."""
    _, forms = _ontology()
    return frozenset(forms.values())


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


@lru_cache(maxsize=8)
def _concept_set(resume_text: str) -> frozenset[str]:
    """The resume's skill concepts. Discovery scores every job against the SAME resume
    (the combined master), so without this the identical token+ontology pass is redone
    once per job  ~1/3 of jd_match's cost on a 100-job sweep. Cached on the resume text
    itself, so a different (e.g. tailored) resume simply gets its own entry."""
    return frozenset(_tokens(resume_text)) & _concept_names()


def _keywords(text: str) -> Counter:
    """Meaningful unigrams (kept for compatibility with older callers/tests)."""
    return Counter(_tokens(text))


def _weighted_terms(jd_text: str) -> Counter:
    """JD terms weighted by prominence: unigram weight = min(freq, 3); repeated
    two-word phrases (both words meaningful) weigh double their capped frequency."""
    weights = Counter()
    for t, c in Counter(_tokens(jd_text)).items():
        weights[t] = min(c, 3)
    # phrases: adjacent meaningful tokens within a punctuation-delimited segment
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
    discovery-ranking problem  score many JDs against the candidate  where per-pair
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


_MIN_JD_CONCEPTS = 4   # below this the JD is too skill-sparse for concept-mode to be stable


def rank_snippets(jd_text: str, snippets: list[str], k: int) -> list[str]:
    """Pick the `k` snippets (resume bullets) most relevant to the JD, most-relevant
    first, dropping near-duplicates. Deterministic, no LLM  used to select which
    bullets a NON-tailored experience block (or the projects section) renders per JD,
    so every block shows JD-relevant work instead of fixed defaults. Empty/absent JD
    → keep the first k in original order."""
    snippets = [s for s in snippets if s and s.strip()]
    if not snippets:
        return []
    if not (jd_text or "").strip():
        return snippets[:k]
    scored = sorted(snippets, key=lambda s: ats_score(jd_text, s)["score"], reverse=True)
    out: list[str] = []
    for s in scored:
        ws = set(re.findall(r"[a-z0-9]+", s.lower()))
        dup = any(ws and (len(ws & set(re.findall(r"[a-z0-9]+", o.lower())))
                          / min(len(ws), len(set(re.findall(r"[a-z0-9]+", o.lower())))) >= 0.6)
                  for o in out)
        if not dup:
            out.append(s)
        if len(out) >= k:
            break
    return out


def jd_match(job_description: str) -> dict:
    """THE single JD↔candidate match: score the JD against the ONE combined master
    (all of the candidate's ML+SDE+DE points). Every scorer  discovery, JD-rerank, the
    tracker rescore  calls this so the same logic runs once, not three copies. Returns
    the usual ats_score dict; `missing_keywords` are the real skill gaps for this JD."""
    from . import profiles  # local import: avoid an import cycle at module load
    return ats_score(job_description, profiles.combined_master_text())


def ats_score(job_description: str, resume_text: str,
              top_n: int | None = DEFAULT_TOP_N) -> dict:
    """Score how well the resume's SKILLS cover the JD's skills. Domain-agnostic.

    A real recruiter (and the LLM reviewer) judges skill FIT, not how many of a posting's
    prominent words happen to appear on the resume  a resume can't contain a JD's
    company jargon ("fulfillment home", "phishing coach"), and penalizing that made the
    old prominent-word score disagree sharply with the LLM. So we score on the ontology's
    concept space: the JD's recognized SKILL concepts (weighted by how much the JD
    emphasizes each) vs the concepts on the resume. `missing_keywords` then lists real
    skill GAPS, not noise.

    Falls back to the prominent-term coverage when the JD names too few recognized skills
    (`_MIN_JD_CONCEPTS`) for concept-mode to be reliable  so niche/non-tech JDs still get
    a number.

    Args:
        job_description: raw JD text.
        resume_text: resume text (tailored Markdown or stripped LaTeX)  score the
            TAILORED resume when judging an application, the master when pre-filtering.
        top_n: cap on prominent terms in the FALLBACK path (concept-mode uses all skills).
    """
    weights = _weighted_terms(job_description)
    concepts = _concept_names()
    resume_concepts = _concept_set(resume_text)
    jd_concepts = {t: w for t, w in weights.items() if t in concepts}

    if len(jd_concepts) >= _MIN_JD_CONCEPTS:
        matched = [c for c in jd_concepts if c in resume_concepts]
        missing = [c for c in jd_concepts if c not in resume_concepts]
        total_w = sum(jd_concepts.values())
        match_w = sum(jd_concepts[c] for c in matched)
        score = round(100 * match_w / total_w) if total_w else 0
        # order by JD emphasis so the top gaps/matches lead
        matched.sort(key=lambda c: -jd_concepts[c])
        missing.sort(key=lambda c: -jd_concepts[c])
    else:
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
        "score": score,  # 0-100 = weighted % of the JD's skills the resume covers
        "evaluated_count": len(matched) + len(missing),
        "matched_keywords": matched,
        "missing_keywords": missing,   # real skill gaps for THIS JD, ranked by emphasis
        "advice": (
            "Strong skill match."
            if score >= 75
            else "Missing skills the JD emphasizes  surface them from your real "
            "experience if truthful; never fabricate."
        ),
    }
