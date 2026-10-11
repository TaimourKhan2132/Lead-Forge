"""Turn a pasted job description into a 10-row sample and a short proposal.

    python src/sample.py --brief "Need a list of 300 dental clinics in Austin, Texas with phone, email and website"
    python src/sample.py --brief "..." --niche "dental clinic" --location "Austin, Texas"

It reads the niche, the location and the fields the job asks for, runs one Maps search (depth 1,
with the email lookup), enriches the results from each business's own site, and keeps the ten
rows that fill the most of the requested fields. It writes samples/<slug>.csv and a proposal of
120 words or fewer, samples/<slug>.md, that points at the attached sample.

The proposal says only what the sample shows. It never claims past clients, reviews or results,
and a field that cannot be sourced (an owner's name, say) is named as missing, not filled in.
Nothing is sent: the files are for you to attach and paste by hand.

Reading a brief is done with plain patterns, so it can misread one. It prints what it understood
before it searches; use --niche, --location and --fields to correct it.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys

import pandas as pd
from dotenv import dotenv_values
from rich.console import Console

from common import ENRICHED, ROOT, log_run, slugify, utf8_stdout
from discover import dedupe, normalise
from enrich import enrich_all, output_name

SAMPLES = ROOT / "samples"
SAMPLE_ROWS = 10
PROPOSAL_MAX_WORDS = 120
console = Console()

# Canonical field -> the words a brief uses for it. Order is the column order of the sample.
FIELDS = {
    "name": r"business names?|company names?|names?\b",
    "category": r"categor(?:y|ies)|business type|type of business|industry",
    "address": r"address(?:es)?|location|street|zip|postcode|postal code",
    "phone": r"phones?(?: numbers?)?|telephone|contact numbers?|mobile",
    "email": r"e-?mails?(?: address(?:es)?)?",
    "website": r"websites?|urls?|domains?|web address",
    "rating": r"ratings?|stars?",
    "review_count": r"review counts?|number of reviews|no\.? of reviews|reviews?",
    "whatsapp": r"whats\s?app",
    "instagram": r"instagram|\big\b",
    "facebook": r"facebook|\bfb\b",
    "linkedin": r"linkedin",
    "maps_link": r"google maps (?:link|url)|maps (?:link|url)|gmb|google business profile",
}
# Things briefs ask for that this pipeline cannot source honestly. Named in the proposal, never filled.
UNAVAILABLE = {
    "owner or decision-maker names": r"owner'?s?(?: names?)?|decision[- ]makers?|contact persons?|founder names?|ceo names?|manager names?",
    "personal or direct emails": r"personal e-?mails?|direct e-?mails?|owner'?s? e-?mails?",
    "revenue or employee counts": r"revenue|turnover|employee counts?|number of employees|headcount|company size",
    "opening hours": r"opening hours|business hours|working hours",
}
DEFAULT_FIELDS = ["name", "address", "phone", "email", "website", "rating", "review_count"]
NOT_PLACES = {"csv", "excel", "google sheets", "google sheet", "sheets", "english", "python", "json", "a spreadsheet",
              "total", "bulk", "advance", "full", "detail", "order", "one", "the", "this", "google maps", "maps"}
BANNED = [r"past clients?", r"previous clients?", r"my clients", r"clients? (?:love|say)", r"\b\d+\+? (?:happy )?clients",
          r"5[- ]star", r"top[- ]rated", r"reviews? (?:from|on) (?:upwork|fiverr)", r"years of experience", r"guarantee"]


def parse_brief(brief: str) -> dict:
    text = " ".join(brief.split())
    low = text.lower()
    fields = [name for name, pattern in FIELDS.items() if re.search(rf"\b(?:{pattern})", low)]
    # "reviews" inside "rating and reviews" is a field; "good reviews on my profile" is not a risk here.
    missing = [label for label, pattern in UNAVAILABLE.items() if re.search(rf"\b(?:{pattern})\b", low)]
    if "name" not in fields:
        fields.insert(0, "name")

    location = ""
    # No full stops inside a place name: "in Abu Dhabi. I need..." must stop at the sentence end.
    for match in re.finditer(r"\b(?:in|across|around|near|within|throughout)\s+((?:the\s+)?[A-Z][\w'-]*(?:,?\s+(?:[A-Z][\w'-]*|of|and|the)){0,4})", text):
        place = re.sub(r"[\s,]+(?:and|of|the)$", "", match.group(1)).strip(" ,.")
        if place.lower() not in NOT_PLACES and not place.lower().startswith(("csv", "excel", "google")):
            location = place
            break

    niche = ""
    stop = r"\s+(?:in|across|around|near|within|throughout|located|based|with|including|that|who|which|from)\b"
    for lead_in in (r"(?:list|lists|database|directory|leads|contacts|details|data|information|records)\s+(?:of|for|on)\s+",
                    r"(?:scrape|scraping|find|collect|extract|gather|compile|need|looking for)\s+"):
        match = re.search(lead_in + r"(?:all\s+|the\s+|local\s+|about\s+|around\s+|at least\s+)*(?:(\d[\d,]*)\+?\s+)?(.+?)" + stop, text, re.I)
        if match:
            niche = re.sub(r"^(?:all|the|local|a|an|some|someone to \w+)\s+", "", match.group(2).strip(" ,.-"), flags=re.I)
            if 2 < len(niche) < 60 and not re.search(r"\b(?:list|database|scraper|someone|freelancer|expert)\b", niche, re.I):
                quantity = match.group(1) or ""
                break
            niche = ""
    else:
        quantity = ""
    if not niche:
        quantity = ""
    wanted = re.search(r"\b(\d[\d,]*)\s*\+?\s+(?:[\w-]+\s+){0,3}?(?:leads|contacts|businesses|records|rows|listings|companies|entries|results)\b", low)
    return {"niche": niche, "location": location, "fields": fields or DEFAULT_FIELDS[:], "unavailable": missing,
            "quantity": quantity or (wanted.group(1) if wanted else "")}


def gather(query: str, slug: str) -> list[dict]:
    """One Maps search plus a light crawl of each listed site. Returns one flat row per business."""
    from maps_playwright import discover

    raw, failures = asyncio.run(discover([query], depth=1, concurrency=1, reviews=True))
    listings = dedupe(normalise(raw, "playwright", "sample"))
    out_dir = ENRICHED / "samples" / slug
    asyncio.run(enrich_all(listings, out_dir, "light", 8, force=False))
    rows = []
    for listing in listings:
        path = out_dir / f"{output_name(listing)}.json"
        record = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        contact = record.get("contact", {})
        emails = [e["email"] for e in contact.get("emails", []) if e["kind"] in ("generic", "named") and e["mx"] is not False]
        socials = contact.get("socials", {})
        rows.append({
            "name": listing["title"], "category": listing["category"], "address": listing["address"],
            "phone": listing["phone"], "email": emails[0] if emails else "",
            "website": listing["website"] if listing["website_kind"] == "site" else "",
            "rating": listing["review_rating"], "review_count": listing["review_count"],
            "whatsapp": (contact.get("whatsapp") or [{}])[0].get("number", ""),
            "instagram": socials.get("instagram", ""), "facebook": socials.get("facebook", ""),
            "linkedin": socials.get("linkedin", ""), "maps_link": listing["link"],
        })
    if failures:
        console.print(f"[yellow]{len(failures)} lookups failed; those cells are left blank.[/yellow]")
    return rows


def pick(rows: list[dict], fields: list[str]) -> list[dict]:
    def filled(row: dict) -> int:
        return sum(1 for f in fields if str(row.get(f, "")).strip() not in ("", "nan"))

    def reviews(row: dict) -> float:
        try:
            return float(row["review_count"])
        except (TypeError, ValueError):
            return 0.0

    return sorted(rows, key=lambda r: (-filled(r), -reviews(r)))[:SAMPLE_ROWS]


def words(text: str) -> int:
    return len(re.findall(r"[\w'’{}$%-]+", text))


def proposal(parsed: dict, rows: list[dict], slug: str, found: int) -> str:
    fields = parsed["fields"]
    name = (dotenv_values(ROOT / ".env").get("LEADFORGE_NAME") or "").strip() or "{{NAME}}"
    labels = {"review_count": "review count", "maps_link": "Maps link"}
    listed = ", ".join(labels.get(f, f) for f in fields)
    n = len(rows)

    def have(field: str) -> int:
        return sum(1 for r in rows if str(r.get(field, "")).strip() not in ("", "nan"))

    coverage = [f"{have(f)} of {n} have {'an' if f == 'email' else 'a'} {labels.get(f, f)}"
                for f in ("email", "phone", "website") if f in fields]
    target = f"the {parsed['quantity']} you asked for" if parsed["quantity"] else "the full list"
    parts = [
        "Hi,",
        f"You asked for {parsed['niche']} in {parsed['location']} with {listed}. I ran that search today and attached "
        f"a {n}-row sample ({slug}.csv), taken from {found} listings, so you can check the data before deciding.",
        ("In the sample, " + ", ".join(coverage) + ". " if coverage else "")
        + ("Emails come from each business's own website and are checked for a working mail server. I do not guess addresses."
           if "email" in fields else "Every row links back to its Google Maps listing."),
    ]
    optional = []
    if parsed["unavailable"]:
        optional.append("Not in the sample: " + "; ".join(parsed["unavailable"])
                        + ". I would leave a column out before filling it with guesses.")
    closing = [f"I can deliver {target} as a CSV or Google Sheet. How many rows do you need, and by when?", name]
    text = "\n\n".join(parts + optional + closing)
    if words(text) > PROPOSAL_MAX_WORDS:  # the honesty note is the one optional paragraph; shorten it before cutting it
        optional = ["Not in the sample: " + "; ".join(parsed["unavailable"]) + "."] if parsed["unavailable"] else []
        text = "\n\n".join(parts + optional + closing)
    for pattern in BANNED:
        if re.search(pattern, text, re.I):
            raise ValueError(f"proposal contains a banned claim: {pattern}")
    if words(text) > PROPOSAL_MAX_WORDS:
        raise ValueError(f"proposal is {words(text)} words (max {PROPOSAL_MAX_WORDS}); shorten the niche, location or field list")
    return text + "\n"


def main() -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--brief", required=True, help="the job description, pasted in quotes")
    ap.add_argument("--niche", default="", help="override the niche read from the brief")
    ap.add_argument("--location", default="", help="override the location read from the brief")
    ap.add_argument("--fields", default="", help=f"override the fields, comma-separated, from: {', '.join(FIELDS)}")
    ap.add_argument("--dry-run", action="store_true", help="only show what was read from the brief")
    args = ap.parse_args()

    parsed = parse_brief(args.brief)
    parsed["niche"] = args.niche.strip() or parsed["niche"]
    parsed["location"] = args.location.strip() or parsed["location"]
    if args.fields:
        parsed["fields"] = [f.strip() for f in args.fields.split(",") if f.strip() in FIELDS]
    console.print(f"[bold]sample[/bold] niche: [cyan]{parsed['niche'] or '?'}[/cyan] | location: [cyan]{parsed['location'] or '?'}[/cyan]"
                  f" | fields: {', '.join(parsed['fields'])}"
                  + (f" | cannot source: {'; '.join(parsed['unavailable'])}" if parsed["unavailable"] else "")
                  + (f" | quantity asked: {parsed['quantity']}" if parsed["quantity"] else ""))
    if not parsed["niche"] or not parsed["location"]:
        console.print("[red]Could not read the niche or the location from the brief. Pass --niche and --location.[/red]")
        return 2
    if args.dry_run:
        return 0

    query = f"{parsed['niche']} in {parsed['location']}"
    slug = slugify(query)[:60]
    try:
        rows = gather(query, slug)
    except Exception as exc:
        if type(exc).__name__ != "GoogleBlocked":
            raise
        console.print(f"[red bold]Google blocked the session: {exc}. Stopping, not retrying.[/red bold]")
        return 3
    if not rows:
        console.print(f"[red]No Maps listings for '{query}'. Try a broader niche or location.[/red]")
        return 1
    best = pick(rows, parsed["fields"])
    columns = parsed["fields"] + (["maps_link"] if "maps_link" not in parsed["fields"] else [])
    SAMPLES.mkdir(exist_ok=True)
    pd.DataFrame(best)[columns].to_csv(SAMPLES / f"{slug}.csv", index=False, encoding="utf-8")
    try:
        text = proposal(parsed, best, slug, len(rows))
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1
    (SAMPLES / f"{slug}.md").write_text(text, encoding="utf-8")

    counts = {"listings": len(rows), "sample_rows": len(best), "fields": len(parsed["fields"]),
              "with_email": sum(bool(r["email"]) for r in best), "proposal_words": words(text)}
    # The brief may name a client, so the log records that a brief was given, not what it said.
    log_run("python src/sample.py --brief <brief>", counts)
    console.print(f"wrote samples/{slug}.csv and samples/{slug}.md  ({counts['proposal_words']} words)")
    console.print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
