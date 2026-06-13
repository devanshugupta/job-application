"""Run log — the self-check / QA audit trail.

Every pipeline step (open page, classify portal, tailor, lint, score, fill, submit, find)
records here whether it did a GOOD job, plus any issues it hit. This gives transparency
("did each step work, and what went wrong?") and a written record you can review later.

It writes JSONL to `data/run_log.jsonl` (one event per line — append-only, easy to tail)
and the dashboard / `report` command summarize it. The agent calls `qa_check` (in
qa.py) which appends here; deterministic checks live in qa.py so they cost no tokens.
"""

from __future__ import annotations

import json
from datetime import date

from .. import config

LOG_PATH = config.RUN_LOG_PATH


def log_step(
    step: str,
    ok: bool,
    *,
    target: str = "",
    issues: list[str] | None = None,
    detail: str = "",
) -> dict:
    """Append one step-check record.

    step: short id, e.g. 'open_page', 'classify_portal', 'tailor', 'lint', 'score',
          'fill_form', 'submit', 'find'.
    ok: did the step do a good job?
    target: what it operated on (url / role / field).
    issues: specific problems found (empty if clean).
    detail: optional free-text note.
    """
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "date": date.today().isoformat(),
        "step": step,
        "ok": ok,
        "target": target,
        "issues": issues or [],
        "detail": detail,
    }
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def read_log() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    return [json.loads(line) for line in LOG_PATH.read_text().splitlines() if line.strip()]


def summary() -> dict:
    """Aggregate: per-step pass/fail counts + all open issues."""
    rows = read_log()
    by_step: dict[str, dict] = {}
    issues: list[dict] = []
    for r in rows:
        s = by_step.setdefault(r["step"], {"ok": 0, "fail": 0})
        s["ok" if r["ok"] else "fail"] += 1
        for i in r["issues"]:
            issues.append({"step": r["step"], "target": r["target"], "issue": i})
    return {"steps": by_step, "issues": issues, "total_events": len(rows)}
