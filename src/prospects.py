"""Sample-pack candidates: the allowed signals each prospect business shows, before verification.

    python src/prospects.py <agency-domain> --niche "dental clinic" --want no_site,stale,no_ads_tags
    python src/prospects.py <agency-domain> --signals queries/packs/<agency-domain>.signals.json

Reads data/raw/pack_<agency-domain>.csv and data/enriched/packs/<agency-domain>/*.json, then
writes data/scored/packs/<agency-domain>.candidates.json plus a readable digest. `--want` names
the signals this particular agency's services can act on; those count double when ranking.

Only the signals in signals.py are ever produced. What this step writes is a list of things worth
checking, read from Maps data and page source. None of it may be used until verify.py has confirmed
it in a rendered browser: pack.py refuses a candidate that has not been through it.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

import pandas as pd
from rich.console import Console

from common import ENRICHED, RAW, SCORED, log_run, utf8_stdout
from enrich import output_name
from signals import STALE_MAX_YEAR, WEIGHTS

console = Console()


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def snippet(text: str, match: re.Match) -> str:
    """The matched words with a little of what surrounds them, as they appear on the page."""
    start, end = max(0, match.start() - 25), min(len(text), match.end() + 120)
    return "…" + " ".join(text[start:end].split()) + "…"


def find_signal(rec: dict, sig: dict) -> tuple[str, str] | None:
    """Look for one custom fit signal. Returns (matched text, the URL it was seen on) or None.

    A signal is {"key", "headline", "label" (with a {match} slot), "pattern", "where": "text" or
    "emails", optional "kinds": [page kinds], optional "weight"}. Signals let a pack be built on
    what a prospect's own site says, for agencies whose buyers are not judged by website gaps.
    """
    pattern = re.compile(sig["pattern"], re.I)
    if sig.get("where") == "emails":
        for email in rec.get("contact", {}).get("emails", []):
            if pattern.search(email["email"]) and email.get("mx") is not False:
                return email["email"], email["source_url"]
        return None
    for page in rec.get("pages", []):
        if sig.get("kinds") and page["kind"] not in sig["kinds"]:
            continue
        match = pattern.search(page["text"])
        if match:
            return snippet(page["text"], match), page["url"]
    return None


def comparison_gaps(reviews: float | None, rating: float | None, pool: dict, link: str) -> list[dict]:
    """Review count and rating against the medians of the listings the pack's searches returned."""
    gaps = []
    median, peers = pool["median_reviews"], pool["peers"]
    if reviews is not None and median >= 20 and reviews < 0.5 * median:
        gaps.append({"key": "low_reviews", "source_url": link,
                     "detail": {"reviews": int(reviews), "median": int(median), "peers": peers}})
    typical = pool.get("median_rating")
    if rating is not None and typical and reviews and reviews >= 15 and rating < 4.0 and rating <= typical - 0.4:
        gaps.append({"key": "low_rating", "source_url": link,
                     "detail": {"rating": rating, "reviews": int(reviews), "median": typical, "peers": pool["rated_peers"]}})
    return gaps


def find_gaps(rec: dict, pool: dict, signals: list[dict] | None = None) -> list[dict]:
    """Allowed signals this business appears to show. Every one is unverified until verify.py runs."""
    maps, site = rec.get("maps", {}), rec.get("site", {})
    link, listed = maps.get("link", ""), maps.get("website", "")
    gaps: list[dict] = []

    def gap(key: str, source_url: str, **detail) -> None:
        gaps.append({"key": key, "source_url": source_url, "detail": detail})

    status = rec.get("status")
    if status == "no_website":
        gap("no_site", link)
    elif status in ("dead", "parked", "http_error", "placeholder"):
        gap("dead_site", link)
    elif status == "ok":
        home = site.get("final_url") or listed
        if not site.get("meta_pixel") and not site.get("google_ads_tag") and not site.get("gtm"):
            gap("no_ads_tags", home)
        year = site.get("copyright_year")
        if year and year <= STALE_MAX_YEAR:
            gap("stale", home, year=year)
        if site.get("https") is False:
            gap("not_https", link)

    for sig in signals or []:
        hit = find_signal(rec, sig)
        if hit:
            gaps.append({"key": sig["key"], "headline": sig["headline"], "weight": sig.get("weight", 3),
                         "label": sig["label"].format(match=hit[0]), "source_url": hit[1]})

    gaps += comparison_gaps(_num(maps.get("review_count")), _num(maps.get("review_rating")), pool, link)
    return gaps


def gap_score(gaps: list[dict], wanted: set[str]) -> int:
    return sum(g.get("weight") or WEIGHTS.get(g["key"], 0) * (2 if g["key"] in wanted else 1) for g in gaps)


