"""Resume tooling — load, patch, lint, and render the resume.

## Format choices (the important part)

INPUT to the LLM: **Markdown** (`resume/master_resume.md`). Why not PDF?
- A PDF sent as a document block costs many more tokens and parses lossily.
- Markdown is essentially plain text — cheapest to read — and already close to the
  final layout (headings, bullets, sections), so the model reasons over real structure.
- JSON is possible but heavier (keys/braces) and less natural for prose bullets.

OUTPUT from the LLM: **a small JSON patch, not the whole resume.** Since most of the
resume is unchanged and only a few targeted tweaks are needed, the agent returns only
the optimizable pieces:
    {
      "summary": "<= 2 lines",
      "technical_skills": "<one tight line, grouped>",
      "top_bullets": ["bullet 1 (hits JD ask)", "bullet 2 (hits JD ask)"],
      "experience_section_index": 0   # which experience block the top_bullets belong to
    }
`apply_patch` merges this into the master Markdown — replacing the summary, the
technical-skills line, and the first two bullets of the chosen experience block. This
saves tokens in BOTH directions and structurally enforces "minimal tweaks."

RENDER: tailored Markdown -> HTML -> PDF via the Chromium that Playwright already
installs (no new heavy dependency like a LaTeX/word toolchain).
"""

from __future__ import annotations

import pathlib
import re

from .. import config
from . import artifacts, latex, profiles

MASTER_PATH = config.LEGACY_MASTER_PATH

# Section word/line budgets. Each section that can be overloaded gets a cap so we
# don't bury the signal. Tune these freely.
BUDGETS = {
    "summary_max_lines": 2,             # 2 rendered lines max, one adjective max
    "summary_min_words": 18,
    "summary_max_words": 40,
    "technical_skills_max_words": 35,   # don't dump every tool you've touched
    "bullet_min_words": 14,
    "bullet_max_words": 30,             # ~1.5 rendered lines in the PDF
}


def read_master(profile: str | None = None) -> str:
    """Read the master resume. If a profile is given (and profiles are configured),
    read that profile's master; otherwise the single legacy master."""
    if profile is not None or profiles.have_profiles():
        return profiles.read_master_for(profile)
    if not MASTER_PATH.exists():
        return (
            "No master resume found at resume/master_resume.md. Copy "
            "resume/master_resume.example.md to resume/master_resume.md and edit it."
        )
    return MASTER_PATH.read_text()


# --- section helpers ---------------------------------------------------------

def _split_sections(md: str) -> list[tuple[str, str]]:
    """Return [(heading_line, body)] split on level-2 '## ' headings.
    The first chunk (name/contact, no ## heading) is returned with heading ''."""
    parts = re.split(r"(?m)^(## .+)$", md)
    sections: list[tuple[str, str]] = []
    if parts and parts[0].strip():
        sections.append(("", parts[0]))
    for i in range(1, len(parts), 2):
        heading = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        sections.append((heading, body))
    return sections


def _rebuild(sections: list[tuple[str, str]]) -> str:
    out = []
    for heading, body in sections:
        if heading:
            out.append(heading)
        out.append(body)
    return "".join(out)


