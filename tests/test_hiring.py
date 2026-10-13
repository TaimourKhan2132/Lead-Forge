"""Hiring signals, as tests: what counts as a role, how fresh it is, and what an email may say about it.

No network. Every page here is invented.
"""
import datetime as dt
from pathlib import Path

import pytest

import hiring
import jobs
import lint_drafts
from common import job_wording

TODAY = dt.date(2026, 10, 14)
WORDING = job_wording(Path(__file__).resolve().parent.parent / "examples" / "job_ask.example.json")
SPEC = {"domain": "harbourline.example", "agency": "Harbourline Studio", "to": "hello@harbourline.example", "type": "A",
        "score": {"score": 71, "tier": "A"}}

OPENINGS = """<html><body><nav><a href="/team">Account Manager stories</a></nav>
<h1>Careers</h1><p>Current openings</p>
<div class="row"><span>01</span> <a href="/careers/data-analyst">Data Analyst</a> <span>Posted 2 October 2026</span>
  <span>Remote</span> <span>Full-time</span> <a href="/careers/data-analyst/apply">Apply</a></div>
<div class="row"><span>02</span> <a href="/careers/web-developer">WEB DEVELOPER</a> <span>On-site, Dubai</span> <a href="#">Apply</a></div>
<div class="row"><span>03</span> <a href="/careers/account-manager">Account Manager</a> <span>Posted 1 March 2026</span> <a href="#">Apply</a></div>
<form><select><option>Python Engineer</option></select></form>
<h2>Our services</h2><ul><li>Web Development</li><li>Lead Generation</li></ul>
</body></html>"""

POOL = """<html><body><h1>Work with us</h1><p>We may not have active openings at every moment. These are the
disciplines we want to meet.</p>
<h3>Automation Engineer</h3><p>Builds the workflows behind our campaigns.</p><a href="mailto:jobs@harbourline.example">Apply</a>
<h3>Graphic Designer</h3><p>Turns ideas into visual systems.</p><a href="mailto:jobs@harbourline.example">Apply</a>
</body></html>"""


def roles(html, pool=None):
    page = hiring.read_page(html, "https://harbourline.example/careers", TODAY)
    found = hiring.settle(page["roles"], page["talent_pool"] if pool is None else pool, TODAY)
    return {role["title"]: role for role in found}


# --- what a role is ---------------------------------------------------------------------------------

def test_a_careers_page_gives_up_its_roles_and_nothing_else():
    found = roles(OPENINGS)
    assert set(found) == {"Data Analyst", "Web Developer", "Account Manager"}  # not the menu, the form or the services
    analyst = found["Data Analyst"]
    assert (analyst["posted"], analyst["mode"], analyst["employment"]) == ("2026-10-02", "remote", "full-time")
    assert analyst["url"] == "https://harbourline.example/careers/data-analyst"
    assert analyst["apply_url"].endswith("/careers/data-analyst/apply")
    assert "Data Analyst" in analyst["snippet"]  # the exact text it was read from


def test_freshness_comes_from_the_posting_date():
    found = roles(OPENINGS)
    assert found["Data Analyst"]["status"] == "fresh"
    assert found["Web Developer"]["status"] == "undated"   # no date shown: usable, but never "you're hiring"
    assert found["Account Manager"]["status"] == "stale"   # posted more than 60 days ago
    assert hiring.freshness("2026-08-15", TODAY) == "fresh" and hiring.freshness("2026-08-14", TODAY) == "stale"


def test_a_list_of_roles_to_hear_about_is_a_talent_pool_not_an_opening():
    found = roles(POOL)
    assert {role["status"] for role in found.values()} == {"talent_pool"}
    assert found["Automation Engineer"]["apply_url"].startswith("mailto:")
    assert roles(OPENINGS + "<p>We are always interested in speculative CVs.</p>")["Web Developer"]["status"] == "undated"


def test_a_closing_date_that_has_passed_makes_a_role_stale():
    late = OPENINGS.replace("Posted 2 October 2026", "Closing date is 11th February")
    assert roles(late)["Data Analyst"]["status"] == "stale"


@pytest.mark.parametrize("title, expected", [
    ("Digital Marketing Data Analyst", "strong"), ("Backend Developer", "strong"), ("Marketing Automation Specialist", "strong"),
    ("BI Reporting Analyst", "strong"), ("Machine Learning Engineer", "strong"), ("Python Developer", "strong"),
    ("Full Stack Developer", "adjacent"), ("Web Developer", "adjacent"), ("CRM Manager", "adjacent"), ("Frontend Developer", "adjacent"),
    ("Data Entry Clerk", "none"), ("Business Development Executive", "none"), ("Mobile App Developer", "none"),
    ("Graphic Designer", "none"), ("Account Manager", "none"),
])
def test_relevance_to_the_operator(title, expected):
    assert hiring.relevance(title) == expected


