"""Outreach drafts: render one agency's draft from a spec, then lint it.

    python src/draft.py build <agency-domain>     # needs data/scored/drafts/<agency-domain>.draft.json
    python src/draft.py quotes [<agency-domain>]  # is what line 1 quotes still on the agency's site today?
    python src/draft.py followups [<agency-domain> ...]   # rewrite only the follow-ups of drafts already built
    python src/draft.py build <name> --spec-dir examples/spec --out-dir examples   # the bundled example

The spec is the reasoning layer's wording: the subject lines, the opening line about the agency
(with the evidence for it), which three businesses from the pack to name, and the follow-ups. The
three lines about those businesses are not typed by anyone. They are built here from the signals
verify.py confirmed, using the wording in signals.py, so an email cannot claim something the
browser did not show. Under the email the draft lists the pages to open to check each claim by hand.

The opening line is checked too. The spec lists the words it relies on and the page each came from
("line1_checks": [{"url", "quotes"}]); `quotes` opens those pages in a browser and reports any words
that are not there. An opening line must not say more than those quoted words do.

Follow-ups are replies in the thread of the first email, so they have no subject of their own. Each
must add something the first email did not say; a bare reminder is not written, and the linter rejects
the usual ones. When the operator's wording file (outreach/job_ask.json) has a "pivot", follow-up 1 is
that sentence: it turns the offer into the job ask. `followups` applies the current rules to a draft
that is already built and leaves everything above its follow-ups byte for byte, because for an email
that has gone out the draft is the record of what was sent.

A spec with "status": "BLOCKED: <reason>" writes a stub that says why and contains no email. A draft
that fails the linter is still written, so it can be fixed, but the command exits non-zero.

Nothing is sent. The file is for a person to read, check, copy and send by hand.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import re
import sys
from html import unescape as html_unescape
from pathlib import Path

from dotenv import dotenv_values
from rich.console import Console

import signals
from common import DRAFTS, JOB_WORDING, ROOT, SCORED, job_wording, log_run, utf8_stdout
from lint_drafts import lint
from pack import load_pack

SPECS = SCORED / "drafts"
LINE1_RESULTS = SPECS / "_line1.json"  # what `quotes` found, per agency, and on which day
CTA = "Want the other 7? Just reply yes."
console = Console()


def named(spec: dict, pack_dir: Path = SCORED / "packs") -> list[dict]:
    """The three businesses the email names: the line about each, and what to open to check it."""
    if not spec.get("picks"):
        return []
    _, rows = load_pack(spec["domain"], pack_dir)
    by_key = {row["key"]: row for row in rows}
    out = []
    for pick in spec["picks"]:
        row = by_key.get(pick["key"])
        if row is None:
            raise ValueError(f"{pick['key']} is not one of the ten businesses in the pack")
        confirmed = {g["key"]: g for g in row["chosen"]}
        missing = [g for g in pick["gaps"] if g not in confirmed]
        if missing:
            raise ValueError(f"{pick['key']}: {missing} are not among the signals the pack uses for it")
        gaps = [confirmed[g] for g in pick["gaps"]]
        keys = {g["key"] for g in gaps}
        parts, checks = [], []
        if "low_reviews" not in keys and not pick.get("no_count"):
            count = f"{int(float(row['review_count'])):,} reviews"
            if pick.get("rating") and "low_rating" not in keys:
                count += f" at {float(row['review_rating']):.1f}"
            parts.append(count)
            checks.append((count, row["maps_link"]))
        for gap in gaps:
            if "headline" in gap and pick.get("text"):
                # Words the line puts in quotation marks must be in what the browser read off the page.
                missing = [q for q in re.findall(r'"([^"]+)"', pick["text"]) if _plain(q) not in _plain(gap["label"])]
                if missing:
                    raise ValueError(f"{pick['key']}: {missing} is not in the text verified on its site")
                parts.append(pick["text"])
            else:
                parts.append(signals.phrase(gap))
            checks += claims(gap, row)
        out.append({"line": f"{pick['name']}: " + ", ".join(parts), "name": pick["name"], "checks": checks})
    return out


def claims(gap: dict, row: dict) -> list[tuple[str, str]]:
    """Each thing the email says about a business, with the exact URL to open to confirm it."""
    key, d, listing = gap["key"], gap.get("detail", {}), row["maps_link"]
    if key == "no_site":
        return [("no Website button on its Google listing", listing)]
    if key == "dead_site":
        link = d.get("link") or row.get("listed_url") or ""
        out = [(f"the Website link on its listing {d['how'].split(',')[0]} (tap Website on the listing)", listing),
               ("the link the listing points to", link)]
        if d.get("by_hand") and link:
            scheme, rest = link.split("://", 1)
            out.append(("what its domain shows", f"{scheme}://{rest.split('/')[0]}/"))
        if d.get("note") and "://www." in link:
            out.append((d["note"].rstrip(".").lower().replace("the same address", "note: the same address"), link.replace("://www.", "://", 1)))
        return out
    if key == "not_https":
        return [(f"its https address {d['https']}", d.get("https_url") or gap["source_url"]),
                ("the site opens over plain http", row["website"])]
    if key == "stale":
        return [(f"the footer copyright says {d['year']} (scroll to the bottom)", gap["source_url"])]
    if key == "no_ads_tags":
        return [("no Google tag or Meta Pixel (desktop only: press F12 and type dataLayer, then gtag, then fbq in the "
                 "Console; each should say 'not defined')", gap["source_url"])]
    if key == "low_reviews":
        return [(f"{int(d['reviews']):,} reviews (the median of {int(d['median']):,} is across the {d['peers']} listings searched)", listing)]
    if key == "low_rating":
        return [(f"rated {d['rating']} (the median of {d['median']} is across the {d['peers']} listings searched)", listing)]
    return [("the quoted words are on this page", gap["source_url"])]


def follow_ups(spec: dict, greeting: str, name: str, pivot: str = "") -> list[str]:
    """The two follow-up sections. With a pivot, follow-up 1 turns the offer into the job ask."""
    first = [pivot] if pivot else [spec["fu1"], "", "Shall I send it over?"]
    return ["## Follow-up 1 (day 3)", "", greeting, "", *first, "", name, "",
            "## Follow-up 2 (day 7)", "", greeting, "", spec["fu2"], "", name, ""]


def render(spec: dict, pack_dir: Path = SCORED / "packs", pack_folder: str = "packs", pivot: str = "") -> str:
    domain = spec["domain"]
    record = SCORED / f"{domain}.json"
    # A real draft takes its score from the scored record. The bundled example carries its own.
    scored = json.loads(record.read_text(encoding="utf-8")) if record.exists() else spec["score"]
    name = (dotenv_values(ROOT / ".env").get("LEADFORGE_NAME") or "").strip() or "{{NAME}}"
    greeting = spec.get("greeting", "Hello,")
    header = [f"# Outreach: {spec['agency']} ({domain})", "", f"- **To:** {spec['to']}",
              f"- **Addressed to:** {spec['addressed_to']}"]
    if spec.get("status", "").upper().startswith("BLOCKED"):
        header += [f"- **Score:** {scored['score']}, tier {scored['tier']}", f"- **Status:** {spec['status']}", ""]
        return "\n".join(header + spec.get("notes", []) + [""])
    header += [f"- **Pack:** `{pack_folder}/{domain}.html` ({spec['pack_note']}). Do not attach it to email 1.",
               f"- **Score:** {scored['score']}, tier {scored['tier']}"]
    header += [f"- {note}" for note in spec.get("notes", [])]
    header += ["", "Send as plain text." if name != "{{NAME}}" else "Send as plain text. Replace `{{NAME}}` before sending.", ""]
    subjects = ["## Subject lines", ""] + [f"{i}. {s}" for i, s in enumerate(spec["subjects"], 1)] + [""]
    people = named(spec, pack_dir)
    items = [p["line"] for p in people] or spec["items"]
    email = ["## Email 1", "", greeting, "", spec["line1"], "", spec["line2"], ""] + items
    email += ([""] + [spec["proof"]] if spec.get("proof") else []) + ["", CTA, "", name, "", "<!--"] + spec["evidence"] + ["-->", ""]
    state = spec.get("line1_note") or line1_state(domain)
    check = ["## Check before sending", ""] + [f"Line 1 ({state}): {c['url']}" for c in spec["line1_checks"]]
    for i, person in enumerate(people, 1):
        check.append(f"{i}. {person['name']}")
        check += [f"   - {what}: {url}" for what, url in person["checks"]]
    check += [f"{i}. {c['name']}: {c['what']}\n   - {c['url']}" for i, c in enumerate(spec.get("checks", []), 1)] + [""]
    note = ["## LinkedIn connection note", "", spec["linkedin"], ""]
    return "\n".join(header + subjects + email + check + follow_ups(spec, greeting, name, pivot) + note)


def line1_state(domain: str, results: Path = LINE1_RESULTS, command: str = "draft.py quotes") -> str:
    """What `quotes` last found for an agency's opening line, in words for the person about to send it."""
    seen = json.loads(results.read_text(encoding="utf-8")).get(domain) if results.exists() else None
    if seen is None:
        return f"not checked yet; run `{command}`"
    if seen["ok"]:
        return f"its quoted words were on the page on {seen['checked']}"
    if seen.get("last_ok"):
        # Read before, unreadable now. That is not the same as the words having gone.
        return (f"its quoted words were on the page on {seen['last_ok']}, but the page could not be read on "
                f"{seen['checked']}. Open it yourself before sending")
    return f"NOT confirmed on {seen['checked']}: {seen['why']}. Read the page yourself before sending"