def apply_patch(patch: dict, profile: str | None = None,
                company: str | None = None, role: str | None = None,
                url: str | None = None) -> str:
    """Merge a tailoring patch into the master resume and write the tailored copy.

    Only touches the Summary, Technical Skills, and the top-two bullets of the chosen
    Experience block. ``profile`` selects which master resume to tailor from. When
    ``company`` and ``role`` are given, also writes a per-application artifact folder
    (data/applications/<slug>/ with tailored_resume.md + changes.json) so the dashboard
    can show exactly what changed and link the files. Returns the tailored Markdown.
    """
    md = read_master(profile)
    if md.startswith("No master resume"):
        return md
    sections = _split_sections(md)

    def find(name: str) -> int | None:
        # containment, not prefix: matches "## Experience" AND "## Work Experience"
        # (the .tex-derived master uses the latter)
        for idx, (heading, _) in enumerate(sections):
            if heading.startswith("## ") and name.lower() in heading.lower():
                return idx
        return None

    # Summary
    if patch.get("summary") is not None:
        i = find("summary")
        new_body = "\n" + patch["summary"].strip() + "\n\n"
        if i is not None:
            sections[i] = (sections[i][0], new_body)
        else:  # insert a Summary right after the contact block
            sections.insert(1, ("## Summary", new_body))

    # Technical Skills
    if patch.get("technical_skills") is not None:
        i = find("technical skills") or find("skills")
        if i is not None:
            sections[i] = (sections[i][0], "\n" + patch["technical_skills"].strip() + "\n\n")

    # Projects re-selection (from the resume + achievements projects pool)
    projects = patch.get("projects")
    if projects:
        i = find("projects")
        if i is not None:
            parts = []
            for p in projects:
                head = f"### {(p.get('name') or '').strip()}"
                if (p.get("url") or "").strip():
                    head += f" | [Code]({p['url'].strip()})"
                parts.append(head + "\n- " + (p.get("bullet") or "").strip())
            sections[i] = (sections[i][0], "\n" + "\n".join(parts) + "\n\n")

    # Top two bullets of a chosen experience block
    bullets = patch.get("top_bullets")
    if bullets:
        i = find("experience")
        if i is not None:
            body = sections[i][1]
            # Within the experience body, replace the FIRST two bullet lines that
            # follow the targeted role. We target the Nth role's bullets.
            role_idx = int(patch.get("experience_section_index", 0))
            sections[i] = (sections[i][0], _replace_top_bullets(body, bullets, role_idx))

    tailored = _rebuild(sections)
    out = config.TAILORED_MD_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(tailored)
    # Per-application folder (traceable record of what we sent where).
    if company and role:
        info = artifacts.save_artifacts(company, role, tailored_md=tailored,
                                        patch=patch, url=url)
        return f"{tailored}\n\n[artifacts saved to {info['dir']}]"
    return tailored


def _replace_top_bullets(experience_body: str, new_bullets: list[str], role_idx: int) -> str:
    """Replace the first two '- ' bullets under the role at role_idx (0-based,
    roles delimited by '### ')."""
    role_chunks = re.split(r"(?m)^(### .+)$", experience_body)
    # role_chunks: [pre, head0, body0, head1, body1, ...]
    rebuilt = [role_chunks[0]] if role_chunks and not role_chunks[0].startswith("### ") else []
    start = 1 if rebuilt else 0
    role_n = 0
    i = start
    while i < len(role_chunks):
        head = role_chunks[i]
        body = role_chunks[i + 1] if i + 1 < len(role_chunks) else ""
        if role_n == role_idx:
            lines = body.split("\n")
            replaced = 0
            for j, line in enumerate(lines):
                if line.strip().startswith("- ") and replaced < len(new_bullets):
                    lines[j] = "- " + new_bullets[replaced].strip()
                    replaced += 1
            body = "\n".join(lines)
        rebuilt.extend([head, body])
        role_n += 1
        i += 2
    return "".join(rebuilt)


# --- linting -----------------------------------------------------------------

