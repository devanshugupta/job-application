r"""LaTeX resume rendering via pdfLaTeX (marker-free, code-side editing).

The candidate's real LaTeX template (e.g. `resume/masters/ml_sde.tex`, a Jake's-Resume
style doc) is rendered with **pdflatex**  it uses pdfTeX-only features (`\pdfgentounicode`
for ATS-parseable output, `fontawesome5`, `helvet`) that the lighter tectonic engine can't
build, so we use a real pdfLaTeX install (BasicTeX/TeX Live).

Tailoring is **marker-free and code-side**: the AGENT only produces the small content
patch (summary / skills / two bullets)  the same JSON it already makes. Python regex
locates the `\section{Summary}` body, the Technical Skills block, and the first two
`\resumeItem{...}` under the first job, and swaps their inner text (LaTeX-escaped). The
agent never reads or writes raw LaTeX, so token cost stays tiny and it can't emit invalid
LaTeX. A compile-check lets callers fall back to Markdown if an edit doesn't build.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

from .. import config

MASTERS_DIR = config.MASTERS_DIR

_LATEX_ESCAPES = [
    ("\\", r"\textbackslash{}"),
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("~", r"\textasciitilde{}"),
    ("^", r"\textasciicircum{}"),
]


def latex_escape(text: str) -> str:
    """Escape LaTeX special characters in a plain-text patch value."""
    if not text:
        return ""
    out = text
    for ch, rep in _LATEX_ESCAPES:
        out = out.replace(ch, rep)
    return out


def have_pdflatex() -> bool:
    """True if ANY supported LaTeX engine is reachable.

    Named have_pdflatex for back-compat; it really means "can we compile LaTeX".
    Prefers tectonic (self-contained, installs without sudo via `brew install
    tectonic`, auto-downloads packages, persists on PATH) over a system pdflatex.
    """
    return _latex_engine() is not None


def _latex_engine() -> tuple[str, str] | None:
    """Return (engine, binary_path) for the best available LaTeX toolchain, or None.

    engine ∈ {'tectonic', 'pdflatex'}  the compile step adapts the source per engine
    (tectonic is XeTeX-based and rejects pdfTeX-only primitives; see _adapt_for_engine).
    """
    tec = shutil.which("tectonic") or next(
        (c for c in ("/opt/homebrew/bin/tectonic", "/usr/local/bin/tectonic")
         if pathlib.Path(c).exists()), None)
    if tec:
        return ("tectonic", tec)
    pdf = shutil.which("pdflatex") or next(
        (c for c in ("/Library/TeX/texbin/pdflatex",
                     "/usr/local/texlive/2026basic/bin/universal-darwin/pdflatex")
         if pathlib.Path(c).exists()), None)
    if pdf:
        return ("pdflatex", pdf)
    return None


def _adapt_for_engine(tex: str, engine: str) -> str:
    r"""Make the source compile under the chosen engine.

    tectonic uses the XeTeX engine, which does NOT have the pdfTeX primitives the
    Jake's-Resume template carries for ATS-parseable output (`\pdfgentounicode=1`,
    `\input{glyphtounicode}`). They are a no-op safety feature, so we comment them
    out for tectonic; pdflatex keeps them.
    """
    if engine != "tectonic":
        return tex
    tex = re.sub(r"(?m)^\s*\\input\{glyphtounicode\}.*$", "% (stripped for tectonic)", tex)
    tex = re.sub(r"(?m)^\s*\\pdfgentounicode\s*=\s*1.*$", "% (stripped for tectonic)", tex)
    # fontawesome5 makes tectonic SIGABRT on this platform; the template only loads it,
    # it uses no \fa* icons, so dropping the package is safe and changes nothing visible.
    tex = re.sub(r"(?m)^\s*\\usepackage(\[[^\]]*\])?\{fontawesome5\}.*$",
                 "% (fontawesome5 stripped for tectonic)", tex)
    return tex


def tex_master_path(profile: str | None) -> pathlib.Path | None:
    """Return the .tex master for a profile if it exists, else None.

    Tries `<profile>.tex`, then falls back to `ml_sde.tex` (the user's single real resume).
    """
    if profile:
        p = MASTERS_DIR / f"{profile}.tex"
        if p.exists():
            return p
    main = MASTERS_DIR / "ml_sde.tex"
    return main if main.exists() else None


# --- LaTeX -> plain text (read the REAL resume as the master) -----------------

_UNESCAPE = [(r"\&", "&"), (r"\%", "%"), (r"\$", "$"), (r"\#", "#"), (r"\_", "_"),
             (r"\{", "{"), (r"\}", "}"), ("~", " ")]


def tex_to_text(tex: str) -> str:
    r"""Convert a resume ``.tex`` into readable plain text for the LLM.

    Why: the ``.tex`` is the candidate's real, maintained resume; the ``.md``
    masters drift. This gives the model the true content at ~1/4 the tokens of
    raw LaTeX, structured as headings + bullets it already understands.
    Handles the Jake's-Resume macro family (resumeSubheading/resumeItem) plus
    generic fallbacks; unknown macros are stripped, their braced args kept.
    """
    body_m = re.search(r"\\begin\{document\}(.*?)(\\end\{document\}|\Z)", tex, re.S)
    body = body_m.group(1) if body_m else tex
    # Drop comment lines (but keep escaped \%)
    body = "\n".join(l for l in body.split("\n") if not l.lstrip().startswith("%"))
    body = re.sub(r"(?<!\\)%.*", "", body)

    body = re.sub(r"\\section\*?\{([^}]*)\}", r"\n## \1\n", body)
    # 2-arg variant (\resumeSubheadingg{Company | Title}{dates}) MUST run before the
    # 4-arg form so "...Subheadingg" isn't half-consumed. Without this, work-experience
    # entries get no "### " heading and apply_patch can't locate the role to replace its
    # top bullets in the markdown the reviewer/scorer read.
    body = re.sub(r"\\resumeSubheadingg\s*\{(.*?)\}\s*\{([^}]*)\}",
                  r"\n### \1 (\2)\n", body, flags=re.S)
    body = re.sub(
        r"\\resumeSubheading\s*\{([^}]*)\}\s*\{([^}]*)\}\s*\{([^}]*)\}\s*\{([^}]*)\}",
        r"\n### \1  \3\n\2 · \4", body)
    body = re.sub(r"\\resumeProjectHeading\s*\{(.*?)\}\s*\{([^}]*)\}",
                  r"\n### \1 (\2)", body, flags=re.S)
    body = re.sub(r"\\resumeItem\s*\{", r"\n- \\relax{", body)  # mark bullets
    body = re.sub(r"\\textbf\s*\{([^}]*)\}", r"\1", body)
    body = re.sub(r"\\textit\s*\{([^}]*)\}", r"\1", body)
    body = re.sub(r"\\emph\s*\{([^}]*)\}", r"\1", body)
    body = re.sub(r"\\href\s*\{[^}]*\}\s*\{([^}]*)\}", r"\1", body)
    body = re.sub(r"\\(small|item|relax|hfill)\b", " ", body)
    body = re.sub(r"\\(vspace|hspace)\*?\{[^}]*\}", " ", body)
    body = re.sub(r"\\begin\{[^}]*\}(\[[^\]]*\])?", " ", body)
    body = re.sub(r"\\end\{[^}]*\}", " ", body)
    body = re.sub(r"\\\\", "\n", body)
    body = re.sub(r"\\[a-zA-Z]+\*?", " ", body)  # any leftover macro
    body = re.sub(r"(?<!\\)\$", "", body)  # math-mode delimiters (e.g. $|$); keeps \$ amounts
    for esc, ch in _UNESCAPE:
        body = body.replace(esc, ch)
    body = re.sub(r"[{}]", "", body)
    body = re.sub(r"[ \t]+", " ", body)
    body = re.sub(r" ?\n ?", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    # join bullet continuation lines (a \resumeItem broken across source lines)
    lines, out = body.split("\n"), []
    for ln in lines:
        if out and out[-1].startswith("- ") and ln and not ln.startswith(("-", "#")) \
                and not out[-1].rstrip().endswith((".", ":")):
            out[-1] = out[-1].rstrip() + " " + ln.strip()
        else:
            out.append(ln.rstrip())
    return "\n".join(l for l in out if l.strip()).strip()


# --- marker-free, structure-aware editing ------------------------------------

def _body_start(tex: str) -> int:
    """Index just after \\begin{document} (so we never touch the preamble/macros)."""
    m = re.search(r"\\begin\{document\}", tex)
    return m.end() if m else 0


def _on_comment_line(tex: str, idx: int) -> bool:
    """True if position idx sits on a line whose first non-space char is % (a comment)."""
    line_start = tex.rfind("\n", 0, idx) + 1
    return tex[line_start:idx].lstrip().startswith("%")


def _replace_first_resume_items(tex: str, bullets: list[str],
                                start: int | None = None, end: int | None = None) -> str:
    r"""Replace the inner text of the first len(bullets) ACTIVE ``\resumeItem{...}`` macros
    in the document body  or only within the [start, end) slice when given (used to
    target one experience block). Skips the preamble (so the ``\newcommand{\resumeItem}``
    definition is never touched) and skips commented-out lines. Matches balanced braces.
    Bullets beyond the items present in range are ignored."""
    if not bullets:
        return tex
    token = r"\resumeItem"
    lo = _body_start(tex) if start is None else start
    hi = len(tex) if end is None else end
    out = [tex[:lo]]
    i = lo
    replaced = 0
    while i < len(tex):
        if (i < hi and replaced < len(bullets) and tex.startswith(token, i)
                # must be exactly \resumeItem, not \resumeItemListStart etc.
                and (i + len(token) >= len(tex) or tex[i + len(token)] in " \t\n{")
                and not _on_comment_line(tex, i)):
            j = i + len(token)
            while j < len(tex) and tex[j] in " \t\n":
                j += 1
            if j < len(tex) and tex[j] == "{":
                depth, k = 0, j
                while k < len(tex):
                    if tex[k] == "{":
                        depth += 1
                    elif tex[k] == "}":
                        depth -= 1
                        if depth == 0:
                            break
                    k += 1
                out.append(tex[i:j + 1])
                out.append(latex_escape(bullets[replaced]))
                out.append("}")
                replaced += 1
                i = k + 1
                continue
        out.append(tex[i])
        i += 1
    return "".join(out)


def _experience_block_span(tex: str, role_idx: int) -> tuple[int, int] | None:
    r"""[start, end) span of the role_idx-th job (0 = most recent) inside the
    Experience \section  delimited by \resumeSubheading/\resumeSubheadingg macros.
    Scoped to the Experience section so Education's subheadings don't shift the index.
    None when the section or that many jobs can't be found (caller falls back)."""
    sec = re.search(r"\\section\{[^}]*Experience[^}]*\}", tex, re.IGNORECASE)
    if not sec:
        return None
    nxt = re.search(r"\\section\{", tex[sec.end():])
    sec_end = sec.end() + nxt.start() if nxt else len(tex)
    heads = [m for m in re.finditer(r"\\resumeSubheadingg?(?![A-Za-z])",
                                    tex[sec.end():sec_end])
             if not _on_comment_line(tex, sec.end() + m.start())]
    if role_idx >= len(heads):
        return None
    start = sec.end() + heads[role_idx].start()
    end = sec.end() + heads[role_idx + 1].start() if role_idx + 1 < len(heads) else sec_end
    return start, end


def _item_spans(block: str) -> list[tuple[int, int, str]]:
    r"""Each ACTIVE ``\resumeItem{...}`` in a block as (start, end, inner_text), where
    [start,end) covers the whole macro. Skips commented lines and the
    ``\resumeItemListStart/End`` macros (which contain ``\resumeItem`` as a substring).
    inner_text is left LaTeX-escaped (as it appears in source)."""
    token = r"\resumeItem"
    out: list[tuple[int, int, str]] = []
    i = 0
    while i < len(block):
        j = block.find(token, i)
        if j == -1:
            break
        after = block[j + len(token): j + len(token) + 1]
        if after not in (" ", "\t", "\n", "{") or _on_comment_line(block, j):
            i = j + len(token)
            continue
        k = j + len(token)
        while k < len(block) and block[k] in " \t\n":
            k += 1
        if k >= len(block) or block[k] != "{":
            i = j + len(token)
            continue
        depth, m = 0, k
        while m < len(block):
            if block[m] == "{":
                depth += 1
            elif block[m] == "}":
                depth -= 1
                if depth == 0:
                    break
            m += 1
        out.append((j, m + 1, block[k + 1:m]))
        i = m + 1
    return out


def _extract_items(block: str) -> list[str]:
    r"""Raw (still LaTeX-escaped) contents of the ACTIVE ``\resumeItem{...}`` macros."""
    return [txt for _, _, txt in _item_spans(block)]


def _set_block_items(block: str, raw_items: list[str]) -> str:
    r"""Render exactly ``raw_items`` (already LaTeX-escaped) as the block's bullets,
    replacing the contiguous run of existing ``\resumeItem`` macros in place. If the
    block has no items yet but has a ``\resumeItemListStart``, insert after it. Marker
    layout is preserved otherwise."""
    body = "\n      ".join(f"\\resumeItem{{{it}}}" for it in raw_items)
    spans = _item_spans(block)
    if spans:
        first_s, last_e = spans[0][0], spans[-1][1]
        return block[:first_s] + body + block[last_e:]
    s = block.find(r"\resumeItemListStart")
    if s != -1:
        s_end = s + len(r"\resumeItemListStart")
        return block[:s_end] + "\n      " + body + "\n    " + block[s_end:]
    return block


def _render_experience_selected(tex: str, chosen_idx: int, top_bullets: list[str],
                                jd_text: str, k: int) -> str:
    r"""Select-and-prune the Experience section so every block renders a 1-page-worth,
    JD-relevant subset of the full point pool now stored in the .tex:

      - the CHOSEN block renders exactly ``top_bullets`` (the LLM's per-JD selection);
      - every OTHER block renders its ``k`` most JD-relevant bullets (deterministic
        ats ranking), so a non-tailored block still shows work that fits the JD instead
        of fixed defaults.

    This is what lets the master hold ALL points without every resume ballooning."""
    from . import ats

    spans: list[tuple[int, int]] = []
    i = 0
    while True:
        sp = _experience_block_span(tex, i)
        if sp is None:
            break
        spans.append(sp)
        i += 1
    if not spans:  # no locatable blocks  best-effort old first-N replace + dedup
        tex = _replace_first_resume_items(tex, top_bullets)
        return _dedupe_resume_items(tex, keep=top_bullets) if top_bullets else tex

    result = tex[:spans[0][0]]
    for idx, (s, e) in enumerate(spans):
        block = tex[s:e]
        if idx == chosen_idx and top_bullets:
            raw = [latex_escape(b.strip()) for b in top_bullets]
        else:
            raw = ats.rank_snippets(jd_text or "", _extract_items(block), k)
        result += _set_block_items(block, raw)
    result += tex[spans[-1][1]:]
    return result


_UNESCAPE_PAIRS = (("\\%", "%"), ("\\&", "&"), ("\\$", "$"), ("\\#", "#"),
                   ("\\_", "_"), ("\\{", "{"), ("\\}", "}"))


def _latex_unescape(s: str) -> str:
    for a, b in _UNESCAPE_PAIRS:
        s = s.replace(a, b)
    return s


def _parse_projects(tex: str) -> list[dict]:
    r"""Parse the .tex Projects section into [{name, url, bullet}] (plain text,
    un-escaped) so they can be JD-ranked and re-emitted. The projects pool now lives in
    the .tex, so this is how the tailor selects projects per JD when the patch doesn't."""
    sec = re.search(r"\\section\{Projects\}", tex)
    if not sec:
        return []
    nxt = re.search(r"\\section\{", tex[sec.end():])
    body = tex[sec.end(): sec.end() + nxt.start()] if nxt else tex[sec.end():]
    projs: list[dict] = []
    heads = list(re.finditer(r"\\resumeProjectHeading", body))
    for hi, h in enumerate(heads):
        seg = body[h.start(): heads[hi + 1].start() if hi + 1 < len(heads) else len(body)]
        nm = re.search(r"\\textbf\{([^}]*)\}", seg)
        url = re.search(r"\\href\{([^}]*)\}", seg)
        bl = re.search(r"\\resumeItem\{(.+?)\}", seg, re.S)
        if nm and bl:
            projs.append({"name": _latex_unescape(nm.group(1).strip()),
                          "url": (url.group(1).strip() if url else ""),
                          "bullet": _latex_unescape(bl.group(1).strip())})
    return projs


def _select_projects_in_tex(tex: str, jd_text: str, k: int) -> str:
    r"""When the patch didn't re-select projects, keep the ``k`` most JD-relevant from the
    .tex pool (deterministic) so the section stays 1-page without dropping to fixed
    document order."""
    from . import ats

    pool = _parse_projects(tex)
    if len(pool) <= k:
        return tex
    ranked_bullets = ats.rank_snippets(jd_text or "",
                                       [f"{p['name']} {p['bullet']}" for p in pool], k)
    chosen = [pool[[f"{p['name']} {p['bullet']}" for p in pool].index(b)]
              for b in ranked_bullets]
    return _replace_projects_section(tex, chosen)


def _replace_projects_section(tex: str, projects: list[dict]) -> str:
    r"""Regenerate the whole ``\section{Projects}`` body from [{name, url, bullet}]
    (most relevant first) using the template's own macros, so the tailor can
    re-select which projects appear per JD. No-op if the section is missing."""
    sec = re.search(r"\\section\{Projects\}", tex)
    if not sec or not projects:
        return tex
    nxt = re.search(r"\\section\{", tex[sec.end():])
    end = sec.end() + nxt.start() if nxt else len(tex)
    blocks = []
    for i, p in enumerate(projects):
        name = latex_escape((p.get("name") or "").strip())
        url = (p.get("url") or "").strip()   # URL goes into \href raw, never escaped
        head = (f"\\textbf{{{name}}} $|$ \\href{{{url}}}{{[Code]}}" if url
                else f"\\textbf{{{name}}}")
        tail = "" if i == len(projects) - 1 else "        \\vspace{-8pt}\n\n"
        blocks.append(
            "    \\resumeProjectHeading\n"
            f"          {{{head}}}{{}}\n"
            "              \\vspace{-9pt}\n"
            "          \\resumeItemListStart\n"
            f"          \\resumeItem{{{latex_escape((p.get('bullet') or '').strip())}}}\n"
            "          \\resumeItemListEnd\n" + tail)
    body = ("\n    \\vspace{-7pt}\n    \\resumeSubHeadingListStart\n\n"
            + "".join(blocks) + "\n    \\resumeSubHeadingListEnd\n\n")
    return tex[:sec.end()] + body + tex[end:]


def _replace_section_body(tex: str, section: str, new_body: str) -> str:
    r"""Replace the prose body of ``\section{<section>}`` (up to the next ``\section``),
    leaving the heading intact. Handles the first ACTIVE (non-comment) content line,
    whether it's bare prose or wrapped in ``\small{...}``. Returns tex unchanged if the
    section isn't found."""
    if not new_body:
        return tex
    esc = latex_escape(new_body)
    pat = re.compile(r"(\\section\{" + re.escape(section) + r"\}[ \t]*\n)(.*?)(?=\\section\{|\Z)",
                     re.DOTALL | re.IGNORECASE)

    def repl(m):
        head, body = m.group(1), m.group(2)
        lines = body.split("\n")
        for idx, ln in enumerate(lines):
            s = ln.strip()
            if not s or s.startswith("%") or s.startswith("\\vspace"):
                continue  # skip blanks, comments, spacing macros
            sm = re.match(r"^(\s*\\small\s*\{)(.*)(\}\s*)$", ln)  # \small{ ... }
            if sm:
                lines[idx] = sm.group(1) + esc + sm.group(3)
            else:
                lines[idx] = (ln[:len(ln) - len(ln.lstrip())]) + esc  # keep indent
            return head + "\n".join(lines)
        return head + esc + "\n" + body  # no content line found; insert

    return pat.sub(repl, tex, count=1)


def _replace_skills_block(tex: str, skills: str) -> str:
    r"""Replace the Technical Skills body with the patch's skills line(s), brace-safely.

    Template shape: ``\section{Technical Skills} ... \small{\item{ <lines> }}``. We find
    the ``\item{`` after the section heading and balance-scan to ITS matching ``}`` (so
    we never miscount the trailing ``}}``  the bug that produced "Extra }"). The patch
    value may be grouped ("Languages: ... | ML: ..." or one group per line) or a flat
    list; grouped input becomes one ``\textbf{Group}{: ...}`` row, matching the template.
    No section / no ``\item{`` -> tex unchanged (safe no-op).
    """
    sec = re.search(r"\\section\{Technical Skills\}", tex, re.I)
    if not sec:
        return tex
    item = re.search(r"\\item\s*\{", tex[sec.end():])
    if not item:
        return tex
    open_brace = sec.end() + item.end() - 1  # index of the '{' after \item
    depth, k = 0, open_brace
    while k < len(tex):
        if tex[k] == "{":
            depth += 1
        elif tex[k] == "}":
            depth -= 1
            if depth == 0:
                break
        k += 1
    if depth != 0:
        return tex  # unbalanced source  don't touch it

    parts = [p.strip() for p in re.split(r"\n|(?<!\w)\|(?!\w)", skills) if p.strip()]
    rows = []
    for p in parts:
        gm = re.match(r"([A-Za-z][A-Za-z &/+.-]{1,28}):\s*(.+)", p)
        if gm:
            rows.append(f"    \\textbf{{{latex_escape(gm.group(1))}}}"
                        f"{{: {latex_escape(gm.group(2))}}}")
        else:
            rows.append(f"    {latex_escape(p)}")
    if not rows:
        return tex
    body = "\n" + " \\\\\n".join(rows) + "\n  "
    return tex[:open_brace + 1] + body + tex[k:]  # keep the closing '}' at k


def edit_tex(tex_source: str, patch: dict, jd_text: str = "") -> str:
    """Apply a tailoring patch to the LaTeX source, marker-free  select-and-prune.

    The .tex master holds the FULL point pool; this renders a 1-page subset:
      - Summary body (patch['summary']) and Technical Skills block
        (patch['technical_skills']).
      - Experience: the chosen block (patch['experience_section_index']) renders exactly
        patch['top_bullets']; every other block renders its k most JD-relevant bullets.
      - Projects: patch['projects'] if the tailor re-selected them, else the k most
        JD-relevant projects from the .tex pool.
    ``jd_text`` drives the deterministic relevance ranking of the non-chosen blocks and
    the projects. Returns edited LaTeX; a compile-check downstream guards bad edits.
    """
    k = config.int_setting("secondary_bullets", 3)
    k_proj = config.int_setting("max_projects", 3)
    tex = tex_source
    if patch.get("summary"):
        tex = _replace_section_body(tex, "Summary", patch["summary"])
    if patch.get("technical_skills"):
        tex = _replace_skills_block(tex, patch["technical_skills"])
    tex = _render_experience_selected(
        tex, int(patch.get("experience_section_index", 0) or 0),
        patch.get("top_bullets") or [], jd_text, k)
    if patch.get("projects"):
        tex = _replace_projects_section(tex, patch["projects"])
    else:
        tex = _select_projects_in_tex(tex, jd_text, k_proj)
    return tex


def _word_overlap(a: str, b: str) -> float:
    wa = set(re.findall(r"[a-z0-9]+", a.lower()))
    wb = set(re.findall(r"[a-z0-9]+", b.lower()))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def _dedupe_resume_items(tex: str, keep: list[str], threshold: float = 0.6) -> str:
    r"""Comment out any ACTIVE ``\resumeItem{...}`` in the body that is a near-duplicate
    (>= threshold word overlap) of one of the freshly-tailored `keep` bullets  except the
    first occurrence of each kept bullet itself. Commenting (not deleting) is reversible
    and keeps the source intact. Skips preamble + already-commented lines."""
    start = _body_start(tex)
    head, body = tex[:start], tex[start:]
    kept_seen = [False] * len(keep)
    out_lines = []
    for line in body.split("\n"):
        s = line.strip()
        m = re.search(r"\\resumeItem\s*\{(.+?)\}", line)
        if m and not s.startswith("%"):
            content = m.group(1)
            dup_idx = next((i for i, k in enumerate(keep)
                            if _word_overlap(content, k) >= threshold), None)
            if dup_idx is not None:
                if not kept_seen[dup_idx]:
                    kept_seen[dup_idx] = True          # first instance = the tailored one
                else:
                    out_lines.append("% " + line + "  % [auto-removed near-duplicate]")
                    continue
        out_lines.append(line)
    return head + "\n".join(out_lines)


# --- compilation -------------------------------------------------------------

def compile_pdf(tex_source: str, out_pdf: pathlib.Path) -> tuple[bool, str]:
    """Compile LaTeX source to PDF. Returns (ok, message). Never raises.

    Uses tectonic if available (preferred  self-contained, auto-fetches packages),
    else a system pdflatex. The source is adapted per engine (see _adapt_for_engine).
    """
    eng = _latex_engine()
    if eng is None:
        return False, "no LaTeX engine (install: `brew install tectonic`)"
    engine, binp = eng
    out_pdf = pathlib.Path(out_pdf)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    tex_file = out_pdf.with_suffix(".tex")
    tex_file.write_text(_adapt_for_engine(tex_source, engine))
    try:
        if engine == "tectonic":
            proc = subprocess.run(
                [binp, "-X", "compile", "--outdir", str(out_pdf.parent),
                 "--keep-logs", str(tex_file)],
                capture_output=True, text=True, timeout=180,
            )
        else:
            for _ in range(2):  # twice for refs/links
                proc = subprocess.run(
                    [binp, "-interaction=nonstopmode", "-halt-on-error",
                     "-output-directory", str(out_pdf.parent), str(tex_file)],
                    capture_output=True, text=True, timeout=120,
                )
    except (subprocess.TimeoutExpired, OSError) as e:
        return False, f"{engine} failed to run: {e}"
    produced = out_pdf.parent / (tex_file.stem + ".pdf")
    if produced != out_pdf and produced.exists():
        produced.replace(out_pdf)
    # Clean scratch so data/ doesn't accumulate .aux/.log/.out litter.
    for ext in (".aux", ".log", ".out"):
        scratch = out_pdf.with_suffix(ext)
        if scratch.exists():
            scratch.unlink()
    if out_pdf.exists():
        return True, f"ok ({engine})"
    tail = (proc.stderr or proc.stdout or "")[-1000:]
    return False, f"{engine} compile error:\n{tail}"
