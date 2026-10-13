"""Discovery: Google Maps queries -> data/raw/<name>.csv (stable schema, deduped by root domain).

    python src/discover.py --region gulf                  # the region's own searches, to data/raw/agencies_gulf.csv
    python src/discover.py --region uk --no-reviews       # another region: same code, another config file
    python src/discover.py queries/one.txt validation --email   # any list of searches, one per line

Engines:
    docker      gosom/google-maps-scraper in Docker (the preferred engine)
    playwright  built-in fallback driving the system's Edge/Chrome (src/maps_playwright.py)
    auto        docker when the daemon is running, otherwise playwright
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from common import RAW, ROOT, clean_url, is_platform, log_run, now_iso, region, root_domain, slugify, utf8_stdout

SCHEMA = [
    "title", "category", "categories", "website", "root_domain", "website_kind", "phone", "emails",
    "review_count", "review_rating", "address", "country", "latitude", "longitude", "place_id",
    "link", "query", "source", "engine", "scraped_at",
]
GOSOM_IMAGE = "gosom/google-maps-scraper"
console = Console()


def read_queries(path: Path) -> list[str]:
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    return [ln for ln in lines if ln and not ln.startswith("#")]


def docker_running() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=25).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def run_gosom(queries: list[str], name: str, depth: int, email: bool) -> tuple[list[dict], list[str]]:
    """Run gosom/google-maps-scraper in Docker and return its rows mapped onto our field names."""
    engine_dir = RAW / "_engine"
    engine_dir.mkdir(parents=True, exist_ok=True)
    query_file = engine_dir / f"{name}.queries.txt"
    result_file = engine_dir / f"{name}.gosom.csv"
    # "query #!#id" makes gosom echo the id back as input_id, so each row keeps its query.
    query_file.write_text("\n".join(f"{q} #!#{i}" for i, q in enumerate(queries)) + "\n", encoding="utf-8")
    result_file.unlink(missing_ok=True)

    # Mount the directory, not the file: Docker Desktop on Windows takes "C:/path:/container",
    # and a missing single-file mount would be silently created as a directory.
    mount = f"{engine_dir.resolve().as_posix()}:/gmapsdata"
    cmd = ["docker", "run", "--rm", "-e", "DISABLE_TELEMETRY=1", "-v", mount, GOSOM_IMAGE,
           "-depth", str(depth), "-c", "4", "-exit-on-inactivity", "3m",
           "-input", f"/gmapsdata/{query_file.name}", "-results", f"/gmapsdata/{result_file.name}"]
    if email:
        cmd.append("-email")
    # Stops Git Bash from rewriting the /gmapsdata arguments into Windows paths.
    env = dict(os.environ, MSYS_NO_PATHCONV="1", MSYS2_ARG_CONV_EXCL="*")
    console.print("[dim]$ " + " ".join(cmd) + "[/dim]")
    proc = subprocess.run(cmd, env=env)
    failures = [] if proc.returncode == 0 else [f"docker exited with code {proc.returncode}"]
    if not result_file.exists() or result_file.stat().st_size == 0:
        return [], failures + ["gosom produced no results file"]

    frame = pd.read_csv(result_file, dtype=str).fillna("")
    rows = []
    for rec in frame.to_dict("records"):
        idx = rec.get("input_id", "")
        rows.append({
            "title": rec.get("title", ""), "category": rec.get("category", ""),
            "categories": rec.get("category", ""), "website": rec.get("website", ""),
            "phone": rec.get("phone", ""), "emails": rec.get("emails", ""),
            "review_count": rec.get("review_count", ""), "review_rating": rec.get("review_rating", ""),
            "address": rec.get("address", ""), "country": "", "latitude": rec.get("latitude", ""),
            "longitude": rec.get("longitude", ""), "place_id": rec.get("place_id", ""),
            "link": rec.get("link", ""),
            "query": queries[int(idx)] if idx.isdigit() and int(idx) < len(queries) else "",
        })
    return rows, failures


def run_playwright(queries: list[str], depth: int, concurrency: int, reviews: bool) -> tuple[list[dict], list[str]]:
    from maps_playwright import discover

    def progress(kind: str, label: str, value) -> None:
        if kind == "query":
            console.print(f"  [cyan]{value:>3}[/cyan] results  {label}")

    channel = os.getenv("LEADFORGE_BROWSER", "msedge")
    return asyncio.run(discover(queries, depth=depth, concurrency=concurrency, reviews=reviews,
                                channel=channel, on_progress=progress))


def normalise(rows: list[dict], engine: str, source: str) -> list[dict]:
    stamp = now_iso()
    out = []
    for row in rows:
        if not row.get("title"):
            continue
        website = clean_url(row.get("website"))
        domain = root_domain(website)
        if not website:
            kind = "none"
        elif is_platform(domain):
            kind = "platform"  # a social or directory profile standing in for a website
        else:
            kind = "site"
        rec = {col: row.get(col, "") for col in SCHEMA}
        rec.update(website=website, root_domain=domain if kind == "site" else "", website_kind=kind,
                   emails=row.get("emails") or "", source=source, engine=engine, scraped_at=stamp)
        for col in ("review_count", "review_rating", "latitude", "longitude"):
            if rec[col] is None:
                rec[col] = ""
        out.append(rec)
    return out


def _reviews(rec: dict) -> float:
    try:
        return float(rec["review_count"])
    except (TypeError, ValueError):
        return -1.0


def dedupe(rows: list[dict]) -> list[dict]:
    """One row per root domain. Listings without a real site fall back to their place id."""
    kept: dict[str, dict] = {}
    for rec in rows:
        key = rec["root_domain"] or "place:" + (rec["place_id"] or slugify(rec["title"]) + rec["phone"])
        if key not in kept:
            kept[key] = dict(rec)
            continue
        winner = kept[key]
        queries = dict.fromkeys(q for q in (winner["query"].split(" | ") + [rec["query"]]) if q)
        if _reviews(rec) > _reviews(winner):  # the busier branch represents the business
            winner = kept[key] = dict(rec)
        winner["query"] = " | ".join(queries)
    return list(kept.values())


def add_emails(rows: list[dict]) -> list[str]:
    from enrich import quick_emails

    targets = [r["website"] for r in rows if r["website_kind"] == "site" and not r["emails"]]
    found, failures = asyncio.run(quick_emails(targets))
    for rec in rows:
        if rec["website"] in found:
            rec["emails"] = "; ".join(found[rec["website"]])
    return failures


def main() -> int:
    utf8_stdout()
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("queries", type=Path, nargs="?", help="text file, one Maps query per line")
    ap.add_argument("name", nargs="?", help="output name: writes data/raw/<name>.csv")
    ap.add_argument("--region", help="run the searches in config/regions/<region>.yaml; writes data/raw/agencies_<region>.csv")
    ap.add_argument("--engine", choices=["auto", "docker", "playwright"],
                    default=os.getenv("LEADFORGE_ENGINE", "auto"))
    ap.add_argument("--depth", type=int, default=1, help="scroll depth per query (default 1)")
    ap.add_argument("--concurrency", type=int, default=2, help="parallel searches, capped at 4")
    ap.add_argument("--email", action="store_true", help="fetch each site's homepage for published emails")
    ap.add_argument("--no-reviews", action="store_true", help="skip the place-page pass for review counts")
    ap.add_argument("--source", default="maps", help="value for the source column")
    args = ap.parse_args()

    if args.region:
        if args.queries or args.name:
            ap.error("give --region, or a queries file and a name, not both")
        queries, args.name = region(args.region)["queries"], f"agencies_{args.region.lower()}"
    elif args.queries and args.name:
        queries = read_queries(args.queries)
    else:
        ap.error("give --region, or a queries file and a name")
    if not queries:
        console.print(f"[red]No queries in {args.queries or 'that region'}[/red]")
        return 2
    engine = args.engine
    if engine == "auto":
        engine = "docker" if docker_running() else "playwright"
    elif engine == "docker" and not docker_running():
        console.print("[red]Docker is not installed or not running. Use --engine playwright.[/red]")
        return 2
    console.print(f"[bold]discover[/bold] {len(queries)} queries, engine={engine}, depth={args.depth}")

    command = "python " + " ".join(["src/discover.py"] + sys.argv[1:])
    # Sample-pack runs are named after the agency they are for; keep that out of the public log.
    redact = (args.name[5:],) if args.name.startswith("pack_") else ()
    try:
        if engine == "docker":
            raw, failures = run_gosom(queries, args.name, args.depth, args.email)
        else:
            raw, failures = run_playwright(queries, args.depth, args.concurrency, not args.no_reviews)
    except Exception as exc:
        if type(exc).__name__ != "GoogleBlocked":
            raise
        console.print(f"[red bold]Google blocked the session: {exc}. Stopping, not retrying.[/red bold]")
        log_run(command, {"queries": len(queries)}, [f"GoogleBlocked: {exc}"], notes="Run aborted.", redact=redact)
        return 3

    rows = normalise(raw, engine, args.source)
    unique = dedupe(rows)
    if args.email and engine != "docker":
        failures += add_emails(unique)

    RAW.mkdir(parents=True, exist_ok=True)
    out_path = RAW / f"{args.name}.csv"
    pd.DataFrame(unique, columns=SCHEMA).to_csv(out_path, index=False, encoding="utf-8")

    counts = {
        "queries": len(queries), "raw_rows": len(rows), "unique": len(unique),
        "with_site": sum(r["website_kind"] == "site" for r in unique),
        "platform_only": sum(r["website_kind"] == "platform" for r in unique),
        "no_website": sum(r["website_kind"] == "none" for r in unique),
        "with_email": sum(bool(r["emails"]) for r in unique),
        "with_review_count": sum(r["review_count"] != "" for r in unique),
    }
    log_run(command, counts, failures, notes=f"engine={engine}, output=data/raw/{args.name}.csv", redact=redact)

    table = Table(title=f"data/raw/{args.name}.csv")
    for key in counts:
        table.add_column(key, justify="right")
    table.add_row(*(str(v) for v in counts.values()))
    console.print(table)
    for failure in failures[:10]:
        console.print(f"[yellow]! {failure}[/yellow]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