def lint(markdown: str | None = None, focus_bullets: list[str] | None = None) -> dict:
    """Check the tailored resume against section budgets.

    Two tiers of findings:
    - ``issues``: blocking problems in sections the agent just tailored (Summary,
      Technical Skills, and the bullets in ``focus_bullets`` if given). These must be
      fixed before rendering.
    - ``advisory``: budget violations in untouched master-resume bullets the agent
      didn't rewrite. Surfaced for awareness; not a reason to block, since rewriting
      every old bullet is out of scope for a targeted tailoring pass.

    ``focus_bullets`` should be the ``top_bullets`` from the patch just applied.
    """
    md = markdown or (config.TAILORED_MD_PATH.read_text()
                      if config.TAILORED_MD_PATH.exists() else read_master())
    issues: list[str] = []
    advisory: list[str] = []
    focus = {b.strip() for b in (focus_bullets or [])}
    def body_of(name: str) -> str:
        for h, b in _split_sections(md):
            if h.lower().startswith(f"## {name}"):
                return b
        return ""

    # Summary
    summary = body_of("summary").strip()
    if summary:
        lines = [l for l in summary.splitlines() if l.strip()]
        if len(lines) > BUDGETS["summary_max_lines"]:
            issues.append(f"Summary is {len(lines)} lines (max {BUDGETS['summary_max_lines']}).")
        sw = len(summary.split())
        if sw > BUDGETS["summary_max_words"]:
            issues.append(f"Summary is {sw} words (max {BUDGETS['summary_max_words']}).")
        if sw < BUDGETS["summary_min_words"]:
            issues.append(f"Summary too short ({sw}w, min {BUDGETS['summary_min_words']}) "
                          "— write 2 full lines: role + domain + scale + a credential.")
        if "—" in summary or "–" in summary:
            issues.append("Em/en dash in summary (use commas).")

    # Technical skills
    skills = body_of("technical skills").strip() or body_of("skills").strip()
    if skills and len(skills.split()) > BUDGETS["technical_skills_max_words"]:
        issues.append(
            f"Technical Skills is {len(skills.split())} words (max "
            f"{BUDGETS['technical_skills_max_words']}); trim to the most relevant."
        )

    # Bullets: word count + repeated leading verb + filler words.
    # Route a finding to `issues` (blocking) if it's in a tailored bullet, else
    # `advisory`. When focus_bullets isn't provided, treat all bullets as blocking
    # (backwards-compatible). Repeated-verb check always blocks, since varying verbs
    # across the WHOLE set is a global readability property.
    bullets = re.findall(r"(?m)^- (.+)$", md)
    seen_verbs: dict[str, list[str]] = {}
    filler = re.compile(r"\b(responsible for|helped|various|successfully|in order to)\b", re.I)
    for b in bullets:
        bucket = issues if (not focus or b.strip() in focus) else advisory
        wc = len(b.split())
        if wc < BUDGETS["bullet_min_words"] or wc > BUDGETS["bullet_max_words"]:
            bucket.append(f"Bullet {wc}w (want {BUDGETS['bullet_min_words']}-{BUDGETS['bullet_max_words']}): {b[:50]}...")
        if filler.search(b):
            bucket.append(f"Filler word in bullet: {b[:50]}...")
        if "—" in b or "–" in b:
            bucket.append(f"Em/en dash in bullet (use commas): {b[:50]}...")
        verb = b.split()[0].lower() if b.split() else ""
        seen_verbs.setdefault(verb, []).append(b.strip())
    # A repeated leading verb blocks only if a TAILORED bullet is one of the repeats;
    # repeats entirely within untouched master bullets are advisory.
    for verb, owners in seen_verbs.items():
        if len(owners) > 1:
            touches_focus = (not focus) or any(o in focus for o in owners)
            target = issues if touches_focus else advisory
            target.append(f"Repeated leading verb '{verb}' x{len(owners)}. Vary them.")

    return {
        "ok": not issues,
        "issues": issues,
        "advisory": advisory,
        "bullet_count": len(bullets),
    }


# --- rendering to PDF --------------------------------------------------------