def test_the_hiring_score_follows_relevance_and_freshness():
    score = lambda relevance, status: hiring.role_score({"relevance": relevance, "status": status})
    assert score("strong", "fresh") == 20 > score("adjacent", "fresh") == 10 > score("strong", "undated") == 5
    assert score("strong", "talent_pool") == score("adjacent", "undated") == 5
    assert score("none", "fresh") == 0 and score("strong", "stale") == 0


def test_a_role_tied_to_an_office_or_a_visa_ranks_below_one_that_is_not():
    found = roles(OPENINGS.replace("<span>Remote</span>", "<span>On-site only. Visa required.</span>"))
    assert set(found["Data Analyst"]["flags"]) == {"onsite", "visa"}
    free = {"title": "Data Analyst", "relevance": "strong", "status": "fresh", "flags": []}
    assert hiring.rank(free) < hiring.rank(found["Data Analyst"])       # same score, but flagged goes after
    assert hiring.rank(found["Data Analyst"]) < hiring.rank(found["Web Developer"])  # flagged is still not dropped


def test_job_systems_are_recognised_by_their_board_addresses():
    html = ('<a href="https://boards.greenhouse.io/harbourline">Jobs</a> <a href="https://jobs.lever.co/harbourline/1">x</a>'
            '<iframe src="https://apply.workable.com/harbourline/"></iframe> <a href="https://harbourline.recruitee.com/">r</a>'
            '<a href="https://harbourline.bamboohr.com/careers">b</a> <a href="https://harbourline.teamtailor.com/jobs">t</a>')
    boards = dict(hiring.read_page(html, "https://harbourline.example/careers", TODAY)["boards"])
    assert set(boards) == {"greenhouse", "lever", "workable", "recruitee", "bamboohr", "teamtailor"}
    assert set(boards.values()) == {"harbourline"}


def test_a_board_api_answer_becomes_roles_with_real_posting_dates():
    lever = [{"text": "Data Engineer", "hostedUrl": "https://jobs.lever.co/harbourline/1", "createdAt": 1791000000000,
              "categories": {"location": "Dubai", "commitment": "Full-time"}, "workplaceType": "remote", "descriptionPlain": "Pipelines."}]
    role = hiring.settle(hiring.api_roles("lever", "harbourline", lever, TODAY), False, TODAY)[0]
    assert (role["title"], role["location"], role["mode"], role["status"], role["relevance"]) == (
        "Data Engineer", "Dubai", "remote", "fresh", "strong")
    greenhouse = {"jobs": [{"title": "Data Analyst", "absolute_url": "u", "updated_at": "2026-10-10T00:00:00Z", "content": ""}]}
    # An edit date is not a posting date, so this one is undated.
    assert hiring.settle(hiring.api_roles("greenhouse", "harbourline", greenhouse, TODAY), False, TODAY)[0]["status"] == "undated"


# --- what the email may say -------------------------------------------------------------------------

def spec(status, **more):
    posted = {"posted": dt.date.today().isoformat()} if status == "fresh" else {}
    return {**SPEC, "hiring": {"url": "https://harbourline.example/careers", "role": "Automation Engineer", "status": status,
                               "relevance": "strong", "fits": True, "score": 20 if status == "fresh" else 5, **posted, **more}}


@pytest.mark.parametrize("status, opener, hire_line", [
    ("fresh", "I saw you're hiring an Automation Engineer.", True),
    ("undated", "I saw the Automation Engineer role on your careers page.", True),
    ("talent_pool", "I saw Automation Engineer listed among the roles on your careers page.", False),
])
def test_the_opener_is_worded_to_match_the_roles_status(status, opener, hire_line):
    text = jobs.render(spec(status), WORDING, results=Path("never-checked.json"))
    assert opener in text and (WORDING["hiring_line"] in text) == hire_line
    assert ("you're hiring" in text) == (status == "fresh")
    assert lint_drafts.lint_job(text, WORDING) == []


def test_an_undated_role_may_not_be_called_hiring():
    text = jobs.render(spec("undated"), WORDING, results=Path("never-checked.json"))
    wrong = text.replace("I saw the Automation Engineer role on your careers page.", "I saw you're hiring an Automation Engineer.")
    assert any("may be called hiring" in problem for problem in lint_drafts.lint_job(wrong, WORDING))


def test_a_fresh_role_needs_a_posting_date_inside_sixty_days(tmp_path, monkeypatch):
    import track
    monkeypatch.setattr(track, "DB", tmp_path / "tracker.db")
    conn = track.connect()
    try:
        old = spec("fresh", posted=(dt.date.today() - dt.timedelta(days=90)).isoformat())
        assert any("fresh only with a posting date" in problem for problem in jobs.problems(old, conn))
        assert not any("fresh only" in problem for problem in jobs.problems(spec("fresh"), conn))
    finally:
        conn.close()
