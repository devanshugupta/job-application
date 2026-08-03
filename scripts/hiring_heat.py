"""Hiring-heat scorer — ZERO LLM tokens, free ATS JSON APIs only.

The single best predictor of outreach response is whether the company is
actively hiring RIGHT NOW. This sweeps every watchlist company with an
ats+token and computes posting velocity from real posting dates:

  new_7d / new_30d   how many roles opened recently (the heat)
  accel              new_30d vs the 30 days before it (accelerating?)
  ghost_share        fraction of open roles >45 days old (ghost-job discount)
  match_new_30d      recent roles matching your target keywords (team-level
                     heat  at big companies only the org you target matters)

Heat rating:
  HOT   match_new_30d >= 3, or new_30d >= 10 with accel >= 1
  WARM  match_new_30d >= 1, or new_30d >= 3
  COOL  anything else with open roles
  DEAD  no open roles / all ghosts

Usage:
    python scripts/hiring_heat.py                     # whole watchlist
    python scripts/hiring_heat.py --company stripe    # one company
    python scripts/hiring_heat.py --keywords "machine learning,ml,ads,personalization,recommend"

Output: ranked console table + data/network/hiring_heat.json
(company-scout reads this instead of guessing heat from funding alone).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tools import boards  # noqa: E402

OUT = ROOT / "data" / "network" / "hiring_heat.json"

FETCHERS = {
    "greenhouse": boards.fetch_greenhouse,
    "lever": boards.fetch_lever,
    "ashby": boards.fetch_ashby,
    "smartrecruiters": boards.fetch_smartrecruiters,
    "workable": boards.fetch_workable,
}

DEFAULT_KEYWORDS = [
    "machine learning", "ml engineer", "mle", "ai engineer", "applied scientist",
    "recommend", "personalization", "ads", "ranking", "software engineer", "sde",
]


def score_company(entry: dict, keywords: list[str]) -> dict | None:
    ats, token = entry.get("ats"), entry.get("token")
    fetch = FETCHERS.get(ats or "")
    if not fetch or not token:
        return None
    name = entry.get("name", token)
    try:
        jobs = fetch(name, token)
    except Exception as e:
        return {"company": name, "error": str(e)[:120]}

    now = time.time()
    day = 86_400
    dated = [j for j in jobs if j.get("posted_ts")]
    new_7d = sum(1 for j in dated if now - j["posted_ts"] <= 7 * day)
    new_30d = sum(1 for j in dated if now - j["posted_ts"] <= 30 * day)
    prev_30d = sum(1 for j in dated if 30 * day < now - j["posted_ts"] <= 60 * day)
    ghosts = sum(1 for j in dated if now - j["posted_ts"] > 45 * day)

    kw = [k.lower() for k in keywords]
    def matches(j: dict) -> bool:
        return any(k in j.get("role", "").lower() for k in kw)
    match_open = [j for j in jobs if matches(j)]
    match_new_30d = sum(
        1 for j in match_open if j.get("posted_ts") and now - j["posted_ts"] <= 30 * day
    )

    accel = round(new_30d / prev_30d, 2) if prev_30d else (999 if new_30d else 0)
    ghost_share = round(ghosts / len(dated), 2) if dated else 0

    if match_new_30d >= 3 or (new_30d >= 10 and accel >= 1):
        heat = "HOT"
    elif match_new_30d >= 1 or new_30d >= 3:
        heat = "WARM"
    elif jobs and ghost_share < 0.9:
        heat = "COOL"
    else:
        heat = "DEAD"

    # freshest matching roles — the reqs to anchor outreach on
    top_match = sorted(
        (j for j in match_open if j.get("posted_ts")),
        key=lambda j: -j["posted_ts"],
    )[:5]

    return {
        "company": name,
        "heat": heat,
        "open_roles": len(jobs),
        "new_7d": new_7d,
        "new_30d": new_30d,
        "prev_30d": prev_30d,
        "accel": accel,
        "ghost_share": ghost_share,
        "match_open": len(match_open),
        "match_new_30d": match_new_30d,
        "freshest_matches": [
            {"role": j["role"], "posted": j["posted_date"], "url": j["url"]}
            for j in top_match
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", default="", help="only this company (name or token substring)")
    ap.add_argument("--keywords", default="", help="comma-separated target-role keywords")
    args = ap.parse_args()

    keywords = ([k.strip() for k in args.keywords.split(",") if k.strip()]
                or DEFAULT_KEYWORDS)
    watchlist = json.loads((ROOT / "config" / "watchlist.json").read_text())
    entries = [c for c in watchlist.get("companies", []) if c.get("ats") and c.get("token")]
    if args.company:
        q = args.company.lower()
        entries = [c for c in entries
                   if q in c.get("name", "").lower() or q in c.get("token", "").lower()]
    if not entries:
        print("no matching watchlist entries with ats+token")
        return

    with ThreadPoolExecutor(max_workers=6) as ex:
        results = [r for r in ex.map(lambda e: score_company(e, keywords), entries) if r]

    order = {"HOT": 0, "WARM": 1, "COOL": 2, "DEAD": 3}
    scored = sorted(
        (r for r in results if "error" not in r),
        key=lambda r: (order[r["heat"]], -r["match_new_30d"], -r["new_30d"]),
    )
    errors = [r for r in results if "error" in r]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "keywords": keywords,
        "companies": scored,
        "errors": errors,
    }, indent=2))

    print(f"{'company':22s} {'heat':5s} {'open':>5s} {'new30':>6s} {'accel':>6s} "
          f"{'ghost':>6s} {'match30':>8s}")
    for r in scored:
        print(f"{r['company'][:22]:22s} {r['heat']:5s} {r['open_roles']:5d} "
              f"{r['new_30d']:6d} {r['accel']:6.1f} {r['ghost_share']:6.0%} "
              f"{r['match_new_30d']:8d}")
    if errors:
        print(f"\n{len(errors)} fetch errors (see {OUT.name})")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
