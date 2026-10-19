"""The job ask: a second offer. The operator asks an agency for part-time remote work.

    python src/jobs.py scan [<agency-domain> ...]     # read each candidate's homepage and careers page, today
    python src/jobs.py build [<agency-domain> ...]    # render and lint outreach/jobs/<agency-domain>.md
    python src/jobs.py quotes [<agency-domain> ...]   # are the words each opener rests on still on the page?
    python src/jobs.py followups [<agency-domain> ...] # rewrite only the follow-ups, sent drafts included

An agency gets one offer. A job ask goes only to an agency that has never been emailed, is not on the
skip list and has no lead-pack draft waiting to go.

The wording is the operator's own and is not in this repository. outreach/job_ask.json holds the
subject, the pitch, the three proof lines and the follow-ups; examples/job_ask.example.json shows the
shape. What is written per agency is the spec, data/scored/jobs/<agency-domain>.job.json:

    opener        one factual sentence about the agency, saying no more than the quoted words do. Prefer a
                  named case study, client or project; fall back to the services it lists only when
                  nothing else on the site can be quoted
    line1_checks  [{"url", "quotes"}]: the exact words the opener rests on and the page they are on
    type          the proof line to use: A marketing, B AI and software, C web development
    hiring        {"url", "role", "status", "relevance", "fits", "posted", "score"}: a role on the agency's
                  own careers page or job system, as hiring.py read it. status is fresh (a posting date in
                  the last 60 days), undated, or talent_pool (a list of roles the agency would like to hear
                  about, not an opening)
    first_name    only with full_name and name_source, the page on the agency's site that names the person

When the role fits, the opener names it instead, worded to match its status: only a fresh role is
"hiring"; an undated one is "the role on your careers page"; a talent-pool one is "listed among the
roles". The line offering help before the hire is added for a fresh or undated role, not for a
talent pool, where no hire has been announced. An agency with no quotable fact gets no email:
`build` refuses a spec without quoted evidence.

Nothing is sent. Each file is for a person to read, check, copy and send by hand.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dotenv import dotenv_values
from rich.console import Console

import draft
from common import (ENRICHED, JOBS, ROOT, SCORED, job_wording, log_run, outreach_open, region_of, root_domain,
                    utf8_stdout)
from lint_drafts import lint_job
from track import connect, skipped_domains

SPECS = SCORED / "jobs"
TYPES = {"A": "marketing, SEO, ads", "B": "AI, automation, software", "C": "web development"}
NEXT_PROOF = {"A": "B", "B": "C", "C": "B"}  # follow-up 1 shows a proof line the first email did not
OPENERS = {"fresh": "hiring_opener", "undated": "undated_opener", "talent_pool": "talent_pool_opener"}
FRESH_DAYS = 60  # a role is "hiring" only with a posting date this recent
CAREERS_LINK = re.compile(r"career|\bjobs?\b|join[-_ ]?(?:us|our)|vacanc|hiring|work[-_ ]?(?:with|for)[-_ ]?us|open[-_ ]?(?:positions|roles)", re.I)
TEXT_CAP = 12_000
console = Console()


def refusal(domain: str, conn) -> str:
    """Why this agency may not be sent a job ask, or ''."""
    if domain in skipped_domains():
        return "it is on the skip list"
    if not outreach_open(region_record(domain)):
        return "its region is scored only: nothing is drafted for it yet"
    lead = conn.execute("SELECT * FROM leads WHERE domain = ?", (domain,)).fetchone()
    if lead and lead["status"] != "drafted":
        return f"it has already been emailed (status: {lead['status']})"
    if lead and lead["offer"] == "lead_pack" and not lead["blocked"]:
        return "it has a lead-pack draft waiting to go, and an agency gets one offer"
    return ""


def region_record(domain: str) -> dict:
    """The scored record, or for a company that was never scored, the region its listing is in."""
    scored, enriched = SCORED / f"{domain}.json", ENRICHED / f"{domain}.json"
    if scored.exists():
        return json.loads(scored.read_text(encoding="utf-8"))
    maps = json.loads(enriched.read_text(encoding="utf-8")).get("maps", {}) if enriched.exists() else {}
    return {"region": region_of(maps)}


def candidates() -> list[str]:
    """Every scored agency that could still be sent a job ask, best score first."""
    conn = connect()
    try:
        records = [json.loads(path.read_text(encoding="utf-8")) for path in SCORED.glob("*.json")]
        records = [r for r in records if "@" in r.get("contact_email", "") and not refusal(r["domain"], conn)]
    finally:
        conn.close()
    return [r["domain"] for r in sorted(records, key=lambda r: (-r["score"], r["domain"]))]


# ----- scan: what the agency's own site shows today -----

def careers_links(html: str, base: str) -> list[str]:
    """Links on a page that look like a careers or jobs page on the same site."""
    found = []
    for a in BeautifulSoup(html, "lxml").find_all("a", href=True):
        url = urljoin(base, a["href"]).split("#")[0]
        if not url.startswith("http") or root_domain(url) != root_domain(base):
            continue
        path = url.split("://", 1)[1].partition("/")[2]
        if (CAREERS_LINK.search(path) or CAREERS_LINK.search(a.get_text(" ", strip=True)[:40])) and "/blog" not in url:
            found.append(url)
    return list(dict.fromkeys(found))


async def _scan(domains: list[str], channel: str) -> dict[str, dict]:
    from playwright.async_api import async_playwright

    from verify import visit
    out: dict[str, dict] = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel=channel, headless=True)
        context = await browser.new_context(locale="en-US", viewport={"width": 1280, "height": 900}, ignore_https_errors=True)
        sem = asyncio.Semaphore(4)  # at most four pages open at once, across every site

        async def read(url: str, kind: str) -> dict:
            async with sem:
                seen = await visit(context, url)
            page = {"url": url, "kind": kind, "state": seen["state"], "why": seen.get("why") or seen.get("how", "")}
            if seen["state"] == "ok":
                page.update(final_url=seen["final_url"], title=seen["title"], text=seen["text"][:TEXT_CAP], html=seen["html"])
            return page

        async def one(domain: str) -> None:
            record = json.loads((SCORED / f"{domain}.json").read_text(encoding="utf-8"))
            home = await read(record["website"], "home")
            links = careers_links(home.pop("html"), home["final_url"]) if home["state"] == "ok" else []
            enriched = ENRICHED / f"{domain}.json"
            known = json.loads(enriched.read_text(encoding="utf-8")).get("hiring", {}).get("careers_page") if enriched.exists() else None
            if known and "/blog" not in known and known not in links:
                links.append(known)
            pages = [home] + [await read(url, "careers") for url in links[:2]]  # depth 1: only pages the homepage links to
            for page in pages:
                page.pop("html", None)
            out[domain] = {"domain": domain, "scanned_on": dt.date.today().isoformat(), "pages": pages}

        try:
            await asyncio.gather(*(one(domain) for domain in domains))
        finally:
            await browser.close()
    return out


def scan(domains: list[str]) -> int:
    picked = domains or candidates()
    results = asyncio.run(_scan(picked, os.getenv("LEADFORGE_BROWSER", "msedge")))
    SPECS.mkdir(parents=True, exist_ok=True)
    unread = with_careers = 0
    for domain in picked:
        result = results[domain]
        (SPECS / f"{domain}.pages.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        home, careers = result["pages"][0], [p for p in result["pages"][1:] if p["state"] == "ok"]
        unread += home["state"] != "ok"
        with_careers += bool(careers)
        shown = ", ".join(p["url"] for p in careers) or "no careers page read"
        console.print(f"[{'green]ok    ' if home['state'] == 'ok' else 'yellow]unread'}[/] {domain}: {home['why'] or shown}")
    log_run("python src/jobs.py scan", {"agencies": len(picked), "homepage_unread": unread, "careers_page_read": with_careers},
            notes="A homepage that would not load is left unread; that agency gets no email until it can be read.")
    return 0


# ----- build: one draft per agency -----

def article(role: str) -> str:
    return "an" if role[:1].lower() in "aeiou" else "a"


def status(spec: dict) -> str:
    """fresh, undated or talent_pool for a role the careers page shows; none when it shows no role."""
    hiring = spec.get("hiring") or {}
    return hiring.get("status", "undated") if hiring.get("role") else "none"


def variant(spec: dict) -> bool:
    """The opener names the role only when that role is work the operator could take on."""
    hiring = spec.get("hiring") or {}
    return bool(hiring.get("role") and hiring.get("fits") and status(spec) in OPENERS)


def named_opener(spec: dict, wording: dict) -> str:
    """Only a fresh role is "hiring". An undated one is on the careers page; a talent-pool one is listed."""
    role = spec["hiring"]["role"]
    return wording[OPENERS[status(spec)]].format(a=article(role), role=role)


def opener_checks(spec: dict) -> list[dict]:
    """The words the opener rests on: quoted from the site, or the role's title on the careers page."""
    hiring = spec.get("hiring") or {}
    return [{"url": hiring["url"], "quotes": [hiring["role"]]}] if variant(spec) else spec.get("line1_checks", [])


