"""People finder: unit, component, and integration coverage — zero live HTTP, zero tokens.

Every network call is a stub, every brain is canned or the real ManualBrain pointed at a
tmp dir, so this suite proves the wiring without spending a cent.
"""

import json
from datetime import date

import pytest

from src.brain import BrainPending, ManualBrain
from src.tools import people


# ------------------------------------------------------------------ unit: signals

HOME = """
<html><body>
<a href="/about">About</a> <a href="/pricing">Pricing</a>
<a href="https://twitter.com/acme">tw</a> <a href="/team">Team</a>
<p>Write to us: <a href="mailto:hello@acme.ai">hello@acme.ai</a></p>
<img src="logo@2x.png"> <span>noreply@acme.ai</span> <span>ops@sentry.acme.ai</span>
</body></html>
"""

TEAM = """
<html><body>
<h2>Jane Doe</h2><p>Jane Doe, Co-Founder and CEO, previously built search at BigCo.</p>
<h2>Sam Rivera</h2><p>Sam Rivera is our Head of Engineering, hiring for the platform team.</p>
<p>Waves crash on the beach all day long which is nice.</p>
<p>contact: jane@acme.ai</p>
</body></html>
"""


def test_extract_emails_filters_junk_and_dedupes():
    got = people.extract_emails(HOME + HOME)
    assert got == ["hello@acme.ai"]


def test_team_links_same_host_only():
    links = people.team_links("https://acme.ai", HOME)
    assert links == ["https://acme.ai/about", "https://acme.ai/team"]


def test_people_chunks_keeps_title_lines_only():
    chunks = people.people_chunks(TEAM)
    text = " ".join(chunks)
    assert "Co-Founder and CEO" in text and "Head of Engineering" in text
    assert "beach" not in text


def test_people_chunks_glues_name_line_above_title():
    # the Apple leadership-page shape: name on its own line, title on the next
    html = "<p>Tim Cook</p><p>Chief Executive Officer</p><p>Senior Vice President</p>"
    chunks = people.people_chunks(html)
    assert any(c.startswith("Tim Cook :: Chief Executive Officer") for c in chunks)


def test_looks_like_name_rejects_title_fragments():
    assert people.looks_like_name("Jane Doe")
    assert people.looks_like_name("José Núñez") is False  # accents fail the ascii regex, fine
    for junk in ("Senior Vice", "Apple Leadership", "Chief Operating", "Meet Our"):
        assert not people.looks_like_name(junk)


def test_jd_hints_catches_real_lines_and_rejects_false_positives():
    assert people.jd_hints("You will report to the Head of Search Infrastructure.") == \
        ["reports to Head of Search Infrastructure"]
    assert people.jd_hints("you'll report into an Engineering Manager on that team") == \
        ["reports to Engineering Manager on that team"]
    # the classic false positives found in real tracked JDs
    assert people.jd_hints("led by the depth and breadth of our technology") == []
    assert people.jd_hints("managed by Coupang as stated in the Privacy Notice") == []
    assert people.jd_hints("reporting tools that enable stakeholders") == []


def test_guess_emails_patterns_and_unicode():
    assert people.guess_emails("Devanshu Gupta", "baseten.co") == \
        ["devanshu@baseten.co", "devanshu.gupta@baseten.co", "dgupta@baseten.co"]
    assert people.guess_emails("Cher", "x.ai") == ["cher@x.ai"]
    assert people.guess_emails("José Núñez", "x.ai")[0] == "jose@x.ai"
    assert people.guess_emails("", "x.ai") == []


def test_ttl_freshness():
    today = date(2026, 8, 4)
    assert people.is_fresh({"people_scouted": "2026-07-20"}, today)
    assert not people.is_fresh({"people_scouted": "2026-06-01"}, today)
    assert not people.is_fresh({"people_scouted": "garbage"}, today)
    assert not people.is_fresh({}, today)


