r"""LaTeX resume rendering via pdfLaTeX (marker-free, code-side editing).

The candidate's real LaTeX template (e.g. `resume/masters/ml_sde.tex`, a Jake's-Resume
style doc) is rendered with **pdflatex** — it uses pdfTeX-only features (`\pdfgentounicode`
for ATS-parseable output, `fontawesome5`, `helvet`) that the lighter tectonic engine can't
build, so we use a real pdfLaTeX install (BasicTeX/TeX Live).

Tailoring is **marker-free and code-side**: the AGENT only produces the small content
patch (summary / skills / two bullets) — the same JSON it already makes. Python regex
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

    engine ∈ {'tectonic', 'pdflatex'} — the compile step adapts the source per engine
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
        r"\n### \1 — \3\n\2 · \4", body)
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


def _replace_first_resume_items(tex: str, bullets: list[str]) -> str:
    r"""Replace the inner text of the first len(bullets) ACTIVE ``\resumeItem{...}`` macros
    in the document body. Skips the preamble (so the ``\newcommand{\resumeItem}``
    definition is never touched) and skips commented-out lines. Matches balanced braces."""
    if not bullets:
        return tex
    token = r"\resumeItem"
    start = _body_start(tex)
    out = [tex[:start]]
    i = start
    replaced = 0
    while i < len(tex):
        if (replaced < len(bullets) and tex.startswith(token, i)
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
    we never miscount the trailing ``}}`` — the bug that produced "Extra }"). The patch
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
        return tex  # unbalanced source — don't touch it

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


def edit_tex(tex_source: str, patch: dict) -> str:
    """Apply a tailoring patch to the LaTeX source, marker-free. Edits:
      - the Summary section body (patch['summary'])
      - the Technical Skills block (patch['technical_skills'])
      - the first two \\resumeItem bullets (patch['top_bullets'])
    Returns edited LaTeX; a compile-check downstream guards against bad edits.
    """
    tex = tex_source
    if patch.get("summary"):
        tex = _replace_section_body(tex, "Summary", patch["summary"])
    if patch.get("technical_skills"):
        tex = _replace_skills_block(tex, patch["technical_skills"])
    bullets = patch.get("top_bullets") or []
    if bullets:
        tex = _replace_first_resume_items(tex, bullets[:2])
        # Tailoring a top bullet can echo a pre-existing bullet further down (e.g. two
        # "Designed an LLM evaluation framework..." lines). Deterministically drop the
        # later near-duplicate so the final resume has no repeated bullet — no LLM needed.
        tex = _dedupe_resume_items(tex, keep=bullets[:2])
    return tex


def _word_overlap(a: str, b: str) -> float:
    wa = set(re.findall(r"[a-z0-9]+", a.lower()))
    wb = set(re.findall(r"[a-z0-9]+", b.lower()))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def _dedupe_resume_items(tex: str, keep: list[str], threshold: float = 0.6) -> str:
    r"""Comment out any ACTIVE ``\resumeItem{...}`` in the body that is a near-duplicate
    (>= threshold word overlap) of one of the freshly-tailored `keep` bullets — except the
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

    Uses tectonic if available (preferred — self-contained, auto-fetches packages),
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
