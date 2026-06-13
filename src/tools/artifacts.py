"""Per-application artifacts — keep a traceable folder per job we tailor for.

When we tailor a resume for a specific role, we don't just overwrite one scratch file —
we write a dedicated folder so you can always see exactly what was sent where:

    data/applications/<company>-<role-slug>-<jobid>/
        tailored_resume.md     # the tailored Markdown
        zsAIEngineer.pdf     # the rendered PDF that gets uploaded
        changes.json            # what changed vs the master (summary/skills/bullets)

The folder name includes the posting's JOB ID (parsed from the URL) so two roles with the
same title at the same company never collide. The dashboard links the PDF and shows the
diff from here (empty only for `find` rows, where no tailoring happened).
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
    raw = f"{company}-{role}".lower()
    s = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")[:55] or "application"
    jid = job_id_from_url(url)
    return f"{s}-{jid}" if jid else s


def folder(company: str, role: str, url: str | None = None) -> pathlib.Path:
    d = BASE / slug(company, role, url)
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_artifacts(company: str, role: str, *, tailored_md: str, patch: dict,
                   url: str | None = None, pdf_bytes: bytes | None = None) -> dict:
    """Write the tailored md, the changes.json, and (optionally) the pdf. Returns the
    paths so the caller can record them on the application (for the dashboard)."""
    d = folder(company, role, url)
    md_path = d / "tailored_resume.md"
    md_path.write_text(tailored_md)
    changes = {
        "summary": patch.get("summary"),
        "technical_skills": patch.get("technical_skills"),
        "top_bullets": patch.get("top_bullets", []),
    }
    (d / "changes.json").write_text(json.dumps(changes, indent=2))
    pdf_path = d / config.resume_pdf_name()
    if pdf_bytes is not None:
        pdf_path.write_bytes(pdf_bytes)
    return {
        "dir": str(d),
        "tailored_md": str(md_path),
        "tailored_pdf": str(pdf_path) if pdf_bytes is not None else None,
        "changes": changes,
    }
