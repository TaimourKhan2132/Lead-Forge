"""US track: agencies that buy build work, not packs of local leads.

    python src/us_track.py prepare
    python src/enrich.py data/raw/us_track.csv --out data/enriched/us --kinds services,about,work,contact,team
    python src/us_track.py digest

These agencies sell to funded companies, not to businesses on Google Maps, so the Gulf rubric and
the sample-pack step do not apply to them. The job here is narrower: read each agency's own site,
find one specific thing worth opening with (a recent case study, the stack they use, a new
service), and record where it was seen. If nothing specific turns up, the digest says so.

`prepare` takes the rows marked track=us in data/raw/clutch_shortlist.csv. That file is pasted in
by hand; Clutch itself is never scraped.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

import pandas as pd
from rich.console import Console

from common import ENRICHED, RAW, clean_url, log_run, now_iso, root_domain, utf8_stdout
from discover import SCHEMA

US_ENRICHED = ENRICHED / "us"
STACK = (r"\b(Drupal|WordPress|Shopify|Webflow|Next\.js|React(?: Native)?|Vue|Angular|Node\.js|Django|Rails|Laravel|"
         r"Python|Go(?:lang)?|Rust|Kotlin|Swift|Flutter|AWS|Azure|GCP|Google Cloud|Snowflake|dbt|Airflow|BigQuery|"
         r"Postgres(?:QL)?|Neo4j|GraphQL|LangChain|LlamaIndex|OpenAI|Anthropic|Claude|n8n|Zapier|Make\.com|HubSpot|"
         r"Salesforce|Segment|Databricks|Kubernetes|Terraform|RAG|LLMs?|knowledge graphs?|vector (?:database|search))\b")
console = Console()


def prepare() -> int:
    path = RAW / "clutch_shortlist.csv"
    if not path.exists():
        console.print(f"[red]{path.name} not found in data/raw/.[/red]")
        return 2
    frame = pd.read_csv(path, dtype=str).fillna("")
    frame.columns = [c.strip().lower() for c in frame.columns]
    if "track" not in frame.columns:
        console.print("[red]The shortlist has no 'track' column, so no rows can be marked us.[/red]")
        return 2
    rows, meta = [], {}
    for rec in frame[frame["track"].str.strip().str.lower() == "us"].to_dict("records"):
        website = clean_url(rec.get("website"))
        domain = root_domain(website)
        if not domain:
            continue
        row = {col: "" for col in SCHEMA}
        row.update(title=rec["name"].strip(), website=website, root_domain=domain, website_kind="site",
                   emails=rec.get("email", "").strip(), address=rec.get("location", "").strip(),
                   source="clutch-us", engine="manual", scraped_at=now_iso())
        rows.append(row)
        meta[domain] = {"name": rec["name"].strip(), "email": rec.get("email", "").strip(),
                        "location": rec.get("location", "").strip(), "est_size": rec.get("est_size", "").strip()}
    pd.DataFrame(rows, columns=SCHEMA).to_csv(RAW / "us_track.csv", index=False, encoding="utf-8")
    (RAW / "us_track.meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    log_run("python src/us_track.py prepare", {"shortlist_rows": len(frame), "us_rows": len(rows)})
    console.print(f"[bold]us_track[/bold] wrote data/raw/us_track.csv with {len(rows)} agencies")
    return 0


def _clip(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n].rstrip() + "…"


def digest() -> int:
    meta = json.loads((RAW / "us_track.meta.json").read_text(encoding="utf-8"))
    blocks = []
    for path in sorted(US_ENRICHED.glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        info = meta.get(rec["domain"], {})
        lines = [f"## {rec['domain']} | {rec['name']} | {info.get('location') or '?'} | est. size {info.get('est_size') or '?'} "
                 f"| shortlist email: {info.get('email') or 'none'} | status {rec['status']} flags {rec.get('flags')}"]
        if rec["status"] != "ok":
            blocks.append("\n".join(lines))
            continue
        pages = {p["kind"]: p for p in rec["pages"]}
        lines.append("pages: " + ", ".join(f"{p['kind']}={p['url']}" for p in rec["pages"]))
        lines.append(f"title: {_clip(rec['site'].get('title'), 100)} | meta: {_clip(rec['site'].get('meta_description'), 200)}")
        lines.append("emails on site: " + (", ".join(f"{e['email']} [{e['kind']}] @ {e['source_url']}" for e in rec["contact"]["emails"][:4]) or "none")
                     + f" | linkedin: {rec['contact']['socials'].get('linkedin', 'none')}")
        lines.append("people: " + ("; ".join(f"{h['name']} «{_clip(h['snippet'], 90)}» @ {h['source_url']}" for h in rec["team"]["founder_hints"][:4]) or "none found"))
        stack = {}
        for p in rec["pages"]:
            for m in re.finditer(STACK, p["text"]):
                stack.setdefault(m.group(1), p["url"])
        lines.append("stack named in copy: " + (", ".join(f"{k} ({v.split('/', 3)[-1] or 'home'})" for k, v in list(stack.items())[:16]) or "none"))
        cases = next((e["snippet"] for e in rec["evidence"] if e["field"] == "case_study_count"), "")
        lines.append(f"case-study links ({rec['offer']['case_study_count']}): {cases or 'none'}")
        lines.append(f"dated content: {rec['site'].get('latest_dated_content', 'none')} | © {rec['site'].get('copyright_year')}")
        for kind, cap in (("home", 900), ("work", 1500), ("services", 700), ("about", 800), ("team", 500), ("contact", 300)):
            if kind in pages:
                lines.append(f"{kind} text: {_clip(pages[kind]['text'], cap)}")
        blocks.append("\n".join(lines))
    out = US_ENRICHED / "_digest.md"
    out.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    console.print(f"[bold]us_track[/bold] wrote {out.relative_to(ENRICHED.parent.parent).as_posix()} for {len(blocks)} agencies")
    return 0


def main() -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["prepare", "digest"])
    args = ap.parse_args()
    return prepare() if args.cmd == "prepare" else digest()


if __name__ == "__main__":
    sys.exit(main())
