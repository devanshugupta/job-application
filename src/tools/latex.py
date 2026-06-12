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

MASTERS_DIR = pathlib.Path("resume/masters")

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
    """True if a pdflatex binary is reachable (BasicTeX adds /Library/TeX/texbin)."""
    return _pdflatex_bin() is not None


def _pdflatex_bin() -> str | None:
    found = shutil.which("pdflatex")
    if found:
        return found
    # BasicTeX on macOS may not be on PATH in non-login shells.
    for cand in ("/Library/TeX/texbin/pdflatex", "/usr/local/texlive/2026basic/bin/universal-darwin/pdflatex"):
        if pathlib.Path(cand).exists():
            return cand
    return None


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


def edit_tex(tex_source: str, patch: dict) -> str:
    """Apply a tailoring patch to the LaTeX source, marker-free. Edits:
      - the Summary section body (patch['summary'])
      - the first two \\resumeItem bullets (patch['top_bullets'])
    Technical Skills is left intact by default (it's a structured block in this template;
    editing it safely would need template-specific handling). Returns edited LaTeX.
    """
    tex = tex_source
    if patch.get("summary"):
        tex = _replace_section_body(tex, "Summary", patch["summary"])
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
    """Compile LaTeX source to PDF with pdflatex. Returns (ok, message). Never raises.

    Writes the .tex next to out_pdf, runs pdflatex twice (refs/links), captures the log.
    """
    binp = _pdflatex_bin()
    if binp is None:
        return False, "pdflatex not installed"
    out_pdf = pathlib.Path(out_pdf)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    tex_file = out_pdf.with_suffix(".tex")
    tex_file.write_text(tex_source)
    try:
        for _ in range(2):
            proc = subprocess.run(
                [binp, "-interaction=nonstopmode", "-halt-on-error",
                 "-output-directory", str(out_pdf.parent), str(tex_file)],
                capture_output=True, text=True, timeout=120,
            )
    except (subprocess.TimeoutExpired, OSError) as e:
        return False, f"pdflatex failed to run: {e}"
    produced = out_pdf.parent / (tex_file.stem + ".pdf")
    if produced != out_pdf and produced.exists():
        produced.replace(out_pdf)
    # Clean pdflatex scratch so data/ doesn't accumulate .aux/.log/.out litter.
    for ext in (".aux", ".log", ".out"):
        scratch = out_pdf.with_suffix(ext)
        if scratch.exists():
            scratch.unlink()
    if out_pdf.exists():
        return True, "ok"
    tail = (proc.stderr or proc.stdout or "")[-800:]
    return False, f"pdflatex compile error:\n{tail}"
