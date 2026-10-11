"""The only things a pack or an email may say about a prospect business.

A signal is allowed only if a person can check it in ten seconds on a phone: open the Google
listing, or open the site and look. There are seven, plus text quoted from the business's own site:

    no_site       no website on the Google listing
    dead_site     the website link on the listing is dead or does not resolve
    not_https     the site is served without https: the https:// version of the same URL fails to
                  load or has an invalid certificate (one that answers and redirects to http works)
    stale         the footer copyright year is 2023 or older
    no_ads_tags   no Google tag, Tag Manager or Meta Pixel in the rendered page after 8 seconds
    low_reviews   review count compared with the pack median
    low_rating    rating compared with the pack median

Retired on 2026-10-11, and never to come back: no booking, no online booking, a book button with
no booking system, no WhatsApp, no chat, no enquiry chat, no social profiles linked. A manual check
found most of those claims false. A page scan sees tools embedded in the page. It does not see a
"Book now" button that opens another site, or a chat widget a script injects later, so "none
found" was reported as "none there".

verify.py confirms each allowed signal in a rendered browser on the day. pack.py and draft.py build
their wording from the functions here, so a pack cannot phrase a signal more strongly than it was
checked. lint_drafts.py rejects the retired wording wherever it turns up.
"""
from __future__ import annotations

import re

STALE_MAX_YEAR = 2023
ALLOWED = ("no_site", "dead_site", "not_https", "stale", "no_ads_tags", "low_reviews", "low_rating")
# Claims that something is missing or broken. These have to hold on two separate visits.
ABSENCE = ("dead_site", "not_https", "no_ads_tags")
# Ranking weight when choosing which candidates to verify first.
WEIGHTS = {"no_site": 5, "dead_site": 5, "not_https": 3, "stale": 3, "no_ads_tags": 3, "low_rating": 3, "low_reviews": 2}
HEADLINES = {
    "no_site": "No website on the listing", "dead_site": "Website link is dead", "not_https": "No https",
    "stale": "Old footer year", "no_ads_tags": "No Google tag or Meta Pixel",
    "low_reviews": "Few reviews for the area", "low_rating": "Rating below the median",
}
# What the reader does to check it, in ten seconds on a phone.
HOW_TO_CHECK = {
    "no_site": "open the listing: there is no Website button",
    "dead_site": "open the listing and tap Website",
    "not_https": "tap Website on the listing: the browser shows Not secure",
    "stale": "open the site and scroll to the footer",
    "no_ads_tags": "on a desktop, open the site, press F12 and type dataLayer, then gtag, then fbq in the Console (each should be 'not defined')",
    "low_reviews": "open the listing and read the review count",
    "low_rating": "open the listing and read the rating",
}

# Wording that must not appear in a pack, an email, a follow-up or a LinkedIn note.
RETIRED = [
    (r"\bno (?:online |tour |appointment )?booking\b", "no booking"),
    (r"\bno way to book\b|\bno booking (?:system|option|prompt)\b|\bbook(?:ing)? (?:button|prompt|option)\b", "book button with no booking system"),
    (r"\bbooking system\b", "booking system"),
    (r"\bno whatsapp\b|\bwhatsapp or chat\b|\bchat or whatsapp\b|\bwhatsapp route\b", "no WhatsApp"),
    (r"\bno (?:enquiry |live |web )?chat\b|\bno way to message\b", "no chat"),
    (r"\bno socials?\b|\bsocial (?:profiles?|links?|pages?)\b|\bno link to a social\b", "no social profiles linked"),
    # Never on the allowed list, so they go the same way.
    (r"\b(?:search|meta) description\b", "search description"),
    (r"\bmobile viewport\b|\bnot mobile-ready\b", "mobile viewport"),
    (r"\blinktree\b|\blinks to (?:an? )?(?:instagram|facebook|social)\b", "listing links to a social profile"),
    (r"\bad tracking\b|\bad or analytics tag\b", "'ad tracking' (say 'Google tag or Meta Pixel')"),
    (r"checked twice in a real browser", "the 'checked twice in a real browser' sentence"),
]


def retired_in(text: str) -> list[str]:
    """Names of the retired signals whose wording appears in `text`."""
    lowered = text.lower()
    return [name for pattern, name in RETIRED if re.search(pattern, lowered)]


def _count(value) -> str:
    return f"{int(float(value)):,}"


def label(gap: dict, niche: str = "comparable") -> str:
    """The full sentence a pack prints for a verified signal."""
    key, d = gap["key"], gap.get("detail", {})
    if key == "no_site":
        return "The Google Maps listing has no Website button."
    if key == "dead_site":
        return f"The website link on the Google listing {d['how']}." + (f" {d['note']}" if d.get("note") else "")
    if key == "not_https":
        return f"The site opens over plain http, and its https address {d['https']}."
    if key == "stale":
        return f"The footer copyright reads {d['year']}: \"{d['line']}\"."
    if key == "no_ads_tags":
        return ("No Google tag, Tag Manager or Meta Pixel on the homepage: none loaded in the 8 seconds after "
                "it opened, and none is named in the page's scripts.")
    if key == "low_reviews":
        return (f"{_count(d['reviews'])} Google reviews, against a median of {_count(d['median'])} across the "
                f"{d['peers']} {niche} listings these searches returned.")
    if key == "low_rating":
        return (f"Rated {d['rating']} on Google from {_count(d['reviews'])} reviews, against a median rating of "
                f"{d['median']} across the {d['peers']} {niche} listings these searches returned.")
    return gap["label"]  # text quoted from the business's own site


def phrase(gap: dict) -> str:
    """The short clause an email line uses for a verified signal."""
    key, d = gap["key"], gap.get("detail", {})
    if key == "no_site":
        return "no website on its Google listing"
    if key == "dead_site":
        return f"the website link on its listing {d['how']}"
    if key == "not_https":
        return "site has no https"
    if key == "stale":
        return f"footer still says {d['year']}"
    if key == "no_ads_tags":
        return "no Google tag or Meta Pixel on its site"
    if key == "low_reviews":
        return f"{_count(d['reviews'])} reviews against a search median of {_count(d['median'])}"
    if key == "low_rating":
        return f"rated {d['rating']} against a search median of {d['median']}"
    return gap.get("phrase") or gap["headline"].lower()


def opener(gap: dict, cand: dict) -> str:
    """A first line the agency could send this business, built only from the verified signal."""
    key, d = gap["key"], gap.get("detail", {})
    reviews = _count(cand["review_count"]) if str(cand.get("review_count") or "").strip() else ""
    busy = f"{reviews} Google reviews, and " if reviews else ""
    if key == "no_site":
        return f"{busy}no website on your Google listing for any of those people to visit."
    if key == "dead_site":
        return f"{busy}the website link on your Google listing {d['how']}."
    if key == "not_https":
        return f"{busy}your website opens as Not secure because it has no https."
    if key == "stale":
        return f"{busy}the footer of your website still says {d['year']}."
    if key == "no_ads_tags":
        return f"{busy}no Google tag or Meta Pixel on your website to show which visits turn into customers."
    if key == "low_reviews":
        return f"You have {_count(d['reviews'])} Google reviews. The median for businesses like yours in the same searches is {_count(d['median'])}."
    if key == "low_rating":
        return f"Your Google rating is {d['rating']} from {_count(d['reviews'])} reviews. The median for businesses like yours in the same searches is {d['median']}."
    return gap.get("opener") or gap["label"]
