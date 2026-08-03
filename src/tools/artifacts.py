"""Per-application artifacts  keep a traceable folder per job we tailor for.

When we tailor a resume for a specific role, we don't just overwrite one scratch file
we write a dedicated folder so you can always see exactly what was sent where:

    data/applications/<Company>/<job-id>/
        Devanshu_Gupta_Resume.pdf   # the rendered PDF that gets uploaded
        tailored_resume.tex         # the edited LaTeX it was compiled from

    (The old tailored_resume.md + changes.json are retired: the diff now lives on the
    tracker row as `resume_diff`, and rescore reads the .tex. See save_artifacts.)

Grouped by company, then by the posting's JOB ID (parsed from the URL), so every role
at one employer sits together and two roles with the same title never collide. Postings
with no id in the URL fall back to a role slug. `migrate_layout()` moves folders written
under the old flat `<company>-<role>-<jobid>/` scheme into this one. The dashboard links
the PDF and shows the diff from here (empty only for `find` rows, where no tailoring
happened).
"""

from __future__ import annotations

import json
import pathlib
import re

from .. import config

BASE = config.APPLICATIONS_DIR


def job_id_from_url(url: str | None) -> str:
    """Extract a stable posting id from common ATS URLs (the longest digit/uuid run),
    e.g. amazon /jobs/10441140/..., greenhouse /jobs/4951814008, apple /details/200313970.
    Falls back to '' if none found."""
    if not url:
        return ""
    ids = re.findall(r"[0-9a-f]{8}-[0-9a-f\-]{27,}|\d{4,}", url)
    return max(ids, key=len) if ids else ""


def slug(company: str, role: str, url: str | None = None) -> str:
    """LEGACY flat folder name  kept so `migrate_layout` can recognise old folders."""
    raw = f"{company}-{role}".lower()
    s = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")[:55] or "application"
    jid = job_id_from_url(url)
    return f"{s}-{jid}" if jid else s


def company_dir(company: str) -> str:
    """Readable, filesystem-safe company folder name ('Hims & Hers' -> 'Hims and Hers')."""
    s = re.sub(r"[^\w .-]", "", (company or "Unknown").replace("&", "and"))
    return re.sub(r"\s+", " ", s).strip(" .") or "Unknown"


def job_dir(role: str, url: str | None = None) -> str:
    """Per-posting folder: '<role-slug>-<job-id>' so the folder says which role it is
    while the id keeps two postings of the same title apart. Either part may be missing."""
    slug_ = re.sub(r"[^a-z0-9]+", "-", (role or "").lower()).strip("-")[:45].strip("-")
    return "-".join(p for p in (slug_, job_id_from_url(url)) if p) or "role"


def folder(company: str, role: str, url: str | None = None) -> pathlib.Path:
    d = BASE / company_dir(company) / job_dir(role, url)
    d.mkdir(parents=True, exist_ok=True)
    return d


# Tokens that start the ROLE part of a legacy folder name  everything before the first
# one is the company (capped at 3 words). Only used for orphan folders whose tracker row
# no longer exists; tracked rows always supply the real company name.
_ROLE_TOKENS = {
    "software", "senior", "sr", "staff", "principal", "lead", "machine", "learning",
    "ml", "mle", "ai", "genai", "llm", "nlp", "data", "engineer", "engineering",
    "scientist", "science", "research", "researcher", "sde", "swe", "backend",
    "frontend", "fullstack", "full", "stack", "graduate", "associate", "intern",
    "new", "grad", "early", "career", "applied", "platform", "infra", "infrastructure",
    "java", "python", "product", "analyst", "developer", "dev", "founding", "quant",
    "cloud", "security", "search", "recsys", "agentic", "deep", "computer", "vision",
    "entry", "level", "algorithm", "solutions", "integration", "advanced", "native",
}
# Trailing posting id in a legacy folder name: full/truncated uuid, req number, or the
# 'manual' marker. Matched text (minus the dash) becomes the new per-job folder.
_ID_SUFFIX = re.compile(
    r"-((?:[0-9a-f]{8}(?:-[0-9a-f-]{27,})?|R?\d{4,}|manual))$", re.I)


def rel_to_root(path: pathlib.Path) -> str:
    """Repo-relative path when possible (what the tracker stores), else absolute."""
    try:
        return str(path.relative_to(config.ROOT))
    except ValueError:
        return str(path)


def _trailing_id(name: str) -> str:
    m = _ID_SUFFIX.search(name)
    return m.group(1) if m else ""


