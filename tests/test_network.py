"""Tests for the networking layer: hiring_heat scoring and the dashboard generator.

Both scripts are deterministic (zero LLM), so they get real unit + e2e coverage:
hiring-heat rating logic against synthetic posting dates, and the dashboard
generated end-to-end from a temp tracker + heat file + dossier, then asserted on
structure (embedded company views, hash links, copy-ready drafts, next actions).
"""

import importlib.util
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hiring_heat = _load("hiring_heat")
dash = _load("network_dashboard")


# ------------------------------------------------------------ hiring_heat

def _jobs(specs):
    """specs: list of (role, days_ago) -> job dicts like boards.py returns."""
    now = time.time()
    return [{"company": "X", "role": r, "url": f"https://x/{i}",
             "posted_date": "2026-01-01", "posted_ts": int(now - d * 86400)}
            for i, (r, d) in enumerate(specs)]


def _score(specs, keywords=("machine learning",)):
    entry = {"name": "X", "ats": "greenhouse", "token": "x"}
    orig = hiring_heat.FETCHERS["greenhouse"]
    hiring_heat.FETCHERS["greenhouse"] = lambda c, t: _jobs(specs)
    try:
        return hiring_heat.score_company(entry, list(keywords))
    finally:
        hiring_heat.FETCHERS["greenhouse"] = orig


def test_hot_when_matching_roles_fresh():
    r = _score([("Machine Learning Engineer", 5)] * 3)
    assert r["heat"] == "HOT" and r["match_new_30d"] == 3
    assert len(r["freshest_matches"]) == 3


def test_hot_needs_volume_and_acceleration_without_matches():
    # 10 fresh non-matching + earlier baseline -> HOT via volume+accel
    specs = [("Sales Lead", 3)] * 10 + [("Sales Lead", 45)] * 5
    r = _score(specs)
    assert r["new_30d"] == 10 and r["accel"] == 2.0 and r["heat"] == "HOT"


def test_warm_and_cool_and_dead():
    assert _score([("Machine Learning Intern", 10)])["heat"] == "WARM"   # 1 match
    assert _score([("Sales Lead", 10)] * 3)["heat"] == "WARM"            # 3 new
    assert _score([("Sales Lead", 40)])["heat"] == "COOL"                # stale, not ghost-heavy
    assert _score([])["heat"] == "DEAD"
    assert _score([("Sales Lead", 90)] * 5)["heat"] == "DEAD"            # all ghosts


def test_ghost_share_counts_45_day_old_posts():
    r = _score([("Sales Lead", 50), ("Sales Lead", 50), ("Sales Lead", 5), ("Sales Lead", 5)])
    assert r["ghost_share"] == 0.5


def test_fetch_error_is_reported_not_raised():
    entry = {"name": "X", "ats": "greenhouse", "token": "x"}
    orig = hiring_heat.FETCHERS["greenhouse"]
    hiring_heat.FETCHERS["greenhouse"] = lambda c, t: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        r = hiring_heat.score_company(entry, ["ml"])
    finally:
        hiring_heat.FETCHERS["greenhouse"] = orig
    assert "error" in r and "boom" in r["error"]


def test_unknown_ats_returns_none():
    assert hiring_heat.score_company({"name": "X", "ats": "workday", "token": "x"}, []) is None


# ------------------------------------------------------- dashboard: units

def test_slugify():
    assert dash.slugify("Scale AI") == "scale-ai"
    assert dash.slugify("  Adapts (adapts.ai) ") == "adapts-adapts-ai"


def test_md_headings_bold_links_lists():
    h = dash.md_to_html("# T\n**b** [x](https://e.com)\n- a\n- b")
    assert "<h1>T</h1>" in h and "<b>b</b>" in h
    assert 'href="https://e.com"' in h and h.count("<li>") == 2


def test_md_blockquote_becomes_copyable_draft():
    h = dash.md_to_html("> Hi Vivek, quick note.\n> Second line.")
    assert 'class="draft"' in h
    assert 'data-raw="Hi Vivek, quick note.\nSecond line."' in h