# ------------------------------------------------------------------ unit: provider seams

def test_search_off_without_key(monkeypatch):
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    assert people.search_provider() == "none"
    assert people.search_people("Acme", ["recruiter"]) == []


def test_search_parses_serper_organic(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "k")
    fake = {"organic": [{"title": "Pat Recruiter - Acme", "link":
                         "https://linkedin.com/in/pat", "snippet": "Talent at Acme"}]}
    got = people.search_people("Acme", ["recruiter"], _post=lambda q: fake)
    assert got == ["Pat Recruiter - Acme | https://linkedin.com/in/pat | Talent at Acme"]


def test_hunter_off_without_key(monkeypatch):
    monkeypatch.delenv("HUNTER_API_KEY", raising=False)
    assert people.hunter_pattern("acme.ai") == ""


def test_hunter_pattern_with_key(monkeypatch):
    monkeypatch.setenv("HUNTER_API_KEY", "k")
    got = people.hunter_pattern("acme.ai", _get=lambda d: {"data": {"pattern": "{first}"}})
    assert got == "{first}"


# ------------------------------------------------------------------ component: find_people

def _fake_fetch(url):
    if url.rstrip("/").endswith(("about", "team")):
        return TEAM
    return HOME


class FakeBrain:
    def __init__(self, out):
        self.out, self.seen = out, []

    def structured(self, name, *, system, user, schema, **kw):
        self.seen.append((name, system, user, schema))
        self.cache_blocks = kw.get("cache_blocks")
        return self.out


CANNED = {
    "company_size": "small",
    "people": [
        {"name": "Sam Rivera", "title": "Head of Engineering", "kind": "hiring_manager",
         "linkedin": "", "email": "sam@acme.ai", "email_source": "guessed",
         "rwl": [2, 1, 3], "hook": "hiring for the platform team",
         "message": "Hi Sam, I saw the platform role."},
        {"name": "Jane Doe", "title": "Co-Founder and CEO", "kind": "founder",
         "linkedin": "", "email": "jane@acme.ai", "email_source": "site",
         "rwl": [1, 0, 2], "hook": "built search at BigCo",
         "message": "Hi Jane, congrats on the launch."},
    ],
    "notes": "small team, site lists everyone",
}


@pytest.fixture
def company():
    return {"name": "Acme", "website": "https://acme.ai", "heat": "HOT",
            "people": [{"name": "Jane Doe", "title": "CEO", "outreach":
                        [{"date": "2026-08-01", "outcome": "sent"}], "hook": "old hook"}]}


def test_find_people_merges_and_stamps(monkeypatch, company):
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("HUNTER_API_KEY", raising=False)
    brain = FakeBrain(CANNED)
    jobs = [{"role": "Platform Engineer", "url": "https://a/1",
             "jd_text": "You will report to the Head of Engineering."}]
    r = people.find_people(company, jobs, brain, fetch_fn=_fake_fetch,
                           today=date(2026, 8, 4))
    assert r["added"] == 1 and r["total"] == 2 and r["size"] == "small"
    assert company["people_scouted"] == "2026-08-04"
    assert company["generic_inbox"] == "hello@acme.ai"
    sam = next(p for p in company["people"] if p["name"] == "Sam Rivera")
    assert sam["email"] == "sam@acme.ai" and sam["email_source"] == "guessed"
    assert sam["draft"] == "Hi Sam, I saw the platform role."
    jane = next(p for p in company["people"] if p["name"] == "Jane Doe")
    # merge updates fields but never clobbers the outreach log
    assert jane["outreach"] == [{"date": "2026-08-01", "outcome": "sent"}]
    assert jane["title"] == "Co-Founder and CEO"

    # the brain saw the real signals: site email, team lines, jd hint, email guesses
    _, system, user, schema = brain.seen[0]
    assert "NEVER invent a person" in system
    payload = json.loads(user)
    assert payload["site_emails"] == ["hello@acme.ai", "jane@acme.ai"]
    assert any("Head of Engineering" in ln for ln in payload["site_text_lines"])
    assert payload["jd_reporting_hints"] == \
        ["Platform Engineer: reports to Head of Engineering"]
    assert "Sam Rivera" in payload["email_pattern_guesses"]
    assert schema["required"] == ["company_size", "people", "notes"]
    # candidate + achievements ride as cache blocks (identical across companies,
    # prompt-cached in API mode), never inside the per-company user payload
    assert brain.cache_blocks and brain.cache_blocks[0].startswith("CANDIDATE:")
    assert "candidate" not in payload and "achievements" not in payload


