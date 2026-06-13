"""Token + cost tracking — so one application can't quietly burn the API budget.

`run_agent` accumulates per-turn token counts into a `UsageMeter`, which:
- tracks input / output / cache-read / cache-write tokens across the whole run,
- estimates USD cost from per-model rates,
- enforces an optional hard ceiling (raises so the loop stops), and
- appends a one-line record to `data/usage_log.jsonl` per run.

`python -m src.cli usage` summarizes the log (per-run + totals). Pricing is approximate
(USD per 1M tokens) and easy to update; cache reads are ~0.1x input, writes ~1.25x.
"""

from __future__ import annotations

import json
from datetime import date

from .. import config

USAGE_LOG = config.USAGE_LOG_PATH

# Pricing lives in config.py so there is exactly one table to update.
_PRICING = config.PRICING
_DEFAULT_RATE = config.DEFAULT_RATE


class BudgetExceeded(RuntimeError):
    """Raised inside the agent loop when a run exceeds its token ceiling."""


class UsageMeter:
    """Accumulates token usage for one agent run and estimates cost."""

    def __init__(self, model: str, label: str = "", max_total_tokens: int = 0):
        self.model = model
        self.label = label
        self.max_total = max_total_tokens  # 0 = unlimited
        self.input = 0
        self.output = 0
        self.cache_read = 0
        self.cache_write = 0

    def add(self, resp_usage) -> None:
        """Add one API response's usage (anthropic Usage object or dict)."""
        g = (lambda k: getattr(resp_usage, k, 0) or 0) if not isinstance(resp_usage, dict) \
            else (lambda k: resp_usage.get(k, 0) or 0)
        # Accept either the raw-SDK key style (input_tokens, ...) or the llm-shim's
        # normalized style (input, output, cache_read, cache_write).
        self.input += g("input_tokens") or g("input")
        self.output += g("output_tokens") or g("output")
        self.cache_read += g("cache_read_input_tokens") or g("cache_read")
        self.cache_write += g("cache_creation_input_tokens") or g("cache_write")

    @property
    def total(self) -> int:
        return self.input + self.output + self.cache_read + self.cache_write

    def cost_usd(self) -> float:
        in_rate, out_rate = _PRICING.get(self.model, _DEFAULT_RATE)
        return round(
            (self.input * in_rate
             + self.output * out_rate
             + self.cache_read * in_rate * 0.1
             + self.cache_write * in_rate * 1.25) / 1_000_000,
            4,
        )

    def check(self) -> None:
        """Raise BudgetExceeded if over the per-run ceiling."""
        if self.max_total and self.total > self.max_total:
            raise BudgetExceeded(
                f"Run exceeded token ceiling ({self.max_total}): used {self.total}. "
                "Raise JOB_AGENT_TOKEN_BUDGET or narrow the task."
            )

    def summary(self) -> str:
        return (f"tokens in={self.input} out={self.output} "
                f"cache_read={self.cache_read} cache_write={self.cache_write} "
                f"total={self.total} ~${self.cost_usd()}")

    def record(self) -> dict:
        """Append this run's usage to the log and return the record."""
        USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "date": date.today().isoformat(),
            "label": self.label,
            "model": self.model,
            "input": self.input,
            "output": self.output,
            "cache_read": self.cache_read,
            "cache_write": self.cache_write,
            "total": self.total,
            "cost_usd": self.cost_usd(),
        }
        with USAGE_LOG.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec


def read_log() -> list[dict]:
    if not USAGE_LOG.exists():
        return []
    return [json.loads(l) for l in USAGE_LOG.read_text().splitlines() if l.strip()]


def totals() -> dict:
    rows = read_log()
    return {
        "runs": len(rows),
        "total_tokens": sum(r["total"] for r in rows),
        "total_cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
    }