def test_md_checkboxes_and_tables():
    h = dash.md_to_html("- [ ] open item\n- [x] done item")
    assert "⬜" in h and "✅" in h
    t = dash.md_to_html("| Role | URL |\n|---|---|\n| MLE | x |")
    assert "<th>Role</th>" in t and "<td>MLE</td>" in t and "---" not in t


def test_md_escapes_html():
    assert "<script>" not in dash.md_to_html("hello <script>alert(1)</script>")


# --------------------------------------------------------- dashboard: e2e

def _tmp_net(tmp_path, monkeypatch):
    net = tmp_path / "network"
    (net / "dossiers").mkdir(parents=True)
    monkeypatch.setattr(dash, "NET", net)
    monkeypatch.setattr(dash, "OUT", net / "dashboard.html")
    return net


def test_dashboard_e2e(tmp_path, monkeypatch):
    net = _tmp_net(tmp_path, monkeypatch)
    (net / "dossiers" / "acme.md").write_text(
        "# Acme, scouted 2026-08-01\n\n> Hi there, draft note.\n\n"
        "## Next actions\n- [ ] ping Jane\n- [x] done thing\n")
    tracker = [{"name": "Acme", "website": "https://acme.com", "dossier": "dossiers/acme.md",
                "status": "contacted", "last_scouted": "2026-08-01", "heat": "HOT",
                "funding": "seed", "open_roles": 2, "fit": "MLE fit",
                "people": [{"name": "Jane Roe", "title": "EM", "rwl": [3, 2, 3],
                            "hook": "wrote the recsys blog",
                            "outreach": [{"date": "2026-08-02", "channel": "dm",
                                          "mode": "A", "touch_n": 1, "outcome": "replied"}]}]}]
    heat = {"computed_at": "2026-08-01T00:00:00+00:00", "companies": [
        {"company": "Acme", "heat": "HOT", "open_roles": 2, "new_30d": 2, "prev_30d": 1,
         "accel": 2.0, "ghost_share": 0.0, "match_open": 2, "match_new_30d": 2,
         "freshest_matches": [{"role": "MLE", "posted": "2026-07-30", "url": "https://a/1"}]}]}
    (net / "companies.json").write_text(json.dumps({"companies": tracker}))
    (net / "hiring_heat.json").write_text(json.dumps(heat))

    html = dash.build_index(tracker, heat)
    (net / "dashboard.html").write_text(html)

    # single self-contained file: home + embedded, hash-linked company view
    assert 'id="home"' in html and 'id="co-acme"' in html
    assert 'href="#co-acme"' in html                       # card links to the view
    assert "function route()" in html                      # router shipped
    # company view carries the actionable pieces
    assert "ping Jane" in html                             # open next action surfaced
    assert 'data-raw="Hi there, draft note."' in html      # copy-ready draft
    assert "Jane Roe" in html and "R3" in html             # person + R score chip
    assert "outcome <b>replied</b>" in html                # outreach log line
    # heat table row is searchable and filterable
    assert 'data-heat="HOT"' in html and 'data-search=' in html
    # replies tile counts the replied touch
    assert "replies" in html


def test_dashboard_empty_inputs_dont_crash(tmp_path, monkeypatch):
    _tmp_net(tmp_path, monkeypatch)
    html = dash.build_index([], {})
    assert "No companies scouted yet" in html


def test_chrome_has_no_ai_glyphs(tmp_path, monkeypatch):
    """The generated UI chrome must not contain em dashes, arrows, or middots
    (source data like real job titles may; chrome may not)."""
    _tmp_net(tmp_path, monkeypatch)
    html = dash.build_index([], {})
    for glyph in ("—", "→", " · "):
        assert glyph not in html


def test_configured_keywords_priority(tmp_path, monkeypatch):
    """network.json (personal constants) wins, then settings.json, then default."""
    root = tmp_path
    (root / "config").mkdir()
    monkeypatch.setattr(hiring_heat, "ROOT", root)
    (root / "config" / "settings.json").write_text(
        '{"network": {"keywords": ["from-settings"]}}')
    (root / "config" / "network.json").write_text(
        '{"keywords": ["robotics", "slam", "perception"]}')
    assert hiring_heat.configured_keywords() == ["robotics", "slam", "perception"]
    (root / "config" / "network.json").unlink()
    assert hiring_heat.configured_keywords() == ["from-settings"]
    (root / "config" / "settings.json").write_text("{}")
    assert hiring_heat.configured_keywords() == hiring_heat.DEFAULT_KEYWORDS