def test_find_people_skips_when_fresh_and_force_overrides(company):
    company["people_scouted"] = "2026-08-01"
    brain = FakeBrain(CANNED)
    r = people.find_people(company, [], brain, fetch_fn=_fake_fetch,
                           today=date(2026, 8, 4))
    assert r["skipped"] == "fresh" and not brain.seen
    r = people.find_people(company, [], brain, fetch_fn=_fake_fetch, force=True,
                           today=date(2026, 8, 4))
    assert brain.seen and r["total"] == 2


def test_find_people_empty_people_is_fine(company):
    brain = FakeBrain({"company_size": "large", "people": [],
                       "notes": "nobody identifiable on the site"})
    r = people.find_people(company, [], brain, fetch_fn=_fake_fetch,
                           today=date(2026, 8, 4))
    assert r["added"] == 0 and company["company_size"] == "large"
    # large companies never get a generic inbox: nobody reads press@bigco
    assert "generic_inbox" not in company


def test_find_people_manual_brain_round_trip(tmp_path, company, monkeypatch):
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("HUNTER_API_KEY", raising=False)
    brain = ManualBrain(base_dir=tmp_path)
    with pytest.raises(BrainPending):
        people.find_people(company, [], brain, fetch_fn=_fake_fetch,
                           today=date(2026, 8, 4))
    packet = next(tmp_path.glob("people-*.prompt.md"))
    resp = packet.with_name(packet.name.replace(".prompt.md", ".response.json"))
    resp.write_text(json.dumps(CANNED))
    r = people.find_people(company, [], brain, fetch_fn=_fake_fetch,
                           today=date(2026, 8, 4))
    assert r["added"] == 1 and company["people_scouted"] == "2026-08-04"


def test_save_and_load_companies_atomic(tmp_path, monkeypatch):
    monkeypatch.setattr(people, "COMPANIES_PATH", tmp_path / "net" / "companies.json")
    db = {"companies": [{"name": "Acme"}]}
    people.save_companies(db)
    assert people.load_companies() == db


# ------------------------------------------------------------------ component: UI surfacing

def test_company_page_shows_email_and_inbox(monkeypatch):
    from src.tools import focus, tracker
    comp = {"name": "Acme", "website": "https://acme.ai", "heat": "HOT",
            "generic_inbox": "hello@acme.ai",
            "people": [{"name": "Sam Rivera", "title": "Head of Engineering",
                        "email": "sam@acme.ai", "email_source": "guessed",
                        "hook": "hiring platform", "draft": "Hi Sam.", "outreach": []}]}
    monkeypatch.setattr(focus, "_net_companies", lambda: [comp])
    monkeypatch.setattr(focus, "_heat_rows", lambda: {})
    monkeypatch.setattr(tracker, "list_applications", lambda: [])
    html = focus.render_company("acme")
    assert "sam@acme.ai (guessed)" in html
    assert "mailto:hello@acme.ai" in html


def test_network_copy_button_uses_scouted_draft(monkeypatch):
    from src.tools import focus
    comp = {"name": "Acme", "people": [{"name": "Sam Rivera", "title": "HM",
                                        "draft": "Hi Sam.", "outreach": []}]}
    assert focus._person_draft(comp, comp["people"][0]) == "Hi Sam."
