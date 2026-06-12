"""Final resume checker — the last gate before a tailored resume is considered done.

Catches problems the agent should NEVER ship: leftover template placeholders, fragment
bullets, a thin summary, missing top-2 JD-aligned bullets, LaTeX that didn't compile (or
a 0-byte / single-page-truncated PDF), and obvious filler. Runs on the tailored output
(the edited `.tex`/markdown + the rendered PDF) and returns blocking `problems` plus
non-blocking `warnings`. The apply/run flow must treat a non-empty `problems` list as a
hard stop (fix or fall back) — so issues are caught here, not by the human.
"""

from __future__ import annotations

import pathlib
import re

from . import resume

# Template/placeholder tokens that must never survive into a real resume.
_PLACEHOLDERS = re.compile(
    r"\bYour Name\b|your@email\.com|\+1-555-000-0000|City, State|"
    r"linkedin\.com/in/you|github\.com/you|Company Inc\b|Startup LLC\b|"
    r"%%[A-Z]+%%|lorem ipsum",
    re.I,
)
_FILLER = re.compile(r"\b(responsible for|helped with|various|successfully|in order to)\b", re.I)


def _active_resume_items(raw: str) -> list[str]:
    r"""Return the text of ACTIVE ``\resumeItem{...}`` macros in the document body — skips
    the preamble (the ``\newcommand`` macro def) and commented-out lines, so the
    duplicate check only sees bullets that actually render."""
    m = re.search(r"\\begin\{document\}", raw)
    body = raw[m.end():] if m else raw
    out = []
    for line in body.split("\n"):
        s = line.strip()
        if s.startswith("%"):  # commented out — won't render
            continue
        for hit in re.findall(r"\\resumeItem\s*\{(.+?)\}", line):
            out.append(hit.strip())
    return out


def check_resume(*, tailored_md: str | None = None, pdf_path: str | None = None,
                 jd_text: str = "", focus_bullets: list[str] | None = None) -> dict:
    """Run all final checks. Returns {ok, problems[], warnings[], stats}.

    tailored_md: the tailored resume text (markdown or LaTeX-stripped) to inspect.
    pdf_path: the rendered PDF to sanity-check (size / non-empty).
    jd_text: the JD, for top-2-bullet alignment heuristics.
    focus_bullets: the two bullets the agent tailored (so we verify they exist & are full).
    """
    problems: list[str] = []
    warnings: list[str] = []
    raw = tailored_md or ""               # may be raw LaTeX or markdown
    is_latex = "\\resumeItem" in raw or "\\section{" in raw
    # Stripped, human-readable text for prose checks (placeholders, lint, filler).
    text = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", " ", raw) if is_latex else raw
    text = re.sub(r"[{}$&#~^]", " ", text) if is_latex else text

    # 1. Leftover template placeholders — hard fail (means tailoring used the example).
    leaks = sorted(set(m.group(0) for m in _PLACEHOLDERS.finditer(text)))
    if leaks:
        problems.append(f"Template placeholders left in resume: {leaks[:5]}")

    # 2. Reuse the lint budgets (bullet length, repeated verbs, filler, summary length).
    if text:
        lint = resume.lint(text, focus_bullets=focus_bullets)
        problems.extend(lint.get("issues", []))
        warnings.extend(lint.get("advisory", []))

    # 3. Filler words anywhere (belt-and-suspenders beyond lint's focus scoping).
    if _FILLER.search(text):
        warnings.append("Filler phrase present somewhere in the resume.")

    # 4. Top-2 tailored bullets must exist and be substantial.
    for i, b in enumerate(focus_bullets or [], 1):
        wc = len(b.split())
        if wc < 14:
            problems.append(f"Top bullet {i} is a fragment ({wc}w): '{b[:50]}...' — expand it.")

    # 5. JD-alignment heuristic: at least one of the JD's top terms should appear in the
    #    first two bullets (only a warning — the LLM scorer is the real judge).
    if jd_text and focus_bullets:
        from . import ats
        jd_terms = [w for w, _ in ats._keywords(jd_text).most_common(15)]
        top = " ".join(focus_bullets).lower()
        if not any(t in top for t in jd_terms):
            warnings.append("Top 2 bullets share no prominent JD term — check alignment.")

    # 6. Near-duplicate bullets — tailoring a top bullet can echo an existing one. Flag
    #    bullet pairs with high word-overlap so the agent removes/merges the weaker one.
    #    Extract from BOTH markdown ("- ") and raw-LaTeX ("\resumeItem{...}") forms; the
    #    raw form must be read before any LaTeX stripping (callers may pass either).
    bullets = [b.strip() for b in re.findall(r"^\s*-\s+(.+)$", raw, re.M)]
    bullets += _active_resume_items(raw)
    def _wset(s): return set(re.findall(r"[a-z0-9]+", s.lower()))
    for a_i in range(len(bullets)):
        for b_i in range(a_i + 1, len(bullets)):
            wa, wb = _wset(bullets[a_i]), _wset(bullets[b_i])
            if wa and wb:
                overlap = len(wa & wb) / min(len(wa), len(wb))
                if overlap >= 0.6:
                    problems.append(
                        f"Near-duplicate bullets ({int(overlap*100)}% overlap): "
                        f"'{bullets[a_i][:40]}...' vs '{bullets[b_i][:40]}...' — merge or cut one.")

    # 7. PDF sanity: exists, non-trivial size.
    if pdf_path:
        p = pathlib.Path(pdf_path)
        if not p.exists():
            problems.append(f"Rendered PDF missing at {pdf_path}.")
        elif p.stat().st_size < 5000:
            problems.append(f"Rendered PDF suspiciously small ({p.stat().st_size}B) — likely a broken compile.")

    return {
        "ok": not problems,
        "problems": problems,
        "warnings": warnings,
        "stats": {"chars": len(text), "bullets": text.count("\n- ") + text.count("\\resumeItem")},
    }