def test_next_actions_not_duplicated_in_company_view(tmp_path, monkeypatch):
    net = _tmp_net(tmp_path, monkeypatch)
    (net / "dossiers" / "acme.md").write_text(
        "# Acme\n\n## Next actions\n- [ ] ping Jane\n- [x] done\n")
    c = {"name": "Acme", "dossier": "dossiers/acme.md", "status": "scouted",
         "last_scouted": "2026-08-03", "heat": "HOT", "people": []}
    html = dash.company_view(c, None)
    assert html.count("Next actions") == 1
    assert html.count("ping Jane") == 1


def test_bare_linkedin_paths_become_links():
    h = dash.md_to_html("- linkedin.com/company/acme/people/ (size, people)")
    assert 'href="https://linkedin.com/company/acme/people/"' in h
    # already-schemed URLs are not double-wrapped
    h2 = dash.md_to_html("https://www.linkedin.com/in/someone/")
    assert h2.count("<a ") == 1


def test_person_gets_linkedin_link():
    c = {"name": "Acme", "people": [
        {"name": "Jane Roe", "title": "EM", "rwl": [1, 1, 1], "hook": "x"},
        {"name": "Bob", "title": "SDE", "rwl": [1, 1, 1], "hook": "y",
         "linkedin": "https://www.linkedin.com/in/bob-exact/"}]}
    h = dash.people_html(c)
    assert "search/results/people/?keywords=Jane+Roe+Acme" in h
    assert "find on LinkedIn" in h
    assert 'href="https://www.linkedin.com/in/bob-exact/"' in h and ">profile</a>" in h


# ------------------------------------------------------------- focus UI

def test_focus_pages_render_and_follow_design_laws(monkeypatch):
    import sys
    sys.path.insert(0, str(ROOT))
    from src.tools import focus, tracker
    # glyph laws apply to OUR chrome, not to source data (ATS job titles may
    # legally contain em dashes) -- so audit pure-chrome renders (empty data)
    monkeypatch.setattr(tracker, "list_applications", lambda: [])
    monkeypatch.setattr(focus, "_net_companies", lambda: [])
    import re
    for page in (focus.render_entry(), focus.render_apply(), focus.render_network()):
        stripped = page.replace("\U0001F319", "").replace("☀️", "")
        assert not re.search(r"[\U0001F300-\U0001FAFF]", stripped)
        assert "—" not in page and "→" not in page
    monkeypatch.undo()
    entry, apply_, net = focus.render_entry(), focus.render_apply(), focus.render_network()
    for page in (entry, apply_, net):
        # one blue accent defined once; nav present
        assert page.count("--accent:#2a78d6") == 1
        assert 'href="/apply"' in page and 'href="/network"' in page
    # entry: story hero + two doors + momentum
    assert 'class="door"' in entry and entry.count('class="door"') == 2
    assert "It is working." in entry
    # lanes cross-link each other at the bottom
    assert "Done applying?" in apply_ and "Messages sent?" in net


def test_focus_company_page():
    import sys
    sys.path.insert(0, str(ROOT))
    from src.tools import focus
    page = focus.render_company("adapts")
    assert page and "Adapts" in page
    assert "Copy message" in page          # dossier draft surfaced
    assert "ranked by reachability" in page
    assert focus.render_company("not-a-company") is None

def test_focus_about_and_footer():
    import sys
    sys.path.insert(0, str(ROOT))
    from src.tools import focus
    about = focus.render_about()
    assert "interviews come from people" in about
    assert "config/network.json" in about
    # every page carries the footer with the about link
    for page in (focus.render_entry(), focus.render_apply(), focus.render_network(), about):
        assert 'class="foot"' in page and 'href="/about"' in page