def build(domain: str, spec_dir: Path = SPECS, out_dir: Path = DRAFTS) -> int:
    spec = json.loads((spec_dir / f"{domain}.draft.json").read_text(encoding="utf-8"))
    real = out_dir == DRAFTS  # the bundled example is not a pipeline run, and its pack sits beside it
    try:
        text = render(spec, pivot=_pivot()) if real else render(spec, spec_dir, out_dir.name)
    except ValueError as exc:
        console.print(f"[red]Draft spec rejected for {domain}:\n{exc}[/red]")
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / (f"{domain}.md" if real else f"{domain}.email.md")
    target.write_text(text, encoding="utf-8")
    problems = lint(text)
    if real:
        log_run(f"python src/draft.py build {domain}", {"lint_problems": len(problems)}, redact=(domain,))
    shown = f"{'outreach/drafts' if real else out_dir.name}/{target.name}"
    if problems:
        console.print(f"[red]FAIL[/red] {shown}")
        for problem in problems:
            console.print(f"   - {problem}")
        return 1
    blocked = spec.get("status", "").upper().startswith("BLOCKED")
    console.print(f"[{'yellow]blocked' if blocked else 'green]ok'}[/]   {shown}")
    return 0


def _pivot() -> str:
    """The operator's sentence that turns a lead-pack follow-up into the job ask, if one is set."""
    return job_wording().get("pivot", "") if JOB_WORDING.exists() else ""


