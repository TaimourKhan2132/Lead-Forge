"""Shortlist: rank enriched leads with cheap rules and write digests for the reasoning layer.

    python src/shortlist.py --top 80

The rule-based number here is only a triage order. It decides which leads are worth an LLM's
(or a human's) attention and nothing else: the real score comes from qualify.py. Each digest
is a compact, evidence-first view of one enriched JSON, batched ten at a time.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
from rich.console import Console

from common import ENRICHED, SCORED, log_run, utf8_stdout

GULF = {"AE", "SA", "QA"}
GULF_WORDS = ("united arab emirates", "dubai", "abu dhabi", "sharjah", "ajman", "saudi", "riyadh",
              "jeddah", "qatar", "doha", "uae", "ksa")
FIT_SERVICES = {"seo", "paid_ads", "social_media", "web_design_dev", "ecommerce", "lead_generation", "crm",
                "automation", "ai", "chatbots", "email_marketing", "content", "branding", "software_dev",
                "app_dev", "data_analytics"}
THIS_YEAR = dt.date.today().year
console = Console()


def in_gulf(rec: dict) -> bool:
    maps = rec.get("maps", {})
    if maps.get("country"):
        return maps["country"] in GULF
    return any(word in (maps.get("address") or "").lower() for word in GULF_WORDS)


def months_since(date_str: str | None) -> float | None:
    try:
        then = dt.date.fromisoformat((date_str or "")[:10])
    except ValueError:
        return None
    return (dt.date.today() - then).days / 30.4


def triage(rec: dict) -> tuple[int, str]:
    """Return (points, skip_reason). A non-empty skip_reason removes the lead from the shortlist."""
    if rec.get("status") != "ok":
        return 0, f"site {rec.get('status')}"
    if not in_gulf(rec):
        return 0, "outside UAE/KSA/Qatar"
    big = {b["signal"] for b in rec.get("big_company", [])}
    if staff_counter(rec) > 50:
        big.add("staff_over_50")
    if big & {"staff_over_50", "multi_country_offices"}:
        return 0, "big-company signal: " + ", ".join(sorted(big))
    services = {k: v for k, v in rec["offer"]["services"].items() if k in FIT_SERVICES and v >= 2}
    if not services:
        return 0, "no relevant services found in site copy"

    points = min(25, 5 * len(services))
    hints = [h["number"] for h in rec["team"]["size_hints"]]
    cards = (rec["team"].get("team_cards") or {}).get("count")
    size = min(hints) if hints else cards
    points += 10 if size is None else 20 if 2 <= size <= 15 else 12 if size <= 30 else 5

    growth = 0
    if rec["hiring"]["roles"] or rec["hiring"]["signals"]:
        growth += 8
    if rec["offer"]["case_study_count"] >= 3:
        growth += 6
    age = months_since(rec["site"].get("latest_dated_content"))
    if age is not None and age <= 6:
        growth += 6
    points += min(20, growth)

    emails = [e for e in rec["contact"]["emails"] if e["kind"] in ("named", "generic") and e["mx"] is not False]
    reach = (7 if emails else 0) + (4 if any(e["kind"] == "named" for e in emails) or rec["team"]["founder_hints"] else 0)
    reach += (2 if rec["contact"]["whatsapp"] else 0) + (2 if "linkedin" in rec["contact"]["socials"] else 0)
    points += min(15, reach)
    points += 6 + (4 if (rec["site"].get("lang") or "en").startswith("en") else 0)
    points += 5

    if len({h["place"] for h in rec.get("offshore_hints", [])}) >= 2:
        points -= 8
    year = rec["site"].get("copyright_year")
    if year and year <= THIS_YEAR - 2:
        points -= 10
    if not emails and not rec["contact"]["whatsapp"]:
        points -= 20
    if "global_footprint" in big:
        points -= 10
    try:
        if float(rec["maps"].get("review_count") or 0) > 300:
            points -= 5
    except ValueError:
        pass
    return max(points, 0), ""


def _clip(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n].rstrip() + "…"


def _path(url: str) -> str:
    """Path part of a URL. Digests print the site's base once, then paths."""
    rest = url.split("//", 1)[-1]
    return "/" + rest.split("/", 1)[1] if "/" in rest else "/"


STAFF_COUNTER = re.compile(
    r"(?:team members?|employees|staff|professionals|experts|specialists)\s*:?\s*([1-9]\d{1,3})\s*\+"
    r"|([1-9]\d{1,3})\s*\+\s*(?:team members?|employees|staff|professionals|experts|specialists)", re.I)


def staff_counter(rec: dict) -> int:
    """Largest "Team members 80+" style counter on the fetched pages, or 0."""
    best = 0
    for page in rec.get("pages", []):
        for match in STAFF_COUNTER.finditer(page["text"]):
            best = max(best, int(match.group(1) or match.group(2)))
    return best


