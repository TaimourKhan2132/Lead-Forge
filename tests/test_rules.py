"""The rules LeadForge must never break, as tests.

Nothing here touches the network or real data. The fixtures are the fictional example pack and a
draft written to fail.
"""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import pytest

import draft
import lint_drafts
import pack
import prospects
import signals
import track
import verify

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
AGENCY = "northlight-growth.example"


@pytest.fixture(scope="module")
def example():
    """Build the fictional pack and email with the real builders, once."""
    code = subprocess.call([sys.executable, str(EXAMPLES / "make_example.py")])
    assert code == 0
    return EXAMPLES


# --- what may be said about a business ---------------------------------------------------------

@pytest.mark.parametrize("text", [
    "212 reviews, no booking on its site",
    "no online booking and no way to book",
    "a book button with no booking system",
    "no WhatsApp or chat",
    "no enquiry chat on the homepage",
    "no social profiles linked",
    "no search description",
    "no ad tracking",
    "Every gap was checked twice in a real browser.",
])
def test_retired_wording_is_caught(text):
    assert signals.retired_in(text)


@pytest.mark.parametrize("text", [
    "212 reviews at 4.7, no website on its Google listing",
    "the website link on its listing does not resolve",
    "site has no https, footer still says 2018",
    "no Google tag or Meta Pixel on its site",
    "rated 3.8 against a search median of 4.7",
    'its homepage says "Book via WhatsApp"',
])
def test_allowed_wording_passes(text):
    assert signals.retired_in(text) == []


def test_generated_wording_never_uses_a_retired_signal():
    details = {
        "no_site": {}, "dead_site": {"how": "does not resolve"}, "not_https": {"https": "shows a certificate error"},
        "stale": {"year": 2019, "line": "© 2019 Example"}, "no_ads_tags": {},
        "low_reviews": {"reviews": 30, "median": 96, "peers": 58},
        "low_rating": {"rating": 3.8, "reviews": 143, "median": 4.7, "peers": 51},
    }
    assert set(details) == set(signals.ALLOWED)
    business = {"review_count": "143", "review_rating": "3.8"}
    for key, detail in details.items():
        gap = {"key": key, "detail": detail}
        wording = " ".join([signals.label(gap, "dental clinic"), signals.phrase(gap), signals.opener(gap, business)])
        assert signals.retired_in(wording) == [], key


# --- reading a footer --------------------------------------------------------------------------

@pytest.mark.parametrize("footer, year", [
    ("© 2017 Example Clinic. All rights reserved", 2017),
    ("Copyright © 2010-2023 Example LLC", 2023),
    ("Copyright © 2016-17 Example Cleaning", 2017),
    ("2019 © Example", 2019),
])
def test_copyright_year_is_the_newest_one_in_the_notice(footer, year):
    assert verify.copyright_year(footer)["year"] == year


@pytest.mark.parametrize("footer", [
    "© Example LLC. PO Box 2015, Dubai",       # a box number is not a year
    "Example, since 1998 © All rights reserved",  # nor is a founding date
    "Established 2005. Call us today.",        # no copyright mark at all
])
def test_copyright_year_is_not_guessed(footer):
    assert verify.copyright_year(footer) is None


def test_a_current_footer_is_not_stale():
    this_year = dt.date.today().year
    assert verify.copyright_year(f"© {this_year} Example")["year"] > signals.STALE_MAX_YEAR


# --- comparing with the median -----------------------------------------------------------------

POOL = {"median_reviews": 96, "peers": 58, "rated_peers": 51, "median_rating": 4.7}


def test_low_rating_needs_to_be_well_below_the_median():
    keys = lambda reviews, rating: [g["key"] for g in prospects.comparison_gaps(reviews, rating, POOL, "link")]
    assert "low_rating" in keys(143, 3.8)
    assert "low_rating" not in keys(143, 4.5)   # under the median, but not by much
    assert "low_rating" not in keys(9, 3.0)     # too few reviews for a rating to mean anything


def test_low_reviews_is_under_half_the_median():
    keys = lambda reviews: [g["key"] for g in prospects.comparison_gaps(reviews, 4.8, POOL, "link")]
    assert "low_reviews" in keys(31)
    assert "low_reviews" not in keys(60)


# --- send rules --------------------------------------------------------------------------------

@pytest.mark.parametrize("sent, fu1, fu2", [
    ("2026-10-12", "2026-10-15", "2026-10-19"),  # Monday: Thursday, then Monday
    ("2026-10-13", "2026-10-16", "2026-10-20"),  # Tuesday: Friday, then Tuesday
    ("2026-10-14", "2026-10-19", "2026-10-21"),  # Wednesday: day 3 is a Saturday, so Monday
    ("2026-10-15", "2026-10-19", "2026-10-22"),  # Thursday: day 3 is a Sunday, so Monday
    ("2026-10-16", "2026-10-19", "2026-10-23"),  # Friday: day 3 is Monday
])
def test_follow_ups_fall_on_day_3_and_day_7_and_never_on_a_weekend(sent, fu1, fu2):
    day = dt.date.fromisoformat(sent)
    assert track.due(day, track.FU1_DAYS) == fu1
    assert track.due(day, track.FU2_DAYS) == fu2


def test_daily_caps():
    assert (track.NEW_CAP, track.DAILY_CAP) == (10, 15)


# --- the builders refuse what was not verified ---------------------------------------------------

def test_the_example_email_passes_the_linter(example):
    text = (example / f"{AGENCY}.email.md").read_text(encoding="utf-8")
    assert lint_drafts.lint(text) == []
    assert "Want the other 7? Just reply yes." in text


def test_the_old_style_email_is_refused():
    problems = lint_drafts.lint((EXAMPLES / "rejected.example.md").read_text(encoding="utf-8"))
    assert any("no booking" in p for p in problems)
    assert any("no WhatsApp" in p for p in problems)
    assert any("checked twice" in p for p in problems)


def test_a_pack_refuses_a_signal_that_was_not_confirmed(example, tmp_path):
    for name in (f"{AGENCY}.pack.json", f"{AGENCY}.candidates.json"):
        (tmp_path / name).write_text((example / "spec" / name).read_text(encoding="utf-8"), encoding="utf-8")
    spec = json.loads((tmp_path / f"{AGENCY}.pack.json").read_text(encoding="utf-8"))
    spec["prospects"][0]["gaps"] = ["no_ads_tags"]  # never confirmed for this business
    (tmp_path / f"{AGENCY}.pack.json").write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError, match="not confirmed"):
        pack.load_pack(AGENCY, tmp_path)


def test_a_pack_refuses_a_check_that_has_gone_stale(example, tmp_path):
    old = (dt.date.today() - dt.timedelta(days=pack.MAX_AGE_DAYS + 1)).isoformat()
    candidates = json.loads((example / "spec" / f"{AGENCY}.candidates.json").read_text(encoding="utf-8"))
    for business in candidates:
        business["verified_on"] = old
    (tmp_path / f"{AGENCY}.candidates.json").write_text(json.dumps(candidates), encoding="utf-8")
    (tmp_path / f"{AGENCY}.pack.json").write_text((example / "spec" / f"{AGENCY}.pack.json").read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ValueError, match="run verify.py"):
        pack.load_pack(AGENCY, tmp_path)


def test_an_email_line_cannot_quote_words_that_were_not_read_off_the_page():
    assert draft._plain("“Book via WhatsApp”") == draft._plain('"book  via whatsapp"')
    assert draft._plain("Book on WhatsApp") not in draft._plain("…Call us 04 000 0000 Book via WhatsApp Open 9 AM…")