def refresh_follow_ups(domains: list[str]) -> int:
    """Rewrite only the follow-up sections of drafts that are already built, under the current rules."""
    paths = [SPECS / f"{d}.draft.json" for d in domains] or sorted(SPECS.glob("*.draft.json"))
    name = (dotenv_values(ROOT / ".env").get("LEADFORGE_NAME") or "").strip() or "{{NAME}}"
    changed = failed = 0
    for path in paths:
        spec = json.loads(path.read_text(encoding="utf-8"))
        target = DRAFTS / f"{spec['domain']}.md"
        if spec.get("status", "").upper().startswith("BLOCKED") or not target.exists():
            continue
        text = target.read_text(encoding="utf-8")
        start, end = text.find("## Follow-up 1"), text.find("## LinkedIn connection note")
        if start < 0 or end < start:
            console.print(f"[red]FAIL[/red] {spec['domain']}: the draft has no follow-up sections to rewrite")
            failed += 1
            continue
        new = text[:start] + "\n".join(follow_ups(spec, spec.get("greeting", "Hello,"), name, _pivot())) + "\n" + text[end:]
        problems = lint(new)
        if problems:
            failed += 1
            console.print(f"[red]FAIL[/red] {spec['domain']}: " + "; ".join(problems))
            continue
        changed += new != text
        target.write_text(new, encoding="utf-8")
        console.print(f"[green]{'ok' if new != text else 'same'}[/green]   outreach/drafts/{target.name}")
    log_run("python src/draft.py followups", {"drafts": len(paths), "rewritten": changed, "failed": failed})
    return 1 if failed else 0


def _plain(text: str) -> str:
    """Lower-case, with quotes, dashes and spacing flattened, so a quote matches however it is typeset."""
    text = re.sub(r"[‘’“”\"']", "", text.lower())
    return " ".join(re.sub(r"[–—-]", " ", text).split())


def _meta_description(html: str) -> str:
    """The description a site writes about itself for search results. Its own words, so it counts."""
    tag = re.search(r"<meta[^>]+name=[\"']description[\"'][^>]*>", html, flags=re.I)
    content = re.search(r"content=[\"']([^\"']*)", tag.group(0), flags=re.I) if tag else None
    return content.group(1) if content else ""


async def _read_pages(urls: list[str]) -> dict[str, str]:
    from playwright.async_api import async_playwright

    from verify import visit
    pages: dict[str, str] = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel=os.getenv("LEADFORGE_BROWSER", "msedge"), headless=True)
        context = await browser.new_context(locale="en-US", viewport={"width": 1280, "height": 900}, ignore_https_errors=True)
        sem = asyncio.Semaphore(4)

        async def one(url: str) -> None:
            async with sem:
                seen = await visit(context, url)
            # The page title counts as the site's own words too, and so does a menu that is folded away:
            # the reader can open it, so the page code is searched as well as the visible text.
            hidden = re.sub(r"<(script|style)\b.*?</\1>|<[^>]+>", " ", seen.get("html", ""), flags=re.S | re.I)
            described = html_unescape(_meta_description(seen.get("html", "")))
            pages[url] = " ".join([seen.get("title", ""), described, seen["text"], hidden]) if seen["state"] == "ok" else ""

        try:
            await asyncio.gather(*(one(url) for url in urls))
        finally:
            await browser.close()
    return pages


