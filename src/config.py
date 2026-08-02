"""Central configuration  single source of truth for paths, models, and knobs.

Everything that used to be a scattered `pathlib.Path("data/...")` literal or a
module-level `os.environ.get(...)` lives here. Three layers, later wins:

    1. Defaults in this file.
    2. Optional ``config/settings.json`` (gitignored; for machine-local overrides).
    3. Environment variables (the existing ``JOB_AGENT_*`` names, unchanged).

All paths are anchored to the PROJECT ROOT (the directory containing this repo),
so the CLI works no matter what directory it is launched from.
"""

from __future__ import annotations

import json
import os
import pathlib
from functools import lru_cache

# --------------------------------------------------------------------------- paths
ROOT = pathlib.Path(__file__).resolve().parents[1]

CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RESUME_DIR = ROOT / "resume"
MASTERS_DIR = RESUME_DIR / "masters"

PROFILE_PATH = CONFIG_DIR / "profile.json"
WATCHLIST_PATH = CONFIG_DIR / "watchlist.json"
QUESTION_BANK_PATH = CONFIG_DIR / "question_bank.json"
SETTINGS_PATH = CONFIG_DIR / "settings.json"

APPLICATIONS_PATH = DATA_DIR / "applications.json"
APPLICATIONS_DIR = DATA_DIR / "applications"
JOB_CACHE_PATH = DATA_DIR / "job_cache.json"
RUN_LOG_PATH = DATA_DIR / "run_log.jsonl"
USAGE_LOG_PATH = DATA_DIR / "usage_log.jsonl"
DASHBOARD_PATH = DATA_DIR / "dashboard.html"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
BRAIN_DIR = DATA_DIR / "brain"          # ManualBrain prompt/response packets
# Per-process so several tailor runs (e.g. parallel agents) never clobber each other's
# intermediate resume markdown. Each process gets its own file; cleaned up implicitly.
TAILORED_MD_PATH = DATA_DIR / f"tailored_resume_{os.getpid()}.md"

RESUME_RULES_PATH = RESUME_DIR / "formatting_rules.md"
MASTERS_INDEX_PATH = MASTERS_DIR / "index.json"
LEGACY_MASTER_PATH = RESUME_DIR / "master_resume.md"
# Raw work context (projects/metrics beyond what fits on the resume) that grounds
# tailored bullets  bullets may be sourced ONLY from the master + this doc.
ACHIEVEMENTS_PATH = RESUME_DIR / "achievements.md"

# --------------------------------------------------------------------------- models
# Exact current model IDs  never append date suffixes.
DEFAULT_MODELS = {
    "anthropic": "claude-opus-4-8",
    "openai": "gpt-4o",
}
FAST_MODEL_DEFAULT = "claude-sonnet-4-6"   # find / cheap triage
SMART_MODEL_DEFAULT = "claude-opus-4-8"    # tailor / score / apply

# Approx USD per 1M tokens (input, output)  used for cost estimates only.
PRICING = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "gpt-4o": (2.5, 10.0),
}
DEFAULT_RATE = (5.0, 25.0)


@lru_cache(maxsize=1)
def _settings() -> dict:
    if SETTINGS_PATH.exists():
        try:
            return json.loads(SETTINGS_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def setting(key: str, default=None):
    """Look up a knob: env var JOB_AGENT_<KEY> wins, then settings.json, then default."""
    env = os.environ.get(f"JOB_AGENT_{key.upper()}")
    if env is not None:
        return env
    return _settings().get(key, default)


def int_setting(key: str, default: int) -> int:
    try:
        return int(setting(key, default))
    except (TypeError, ValueError):
        return default


def float_setting(key: str, default: float) -> float:
    try:
        return float(setting(key, default))
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- knobs
def fast_model() -> str:
    return str(setting("fast_model", FAST_MODEL_DEFAULT))


def smart_model() -> str:
    return str(setting("model", SMART_MODEL_DEFAULT))


def token_budget() -> int:
    return int_setting("token_budget", 0)  # 0 = unlimited


def user_data_dir() -> str | None:
    v = setting("user_data_dir")
    return str(v) if v else None


def has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"))


def brain_mode() -> str:
    """Which brain the pipeline uses by default.

    'api'    -> call Anthropic/OpenAI (needs a key).
    'manual' -> no API: write prompt packets to data/brain/ for an LLM (e.g. the
                Claude Code session driving this repo) to answer.

    Resolution: explicit JOB_AGENT_BRAIN / settings.json wins; otherwise auto
    'api' only when a key is actually present, else 'manual'. So a machine with no
    key transparently uses the LLM-as-brain path instead of erroring.
    """
    explicit = setting("brain")
    if explicit in ("api", "manual"):
        return explicit
    return "api" if has_api_key() else "manual"


def resume_pdf_name() -> str:
    """Filename for rendered resume PDFs, derived from the profile's full name
    (e.g. 'Devanshu_Gupta_Resume.pdf'). Falls back to a generic name."""
    override = setting("resume_pdf_name")
    if override:
        return str(override)
    try:
        profile = json.loads(PROFILE_PATH.read_text())
        full = profile.get("personal", {}).get("full_name", "").strip()
        if full:
            return "_".join(full.split()) + "_Resume.pdf"
    except (OSError, json.JSONDecodeError):
        pass
    return "Tailored_Resume.pdf"


# GitHub feeds the discovery step pulls (name -> raw listings.json URL).
# Override/extend via settings.json {"feeds": {...}}.
DEFAULT_FEEDS = {
    "simplify-newgrad": (
        "https://raw.githubusercontent.com/SimplifyJobs/"
        "New-Grad-Positions/dev/.github/scripts/listings.json"
    ),
}


def feeds() -> dict:
    custom = _settings().get("feeds")
    return dict(DEFAULT_FEEDS, **custom) if isinstance(custom, dict) else dict(DEFAULT_FEEDS)
