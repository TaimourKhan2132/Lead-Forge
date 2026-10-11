"""Sample packs: render "10 qualified prospects for <Agency>" as Markdown and printable HTML.

    python src/pack.py build <agency-domain>     # needs data/scored/packs/<agency-domain>.pack.json
    python src/pack.py fill                      # fill {{NAME}} etc. in packs, drafts and README from .env
    python src/pack.py fill --readme-no-email    # same, but keep your email out of the public README

The pack spec is the reasoning layer's selection: which ten candidates, which of their observed
gaps matter to this agency, why, and an opener line. Names, links, contact details and the gap
wording itself are pulled from the candidates file, never retyped, so a pack cannot state a
fact that the pipeline did not observe.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

from common import DRAFTS, PACKS, ROOT, SCORED, US_TRACK, log_run, utf8_stdout

PLACEHOLDERS = {"{{NAME}}": "LEADFORGE_NAME", "{{EMAIL}}": "LEADFORGE_EMAIL",
                "{{LINKEDIN}}": "LEADFORGE_LINKEDIN", "{{GITHUB}}": "LEADFORGE_GITHUB"}
HEADLINES = {
    "no_site": "No website", "platform_site": "Social profile instead of a website",
    "dead_site": "Website not loading", "no_booking": "No online booking",
    "booking_cta_only": "Booking is a form or a call", "no_chat": "No WhatsApp or chat",
    "no_ads_tags": "No ad tracking", "stale": "Stale site", "no_viewport": "Not mobile-ready",
    "not_https": "No https", "no_meta_description": "No meta description",
    "no_socials": "No socials linked", "no_email": "No email published",
    "low_reviews": "Few reviews", "low_rating": "Low rating",
}
console = Console()

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f4f2ee;color:#1d1d1b;font:15px/1.55 Georgia,'Times New Roman',serif}
.page{max-width:820px;margin:0 auto;padding:44px 40px 56px;background:#fff}
h1{font:700 27px/1.25 'Segoe UI',Helvetica,Arial,sans-serif;margin:0 0 6px;letter-spacing:-.01em}
.kicker{font:600 11px/1 'Segoe UI',Helvetica,Arial,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:#8a5a00;margin-bottom:14px}
.lede{font-size:16px;color:#3a3a36;margin:14px 0 26px}
table{width:100%;border-collapse:collapse;font:13px/1.4 'Segoe UI',Helvetica,Arial,sans-serif;margin-bottom:34px}
th{text-align:left;font-weight:600;color:#6b6b63;border-bottom:2px solid #1d1d1b;padding:6px 8px 6px 0}
td{border-bottom:1px solid #e3dfd6;padding:7px 8px 7px 0;vertical-align:top}
td.n,th.n{width:26px;color:#8a5a00;font-weight:700}
td.r{white-space:nowrap}
.card{border-top:2px solid #1d1d1b;padding:18px 0 22px;break-inside:avoid;page-break-inside:avoid}
.card h2{font:700 18px/1.3 'Segoe UI',Helvetica,Arial,sans-serif;margin:0 0 2px}
.card h2 span{color:#8a5a00;margin-right:8px}
.meta{font:13px/1.5 'Segoe UI',Helvetica,Arial,sans-serif;color:#55554f;margin-bottom:12px}
.meta a{color:#1a4f8b;text-decoration:none;border-bottom:1px solid #b9cbe0}
.label{font:600 11px/1 'Segoe UI',Helvetica,Arial,sans-serif;letter-spacing:.1em;text-transform:uppercase;color:#6b6b63;margin:14px 0 5px}
ul{margin:0;padding-left:18px}
li{margin-bottom:4px}
li a{font:12px 'Segoe UI',Helvetica,Arial,sans-serif;color:#1a4f8b;white-space:nowrap}
p{margin:0}
.opener{background:#faf6ec;border-left:3px solid #8a5a00;padding:10px 14px;font-style:italic}
footer{border-top:2px solid #1d1d1b;margin-top:10px;padding-top:14px;font:12px/1.6 'Segoe UI',Helvetica,Arial,sans-serif;color:#55554f}
footer strong{color:#1d1d1b}
@media print{body{background:#fff}.page{padding:0;max-width:none}a{color:inherit}}
@media (max-width:600px){.page{padding:26px 18px}td.c{display:none}}
"""


def _profile(c: dict) -> str:
    try:
        return f"{float(c['review_rating']):.1f}★ from {int(float(c['review_count']))} Google reviews"
    except (TypeError, ValueError):
        return "no Google rating yet"


