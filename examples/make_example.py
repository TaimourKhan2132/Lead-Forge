"""Write the fictional inputs for the example pack, then render it with the real builder.

    python examples/make_example.py

Every business here is invented and sits on a reserved .example domain. Nothing was scraped.
The point is to show the output format without publishing anyone's real data.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = HERE / "spec"
AGENCY_DOMAIN = "northlight-growth.example"
MEDIAN = "a median of 96 across the 58 dental clinic listings these searches returned"
SCOPE = "the homepage and contact page"

LABELS = {
    "no_booking": f"No online booking: no booking system and no 'book' call-to-action found on {SCOPE}.",
    "booking_cta_only": f"There is a 'book' call-to-action but no booking system in the page source of {SCOPE}, so it most likely leads to a form or a phone call.",
    "no_chat": f"No WhatsApp link and no chat widget in the page source of {SCOPE}.",
    "no_ads_tags": f"No Meta Pixel, Google Ads tag or Tag Manager container in the page source of {SCOPE}, so paid traffic is not being tracked there.",
    "no_viewport": "The homepage has no mobile viewport tag, so it will not scale properly on phones.",
    "not_https": "The site is served over plain http, without https.",
    "no_site": "The Google Maps listing has no website attached.",
}
ON_LISTING = {"no_site", "platform_site", "low_reviews", "low_rating"}

# (name, area, reviews, rating, site, email, gaps, why_fit, opener)
BUSINESSES = [
    ("Marina Pearl Dental Studio", "Dubai Marina", 212, 4.7, "marinapearl-dental.example", "hello@marinapearl-dental.example",
     ["no_booking", "no_chat"],
     "212 reviews says the chairs are busy, yet the only way to book is to phone. That is the exact WhatsApp booking flow Northlight builds, with obvious volume behind it.",
     "Your Marina clinic has 212 Google reviews and no way to book without phoning. Have you looked at what a WhatsApp booking flow would take off the front desk?"),
    ("JLT Family Dentistry", "JLT", 31, 4.9, "jltfamilydentistry.example", "info@jltfamilydentistry.example",
     ["low_reviews", "no_ads_tags"],
     "A 4.9 rating that almost nobody sees. No ad tracking on the site means no paid search is running, so Northlight's Google Ads offer starts from a clean account.",
     "A 4.9 rating from 31 reviews in JLT is a strong base that is not being advertised anywhere. Is paid search something you have tried?"),
    ("Al Barsha Smile Centre", "Al Barsha", 88, 4.4, "albarshasmile.example", "reception@albarshasmile.example",
     ["booking_cta_only", "stale:2021"],
     "They already want online bookings (the button is there) but it lands on a form. Swapping that form for an automated WhatsApp flow is a small, concrete first project.",
     "Your 'Book now' button opens a contact form, so patients still wait for a call back. Would an instant WhatsApp confirmation be worth testing?"),
    ("Dr. Hana Orthodontics", "Business Bay", 17, 5.0, "", "",
     ["platform_site", "low_reviews"],
     "A solo orthodontist running the practice from Instagram. There is no website to rebuild, so a WhatsApp booking link in the bio is the whole job and quick to show working.",
     "Your Maps listing sends patients to Instagram, where they have to DM to book. A booking link in the bio would cut that to one tap."),
    ("Creekside Dental & Implant Clinic", "Deira", 143, 3.8, "creeksidedental.example", "care@creeksidedental.example",
     ["low_rating", "no_chat"],
     "143 reviews at 3.8 points to a service or response problem, and patients have no chat or WhatsApp route to reach the clinic. Faster replies are the cheapest fix for both.",
     "At 143 reviews and 3.8 stars, a few slow replies are probably costing you more than they should. Do patients have any way to message the clinic directly?"),
    ("Palm View Dental", "Palm Jumeirah", 64, 4.6, "palmviewdental.example", "info@palmviewdental.example",
     ["no_viewport", "no_booking"],
     "A Palm Jumeirah clinic whose site does not scale on a phone and has no booking route. High-value patients, low-effort fixes, and a clear before and after.",
     "Your site does not resize on a phone and there is no way to book from it. For a Palm clinic most of that traffic will be mobile."),
    ("Mirdif Kids Dental", "Mirdif", 39, 4.8, "mirdifkidsdental.example", "smile@mirdifkidsdental.example",
     ["low_reviews", "no_booking"],
     "A children's clinic lives on parents booking between other things. There is no online booking and few reviews, and a post-visit WhatsApp review request would lift both.",
     "Parents booking for kids rarely want to phone during clinic hours. Have you considered letting them book and confirm over WhatsApp?"),
    ("Silicon Oasis Dental Care", "Dubai Silicon Oasis", 22, 4.5, "", "",
     ["no_site", "low_reviews"],
     "No website at all, so every search click that is not a phone call is lost. A single landing page with a WhatsApp booking button is Northlight's entry package.",
     "Your Maps listing has no website attached, so anyone who does not want to phone has nowhere to go. A one-page site with WhatsApp booking would close that."),
    ("Jumeirah Aesthetic Dentistry", "Jumeirah 1", 301, 4.9, "jumeirah-aesthetic.example", "concierge@jumeirah-aesthetic.example",
     ["no_ads_tags", "no_chat"],
     "The strongest profile in the set (301 reviews, 4.9) with no ad tracking and no chat. They can clearly afford growth work and are not doing the basics yet.",
     "301 reviews at 4.9 is the best profile I found in Jumeirah, and there is no ad tracking on the site. Are you relying on word of mouth alone?"),
    ("Karama Dental Point", "Al Karama", 57, 4.2, "karamadentalpoint.example", "info@karamadentalpoint.example",
     ["not_https", "stale:2019"],
     "A dated, insecure site is a credibility problem for a clinic. Lower priority than the others, but an easy conversation starter that leads into ads and booking.",
     "Browsers flag your site as 'Not secure' because it runs without https. That warning shows before a patient reads a word."),
]


def label_for(gap: str, reviews: int, rating: float) -> tuple[str, str]:
    key, _, arg = gap.partition(":")
    if key == "stale":
        return key, f"The footer copyright still reads {arg}."
    if key == "low_reviews":
        return key, f"{reviews} Google reviews, against {MEDIAN}."
    if key == "low_rating":
        return key, f"Rated {rating} on Google from {reviews} reviews."
    if key == "platform_site":
        return key, "The listing's website field points to a social or directory profile (https://instagram.example/drhana.ortho), not a site of their own."
    return key, LABELS[key]


def main() -> int:
    candidates, prospects = [], []
    for i, (name, area, reviews, rating, site, email, gaps, why, opener) in enumerate(BUSINESSES, 1):
        maps = f"https://maps.example/place/EXAMPLE{i:02d}"
        home = f"https://{site}/" if site else ""
        built = []
        for gap in gaps:
            key, label = label_for(gap, reviews, rating)
            built.append({"key": key, "label": label, "source_url": maps if key in ON_LISTING else home})
        key = site or f"listing-{i:02d}"
        candidates.append({
            "key": key, "name": name, "category": "Dental clinic", "address": f"{area}, Dubai",
            "maps_link": maps, "website": home, "phone": f"+971 4 555 01{i:02d}", "emails": [email] if email else [],
            "review_count": str(reviews), "review_rating": str(rating), "gaps": built,
        })
        prospects.append({"key": key, "gaps": [g["key"] for g in built], "why_fit": why, "opener": opener})
    spec = {
        "agency_domain": AGENCY_DOMAIN, "agency": "Northlight Growth", "niche": "dental clinics", "city": "Dubai",
        "summary": ("Northlight Growth sells WhatsApp booking flows and Google Ads management to clinics. Five Maps "
                    "searches across Dubai returned 58 dental clinics. These ten are established enough to have a "
                    "budget, and each shows a gap on its own listing or website that sits inside what Northlight "
                    "already delivers. This is an illustrative pack: the agency and every business are fictional."),
        "prospects": prospects,
    }
    SPEC.mkdir(exist_ok=True)
    (SPEC / f"{AGENCY_DOMAIN}.candidates.json").write_text(json.dumps(candidates, indent=1), encoding="utf-8")
    (SPEC / f"{AGENCY_DOMAIN}.pack.json").write_text(json.dumps(spec, indent=1), encoding="utf-8")
    return subprocess.call([sys.executable, str(HERE.parent / "src" / "pack.py"), "build", AGENCY_DOMAIN,
                            "--spec-dir", str(SPEC), "--out-dir", str(HERE)])


if __name__ == "__main__":
    sys.exit(main())