def digest_text(candidates: list[dict], wanted: set[str], header: str, limit: int) -> str:
    """Compact view for the reasoning layer. Standard signals are shown by key, since their wording
    is fixed; custom signals show the matched text, because that text is the evidence."""
    relevant = [c for c in candidates if not wanted or any(g["key"] in wanted or "weight" in g for g in c["gaps"])]
    lines = [f"{header}; {len(relevant)} show a wanted signal\n"]
    for c in relevant[:limit]:
        lines.append(f"## {c['key']} | {c['name'][:60]} | {c['category']} | {c['review_count']} rev {c['review_rating']}★ "
                     f"| {c['address'][:45]} | site [{c['status']}] | {'phone' if c['phone'] else 'no phone'}, "
                     f"{c['emails'][0] if c['emails'] else 'no email'} | score {c['gap_score']}"
                     + (f" | VERIFIED {c['verified_on']}" if c.get("verified_on") else " | not verified"))
        lines.append("   signals: " + ", ".join(
            g["key"] + (f"({g['detail'].get('year')})" if g["key"] == "stale" else "") for g in c["gaps"] if "weight" not in g))
        lines.extend(f"   quote [{g['key']}]: {g['label'][:230]}" for g in c["gaps"] if "weight" in g)
    return "\n".join(lines) + "\n"


def main() -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("agency", help="the agency's domain; selects pack_<agency>.csv and its enriched folder")
    ap.add_argument("--niche", default="", help="plain-language niche, used in the review comparison wording")
    ap.add_argument("--want", default="", help="comma-separated signal keys this agency can act on (counted double)")
    ap.add_argument("--max-reviews", type=int, default=0, help="drop listings above this review count (chains)")
    ap.add_argument("--signals", type=Path, help="JSON file of custom fit signals for this agency")
    ap.add_argument("--require-signal", action="store_true", help="keep only prospects showing a custom signal")
    ap.add_argument("--min-reviews", type=int, default=3, help="drop listings below this review count")
    ap.add_argument("--digest", type=int, default=24, help="how many candidates to write to the digest")
    args = ap.parse_args()
    signals = json.loads(args.signals.read_text(encoding="utf-8")) if args.signals else None

    leads = pd.read_csv(RAW / f"pack_{args.agency}.csv", dtype=str).fillna("").to_dict("records")
    enriched_dir = ENRICHED / "packs" / args.agency
    wanted = {w.strip() for w in args.want.split(",") if w.strip()}
    unknown = wanted - set(WEIGHTS)
    if unknown:
        console.print(f"[red]Not an allowed signal: {sorted(unknown)}. Allowed: {sorted(WEIGHTS)}[/red]")
        return 2
    counts = [_num(lead["review_count"]) for lead in leads]
    counts = [c for c in counts if c is not None]
    median = statistics.median(counts) if counts else 0.0
    # A rating means little under 15 reviews, so the rating median is taken over the rest.
    ratings = [_num(lead["review_rating"]) for lead in leads if (_num(lead["review_count"]) or 0) >= 15]
    ratings = [r for r in ratings if r is not None]
    pool = {"median_reviews": median, "peers": len(counts), "rated_peers": len(ratings),
            "median_rating": round(statistics.median(ratings), 1) if ratings else None}

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
        if not (lead["phone"] or emails) or reviews < args.min_reviews or (args.max_reviews and reviews > args.max_reviews):
            dropped += 1
            continue
        if rec.get("status") in ("blocked", "platform_only"):
            dropped += 1  # nothing on the allowed list can be said about these
            continue
        gaps = find_gaps(rec, pool, signals)
        if not gaps or (signals and args.require_signal and not any("weight" in g for g in gaps)):
            dropped += 1
            continue
        candidates.append({
            "key": path.stem, "name": lead["title"], "category": lead["category"], "address": lead["address"],
            "maps_link": lead["link"], "website": rec.get("site", {}).get("final_url") or lead["website"],
            "listed_url": lead["website"], "niche": args.niche or "comparable", "pool": pool,
            "phone": lead["phone"], "emails": emails[:2], "review_count": lead["review_count"],
            "review_rating": lead["review_rating"], "query": lead["query"], "status": rec.get("status"),
            "site_title": rec.get("site", {}).get("title", ""), "gap_score": gap_score(gaps, wanted), "gaps": gaps,
        })
    candidates.sort(key=lambda c: (-c["gap_score"], -(_num(c["review_count"]) or 0)))

    out_dir = SCORED / "packs"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{args.agency}.candidates.json").write_text(json.dumps(candidates, ensure_ascii=False, indent=1), encoding="utf-8")
    header = f"# Candidates for {args.agency}: median reviews {int(median)} across {len(counts)} listings, not yet verified"
    (out_dir / f"{args.agency}.candidates.md").write_text(digest_text(candidates, wanted, header, args.digest), encoding="utf-8")

    summary = {"listings": len(leads), "candidates": len(candidates), "dropped": dropped, "median_reviews": int(median),
               "median_rating": pool["median_rating"]}
    log_run("python " + " ".join(["src/prospects.py"] + sys.argv[1:]), summary, redact=(args.agency,))
    console.print("[bold]prospects[/bold] " + ", ".join(f"{k}={v}" for k, v in summary.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