def render_pdf(markdown: str | None = None, out_path: str | None = None,
               company: str | None = None, role: str | None = None,
               url: str | None = None, profile: str | None = None,
               patch: dict | None = None) -> str:
    """Render a tailored resume PDF.

    The PDF filename comes from the profile's full name ("First_Last_Resume.pdf")
    so recruiters see a proper name — never a hardcoded internal filename.

    Preferred path: if the profile has a `.tex` master AND pdflatex is installed, edit the
    LaTeX template with the patch (marker-free) and compile it (polished, real-resume
    look). Otherwise fall back to the Markdown->HTML->Chromium path (always available). On
    any LaTeX error we fall back too — never hard-fail.
    """
    pdf_name = config.resume_pdf_name()
    dest = pathlib.Path(out_path) if out_path else config.DATA_DIR / pdf_name
    dest.parent.mkdir(parents=True, exist_ok=True)

    # --- preferred: LaTeX via pdflatex (marker-free edit of the user's real template) ---
    if profile is not None and patch is not None:
        tex_master = latex.tex_master_path(profile)
        if tex_master is not None and latex.have_pdflatex():
            edited = latex.edit_tex(tex_master.read_text(), patch)
            ok, msg = latex.compile_pdf(edited, dest)
            if ok:
                if company and role:
                    appdir = artifacts.folder(company, role, url)
                    (appdir / pdf_name).write_bytes(dest.read_bytes())
                    (appdir / "tailored_resume.tex").write_text(edited)
                    return f"Rendered LaTeX PDF (pdflatex) to {appdir / pdf_name}"
                return f"Rendered LaTeX PDF (pdflatex) to {dest}"
            _latex_note = f" (LaTeX fallback: {msg})"
        else:
            _latex_note = " (no .tex master or pdflatex; used Markdown)"
    else:
        _latex_note = ""

    # --- fallback: Markdown -> HTML -> Chromium ---
    md = markdown or (config.TAILORED_MD_PATH.read_text()
                      if config.TAILORED_MD_PATH.exists() else read_master())
    html = _md_to_html(md)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until="load")
        page.pdf(path=str(dest), format="Letter",
                 margin={"top": "0.5in", "bottom": "0.5in", "left": "0.6in", "right": "0.6in"})
        browser.close()
    # Copy into the per-application folder so the dashboard can link it.
    if company and role:
        appdir = artifacts.folder(company, role, url)
        (appdir / pdf_name).write_bytes(dest.read_bytes())
        return f"Rendered resume PDF to {appdir / pdf_name}{_latex_note}"
    return f"Rendered resume PDF to {dest}{_latex_note}"


def _md_to_html(md: str) -> str:
    lines = md.splitlines()
    html: list[str] = []
    in_ul = False

    def close_ul():
        nonlocal in_ul
        if in_ul:
            html.append("</ul>")
            in_ul = False

    for line in lines:
        s = line.rstrip()
        if s.startswith("# "):
            close_ul(); html.append(f"<h1>{_inline(s[2:])}</h1>")
        elif s.startswith("### "):
            close_ul(); html.append(f"<h3>{_inline(s[4:])}</h3>")
        elif s.startswith("## "):
            close_ul(); html.append(f"<h2>{_inline(s[3:])}</h2>")
        elif s.startswith("- "):
            if not in_ul:
                html.append("<ul>"); in_ul = True
            html.append(f"<li>{_inline(s[2:])}</li>")
        elif not s.strip():
            close_ul()
        else:
            close_ul(); html.append(f"<p>{_inline(s)}</p>")
    close_ul()
    body = "\n".join(html)
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
      body {{ font-family: Georgia, 'Times New Roman', serif; font-size: 10.5pt;
              line-height: 1.3; color: #111; }}
      h1 {{ font-size: 18pt; margin: 0 0 2px; }}
      h2 {{ font-size: 11.5pt; text-transform: uppercase; letter-spacing: .5px;
            border-bottom: 1px solid #444; margin: 12px 0 4px; padding-bottom: 2px; }}
      h3 {{ font-size: 11pt; margin: 8px 0 0; }}
      p {{ margin: 2px 0; }}
      ul {{ margin: 2px 0 6px; padding-left: 18px; }}
      li {{ margin: 1px 0; }}
    </style></head><body>{body}</body></html>"""


def _inline(text: str) -> str:
    text = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    return text