def digest(rec: dict, points: int) -> str:
    maps, site, contact, team, hiring = rec["maps"], rec["site"], rec["contact"], rec["team"], rec["hiring"]
    pages = {p["kind"]: p for p in rec["pages"]}
    base = "/".join(rec["pages"][0]["url"].split("/")[:3])
    lines = [f"## {rec['domain']} | {_clip(rec['name'], 60)}  (triage {points}, source={rec.get('source', 'maps')})"]
    lines.append(f"maps: {maps.get('category')} | {maps.get('review_count') or '?'} reviews {maps.get('review_rating') or '?'}★ | "
                 f"{_clip(maps.get('address'), 70)} | q: {_clip(maps.get('query'), 60)}")
    lines.append(f"base: {base} | pages: " + ", ".join(f"{p['kind']}={_path(p['url'])}" for p in rec["pages"]))
    lines.append(f"title: {_clip(site.get('title'), 90)} | meta: {_clip(site.get('meta_description'), 150)}")
    lines.append("emails: " + (", ".join(f"{e['email']} [{e['kind'][0]}{'' if e['mx'] else ' NO-MX'}]" for e in contact["emails"][:4]) or "none")
                 + f" | wa: {'yes' if contact['whatsapp'] else 'no'} | li: {contact['socials'].get('linkedin', 'none')}"
                 + f" | socials: {','.join(k for k in contact['socials'] if k != 'linkedin') or 'none'}")
    lines.append("services: " + ", ".join(f"{k}×{v}" for k, v in list(rec["offer"]["services"].items())[:7])
                 + " | industries: " + (", ".join(f"{k}×{v}" for k, v in list(rec["offer"]["industries"].items())[:5]) or "none")
                 + f" | cases: {rec['offer']['case_study_count']}")
    size = "; ".join(f"{h['number']} «{_clip(h['snippet'], 70)}» ({_path(h['source_url'])})" for h in team["size_hints"][:2]) or "none"
    cards = team.get("team_cards")
    founders = "; ".join(f"{h['name']} «{_clip(h['snippet'], 60)}» ({_path(h['source_url'])})" for h in team["founder_hints"][:3]) or "none"
    lines.append(f"team: size {size} | cards: " + (f"{cards['count']} ({_path(cards['source_url'])})" if cards else "none")
                 + f" | staff counter: {staff_counter(rec) or 'none'} | founders: {founders}")
    lines.append(f"hiring: careers={_path(hiring['careers_page']) if hiring.get('careers_page') else 'none'} | roles: "
                 + (", ".join(hiring["roles"][:4]) or "none") + (" | SAYS NO OPENINGS" if hiring.get("says_no_openings") else "")
                 + " | wording: " + ("; ".join(f"«{_clip(s['snippet'], 60)}» ({_path(s['source_url'])})" for s in hiring["signals"][:1]) or "none"))
    lines.append("tools: " + (", ".join(f"{k}({'copy' if v == 'mentioned' else 'src'})" for k, v in rec["tools"].items()) or "none")
                 + f" | site: ©{site.get('copyright_year')} dated={site.get('latest_dated_content', '?')} lang={site.get('lang') or '?'}"
                 f" ar={site.get('arabic_ratio')} chat={site.get('chat_widget')} book={site.get('booking_system')}"
                 f" pixel={site.get('meta_pixel')} flags={rec.get('flags')}")
    if rec.get("big_company") or rec.get("offshore_hints"):
        lines.append("caution: " + "; ".join(
            [f"{b['signal']} «{_clip(b['snippet'], 70)}»" for b in rec.get("big_company", [])] +
            [f"{o['place']} «{_clip(o['snippet'], 60)}»" for o in rec.get("offshore_hints", [])[:2]]))
    lines.append(f"home: {_clip(pages['home']['text'], 330)}")
    if "about" in pages:
        lines.append(f"about: {_clip(pages['about']['text'], 330)}")
    return "\n".join(lines)


def main() -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--enriched", type=Path, default=ENRICHED)
    ap.add_argument("--top", type=int, default=80, help="how many leads go forward to qualification")
    ap.add_argument("--batch", type=int, default=10)
    ap.add_argument("--domains", default="", help="only these domains (comma-separated), e.g. after a re-crawl")
    ap.add_argument("--name", default="batch", help="prefix for the digest files; use with --domains")
    args = ap.parse_args()
    only = {d.strip().lower() for d in args.domains.split(",") if d.strip()}

    rows, skipped = [], Counter()
    records = {}
    for path in sorted(args.enriched.glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        if only and (rec.get("domain") or path.stem).lower() not in only:
            continue
        points, reason = triage(rec)
        if reason:
            skipped[reason.split(":")[0]] += 1
        records[rec["domain"] or path.stem] = rec
        rows.append({"domain": rec["domain"] or path.stem, "name": rec.get("name", ""),
                     "source": rec.get("source", "maps"), "triage": points, "skip_reason": reason})
    # Clutch leads are hand-picked by the operator, so they go first whenever they are usable.
    rows.sort(key=lambda r: (bool(r["skip_reason"]), r["source"] != "clutch", -r["triage"]))
    SCORED.mkdir(parents=True, exist_ok=True)
    # A partial run must not overwrite the full triage table or the main digest batches.
    pd.DataFrame(rows).to_csv(SCORED / ("_triage.csv" if not only else f"_triage_{args.name}.csv"),
                              index=False, encoding="utf-8")

    chosen = [r for r in rows if not r["skip_reason"]][:args.top]
    digest_dir = SCORED / "_digests"
    digest_dir.mkdir(exist_ok=True)
    for old in digest_dir.glob(f"{args.name}_*.md"):
        old.unlink()
    for i in range(0, len(chosen), args.batch):
        batch = chosen[i:i + args.batch]
        body = "\n\n".join(digest(records[r["domain"]], r["triage"]) for r in batch)
        (digest_dir / f"{args.name}_{i // args.batch + 1:02d}.md").write_text(body + "\n", encoding="utf-8")

    counts = {"enriched": len(rows), "eligible": sum(not r["skip_reason"] for r in rows),
              "shortlisted": len(chosen), "batches": -(-len(chosen) // args.batch)}
    command = "python " + " ".join(["src/shortlist.py"] + sys.argv[1:])
    if args.domains:  # the public log must not name the agencies being looked at
        command = command.replace(args.domains, f"<{len(only)} domains>")
    log_run(command, counts,
            notes="skipped: " + (", ".join(f"{k}={v}" for k, v in skipped.most_common()) or "none"))
    console.print("[bold]shortlist[/bold] " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    for reason, n in skipped.most_common():
        console.print(f"  skipped {n:>3}  {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