def checks(spec: dict) -> list[dict]:
    """Everything the email relies on: the opener's words, a listed role, and the name it greets."""
    hiring = spec.get("hiring") or {}
    role = [{"url": hiring["url"], "quotes": [hiring["role"]]}] if hiring.get("role") and not variant(spec) else []
    name = [{"url": spec["name_source"], "quotes": [spec["full_name"]]}] if spec.get("first_name") else []
    return opener_checks(spec) + role + name


def problems(spec: dict, conn) -> list[str]:
    """Reasons a spec may not become an email. An agency with any of these is dropped, not patched."""
    out = []
    refused = refusal(spec["domain"], conn)
    if refused:
        out.append(refused)
    if spec.get("type") not in TYPES:
        out.append(f"type must be one of {', '.join(TYPES)}")
    enriched = ENRICHED / f"{spec['domain']}.json"
    published = ({e["email"].lower() for e in json.loads(enriched.read_text(encoding="utf-8")).get("contact", {}).get("emails", [])}
                 if enriched.exists() else set())
    if spec.get("to", "").lower() not in published:
        out.append(f"{spec.get('to') or 'no address'} was not found on the agency's own site")
    if spec.get("first_name") and not (spec.get("name_source", "").startswith("http") and spec.get("full_name")):
        out.append("first_name needs full_name and name_source: the page on the agency's site that names the person")
    hiring = spec.get("hiring") or {}
    if hiring.get("role") and not hiring.get("url", "").startswith("http"):
        out.append("a role needs the URL of the page it is on")
    if hiring.get("role") and status(spec) not in OPENERS:
        out.append(f"a role's status must be one of {', '.join(OPENERS)}")
    if status(spec) == "fresh":
        try:
            age = (dt.date.today() - dt.date.fromisoformat(hiring.get("posted", "")[:10])).days
        except ValueError:
            age = None
        if age is None or not 0 <= age <= FRESH_DAYS:
            out.append(f"a role is fresh only with a posting date in the last {FRESH_DAYS} days; otherwise it is undated")
    if not variant(spec):
        if not spec.get("opener"):
            out.append("no opener")
        if not any(check.get("quotes") for check in spec.get("line1_checks", [])):
            out.append("the opener has no quoted words from the agency's site to rest on")
    return out


