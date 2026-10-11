"""Write the fictional inputs for the example pack, then render it with the real builder.

    python examples/make_example.py

Every business here is invented and sits on a reserved .example domain. Nothing was scraped and
nothing was opened in a browser. The point is to show the output format without publishing anyone's
real data, so the "checked" date on each signal is simply the day this script ran.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = HERE / "spec"
AGENCY_DOMAIN = "northlight-growth.example"
POOL = {"median_reviews": 96, "peers": 58, "rated_peers": 51, "median_rating": 4.7}
ON_LISTING = {"no_site", "dead_site", "low_reviews", "low_rating"}

# (name, area, reviews, rating, site, email, signals)
BUSINESSES = [
    ("Marina Pearl Dental Studio", "Dubai Marina", 212, 4.7, "", "", ["no_site"]),
    ("JLT Family Dentistry", "JLT", 31, 4.9, "jltfamilydentistry.example", "info@jltfamilydentistry.example",
     ["low_reviews", "no_ads_tags"]),
    ("Al Barsha Smile Centre", "Al Barsha", 188, 4.4, "albarshasmile.example", "reception@albarshasmile.example",
     ["stale:2019"]),
    ("Dr. Hana Orthodontics", "Business Bay", 17, 5.0, "", "", ["no_site", "low_reviews"]),
    ("Creekside Dental & Implant Clinic", "Deira", 143, 3.8, "creeksidedental.example", "care@creeksidedental.example",
     ["low_rating", "no_ads_tags"]),
    ("Palm View Dental", "Palm Jumeirah", 164, 4.6, "palmviewdental.example", "info@palmviewdental.example",
     ["dead_site"]),
    ("Mirdif Kids Dental", "Mirdif", 139, 4.8, "mirdifkidsdental.example", "smile@mirdifkidsdental.example",
     ["no_ads_tags"]),
    ("Silicon Oasis Dental Care", "Dubai Silicon Oasis", 22, 4.5, "", "", ["no_site", "low_reviews"]),
    ("Jumeirah Aesthetic Dentistry", "Jumeirah 1", 301, 4.9, "jumeirah-aesthetic.example", "concierge@jumeirah-aesthetic.example",
     ["no_ads_tags", "stale:2022"]),
    ("Karama Dental Point", "Al Karama", 157, 4.2, "karamadentalpoint.example", "info@karamadentalpoint.example",
     ["not_https", "stale:2018"]),
]
FIT = {
    "no_site": "With {reviews} reviews and no website on the listing, there is no page of its own to rank or to send ad traffic to. A first site is Northlight's entry project.",
    "dead_site": "The listing sends people to a link that does not open. Every tap on Website is a lost visit until the site is rebuilt or the link is fixed.",
    "not_https": "Browsers mark the site Not secure before a patient reads a word. Moving it to https is a small first job that opens the door to the rest.",
    "stale": "A footer that still says {year} suggests nobody has touched the site since, which is the redesign conversation.",
    "no_ads_tags": "No Google tag or Meta Pixel means no paid search or paid social is being measured here, so a Google Ads account would start clean.",
    "low_reviews": "{reviews} reviews against a median of {median} nearby: a local SEO and review-request job.",
    "low_rating": "A {rating} rating against a median of {median} is the first thing a new patient sees, which is where local SEO work has to start.",
}


def detail_for(gap: str, name: str, reviews: int, rating: float) -> tuple[str, dict]:
    key, _, arg = gap.partition(":")
    if key == "stale":
        return key, {"year": int(arg), "line": f"© {arg} {name}. All rights reserved"}
    if key == "low_reviews":
        return key, {"reviews": reviews, "median": POOL["median_reviews"], "peers": POOL["peers"]}
    if key == "low_rating":
        return key, {"rating": rating, "reviews": reviews, "median": POOL["median_rating"], "peers": POOL["rated_peers"]}
    if key == "dead_site":
        return key, {"how": "does not resolve"}
    if key == "not_https":
        return key, {"https": "does not load"}
    return key, {}


def main() -> int:
    today = dt.date.today().isoformat()
    candidates, prospects = [], []
    for i, (name, area, reviews, rating, site, email, gaps) in enumerate(BUSINESSES, 1):
        maps = f"https://maps.example/place/EXAMPLE{i:02d}"
        home = f"https://{site}/" if site else ""
        built = []
        for gap in gaps:
            key, detail = detail_for(gap, name, reviews, rating)
            built.append({"key": key, "detail": detail, "checked": today, "source_url": maps if key in ON_LISTING else home})
        key = site or f"listing-{i:02d}"
        candidates.append({
            "key": key, "name": name, "category": "Dental clinic", "address": f"{area}, Dubai", "niche": "dental clinic",
            "maps_link": maps, "website": home, "phone": f"+971 4 555 01{i:02d}", "emails": [email] if email else [],
            "review_count": str(reviews), "review_rating": str(rating), "pool": POOL, "verified_on": today, "gaps": built,
        })
        prospects.append({"key": key, "gaps": [g["key"] for g in built]})
    spec = {
        "agency_domain": AGENCY_DOMAIN, "agency": "Northlight Growth", "niche": "dental clinics", "city": "Dubai",
        "summary": ("Northlight Growth sells website builds, Google Ads management and local SEO to clinics. Five Maps "
                    "searches across Dubai returned 58 dental clinics. Each of these ten shows something on its own "
                    "Google listing or website that sits inside what Northlight already delivers, and each line below "
                    "can be checked in a few seconds by opening the link beside it. This is an illustrative pack: the "
                    "agency and every business are fictional."),
        "fit": FIT,
        "method": ("Illustrative pack: every business is fictional, so nothing was searched or opened. A real pack "
                   "states here the date of its Maps searches and the date each listing and website was opened in a "
                   "browser, and what was checked."),
        "prospects": prospects,
    }
    SPEC.mkdir(exist_ok=True)
    (SPEC / f"{AGENCY_DOMAIN}.candidates.json").write_text(json.dumps(candidates, indent=1, ensure_ascii=False), encoding="utf-8")
    (SPEC / f"{AGENCY_DOMAIN}.pack.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False), encoding="utf-8")
    return subprocess.call([sys.executable, str(HERE.parent / "src" / "pack.py"), "build", AGENCY_DOMAIN,
                            "--spec-dir", str(SPEC), "--out-dir", str(HERE)])


if __name__ == "__main__":
    sys.exit(main())
