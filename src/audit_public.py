"""Check that the repository is safe to publish before pushing it anywhere.

    python src/audit_public.py            # history, ignore rules, README links
    python src/audit_public.py --online   # also request the README's external links

It builds a list of everything that must never appear in git from the local, gitignored data: every
domain and business name in data/raw/*.csv, every email address found during enrichment, and every
lead in the tracker. Then it searches the full history (every commit's patch and message, on every
ref) for each of them, and the built page in _site/ if there is one, since that is published too. It
also confirms that data/ and .env are ignored and untracked, that nothing under an ignored folder has
been committed, and that the README's links resolve.

Exit code 0 means clean. The script names no business itself: it reads them from data/ at run time.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys

import pandas as pd
from rich.console import Console

from common import DATA, RAW, ROOT, is_platform, utf8_stdout
from enrich import JUNK_LOCAL

# Addresses and domains that appear in the code on purpose (constants, reserved examples, tool credits).
ALLOWED_DOMAINS = {"example.com", "anthropic.com", "github.com", "google.com", "gmail.com", "yahoo.com",
                   "hotmail.com", "outlook.com", "icloud.com", "live.com", "ymail.com", "sentry.io",
                   "wixpress.com", "domain.com", "email.com", "company.com", "test.com", "mail.com"}
PRIVATE_PATHS = ["data", ".env", "packs", "outreach/drafts", "outreach/ready", "outreach/us_track", "queries/packs", "samples"]
SITE = ROOT / "_site"  # the live page, built by docs/make_site.py
SITE_TEXT = {".html", ".css", ".js", ".svg", ".json", ".txt", ".xml", ".md"}
GENERIC_WORDS = set("""a ai agency agencies and app apps arabia automation beauty best branding business car
    center centre clinic clinics cleaning company consultancy consultant consulting content crm data dental design
    development dhabi abu digital doha dubai ecommerce estate generation group growth house hubspot in it jeddah
    ksa lead leads llc management marketing media mobile of online partner performance qatar real rental riyadh
    salon saudi school seo service services sharjah social software solutions studio systems tech technologies
    technology the top tours travel uae web website""".split())
console = Console()


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace").stdout


def sensitive_terms() -> tuple[set[str], set[str], set[str]]:
    domains: set[str] = set()
    names: set[str] = set()
    emails: set[str] = set()
    for path in RAW.glob("*.csv"):
        frame = pd.read_csv(path, dtype=str).fillna("")
        for column in ("root_domain", "website"):
            if column in frame.columns:
                for value in frame[column]:
                    host = re.sub(r"^https?://(?:www\.)?", "", value.strip().lower()).split("/")[0]
                    if host and "." in host:
                        domains.add(host)
        for column in ("title", "name"):
            if column in frame.columns:
                names |= {v.strip() for v in frame[column] if len(v.strip()) >= 12 and " " in v.strip()}
        for column in ("emails", "email"):
            if column in frame.columns:
                emails |= {e.strip().lower() for v in frame[column] for e in re.split(r"[;,\s]+", v) if "@" in e}
    for path in (DATA / "enriched").rglob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if record.get("domain"):
            domains.add(record["domain"].lower())
        emails |= {e["email"].lower() for e in record.get("contact", {}).get("emails", [])}
    tracker = DATA / "tracker.db"
    if tracker.exists():
        with sqlite3.connect(tracker) as conn:
            for domain, agency, email in conn.execute("SELECT domain, agency, email FROM leads"):
                domains.add(domain.lower())
                if agency and len(agency) >= 8:
                    names.add(agency)
                if email and "@" in email:
                    emails.add(email.lower())
    domains = {d for d in domains if d not in ALLOWED_DOMAINS and not is_platform(d)}
    # Form placeholders ("yourname@...") that early crawls picked up are not anyone's address.
    emails = {e for e in emails if e.split("@")[0] not in JUNK_LOCAL and e.split("@")[-1] != "example.com"}
    # A listing titled "AI Automation Agency" identifies no one, and the same words are in the query files.
    names = {n for n in names if not set(re.findall(r"[a-z]+", n.lower())) <= GENERIC_WORDS}
    return domains, names, emails


def scan_history(domains: set[str], names: set[str], emails: set[str]) -> list[str]:
    history = git("log", "--all", "-p", "--format=commit %H%n%an <%ae>%n%B")
    return find_terms(history, domains, names, emails)


def scan_site(domains: set[str], names: set[str], emails: set[str]) -> list[str]:
    """The built page is published from the gh-pages branch, so it is searched like the history is."""
    text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in sorted(SITE.rglob("*"))
                     if path.is_file() and ".git" not in path.parts and path.suffix in SITE_TEXT)
    return find_terms(text, domains, names, emails)


def find_terms(text: str, domains: set[str], names: set[str], emails: set[str]) -> list[str]:
    lowered = text.lower()
    hits = []
    for domain in sorted(domains):
        if domain in lowered and re.search(rf"(?<![\w.@-]){re.escape(domain)}(?![\w-])", lowered):
            hits.append(f"domain   {domain}")
    for email in sorted(emails):
        if email in lowered:
            hits.append(f"email    {email}")
    for name in sorted(names):
        if name.lower() in lowered:
            hits.append(f"name     {name}")
    return hits


def check_ignored() -> list[str]:
    problems = []
    for path in PRIVATE_PATHS:
        probe = path if path == ".env" else f"{path}/probe.tmp"
        if subprocess.run(["git", "check-ignore", "-q", probe], cwd=ROOT).returncode != 0:
            problems.append(f"{path} is not ignored by .gitignore")
    keep = {"packs/.gitkeep", "outreach/drafts/.gitkeep"}
    for line in git("log", "--all", "--name-only", "--format=").splitlines():
        line = line.strip()
        if line and line not in keep and any(line == p or line.startswith(p + "/") for p in PRIVATE_PATHS):
            problems.append(f"{line} was committed at some point in history")
    return sorted(set(problems))


def check_readme(online: bool) -> list[str]:
    problems = []
    tracked = set(git("ls-files").splitlines())
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        if target.startswith(("http://", "https://")):
            if online and "linkedin.com" not in target:  # LinkedIn refuses automated requests
                import httpx
                try:
                    status = httpx.get(target, follow_redirects=True, timeout=20).status_code
                except httpx.HTTPError as exc:
                    status = type(exc).__name__
                if status != 200:
                    problems.append(f"README link {target} returned {status}")
            continue
        path = target.split("#")[0]
        if path and path not in tracked:
            problems.append(f"README links to {path}, which is not a tracked file")
    # Images and links written as HTML: a file the README shows has to be one that is published.
    for target in re.findall(r"""(?:src|href)=["']([^"']+)["']""", text):
        path = target.split("#")[0]
        if path and not target.startswith(("http://", "https://", "mailto:")) and path not in tracked:
            problems.append(f"README shows {path}, which is not a tracked file")
    if re.search(r"\{\{[A-Z]+\}\}", text):
        problems.append("README still contains unfilled {{...}} placeholders")
    for path in sorted((ROOT / "examples").glob("northlight*")):
        if re.search(r"\{\{[A-Z]+\}\}", path.read_text(encoding="utf-8")):
            problems.append(f"examples/{path.name} still contains unfilled {{{{...}}}} placeholders")
    return problems


def main() -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--online", action="store_true", help="also request the README's external links")
    args = ap.parse_args()

    domains, names, emails = sensitive_terms()
    commits = len(git("rev-list", "--all").split())
    console.print(f"[bold]audit[/bold] {commits} commits checked against {len(domains)} domains, "
                  f"{len(names)} business names and {len(emails)} email addresses from data/")
    sections = {
        "Real businesses in git history": scan_history(domains, names, emails),
        "Real businesses in the built page (_site/)": scan_site(domains, names, emails) if SITE.exists() else None,
        "Ignore rules": check_ignored(),
        "README": check_readme(args.online),
    }
    dirty = 0
    for title, problems in sections.items():
        if problems is None:  # not checked is not the same as clean
            console.print(f"[dim]skip {title}: not built, so nothing was searched[/dim]")
        elif problems:
            dirty += len(problems)
            console.print(f"[red]FAIL[/red] {title} ({len(problems)})")
            for problem in problems[:40]:
                console.print(f"   - {problem}")
        else:
            console.print(f"[green]ok[/green]   {title}")
    authors = sorted(set(git("log", "--all", "--format=%an <%ae>").splitlines()))
    console.print("[dim]Commit authors (public once pushed): " + "; ".join(authors) + "[/dim]")
    uncommitted = git("status", "--short").strip()
    if uncommitted:
        console.print("[yellow]Uncommitted changes (not part of this audit):[/yellow]\n" + uncommitted)
    return 1 if dirty else 0


if __name__ == "__main__":
    sys.exit(main())
