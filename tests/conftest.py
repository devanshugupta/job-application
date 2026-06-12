"""Test config — make `src` importable and isolate file writes to a tmp dir.

These tests exercise the pure-Python logic only (no Anthropic API, no browser). Modules
that write to data/ are redirected to a per-test temp dir via monkeypatch fixtures so the
real data/ is never touched.
"""

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def tmp_data(tmp_path, monkeypatch):
    """Redirect tracker / runlog / artifacts / dashboard outputs into tmp_path."""
    from src.tools import artifacts, dashboard, finder, runlog, tracker

    monkeypatch.setattr(tracker, "APPLICATIONS_PATH", tmp_path / "applications.json")
    monkeypatch.setattr(runlog, "LOG_PATH", tmp_path / "run_log.jsonl")
    monkeypatch.setattr(finder, "CACHE_PATH", tmp_path / "job_cache.json")
    monkeypatch.setattr(artifacts, "BASE", tmp_path / "applications")
    monkeypatch.setattr(dashboard, "OUT_PATH", tmp_path / "dashboard.html")
    return tmp_path