def render(spec: dict, wording: dict, results: Path | None = None) -> str:
    domain, hiring, named = spec["domain"], spec.get("hiring") or {}, variant(spec)
    record = SCORED / f"{domain}.json"
    scored = json.loads(record.read_text(encoding="utf-8")) if record.exists() else spec.get("score")
    state = status(spec)
    env = dotenv_values(ROOT / ".env")
    name = (env.get("LEADFORGE_NAME") or "").strip() or "{{NAME}}"
    demo = (env.get("LEADFORGE_DEMO_URL") or "").strip()
    greeting = f"Hi {spec.get('first_name') or 'there'},"
    opener = named_opener(spec, wording) if named else spec["opener"]
    # A talent pool announces no hire, so there is no hire to offer help ahead of.
    ask = (wording["hiring_line"] + " " if named and state != "talent_pool" else "") + f"{wording['ask']} {wording['work']}"
    quoted = " | ".join(f'"{q}"' for check in opener_checks(spec) for q in check["quotes"])
    header = [
        f"# Job ask: {spec['agency']} ({domain})", "", f"- **To:** {spec['to']}",
        "- **Addressed to:** " + (f"{spec['full_name']}, named on {spec['name_source']}" if spec.get("first_name")
                                  else "no named contact on the site"),
        "- **Offer:** job_ask", f"- **Proof:** {spec['type']} ({TYPES[spec['type']]})",
        "- **Hiring:** " + (f"talent pool, {hiring['role']}" if state == "talent_pool" else
                            f"yes, {hiring['role']}" if state != "none" else "no"),
        f"- **Role status:** {state}" + (f" ({hiring['relevance']})" if hiring.get("relevance") else ""),
        f"- **Hiring score:** {hiring.get('score', 0)}",
        f"- **Careers page:** {hiring.get('url') or 'none found'}",
        f"- **Names the role:** {'yes' if named else 'no'}",
        f"- **Opener quote:** {quoted}", f"- **Evidence:** {opener_checks(spec)[0]['url']}",
        "- **Score:** " + (f"{scored['score']}, tier {scored['tier']}" if scored else "unscored")]
    header += [f"- {note}" for note in spec.get("notes", [])]
    header += ["", "Send as plain text, with no attachment." + ("" if name != "{{NAME}}" else " Replace `{{NAME}}` before sending."), ""]
    subject = ["## Subject", "", wording["subject"].format(agency=spec["agency"]), ""]
    email = ["## Email 1", "", greeting, "", opener, "", f"{wording['pitch']} {wording['proof'][spec['type']]}", "", ask, "",
             name, "", wording["ps"], ""]
    read = draft.line1_state(domain, results or SPECS / "_line1.json", "jobs.py quotes")
    check = ["## Check before sending", "", f"What the email rests on ({read}). Open each page and find the words:", ""]
    check += [f"- {c['url']} : " + ", ".join(f'"{q}"' for q in c["quotes"]) for c in checks(spec)] + [""]
    # The new piece of proof: the demo report if the wording file has one, else the recording, else a proof line
    # the first email did not use. A role the first email named is named again in the report's lead-in.
    new = (draft._report(hiring.get("role", "") if named else "", wording) if wording.get("follow_up_report")
           else wording["follow_up_demo"].format(url=demo) if demo
           else f"{wording['follow_up_lead']} {wording['proof'][NEXT_PROOF[spec['type']]]}")
    follow_ups = ["## Follow-up 1 (day 3)", "", greeting, "", new, "", wording["ask"], "", name, "",
                  "## Follow-up 2 (day 7)", "", greeting, "", wording["follow_up_2"], "", name, ""]
    return "\n".join(header + subject + email + check + follow_ups)


