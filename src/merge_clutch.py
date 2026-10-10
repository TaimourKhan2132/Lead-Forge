"""Merge a hand-made Clutch shortlist into a discovery CSV.

    python src/merge_clutch.py data/raw/agencies_gulf.csv

Reads data/raw/clutch_shortlist.csv (columns: name,website), which the operator pastes in by
hand. Clutch itself is never scraped. Shortlisted agencies are tagged source=clutch, which puts
them first in line at every later stage. If the file is missing this is a no-op, not an error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from rich.console import Console

from common import RAW, clean_url, log_run, now_iso, root_domain, utf8_stdout
from discover import SCHEMA

console = Console()


def main() -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path, help="discovery CSV to merge into (rewritten in place)")
    ap.add_argument("--shortlist", type=Path, default=RAW / "clutch_shortlist.csv")
    args = ap.parse_args()

    if not args.shortlist.exists():
        console.print(f"[yellow]No {args.shortlist.name} yet. Nothing merged; continuing with Maps data.[/yellow]")
        return 0
    leads = pd.read_csv(args.csv, dtype=str).fillna("")
    shortlist = pd.read_csv(args.shortlist, dtype=str).fillna("")
    shortlist.columns = [c.strip().lower() for c in shortlist.columns]
    if not {"name", "website"} <= set(shortlist.columns):
        console.print("[red]clutch_shortlist.csv needs the columns: name,website[/red]")
        return 2

    retagged = added = skipped = 0
    for row in shortlist.to_dict("records"):
        website = clean_url(row["website"])
        domain = root_domain(website)
        if not domain:
            skipped += 1
            continue
        match = leads["root_domain"] == domain
        if match.any():
            leads.loc[match, "source"] = "clutch"
            retagged += 1
            continue
        new = {col: "" for col in SCHEMA}
        new.update(title=row["name"].strip(), website=website, root_domain=domain, website_kind="site",
                   source="clutch", engine="manual", scraped_at=now_iso())
        leads = pd.concat([leads, pd.DataFrame([new])], ignore_index=True)
        added += 1
    leads.to_csv(args.csv, index=False, encoding="utf-8")
    counts = {"shortlist_rows": len(shortlist), "added": added, "retagged_existing": retagged, "skipped_no_domain": skipped}
    log_run("python " + " ".join(["src/merge_clutch.py"] + sys.argv[1:]), counts)
    console.print("[bold]merge_clutch[/bold] " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