def _fetch_pages(urls: list[str]) -> dict[str, str]:
    """A plain request for each page: enough when the words are in the HTML the server sends."""
    import httpx

    pages = {}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; LeadForge quote check)", "Accept-Language": "en"}
    with httpx.Client(follow_redirects=True, timeout=30, headers=headers) as client:
        for url in urls:
            try:
                body = client.get(url).text
            except httpx.HTTPError:
                body = ""
            title = re.search(r"<title[^>]*>(.*?)</title>", body, flags=re.S | re.I)
            text = re.sub(r"<(script|style)\b.*?</\1>|<[^>]+>", " ", body, flags=re.S | re.I)
            pages[url] = html_unescape(" ".join([title.group(1) if title else "", _meta_description(body), text])).strip()
            if title and re.search(r"one moment|just a moment|checking your browser", title.group(1), flags=re.I):
                pages[url] = ""  # the host's browser check, not the page
    return pages


def quotes(domains: list[str], browser: bool = True, spec_dir: Path = SPECS, suffix: str = ".draft.json",
           checks=lambda spec: spec.get("line1_checks", []), command: str = "python src/draft.py quotes") -> int:
    """Confirm the words each opening line relies on are on the agency's page today.

    A plain request is tried first. Only pages where words are still missing are opened in a browser,
    which also sees text that scripts add.
    """
    paths = [spec_dir / f"{d}{suffix}" for d in domains] or sorted(spec_dir.glob(f"*{suffix}"))
    specs = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    specs = [s for s in specs if not s.get("status", "").upper().startswith("BLOCKED")]
    pages = _fetch_pages(sorted({c["url"] for s in specs for c in checks(s)}))
    unsure = sorted({c["url"] for s in specs for c in checks(s)
                     if any(_plain(q) not in _plain(pages[c["url"]]) for q in c["quotes"])})
    if unsure and browser:
        pages.update(asyncio.run(_read_pages(unsure)))
    failed = 0
    found = spec_dir / LINE1_RESULTS.name
    results = json.loads(found.read_text(encoding="utf-8")) if found.exists() else {}
    today = dt.date.today().isoformat()
    for spec in specs:
        relied = checks(spec)
        missing = [f"{q!r} on {c['url']}" for c in relied for q in c["quotes"] if _plain(q) not in _plain(pages[c["url"]])]
        missing += [f"{c['url']} did not load" for c in relied if not pages[c["url"]]]
        unread = [c["url"] for c in relied if not pages[c["url"]]]
        if missing or not any(c["quotes"] for c in relied):
            failed += 1
            why = ("the page could not be read from this machine (no answer, or a browser check)" if unread
                   else "these words were not found: " + "; ".join(missing)) if relied else "the spec lists no words to check"
            before = results.get(spec["domain"], {})
            results[spec["domain"]] = {"ok": False, "checked": today, "why": why}
            # A page that would not load today takes nothing back: keep the last day its words were read.
            last_ok = before.get("checked") if before.get("ok") else before.get("last_ok")
            if unread and last_ok:
                results[spec["domain"]]["last_ok"] = last_ok
            console.print(f"[red]FAIL[/red] {spec['domain']}: {missing or 'no line1_checks given'}")
        else:
            results[spec["domain"]] = {"ok": True, "checked": today, "why": ""}
            console.print(f"[green]ok[/green]   {spec['domain']}: {sum(len(c['quotes']) for c in relied)} quote(s) found on its site")
    found.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    log_run(command, {"drafts": len(specs), "failed": failed})
    return 1 if failed else 0


def main() -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_build = sub.add_parser("build", help="render and lint one agency's draft")
    p_build.add_argument("agency")
    p_build.add_argument("--spec-dir", type=Path, default=SPECS)
    p_build.add_argument("--out-dir", type=Path, default=DRAFTS)
    p_quotes = sub.add_parser("quotes", help="confirm line 1's quoted words on the agency's rendered page")
    p_quotes.add_argument("agency", nargs="*", help="omit to check every draft")
    p_quotes.add_argument("--no-browser", action="store_true", help="plain requests only; report what they could not find")
    p_follow = sub.add_parser("followups", help="rewrite only the follow-up sections of drafts already built")
    p_follow.add_argument("agency", nargs="*", help="omit to rewrite every draft")
    args = ap.parse_args()
    if args.cmd == "quotes":
        return quotes(args.agency, browser=not args.no_browser)
    if args.cmd == "followups":
        return refresh_follow_ups(args.agency)
    return build(args.agency, args.spec_dir.resolve(), args.out_dir.resolve())


if __name__ == "__main__":
    sys.exit(main())