def _headline(gap: dict) -> str:
    """Short label for the summary table. Custom signals carry their own."""
    return gap.get("headline") or HEADLINES[gap["key"]]


def _contact(c: dict) -> list[str]:
    return [x for x in [c.get("phone")] + list(c.get("emails", [])) if x]


def load_pack(agency: str, spec_dir: Path) -> tuple[dict, list[dict]]:
    spec = json.loads((spec_dir / f"{agency}.pack.json").read_text(encoding="utf-8"))
    candidates = {c["key"]: c for c in json.loads(
        (spec_dir / f"{agency}.candidates.json").read_text(encoding="utf-8"))}
    problems, rows = [], []
    if len(spec["prospects"]) != 10:
        problems.append(f"a pack needs exactly 10 prospects, got {len(spec['prospects'])}")
    for item in spec["prospects"]:
        cand = candidates.get(item["key"])
        if cand is None:
            problems.append(f"{item['key']}: not in the candidates file")
            continue
        observed = {g["key"]: g for g in cand["gaps"]}
        missing = [g for g in item["gaps"] if g not in observed]
        if missing or not item["gaps"]:
            problems.append(f"{item['key']}: gaps {missing or '(none listed)'} were not observed for this business")
            continue
        if not item.get("why_fit") or not item.get("opener"):
            problems.append(f"{item['key']}: needs why_fit and opener")
        rows.append({**cand, "chosen": [observed[g] for g in item["gaps"]],
                     "why_fit": item.get("why_fit", ""), "opener": item.get("opener", "")})
    if problems:
        raise ValueError("\n".join(problems))
    return spec, rows


def render_md(spec: dict, rows: list[dict], method: str) -> str:
    title = f"10 qualified prospects for {spec['agency']}: {spec['niche']}, {spec['city']}"
    out = [f"# {title}", "", spec["summary"], "", f"| # | Business | Google profile | {spec.get('table_label', 'Main gap')} |", "|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        out.append(f"| {i} | {r['name'].replace('|', '/')} | {_profile(r)} | {_headline(r['chosen'][0])} |")
    for i, r in enumerate(rows, 1):
        out += ["", f"## {i}. {r['name']}", "",
                f"- **Maps:** {r['maps_link']}",
                f"- **Website:** {r['website'] or 'none listed'}",
                f"- **Contact:** {' · '.join(_contact(r)) or 'unknown'}",
                f"- **Google profile:** {_profile(r)} · {r['category']}",
                f"- **{spec.get('gap_label', 'Observed gap')}:**"]
        out += [f"  - {g['label']} ([source]({g['source_url']}))" for g in r["chosen"]]
        out += [f"- **Why it fits {spec['agency']}:** {r['why_fit']}",
                f"- **Suggested opener:** \"{r['opener']}\""]
    out += ["", "---", "", f"Generated by LeadForge. {method}", "",
            "{{NAME}} · {{EMAIL}} · {{LINKEDIN}} · {{GITHUB}}", ""]
    return "\n".join(out)


def render_html(spec: dict, rows: list[dict], method: str) -> str:
    e = html.escape
    title = f"10 qualified prospects for {spec['agency']}: {spec['niche']}, {spec['city']}"
    table = "".join(
        f"<tr><td class=n>{i}</td><td>{e(r['name'])}</td><td class='r c'>{e(_profile(r))}</td>"
        f"<td>{e(_headline(r['chosen'][0]))}</td></tr>" for i, r in enumerate(rows, 1))
    cards = []
    for i, r in enumerate(rows, 1):
        site = f"<a href='{e(r['website'])}'>{e(r['website'].split('//')[-1].rstrip('/'))}</a>" if r["website"] else "no website listed"
        gaps = "".join(f"<li>{e(g['label'])} <a href='{e(g['source_url'])}'>source ↗</a></li>" for g in r["chosen"])
        cards.append(
            f"<section class=card><h2><span>{i:02d}</span>{e(r['name'])}</h2>"
            f"<div class=meta>{e(r['category'])} · {e(_profile(r))} · <a href='{e(r['maps_link'])}'>Google Maps</a> · {site}"
            f"<br>{e(' · '.join(_contact(r)) or 'contact unknown')}</div>"
            f"<div class=label>{e(spec.get('gap_label', 'Observed gap'))}</div><ul>{gaps}</ul>"
            f"<div class=label>Why it fits {e(spec['agency'])}</div><p>{e(r['why_fit'])}</p>"
            f"<div class=label>Suggested opener</div><p class=opener>{e(r['opener'])}</p></section>")
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{e(title)}</title><style>{CSS}</style></head><body><div class=page>"
        f"<div class=kicker>Prospect research · {e(spec['niche'])} · {e(spec['city'])}</div>"
        f"<h1>{e(title)}</h1><p class=lede>{e(spec['summary'])}</p>"
        "<table><thead><tr><th class=n>#</th><th>Business</th><th class=c>Google profile</th>"
        f"<th>{e(spec.get('table_label', 'Main gap'))}</th></tr></thead>"
        f"<tbody>{table}</tbody></table>{''.join(cards)}"
        f"<footer><strong>Generated by LeadForge.</strong> {e(method)}<br>"
        "{{NAME}} · {{EMAIL}} · {{LINKEDIN}} · {{GITHUB}}</footer></div></body></html>\n")


