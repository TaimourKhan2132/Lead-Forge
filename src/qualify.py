"""Qualification: validate the reasoning layer's verdicts and build the ranked summary.

    python src/qualify.py ingest data/scored/_batches/batch_01.json
    python src/qualify.py summary --top 15

The reasoning layer (an LLM, or a person) reads the digests from shortlist.py and returns one
verdict per lead. This script is the gate between that judgement and the rest of the pipeline:
it recomputes the score from the rubric, and rejects any verdict whose "why it fits" bullets
cite a URL the enrichment step never actually fetched. Evidence, or it does not get in.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.table import Table

from common import ENRICHED, SCORED, log_run, now_iso, utf8_stdout

RUBRIC = {"service_fit": 25, "size_fit": 20, "growth": 20, "reachability": 15, "geo_lang": 10, "hook": 10}
PENALTIES = {"offshore_dev_shop": -15, "outdated_site": -10, "no_contact_route": -20}
console = Console()


def tier_for(score: int) -> str:
    return "A" if score >= 70 else "B" if score >= 50 else "C"


def norm_url(url: str | None) -> str:
    """Compare URLs without scheme, "www." or a trailing slash."""
    return re.sub(r"^https?://(?:www\.)?", "", (url or "").strip().lower()).rstrip("/")


def known_urls(enriched: dict) -> set[str]:
    urls = {p["url"] for p in enriched.get("pages", [])}
    urls |= {e["source_url"] for e in enriched.get("evidence", []) if e.get("source_url")}
    urls.add(enriched.get("maps", {}).get("link", ""))
    urls |= set(enriched.get("contact", {}).get("socials", {}).values())
    return {norm_url(u) for u in urls if u}


def validate(verdict: dict, enriched: dict) -> list[str]:
    problems = []
    scores = verdict.get("scores", {})
    for key, cap in RUBRIC.items():
        value = scores.get(key)
        if not isinstance(value, int) or not 0 <= value <= cap:
            problems.append(f"scores.{key} must be an int in 0..{cap}, got {value!r}")
    for pen in verdict.get("penalties", []):
        if pen.get("name") not in PENALTIES:
            problems.append(f"unknown penalty {pen.get('name')!r}")
        elif not pen.get("reason"):
            problems.append(f"penalty {pen['name']} needs a reason")
    why = verdict.get("why_fit", [])
    if len(why) != 3:
        problems.append(f"why_fit needs exactly 3 bullets, got {len(why)}")
    urls = known_urls(enriched)
    for bullet in why:
        if norm_url(bullet.get("source_url")) not in urls:
            problems.append(f"why_fit cites a URL that was not fetched for this lead: {bullet.get('source_url')!r}")
    for key in ("their_icp", "best_angle", "next_action"):
        if not verdict.get(key):
            problems.append(f"missing {key}")
    email = verdict.get("contact_email", "unknown")
    if email != "unknown" and email not in {e["email"] for e in enriched.get("contact", {}).get("emails", [])}:
        problems.append(f"contact_email {email!r} was not found on the lead's site")
    return problems


def ingest(batch_path: Path) -> int:
    verdicts = json.loads(batch_path.read_text(encoding="utf-8"))
    written, failures = 0, []
    for verdict in verdicts:
        domain = verdict.get("domain", "")
        source = ENRICHED / f"{domain}.json"
        if not source.exists():
            failures.append(f"{domain}: no enriched record")
            continue
        enriched = json.loads(source.read_text(encoding="utf-8"))
        problems = validate(verdict, enriched)
        if problems:
            failures.extend(f"{domain}: {p}" for p in problems)
            continue
        penalty_total = sum(PENALTIES[p["name"]] for p in verdict.get("penalties", []))
        score = max(0, min(100, sum(verdict["scores"].values()) + penalty_total))
        maps = enriched.get("maps", {})
        record = {
            "domain": domain, "agency": verdict.get("agency") or enriched.get("name", ""),
            "score": score, "tier": tier_for(score), "source": enriched.get("source", "maps"),
            "scores": verdict["scores"], "penalties": verdict.get("penalties", []),
            "city": verdict.get("city", "unknown"), "their_icp": verdict["their_icp"],
            "why_fit": verdict["why_fit"], "risks": verdict.get("risks", []),
            "best_angle": verdict["best_angle"], "next_action": verdict["next_action"],
            "contact_email": verdict.get("contact_email", "unknown"),
            "contact_name": verdict.get("contact_name", "unknown"),
            "website": enriched.get("site", {}).get("final_url") or maps.get("website", ""),
            "maps_link": maps.get("link", ""), "scored_at": now_iso(),
            "scored_by": verdict.get("scored_by", "claude (in-session reasoning)"),
        }
        (SCORED / f"{domain}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        written += 1
    log_run(f"python src/qualify.py ingest {batch_path.as_posix()}",
            {"verdicts": len(verdicts), "written": written, "rejected": len(verdicts) - written}, failures)
    console.print(f"[bold]ingest[/bold] {batch_path.name}: written={written}, rejected={len(verdicts) - written}")
    for failure in failures:
        console.print(f"[red]! {failure}[/red]")
    return 1 if failures else 0


def load_scored() -> list[dict]:
    records = [json.loads(p.read_text(encoding="utf-8")) for p in SCORED.glob("*.json")]
    # Ties go to hand-picked Clutch leads, then to the stronger service fit.
    records.sort(key=lambda r: (-r["score"], r["source"] != "clutch", -r["scores"]["service_fit"], r["domain"]))
    return records


def summary(top: int) -> int:
    records = load_scored()
    rows = [{
        "rank": i, "domain": r["domain"], "agency": r["agency"], "score": r["score"], "tier": r["tier"],
        "source": r["source"], "city": r["city"], "their_icp": r["their_icp"], "best_angle": r["best_angle"],
        "contact_email": r["contact_email"], "contact_name": r["contact_name"],
        "next_action": r["next_action"], "risks": " | ".join(r["risks"]),
        "why_fit": " | ".join(f"{w['point']} ({w['source_url']})" for w in r["why_fit"]),
        "website": r["website"], "maps_link": r["maps_link"],
    } for i, r in enumerate(records, 1)]
    pd.DataFrame(rows).to_csv(SCORED / "summary.csv", index=False, encoding="utf-8")
    tiers = {t: sum(r["tier"] == t for r in records) for t in "ABC"}
    log_run(f"python src/qualify.py summary --top {top}", {"scored": len(records), **{f"tier_{k}": v for k, v in tiers.items()}})

    table = Table(title=f"Top {min(top, len(records))} of {len(records)} scored agencies  (A={tiers['A']} B={tiers['B']} C={tiers['C']})",
                  show_lines=True)
    for col, width in (("#", 3), ("Agency", 26), ("Score", 5), ("City", 10), ("Sells to", 34), ("Best angle", 54)):
        table.add_column(col, max_width=width, overflow="fold")
    for row in rows[:top]:
        table.add_row(str(row["rank"]), f"{row['agency']}\n[dim]{row['domain']}[/dim]", f"{row['score']} {row['tier']}",
                      row["city"], row["their_icp"], row["best_angle"])
    console.print(table)
    return 0


def main() -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_ingest = sub.add_parser("ingest", help="validate a batch of verdicts and write data/scored/<domain>.json")
    p_ingest.add_argument("batch", type=Path)
    p_summary = sub.add_parser("summary", help="write data/scored/summary.csv and print the top leads")
    p_summary.add_argument("--top", type=int, default=15)
    args = ap.parse_args()
    return ingest(args.batch) if args.cmd == "ingest" else summary(args.top)


if __name__ == "__main__":
    sys.exit(main())
