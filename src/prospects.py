"""Sample-pack candidates: find observable gaps on each prospect business, with evidence.

    python src/prospects.py <agency-domain> --want no_booking,no_chat,low_reviews

Reads data/raw/pack_<agency-domain>.csv and data/enriched/packs/<agency-domain>/*.json, then
writes data/scored/packs/<agency-domain>.candidates.json plus a readable digest. Each gap is a
plain observation tied to the URL it was observed on. `--want` names the gaps this particular
agency's services can fix; those count double when ranking.

A gap only ever says what was looked at. "No booking system found on the homepage or contact
page" is a claim we can stand behind. "They have no online booking" is not, so it is never made.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

import pandas as pd
from rich.console import Console

from common import ENRICHED, RAW, SCORED, log_run, utf8_stdout
from enrich import output_name

THIS_YEAR = dt.date.today().year
WEIGHTS = {"no_site": 5, "platform_site": 5, "dead_site": 5, "no_booking": 4, "booking_cta_only": 2,
           "no_chat": 3, "no_ads_tags": 3, "stale": 3, "no_viewport": 3, "not_https": 2,
           "no_meta_description": 2, "no_socials": 2, "no_email": 1, "low_reviews": 3, "low_rating": 3}
console = Console()


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def find_gaps(rec: dict, median_reviews: float, peers: int, niche: str) -> list[dict]:
    maps, site = rec.get("maps", {}), rec.get("site", {})
    link, listed = maps.get("link", ""), maps.get("website", "")
    gaps: list[dict] = []

    def gap(key: str, label: str, url: str) -> None:
        gaps.append({"key": key, "label": label, "source_url": url})

    status = rec.get("status")
    if status == "no_website":
        gap("no_site", "The Google Maps listing has no website attached.", link)
    elif status == "platform_only":
        gap("platform_site", f"The listing's website field points to a social or directory profile ({listed}), not a site of their own.", link)
    elif status in ("dead", "parked", "http_error", "placeholder"):
        why = next((e["snippet"] for e in rec.get("evidence", []) if e["field"] == "site_status"), status)
        gap("dead_site", f"The website on their listing did not load when checked ({why}).", listed)
    elif status == "ok":
        home = site.get("final_url") or listed
        n_pages = len(rec.get("pages", []))
        scope = "the homepage and contact page" if n_pages > 1 else "the homepage"
        if not site.get("booking_system") and not site.get("booking_cta"):
            gap("no_booking", f"No online booking: no booking system and no 'book' call-to-action found on {scope}.", home)
        elif not site.get("booking_system"):
            gap("booking_cta_only", f"There is a 'book' call-to-action but no booking system in the page source of {scope}, so it most likely leads to a form or a phone call.", home)
        if not site.get("chat_widget") and not site.get("whatsapp_link"):
            gap("no_chat", f"No WhatsApp link and no chat widget in the page source of {scope}.", home)
        if not site.get("meta_pixel") and not site.get("google_ads_tag") and not site.get("gtm"):
            gap("no_ads_tags", f"No Meta Pixel, Google Ads tag or Tag Manager container in the page source of {scope}, so paid traffic is not being tracked there.", home)
        year = site.get("copyright_year")
        if year and year <= THIS_YEAR - 2:
            gap("stale", f"The footer copyright still reads {year}.", home)
        if site.get("has_viewport_meta") is False:
            gap("no_viewport", "The homepage has no mobile viewport tag, so it will not scale properly on phones.", home)
        if site.get("https") is False:
            gap("not_https", "The site is served over plain http, without https.", home)
        if not site.get("meta_description"):
            gap("no_meta_description", "The homepage has no meta description for search results.", home)
        if not rec.get("contact", {}).get("socials"):
            gap("no_socials", f"No social profiles are linked from {scope}.", home)
        if not rec.get("contact", {}).get("emails"):
            gap("no_email", f"No email address is published on {scope}.", home)

    reviews, rating = _num(maps.get("review_count")), _num(maps.get("review_rating"))
    if reviews is not None and median_reviews >= 20 and reviews < 0.5 * median_reviews:
        gap("low_reviews", f"{int(reviews)} Google reviews, against a median of {int(median_reviews)} across the {peers} {niche} listings these searches returned.", link)
    if rating is not None and reviews and reviews >= 15 and rating < 4.0:
        gap("low_rating", f"Rated {rating} on Google from {int(reviews)} reviews.", link)
    return gaps


def main() -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("agency", help="the agency's domain; selects pack_<agency>.csv and its enriched folder")
    ap.add_argument("--niche", default="", help="plain-language niche, used in the review comparison wording")
    ap.add_argument("--want", default="", help="comma-separated gap keys this agency can fix (counted double)")
    ap.add_argument("--max-reviews", type=int, default=0, help="drop listings above this review count (chains)")
    args = ap.parse_args()

    leads = pd.read_csv(RAW / f"pack_{args.agency}.csv", dtype=str).fillna("").to_dict("records")
    enriched_dir = ENRICHED / "packs" / args.agency
    wanted = {w.strip() for w in args.want.split(",") if w.strip()}
    unknown = wanted - set(WEIGHTS)
    if unknown:
        console.print(f"[red]Unknown gap keys: {sorted(unknown)}. Valid: {sorted(WEIGHTS)}[/red]")
        return 2
    counts = [_num(lead["review_count"]) for lead in leads]
    counts = [c for c in counts if c is not None]
    median = statistics.median(counts) if counts else 0.0

    candidates, dropped = [], 0
    for lead in leads:
        path = enriched_dir / f"{output_name(lead)}.json"
        if not path.exists():
            dropped += 1
            continue
        rec = json.loads(path.read_text(encoding="utf-8"))
        reviews = _num(lead["review_count"]) or 0
        emails = [e["email"] for e in rec.get("contact", {}).get("emails", []) if e["kind"] in ("generic", "named") and e["mx"] is not False]
        # A prospect has to be reachable and visibly trading, and small enough to need an agency.
        if not (lead["phone"] or emails) or reviews < 3 or (args.max_reviews and reviews > args.max_reviews):
            dropped += 1
            continue
        if rec.get("status") == "blocked":
            dropped += 1  # the site refused our request, so we know nothing about it
            continue
        gaps = find_gaps(rec, median, len(counts), args.niche or "comparable")
        if not gaps:
            dropped += 1
            continue
        score = sum(WEIGHTS[g["key"]] * (2 if g["key"] in wanted else 1) for g in gaps)
        candidates.append({
            "key": path.stem, "name": lead["title"], "category": lead["category"], "address": lead["address"],
            "maps_link": lead["link"], "website": rec.get("site", {}).get("final_url") or lead["website"],
            "phone": lead["phone"], "emails": emails[:2], "review_count": lead["review_count"],
            "review_rating": lead["review_rating"], "query": lead["query"], "status": rec.get("status"),
            "site_title": rec.get("site", {}).get("title", ""), "gap_score": score, "gaps": gaps,
            "home_excerpt": (rec["pages"][0]["text"][:260] if rec.get("pages") else ""),
        })
    candidates.sort(key=lambda c: -c["gap_score"])

    out_dir = SCORED / "packs"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{args.agency}.candidates.json").write_text(json.dumps(candidates, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# Candidates for {args.agency}: median reviews {int(median)} across {len(counts)} listings\n"]
    for c in candidates[:28]:
        lines.append(f"## {c['key']} | {c['name'][:70]}  (gap score {c['gap_score']})")
        lines.append(f"- {c['category']} | {c['review_count']} reviews, {c['review_rating']}★ | {c['address'][:80]} | query: {c['query'][:60]}")
        lines.append(f"- site: {c['website'] or 'none'} [{c['status']}] «{c['site_title'][:70]}» | phone {c['phone'] or 'none'} | email {', '.join(c['emails']) or 'none'}")
        lines.extend(f"  - [{g['key']}] {g['label']}" for g in c["gaps"])
        if c["home_excerpt"]:
            lines.append(f"- excerpt: {c['home_excerpt']}")
    (out_dir / f"{args.agency}.candidates.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = {"listings": len(leads), "candidates": len(candidates), "dropped": dropped, "median_reviews": int(median)}
    log_run("python " + " ".join(["src/prospects.py"] + sys.argv[1:]), summary, redact=(args.agency,))
    console.print("[bold]prospects[/bold] " + ", ".join(f"{k}={v}" for k, v in summary.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