def build(agency: str, spec_dir: Path = SCORED / "packs", out_dir: Path = PACKS) -> int:
    try:
        spec, rows = load_pack(agency, spec_dir)
    except ValueError as exc:
        console.print(f"[red]Pack spec rejected:\n{exc}[/red]")
        return 1
    date = dt.date.today().strftime("%d %b %Y")
    method = spec.get("method", "").replace("{date}", date) or (
        f"Method: Google Maps searches for {spec['niche']} in {spec['city']} on {date}, one visit to each "
        "listed website (homepage and contact page), and page-source checks for booking, chat, WhatsApp "
        "and ad tags. Every gap links to the page it was observed on; anything that could not be checked "
        "was left out.")
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"{agency}.md").write_text(render_md(spec, rows, method), encoding="utf-8")
    (out_dir / f"{agency}.html").write_text(render_html(spec, rows, method), encoding="utf-8")
    if out_dir == PACKS:  # the bundled example is not a pipeline run
        log_run(f"python src/pack.py build {agency}", {"prospects": len(rows), "files": 2}, redact=(agency,))
    console.print(f"[bold]pack[/bold] wrote {out_dir.name}/{agency}.md and {out_dir.name}/{agency}.html")
    return 0


def fill(readme: bool = True, readme_email: bool = True) -> int:
    """Fill the placeholders. Packs and drafts are private; the README is the one public file."""
    if not (ROOT / ".env").exists():
        console.print("[red]No .env file. Copy .env.example to .env and put your details there, not in the example.[/red]")
        return 2
    load_dotenv(ROOT / ".env")
    values = {token: os.getenv(var, "").strip() for token, var in PLACEHOLDERS.items()}
    missing = [var for token, var in PLACEHOLDERS.items() if not values[token]]
    if missing:
        console.print(f"[yellow]Not set in .env, left as placeholders: {', '.join(missing)}[/yellow]")
    changed = 0
    targets = [*PACKS.glob("*.md"), *PACKS.glob("*.html"), *DRAFTS.glob("*.md"), *US_TRACK.glob("*.md")]
    if readme:
        path = ROOT / "README.md"
        text = original = path.read_text(encoding="utf-8")
        if not readme_email:
            text = text.replace(" · {{EMAIL}}", "")  # keep a personal address out of the public file
        for token, value in values.items():
            if value:
                text = text.replace(token, value)
        if text != original:
            path.write_text(text, encoding="utf-8")
            changed += 1
    for path in targets:
        text = original = path.read_text(encoding="utf-8")
        for token, value in values.items():
            if value:
                text = text.replace(token, value)
        if text != original:
            path.write_text(text, encoding="utf-8")
            changed += 1
    console.print(f"[bold]fill[/bold] updated {changed} file(s)")
    return 0


def main() -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_build = sub.add_parser("build", help="render one agency's pack")
    p_build.add_argument("agency")
    p_build.add_argument("--spec-dir", type=Path, default=SCORED / "packs")
    p_build.add_argument("--out-dir", type=Path, default=PACKS)
    p_fill = sub.add_parser("fill", help="fill the {{...}} placeholders from .env")
    p_fill.add_argument("--skip-readme", action="store_true", help="fill packs and drafts only")
    p_fill.add_argument("--readme-no-email", action="store_true",
                        help="fill the README but leave your email address out of it")
    args = ap.parse_args()
    if args.cmd == "fill":
        return fill(readme=not args.skip_readme, readme_email=not args.readme_no_email)
    return build(args.agency, args.spec_dir.resolve(), args.out_dir.resolve())


if __name__ == "__main__":
    sys.exit(main())