def build(domains: list[str], spec_dir: Path = SPECS, out_dir: Path = JOBS, wording: dict | None = None) -> int:
    wording = wording or job_wording()
    paths = [spec_dir / f"{d}.job.json" for d in domains] or sorted(spec_dir.glob("*.job.json"))
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = connect()
    failed = 0
    try:
        for path in paths:
            spec = json.loads(path.read_text(encoding="utf-8"))
            target = out_dir / f"{spec['domain']}.md"
            lead = conn.execute("SELECT status FROM leads WHERE domain = ?", (spec["domain"],)).fetchone()
            if lead and lead["status"] != "drafted" and target.exists():
                # It has gone out. The draft is the record of what was sent, and its follow-ups are read from it.
                console.print(f"[dim]sent[/dim] outreach/jobs/{target.name} left as it is")
                continue
            found = problems(spec, conn)
            if not found:
                text = render(spec, wording, spec_dir / "_line1.json")
                target.write_text(text, encoding="utf-8")
                found = lint_job(text, wording)
            elif target.exists():
                target.unlink()  # a spec that is refused must not leave an older email behind
            if found:
                failed += 1
                console.print(f"[red]FAIL[/red] {spec['domain']}")
                for problem in found:
                    console.print(f"   - {problem}")
            else:
                console.print(f"[green]ok[/green]   outreach/jobs/{target.name}")
    finally:
        conn.close()
    if out_dir == JOBS:
        log_run("python src/jobs.py build", {"drafts": len(paths) - failed, "refused": failed})
    return 1 if failed else 0


def refresh_follow_ups(domains: list[str], spec_dir: Path = SPECS, out_dir: Path = JOBS, wording: dict | None = None) -> int:
    """Rewrite only the follow-up sections of drafts already built, sent ones included.

    The subject and email 1 above them are the record of what was sent and stay exactly as they are."""
    wording = wording or job_wording()
    paths = [spec_dir / f"{d}.job.json" for d in domains] or sorted(spec_dir.glob("*.job.json"))
    changed = failed = 0
    for path in paths:
        spec = json.loads(path.read_text(encoding="utf-8"))
        target = out_dir / f"{spec['domain']}.md"
        if not target.exists():
            continue
        text = target.read_text(encoding="utf-8")
        fresh = render(spec, wording, spec_dir / "_line1.json")
        start, fresh_start = text.find("## Follow-up 1"), fresh.find("## Follow-up 1")
        if start < 0:
            console.print(f"[red]FAIL[/red] {spec['domain']}: the draft has no follow-up sections to rewrite")
            failed += 1
            continue
        new = text[:start] + fresh[fresh_start:]
        found = lint_job(new, wording)
        if found:
            failed += 1
            console.print(f"[red]FAIL[/red] {spec['domain']}: " + "; ".join(found))
            continue
        changed += new != text
        target.write_text(new, encoding="utf-8")
        console.print(f"[green]{'ok' if new != text else 'same'}[/green]   outreach/jobs/{target.name}")
    if out_dir == JOBS:
        log_run("python src/jobs.py followups", {"drafts": len(paths), "rewritten": changed, "failed": failed})
    return 1 if failed else 0


def main() -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, text in (("scan", "read each candidate's homepage and careers page in a browser"),
                       ("build", "render and lint the job-ask drafts"),
                       ("quotes", "confirm each opener's quoted words on the agency's page today"),
                       ("followups", "rewrite only the follow-ups of drafts already built, sent ones included")):
        sub.add_parser(name, help=text).add_argument("agency", nargs="*", help="omit for every candidate, or every spec")
    args = ap.parse_args()
    if args.cmd == "scan":
        return scan(args.agency)
    if args.cmd == "followups":
        return refresh_follow_ups(args.agency)
    if args.cmd == "quotes":
        return draft.quotes(args.agency, spec_dir=SPECS, suffix=".job.json", checks=checks, command="python src/jobs.py quotes")
    return build(args.agency)


if __name__ == "__main__":
    sys.exit(main())