def _leaf_dirs(base: pathlib.Path) -> list[pathlib.Path]:
    """Every folder holding artifacts  both the legacy flat ones and the nested
    <Company>/<job>/ ones, so a re-run picks up either generation."""
    return [p for p in base.rglob("*")
            if p.is_dir() and not any(c.is_dir() for c in p.iterdir())
            and any(f.is_file() and not f.name.startswith(".") for f in p.iterdir())]


def _company_from_dirname(name: str, known: dict[str, str]) -> str:
    """Best-effort company for a legacy folder with no tracker row ('' if unguessable).
    A name that starts with a company we DO track wins, so casing stays real."""
    stem = _ID_SUFFIX.sub("", name)
    for cslug, real in known.items():
        if stem == cslug or stem.startswith(cslug + "-"):
            return real
    parts: list[str] = []
    for tok in stem.split("-"):
        if not tok or tok in _ROLE_TOKENS or len(parts) == 3:
            break
        parts.append(tok)
    return " ".join(p.capitalize() for p in parts)


def migrate_layout(apply: bool = True) -> list[tuple[str, str]]:
    """Refile artifact folders as <Company>/<role-slug>-<job-id>/ and repoint the tracker.

    Runs over both generations of layout (flat `<company>-<role>-<id>/` and nested
    `<Company>/<job>/`), so it is safe to re-run after the naming scheme changes. A
    folder is matched to its tracker row by the old `slug()` or by the job id in its
    name; that row supplies the real company/role/url. Untracked flat folders (row since
    deleted or deduped) get a company inferred from the name, or land in `_archive/`;
    untracked nested ones are left alone. Returns the (old, new) path pairs; pass
    apply=False for a dry run.
    """
    from . import tracker

    db = tracker._load_applications()
    rows = db["applications"]
    by_slug = {slug(r.get("company", ""), r.get("role", ""), r.get("url")): r
               for r in rows}
    by_id: dict[str, dict] = {}
    known: dict[str, str] = {}
    for r in rows:
        jid = job_id_from_url(r.get("url"))
        if jid:
            by_id.setdefault(jid, r)
        cslug = re.sub(r"[^a-z0-9]+", "-", (r.get("company") or "").lower()).strip("-")
        if cslug:
            known.setdefault(cslug, r["company"])

    moves: list[tuple[str, str]] = []
    for old in sorted(_leaf_dirs(BASE)):
        rec = (by_slug.get(old.name)
               or by_id.get(_trailing_id(old.name) or job_id_from_url(old.name)))
        if rec is not None:
            new = BASE / company_dir(rec["company"]) / job_dir(rec.get("role", ""),
                                                               rec.get("url"))
        elif old.parent != BASE:
            continue          # already nested and untracked  leave the archive alone
        else:
            company = _company_from_dirname(old.name, known)
            if not company:
                new = BASE / "_archive" / old.name
            else:
                cslug = re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")
                rest = re.sub(rf"^{re.escape(cslug)}-", "", old.name)
                new = BASE / company_dir(company) / rest
        if new == old:
            continue
        base_new, n = new, 2
        while new.exists():           # two old folders for one posting id
            new = base_new.with_name(f"{base_new.name}-{n}")
            n += 1
        moves.append((str(old.relative_to(BASE)), str(new.relative_to(BASE))))
        if not apply:
            continue
        new.parent.mkdir(parents=True, exist_ok=True)
        old.rename(new)
        if rec is not None:
            for field in ("tailored_pdf", "tailored_md"):
                if rec.get(field):
                    rec[field] = rel_to_root(new / pathlib.Path(rec[field]).name)
    if apply and moves:
        tracker._save_db(db)
    return moves


def save_artifacts(company: str, role: str, *, tailored_md: str, patch: dict,
                   url: str | None = None, pdf_bytes: bytes | None = None) -> dict:
    """Ensure the per-application folder exists and (optionally) drop the PDF into it.

    The canonical per-application artifacts are the PDF and ``tailored_resume.tex``, both
    written by resume.render_pdf. The old ``changes.json`` and ``tailored_resume.md`` this
    used to emit are RETIRED: nothing reads changes.json (the diff lives on the tracker
    row as ``resume_diff``, which the dashboard uses), and rescore reads the ``.tex``. So
    this no longer writes them  keeping every application folder consistent (PDF + tex).
    Return shape is unchanged for callers."""
    d = folder(company, role, url)
    pdf_path = d / config.resume_pdf_name()
    if pdf_bytes is not None:
        pdf_path.write_bytes(pdf_bytes)
    return {
        "dir": str(d),
        "tailored_md": None,
        "tailored_pdf": str(pdf_path) if pdf_bytes is not None else None,
        "changes": None,
    }
