"""Hiring signals: which companies list a role, read from their own careers page or public job system.

    python src/hiring.py scan --region gulf         # every discovered company in the region
    python src/hiring.py scan <domain> ...          # just these
    python src/hiring.py report --region gulf       # data/scored/hiring_<region>.csv and outreach/apply_by_hand.md
    python src/hiring.py drafts --region gulf       # job-ask specs for the strong and adjacent matches
    python src/track.py discover --by-hiring --region gulf     # all three, in that order

A company with an open, relevant role has the budget and has said it needs the work. For each
company this reads, at most: its robots.txt, its homepage, the careers page the homepage links to
(or /careers, /jobs, /join-us when it links to none), and the public job-board API of any job
system those pages point at (Greenhouse, Lever, Workable, Recruitee). One request at a time per
site, four sites at once, and a result is kept for 7 days. A page that needs JavaScript is opened
in the browser; nothing else is. A page robots.txt disallows is not fetched.

Every role is recorded with its title, URL, posting date if one is shown, location, whether it is
remote, hybrid or on site, its employment type, and the exact text it was read from. Then:

    status     fresh        a posting date in the last 60 days
               undated      listed as open, with no date. It may be used, but never as "you're hiring"
               talent_pool  "roles we'd like to hear about": a list of disciplines, not an opening
               stale        a posting date older than 60 days, or a closing date that has passed. Dropped.
    relevance  strong       data, automation, Python, scraping, reporting and BI, backend, ML
               adjacent     full-stack, web developer, CRM or marketing operations
               none         everything else
    score      20 strong and fresh; 10 adjacent and fresh; 5 strong or adjacent but undated or a
               talent pool; 0 otherwise. A company's hiring score is its best role's.

A role that is on site only, or says a visa is required, is flagged and ranked below the others.
Nothing is ever submitted: an Apply link is listed for the operator to use himself.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as dt
import json
import re
import sys
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from rich.console import Console

from common import (DATA, DEFAULT_REGION, ENRICHED, ROOT, SCORED, USER_AGENT, in_region, log_run, now_iso, region,
                    root_domain, utf8_stdout)

CACHE = DATA / "hiring"
APPLY_FILE = ROOT / "outreach" / "apply_by_hand.md"
CACHE_DAYS, FRESH_DAYS, TIMEOUT = 7, 60, 20.0
PROBES = ("/careers", "/jobs", "/join-us")
CAREERS_LINK = re.compile(r"careers?|\bjobs?\b|join[-_ ]?us|work[-_ ]?with[-_ ]?us|vacanc", re.I)
# Job systems, by the address their boards live at. Each pattern captures the company's board name.
ATS = {
    "greenhouse": re.compile(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board(?:/js)?\?for=)?([\w-]+)", re.I),
    "lever": re.compile(r"jobs(?:\.eu)?\.lever\.co/([\w-]+)", re.I),
    "workable": re.compile(r"apply\.workable\.com/([\w-]+)", re.I),
    "recruitee": re.compile(r"https?://([\w-]+)\.recruitee\.com", re.I),
    "bamboohr": re.compile(r"https?://([\w-]+)\.bamboohr\.com/(?:careers|jobs)", re.I),
    "zoho_recruit": re.compile(r"https?://([\w-]+)\.zohorecruit\.(?:com|eu|in)", re.I),
    "teamtailor": re.compile(r"https?://([\w-]+)\.teamtailor\.com", re.I),
}
NOT_A_BOARD = {"www", "api", "app", "careers", "jobs", "j", "embed", "widget", "static", "cdn", "help", "support"}
# Only these have a public job-board API. The others are recorded, with their address, to be read by hand.
API = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{board}?mode=json",
    "workable": "https://apply.workable.com/api/v1/widget/accounts/{board}?details=true",
    "recruitee": "https://{board}.recruitee.com/api/offers/",
}
# A job title names a person's job, which is what tells it from a service ("Web Development") in the same list.
ROLE_WORD = re.compile(
    r"\b(developer|engineer|designer|manager|executive|analyst|specialist|strategist|officer|consultant|copywriter|writer|"
    r"editor|intern|internship|assistant|coordinator|director|architect|administrator|scientist|accountant|associate|"
    r"technician|producer|videographer|photographer|marketer|programmer|tester|recruiter|representative|planner|creator|"
    r"artist|animator|advisor|adviser|trainee|apprentice|secretary|receptionist|supervisor)s?\b|\blead\b|\bhead of\b", re.I)
NOT_A_ROLE = re.compile(r"\b(our|your|meet|why|how|what|hire an?|become|talk to|contact|about|from the|by the|for an?|"
                        r"lead generation|leadership|(?:ai|virtual|voice|chat|shopping) assistant)\b|[.!?:]$|@", re.I)
MISSING = re.compile(r"<title[^>]*>[^<]*(?:404|not found|page (?:can(?:'|’)?t|cannot) be found)", re.I)
OPEN_CUE = re.compile(r"\bapply\b|view (?:role|job|details|position|vacancy)|read more|learn more|full[- ]time|part[- ]time|"
                      r"permanent|contract|\bremote\b|\bhybrid\b|on-?site|closing date|salary|experience|job description|"
                      r"positions?\b", re.I)
OPENINGS = re.compile(r"current (?:openings|vacancies|opportunities|roles|positions)|open (?:positions|roles|vacancies)|"
                      r"(?:latest|live|available|job) (?:career )?(?:openings|vacancies|roles|positions|opportunities)|"
                      r"we(?:'|’| a)re hiring|now hiring|vacancies", re.I)
TALENT_POOL = re.compile(
    r"always (?:interested|keen|on the lookout|looking|open)|may not have (?:any )?(?:active|current|open) "
    r"(?:openings|vacancies|roles|positions)|disciplines we want to meet|roles we(?:'|’| woul)d (?:like|love) to hear|"
    r"talent (?:pool|network|community|areas)|future (?:roles|openings|opportunities|vacancies)|register your interest|"
    r"(?:no|don(?:'|’)t have any|do not have any) (?:current |open |live )?(?:vacancies|openings|positions|roles)|"
    r"not (?:currently|actively) (?:hiring|recruiting)|keep (?:your )?(?:cv|details) on file", re.I)
# Someone describing their own job on the careers page: a job title, but not one on offer.
TESTIMONIAL = re.compile(r"[\"“][^\"”]{40,}|\bI(?:'|’)ve\b|\bI have\b|\bI joined\b|\bworking at\b|\bmy (?:role|job|team|career)\b", re.I)
STRONG = re.compile(r"\bdata\b|\banalytics\b|\bautomation\b|\bpython\b|scrap(?:ing|er)|\breporting\b|\bbi\b|business intelligence|"
                    r"back[- ]?end|machine learning|\bml\b|\bai (?:engineer|developer)", re.I)
NOT_STRONG = re.compile(r"data entry|data protection|data centre|data center", re.I)
ADJACENT = re.compile(r"full[- ]?stack|web developer|software (?:engineer|developer)|front[- ]?end|wordpress|shopify developer|"
                      r"\bphp\b|laravel|\bcrm\b|marketing op(?:eration)?s|\brevops\b|hubspot|^(?:senior |junior |lead )?developer$", re.I)
NOT_ADJACENT = re.compile(r"business develop|mobile|\bios\b|android|flutter|game", re.I)
MODE = (("remote", re.compile(r"\bremote\b|work from home|\bwfh\b|telecommut", re.I)), ("hybrid", re.compile(r"\bhybrid\b", re.I)),
        ("onsite", re.compile(r"on[- ]?site|in[- ]office|office[- ]based", re.I)))
EMPLOYMENT = re.compile(r"full[- ]time|part[- ]time|contract|permanent|freelance|internship|temporary", re.I)
VISA = re.compile(r"visa (?:sponsorship )?(?:is )?(?:required|needed)|must (?:have|hold) (?:a |an )?(?:valid )?(?:[\w ]{0,20})visa|"
                  r"own visa|right to work", re.I)
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b|\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
                  r"(?:,?\s+(\d{4}))?|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", re.I)
AGO = re.compile(r"(\d+)\s+(day|week|month)s?\s+ago", re.I)
NEEDS_JS = re.compile(r"enable javascript|javascript is (?:required|disabled)|you need to enable", re.I)
console = Console()


# ----- what a role is worth -----

def relevance(title: str) -> str:
    if STRONG.search(title) and not NOT_STRONG.search(title):
        return "strong"
    if ADJACENT.search(title) and not NOT_ADJACENT.search(title):
        return "adjacent"
    return "none"


def freshness(posted: str, today: dt.date | None = None) -> str:
    """fresh or stale from a posting date; undated when the page shows none."""
    if not posted:
        return "undated"
    age = ((today or dt.date.today()) - dt.date.fromisoformat(posted[:10])).days
    return "fresh" if age <= FRESH_DAYS else "stale"


def role_score(role: dict) -> int:
    if role["relevance"] == "none" or role["status"] == "stale":
        return 0
    if role["status"] == "fresh":
        return 20 if role["relevance"] == "strong" else 10
    return 5


CLOSEST = ("python", "scrap", "data", "automation", "report", "back", "machine learning", "full", "web")


def rank(role: dict) -> tuple:
    """Best first: the score, then roles not tied to an office or a visa, then strong before adjacent.

    Among equals, the title closest to what the operator does goes first: Python before data before the rest.
    """
    title = role["title"].lower()
    closest = next((i for i, word in enumerate(CLOSEST) if word in title), len(CLOSEST))
    return (-role_score(role), bool(role.get("flags")), role["relevance"] != "strong", closest, title)


def tidy_title(title: str) -> str:
    """A title as an email would write it: no bracketed aside, and not in capitals."""
    title = " ".join(re.sub(r"\s*[\(\[].*?[\)\]]", "", unescape(title)).split())
    title = re.split(r"\s+[—–|]\s+", title)[0].strip(" -–—|:+")  # "PHP Developer — Riyadh, KSA" is a PHP Developer
    return title.title().replace("Ui/Ux", "UI/UX").replace("Seo", "SEO").replace("Ppc", "PPC") if title.isupper() else title


# ----- reading a page -----

def find_date(text: str, today: dt.date) -> tuple[str, bool]:
    """(ISO date, is_closing_date) for the first date in a snippet, or ('', False)."""
    ago = AGO.search(text)
    if ago:
        days = int(ago.group(1)) * {"day": 1, "week": 7, "month": 30}[ago.group(2).lower()]
        return (today - dt.timedelta(days=days)).isoformat(), False
    m = DATE.search(text)
    if not m:
        return "", False
    try:
        if m.group(1):
            day = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        elif m.group(4):
            day = dt.date(int(m.group(6) or today.year), MONTHS[m.group(5).lower()[:3]], int(m.group(4)))
            if not m.group(6) and day > today:  # "11th February" with no year: the last one, not the next
                day = day.replace(year=today.year - 1)
        else:
            day = dt.date(int(m.group(9)), MONTHS[m.group(7).lower()[:3]], int(m.group(8)))
    except ValueError:
        return "", False
    closing = bool(re.search(r"clos(?:ing|es?)|deadline|apply by|until", text[max(0, m.start() - 40):m.start()], re.I))
    return day.isoformat(), closing


def describe(text: str, today: dt.date) -> dict:
    """Mode, employment type, flags and date read from the words around a role."""
    mode = next((name for name, pattern in MODE if pattern.search(text)), "")
    posted, closing = find_date(text, today)
    employment = EMPLOYMENT.search(text)
    flags = (["onsite"] if mode == "onsite" else []) + (["visa"] if VISA.search(text) else [])
    out = {"mode": mode, "employment": employment.group(0).lower() if employment else "", "flags": flags,
           "posted": "" if closing else posted}
    if closing:
        out["closes"] = posted
    return out


def json_ld_roles(soup: BeautifulSoup, page_url: str, today: dt.date) -> list[dict]:
    """Roles a page declares as schema.org JobPosting: the most reliable thing a careers page can say."""
    roles = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                stack.extend(item.get("@graph") or [])
                if item.get("@type") == "JobPosting" and item.get("title"):
                    place = item.get("jobLocation") or {}
                    place = place[0] if isinstance(place, list) and place else place
                    address = place.get("address", {}) if isinstance(place, dict) else {}
                    location = ", ".join(str(v) for v in (address.get("addressLocality"), address.get("addressCountry"))
                                         if isinstance(v, str) and v) if isinstance(address, dict) else ""
                    remote = "TELECOMMUTE" in str(item.get("jobLocationType", ""))
                    role = {"title": item["title"], "url": item.get("url") or page_url, "location": location,
                            "posted": str(item.get("datePosted") or "")[:10], "mode": "remote" if remote else "",
                            "employment": str(item.get("employmentType") or "").replace("_", " ").lower(), "flags": [],
                            "snippet": f"JobPosting: {item['title']}", "source": "json-ld"}
                    if str(item.get("validThrough") or "")[:10] and str(item["validThrough"])[:10] < today.isoformat():
                        role["closes"] = str(item["validThrough"])[:10]
                    roles.append(role)
    return roles


def html_roles(soup: BeautifulSoup, page_url: str, today: dt.date) -> list[dict]:
    """Roles read from the page itself: a job title beside something that says it can be applied for."""
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "form", "select", "option", "svg"]):
        tag.decompose()
    roles, seen = [], set()
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "a", "li", "summary", "strong", "b", "button", "p", "td", "span", "div"]):
        if tag.find(["h1", "h2", "h3", "h4", "h5", "h6", "li", "p", "div", "td"]) or any(
                ROLE_WORD.search(inner.get_text(" ", strip=True)) for inner in tag.find_all(True)):
            continue  # a container, or a row whose title is one of its own parts: that part is read instead
        title = " ".join(tag.get_text(" ", strip=True).split())
        # A row often reads "04 Backend Developer Apply": the number and the button are not part of the title.
        title = re.sub(r"^\d{1,2}[.)]?\s+|\s+(?:apply(?: now)?|view(?: role| job)?|learn more|read more)\W*$", "", title, flags=re.I)
        if not 4 <= len(title) <= 80 or len(title.split()) > 9 or not ROLE_WORD.search(title) or NOT_A_ROLE.search(title):
            continue
        key = re.sub(r"\W+", "", title.lower())
        if key in seen:
            continue
        block = tag
        for _ in range(4):  # the words around it: its card, row or list item, and no other role's
            wider = block.parent.get_text(" ", strip=True) if block.parent is not None else ""
            if not wider or len(wider) > 700 or len(ROLE_WORD.findall(wider)) > len(ROLE_WORD.findall(title)):
                break
            block = block.parent
        around = " ".join(block.get_text(" ", strip=True).split())
        after = []
        if block is tag:
            # No card of its own: the title is one of many in a long list. Read on to the next title instead.
            for sibling in tag.next_siblings:
                if getattr(sibling, "name", None) == tag.name or sum(len(part) for part in after) > 400:
                    break
                after.append(sibling)
            around += " " + " ".join(" ".join((s.get_text(" ", strip=True) if getattr(s, "name", None) else str(s)).split())
                                     for s in after)
        links = [s for s in after if getattr(s, "name", None) == "a" and s.get("href")]
        link = tag if tag.name == "a" else tag.find_parent("a") or block.find("a", href=True) or (links[0] if links else None)
        href = urljoin(page_url, link["href"]).split("#")[0] if link is not None and link.get("href") else ""
        # A role's own page counts as evidence only on the company's site or a job system. Anywhere else, such
        # as a social network's jobs tab, is just where to apply: it is never fetched and never cited.
        board = any(p.search(href) for p in ATS.values())
        own_page = href.startswith("http") and href.rstrip("/") != page_url.rstrip("/") and (board or (
            root_domain(href) == root_domain(page_url) and bool(CAREERS_LINK.search(urlsplit(href).path))))
        elsewhere = href if href.startswith("http") and not own_page and root_domain(href) != root_domain(page_url) else ""
        if not (own_page or OPEN_CUE.search(around.replace(title, "", 1))) or TESTIMONIAL.search(around):
            continue  # a job title with nothing around it to say it is on offer: a team list or a testimonial
        seen.add(key)
        apply = next((urljoin(page_url, a["href"]) for a in [*block.find_all("a", href=True), *links]
                      if re.search(r"\bapply\b", a.get_text(" ", strip=True), re.I)), "")
        roles.append({"title": title, "url": href if own_page else page_url, "location": "",
                      "apply_url": apply or (href if own_page else elsewhere),
                      "snippet": around[:300], "source": "html", **describe(around, today)})
    return roles


def read_page(html: str, page_url: str, today: dt.date) -> dict:
    """Everything one careers page says: its roles, the job systems it points at, and whether it is a talent pool."""
    soup = BeautifulSoup(html, "lxml")
    boards = {(name, m.group(1).lower()) for name, pattern in ATS.items() for m in pattern.finditer(html)
              if m.group(1).lower() not in NOT_A_BOARD}
    roles = json_ld_roles(soup, page_url, today)
    declared = {re.sub(r"\W+", "", r["title"].lower()) for r in roles}
    roles += [r for r in html_roles(soup, page_url, today)
              if not any(known in re.sub(r"\W+", "", r["title"].lower()) for known in declared)]
    shown = BeautifulSoup(html, "lxml")
    for tag in shown(["script", "style", "noscript"]):
        tag.decompose()
    text = " ".join(shown.get_text(" ", strip=True).split())
    pool = bool(TALENT_POOL.search(text)) and not OPENINGS.search(text)
    return {"roles": roles, "boards": sorted(boards), "talent_pool": pool, "text_chars": len(text),
            "needs_js": len(text) < 300 or bool(NEEDS_JS.search(text[:2000]))}


def api_roles(system: str, board: str, payload, today: dt.date) -> list[dict]:
    """Roles from a job system's public board API, in the same shape as the ones read from a page."""
    roles = []
    if system == "greenhouse":
        for job in payload.get("jobs", []):
            text = BeautifulSoup(unescape(job.get("content") or ""), "lxml").get_text(" ", strip=True)
            roles.append({"title": job["title"], "url": job.get("absolute_url", ""), "location": (job.get("location") or {}).get("name", ""),
                          **describe(f"{(job.get('location') or {}).get('name', '')} {text[:1500]}", today),
                          # Only a first-published date is a posting date. An edit date would make an old role look new.
                          "posted": str(job.get("first_published") or "")[:10], "snippet": f"{job['title']} | {text[:220]}"})
    elif system == "lever":
        for job in payload if isinstance(payload, list) else []:
            cats = job.get("categories") or {}
            text = job.get("descriptionPlain") or ""
            posted = dt.datetime.fromtimestamp(job["createdAt"] / 1000, dt.timezone.utc).date().isoformat() if job.get("createdAt") else ""
            found = describe(f"{job.get('workplaceType', '')} {cats.get('commitment', '')} {text[:1500]}", today)
            roles.append({"title": job["text"], "url": job.get("hostedUrl", ""), "location": cats.get("location", ""), **found,
                          "posted": posted, "snippet": f"{job['text']} | {text[:220]}"})
    elif system == "workable":
        for job in payload.get("jobs", []):
            text = BeautifulSoup(unescape(job.get("description") or ""), "lxml").get_text(" ", strip=True)
            place = ", ".join(v for v in (job.get("city"), job.get("country")) if v)
            found = describe(f"{'remote' if job.get('telecommuting') else ''} {job.get('employment_type', '')} {text[:1500]}", today)
            roles.append({"title": job["title"], "url": job.get("url") or job.get("shortlink", ""), "location": place, **found,
                          "posted": str(job.get("published_on") or job.get("created_at") or "")[:10],
                          "snippet": f"{job['title']} | {text[:220]}"})
    elif system == "recruitee":
        for job in payload.get("offers", []):
            text = BeautifulSoup(unescape(job.get("description") or ""), "lxml").get_text(" ", strip=True)
            found = describe(f"{'remote' if job.get('remote') else ''} {job.get('employment_type_code', '')} {text[:1500]}", today)
            roles.append({"title": job["title"], "url": job.get("careers_url", ""), "location": job.get("location", ""), **found,
                          "posted": str(job.get("published_at") or job.get("created_at") or "")[:10],
                          "snippet": f"{job['title']} | {text[:220]}"})
    for role in roles:
        role.update(source=f"{system} api", apply_url=role["url"])
    return roles


def settle(roles: list[dict], pool: bool, today: dt.date) -> list[dict]:
    """Give every role its status, relevance and score, and put the best first."""
    for role in roles:
        role["title"] = tidy_title(role["title"])
        status = freshness(role.get("posted", ""), today)
        if role.get("closes") and role["closes"] < today.isoformat():
            status = "stale"  # the closing date has passed
        elif pool and role["source"] == "html" and status == "undated":
            status = "talent_pool"
        role.update(status=status, relevance=relevance(role["title"]))
        role["score"] = role_score(role)
    return sorted(roles, key=rank)


# ----- fetching: one request at a time per site, robots.txt respected -----

class Site:
    """One company's site. Requests to it are made one after another, never side by side."""

    def __init__(self, client: httpx.AsyncClient):
        self.client, self.robots = client, {}

    async def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in self.robots:
            parser = RobotFileParser()
            try:
                answer = await self.client.get(f"{host}/robots.txt")
                parser.parse(answer.text.splitlines() if answer.status_code == 200 else [])
            except httpx.HTTPError:
                parser.parse([])
            self.robots[host] = parser
        return self.robots[host].can_fetch("LeadForge", url)

    async def get(self, url: str) -> tuple[str, str, str]:
        """(state, final URL, body). state is ok, robots, or the reason the page was not read."""
        if not await self.allowed(url):
            return "robots", url, ""
        try:
            answer = await self.client.get(url)
        except httpx.HTTPError as exc:
            return type(exc).__name__, url, ""
        if answer.status_code != 200:
            return f"http {answer.status_code}", str(answer.url), ""
        return "ok", str(answer.url), answer.text[:2_000_000]


async def scan_one(client: httpx.AsyncClient, enriched: dict, today: dt.date) -> dict:
    """Read one company: homepage, careers page, and any job system's public API."""
    domain = enriched["domain"]
    home_url = enriched.get("site", {}).get("final_url") or enriched.get("maps", {}).get("website") or f"https://{domain}/"
    site = Site(client)
    out = {"domain": domain, "scanned_at": now_iso(), "site": home_url, "careers_url": "", "careers_state": "none",
           "boards": [], "roles": [], "talent_pool": False, "notes": []}
    state, home_url, html = await site.get(home_url)
    if state != "ok":
        out.update(careers_state="unread", notes=[f"homepage: {state}"])
        return out
    soup = BeautifulSoup(html, "lxml")
    boards = {(name, m.group(1).lower()) for name, pattern in ATS.items() for m in pattern.finditer(html)
              if m.group(1).lower() not in NOT_A_BOARD}
    links = {}
    for a in soup.find_all("a", href=True):
        url = urljoin(home_url, a["href"]).split("#")[0]
        if url.startswith("http") and root_domain(url) == root_domain(home_url) and "/blog" not in url and url.rstrip("/") != home_url.rstrip("/"):
            said = bool(CAREERS_LINK.search(a.get_text(" ", strip=True)[:30]))
            if said or CAREERS_LINK.search(urlsplit(url).path):
                links[url] = links.get(url, False) or said
    # A link that says "Careers" before one that only has the word in its address, then the shortest:
    # /careers before /careers/graduate-scheme, and before a project that happens to be called Jobs Club.
    candidates = sorted(links, key=lambda url: (not links[url], len(url)))[:1] or [urljoin(home_url, path) for path in PROBES]
    page = None
    for url in candidates:
        state, final, body = await site.get(url)
        if state == "robots":
            out["notes"].append(f"robots.txt disallows {urlsplit(url).path}")
            out["careers_state"] = "robots"
        if state == "ok" and len(body) > 500 and urlsplit(final).path.rstrip("/") not in ("", "/index.html") and not MISSING.search(body):
            page = read_page(body, final, today)
            out.update(careers_url=final, careers_state="needs_js" if page["needs_js"] else "found", talent_pool=page["talent_pool"])
            break
    if page:
        boards |= {tuple(b) for b in page["boards"]}
        out["roles"] = page["roles"]
    for system, board in sorted(boards):
        entry = {"system": system, "board": board, "read": "by hand"}
        if system in API:
            state, _, body = await site.get(API[system].format(board=board))
            entry["read"] = state
            if state == "ok":
                try:
                    out["roles"] += api_roles(system, board, json.loads(body), today)
                    entry["read"] = "api"
                except (ValueError, KeyError, TypeError) as exc:
                    entry["read"] = f"api answer not understood ({type(exc).__name__})"
        out["boards"].append(entry)
    if out["boards"] and out["careers_state"] == "none":
        out["careers_state"] = "found"  # the homepage links straight to a job system
    out["roles"] = settle(out["roles"], out["talent_pool"], today)
    return out


def cached(domain: str) -> dict | None:
    path = CACHE / f"{domain}.json"
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    age = dt.datetime.now().astimezone() - dt.datetime.fromisoformat(record["scanned_at"])
    return record if age.days < CACHE_DAYS else None


def companies(where: dict, only: list[str]) -> list[dict]:
    """Every discovered company in the region whose site could be read, or just the ones named."""
    found = []
    for path in sorted(ENRICHED.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if only:
            if record.get("domain") in only:
                found.append(record)
        elif record.get("status") == "ok" and in_region(record.get("maps", {}), where):
            found.append(record)
    return found


async def _scan(records: list[dict], today: dt.date, where: dict) -> list[dict]:
    limits = httpx.Limits(max_connections=8)
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en"}
    sem, results = asyncio.Semaphore(4), []  # four sites at once; within a site, one request at a time
    async with httpx.AsyncClient(follow_redirects=True, timeout=TIMEOUT, headers=headers, limits=limits) as client:
        async def one(record: dict) -> None:
            async with sem:
                try:
                    result = await asyncio.wait_for(scan_one(client, record, today), timeout=150)
                except Exception as exc:  # one site's trouble must not stop the others
                    result = {"domain": record["domain"], "scanned_at": now_iso(), "site": "", "careers_url": "",
                              "careers_state": "unread", "boards": [], "roles": [], "talent_pool": False,
                              "notes": [f"scan failed: {type(exc).__name__}"]}
            results.append(result)

        async def board(system: str, name: str) -> None:
            async with sem:
                results.append(await scan_board(client, system, name, where, today))

        named = [(system, name) for system, names in (where.get("job_boards") or {}).items() if system in API for name in names]
        await asyncio.gather(*(one(record) for record in records), *(board(*pair) for pair in named))
    return results


async def scan_board(client: httpx.AsyncClient, system: str, name: str, where: dict, today: dt.date) -> dict:
    """A job board named in the region file: a company found by its openings, not by a Maps search."""
    site = Site(client)
    url = API[system].format(board=name)
    state, _, body = await site.get(url)
    roles = []
    if state == "ok":
        try:
            roles = api_roles(system, name, json.loads(body), today)
        except (ValueError, KeyError, TypeError):
            state = "api answer not understood"
    words = [*where["address_words"], "remote"]
    roles = [r for r in roles if any(word in (r.get("location") or "").lower() for word in words)]
    return {"domain": f"{name}@{system}", "scanned_at": now_iso(), "site": url, "careers_url": url, "careers_state": "found",
            "boards": [{"system": system, "board": name, "read": "api" if state == "ok" else state}],
            "roles": settle(roles, False, today), "talent_pool": False, "notes": ["a job board named in the region file"]}


async def _render(results: list[dict], today: dt.date) -> None:
    """Open in the browser only the careers pages that showed no text without JavaScript."""
    todo = [r for r in results if r["careers_state"] == "needs_js"]
    if not todo:
        return
    import os

    from playwright.async_api import async_playwright

    from verify import visit
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel=os.getenv("LEADFORGE_BROWSER", "msedge"), headless=True)
        context = await browser.new_context(locale="en-US", viewport={"width": 1280, "height": 900}, ignore_https_errors=True)
        sem = asyncio.Semaphore(4)

        async def one(result: dict) -> None:
            async with sem:
                seen = await visit(context, result["careers_url"])
            if seen["state"] != "ok":
                result["notes"].append(f"careers page in the browser: {seen.get('why') or seen.get('how')}")
                result["careers_state"] = "unread"
                return
            page = read_page(seen["html"], seen["final_url"], today)
            result.update(careers_state="found", talent_pool=page["talent_pool"])
            result["roles"] = settle([r for r in result["roles"] if r["source"] != "html"] + page["roles"], page["talent_pool"], today)
            result["notes"].append("careers page read in the browser: it shows nothing without JavaScript")

        try:
            await asyncio.gather(*(one(result) for result in todo))
        finally:
            await browser.close()


def scan(where: dict, only: list[str], force: bool = False) -> list[dict]:
    """Scan the region's companies, reusing anything read in the last 7 days."""
    today = dt.date.today()
    records = companies(where, only)
    kept = [] if force else [c for c in (cached(r["domain"]) for r in records) if c]
    have = {c["domain"] for c in kept}
    # Boards named in the region file are read on every region-wide run; they are one request each.
    fresh = asyncio.run(_scan([r for r in records if r["domain"] not in have], today, {} if only else where))
    asyncio.run(_render(fresh, today))
    CACHE.mkdir(parents=True, exist_ok=True)
    for result in fresh:
        (CACHE / f"{result['domain']}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    results = kept + fresh
    counts = summary(results)
    log_run(f"python src/hiring.py scan --region {where['name']}" if not only else "python src/hiring.py scan <companies>",
            {"companies": len(results), "read_now": len(fresh), "from_cache": len(kept), **counts},
            notes="One request at a time per site, robots.txt respected, results kept for 7 days.")
    console.print("[bold]hiring scan[/bold] " + ", ".join(f"{k}={v}" for k, v in {"companies": len(results), **counts}.items()))
    return results


def open_roles(result: dict) -> list[dict]:
    return [role for role in result["roles"] if role["status"] != "stale"]


def summary(results: list[dict]) -> dict:
    roles = [role for result in results for role in open_roles(result)]
    return {
        "careers_page": sum(r["careers_state"] in ("found", "needs_js") for r in results),
        "unread": sum(r["careers_state"] in ("unread", "robots") for r in results),
        "job_system": sum(bool(r["boards"]) for r in results),
        "with_roles": sum(bool(open_roles(r)) for r in results),
        "fresh": sum(role["status"] == "fresh" for role in roles),
        "undated": sum(role["status"] == "undated" for role in roles),
        "talent_pool": sum(role["status"] == "talent_pool" for role in roles),
        "stale_dropped": sum(role["status"] == "stale" for result in results for role in result["roles"]),
        "strong": sum(role["relevance"] == "strong" for role in roles),
        "adjacent": sum(role["relevance"] == "adjacent" for role in roles),
    }


# ----- what it produces -----

COLUMNS = ("company", "domain", "company_score", "hiring_score", "role", "relevance", "status", "mode", "flags", "employment",
           "location", "posted", "evidence_url", "snippet", "source", "apply_url", "careers_url", "email")


def company_name(domain: str) -> tuple[str, object]:
    """The agency's name and rubric score when it has been scored; otherwise the listing's own title."""
    scored = SCORED / f"{domain}.json"
    if "@" in domain:  # a board from the region file: all that is known of the company is the board's name
        return domain.split("@")[0].replace("-", " ").title(), ""
    if scored.exists():
        record = json.loads(scored.read_text(encoding="utf-8"))
        return record["agency"], record["score"]
    listing = json.loads((ENRICHED / f"{domain}.json").read_text(encoding="utf-8"))
    return (listing.get("maps", {}).get("title") or listing.get("name") or domain), ""


def best_email(domain: str) -> str:
    """An address the company publishes on its own site, a named one before a generic one."""
    if not (ENRICHED / f"{domain}.json").exists():
        return ""
    emails = json.loads((ENRICHED / f"{domain}.json").read_text(encoding="utf-8")).get("contact", {}).get("emails", [])
    usable = [e for e in emails if e.get("kind") in ("named", "generic") and e.get("mx") is not False]
    return sorted(usable, key=lambda e: e["kind"] != "named")[0]["email"] if usable else ""


def rows(results: list[dict]) -> list[dict]:
    """One row per open role, the best match first."""
    out = []
    for result in results:
        if not open_roles(result):
            continue
        name, score = company_name(result["domain"])
        best = max(role["score"] for role in open_roles(result))
        for role in open_roles(result):
            out.append({"company": name, "domain": result["domain"], "company_score": score, "hiring_score": best,
                        "role": role["title"], "relevance": role["relevance"], "status": role["status"], "mode": role.get("mode", ""),
                        "flags": " ".join(role.get("flags", [])), "employment": role.get("employment", ""),
                        "location": role.get("location", ""), "posted": role.get("posted", ""),
                        "evidence_url": role.get("url") or result["careers_url"], "snippet": role.get("snippet", ""),
                        "source": role["source"], "apply_url": role.get("apply_url", ""), "careers_url": result["careers_url"],
                        "email": best_email(result["domain"]), "_rank": rank(role)})
    out.sort(key=lambda r: (r["_rank"][:3], -(r["company_score"] or 0), r["company"].lower(), r["role"].lower()))
    return out


def report(where: dict, results: list[dict]) -> list[dict]:
    """Write the region's hiring table, and add its strong matches with an Apply link to the by-hand list."""
    table = rows(results)
    path = SCORED / f"hiring_{where['name']}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(table)
    console.print(f"[bold]hiring[/bold] wrote {path.relative_to(ROOT).as_posix()} with {len(table)} roles")
    apply_by_hand()
    return table


def apply_by_hand() -> None:
    """Every strong match, in any region, that has somewhere to apply. The operator applies himself."""
    lines = ["# Apply by hand", "",
             "Roles that match strongly and have an Apply link or form. Nothing here has been submitted, and nothing will be:",
             "open the link and apply yourself. A role marked undated shows no posting date, so check it is still open.", ""]
    count = 0
    for path in sorted(SCORED.glob("hiring_*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as fh:
            strong = [r for r in csv.DictReader(fh) if r["relevance"] == "strong" and r["status"] != "talent_pool" and r["apply_url"]]
        if not strong:
            continue
        lines += [f"## {region(path.stem.removeprefix('hiring_'))['label'].capitalize()}", ""]
        for row in strong:
            count += 1
            detail = ", ".join(v for v in (row["status"], row["posted"] and f"posted {row['posted']}", row["mode"], row["employment"],
                                           row["location"], row["flags"] and f"flagged: {row['flags']}") if v)
            lines += [f"### {row['role']} at {row['company']}", "", f"- **Apply:** {row['apply_url']}", f"- **Role page:** {row['evidence_url']}",
                      f"- **Details:** {detail}", f"- **Read from:** {row['snippet'][:240]}", ""]
    if not count:
        lines += ["No strong match with an Apply link yet.", ""]
    APPLY_FILE.parent.mkdir(parents=True, exist_ok=True)
    APPLY_FILE.write_text("\n".join(lines), encoding="utf-8")
    console.print(f"[bold]hiring[/bold] wrote {APPLY_FILE.relative_to(ROOT).as_posix()} with {count} roles")


def drafts(where: dict, results: list[dict]) -> int:
    """Write or refresh a job-ask spec for each company whose best role is strong or adjacent."""
    import jobs
    from track import connect

    made = skipped = 0
    conn = connect()
    try:
        for result in results:
            roles = [r for r in open_roles(result) if r["relevance"] != "none"]
            path = jobs.SPECS / f"{result['domain']}.job.json"
            if not roles:
                continue
            best = roles[0]
            hiring = {"url": best.get("url") or result["careers_url"], "role": best["title"], "status": best["status"],
                      "relevance": best["relevance"], "fits": True, "score": best["score"], "posted": best.get("posted", "")}
            if "@" in result["domain"] or jobs.refusal(result["domain"], conn):
                skipped += 1  # includes every company already emailed: a sent email's spec is never rewritten
                continue
            if path.exists():
                spec = json.loads(path.read_text(encoding="utf-8"))
            else:
                email = best_email(result["domain"])
                if not email:
                    skipped += 1
                    continue
                name, _ = company_name(result["domain"])
                spec = {"domain": result["domain"], "agency": name, "to": email, "type": proof_type(result["domain"]),
                        "notes": ["Written from the hiring scan. Check the agency's name and the role before sending."]}
            spec["hiring"] = hiring
            jobs.SPECS.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
            made += 1
    finally:
        conn.close()
    console.print(f"[bold]hiring[/bold] {made} job-ask specs written or refreshed for {where['label']}; {skipped} left out "
                  "(already emailed, on the skip list, scored only, or no published address)")
    return made


def proof_type(domain: str) -> str:
    """Which proof line fits: B for AI, automation and software; C for web development; A otherwise."""
    services = json.loads((ENRICHED / f"{domain}.json").read_text(encoding="utf-8")).get("offer", {}).get("services", {})
    top = next(iter(services), "")
    return "B" if top in ("ai", "automation", "software_dev", "data_analytics", "chatbots") else \
        "C" if top in ("web_design_dev", "ecommerce", "app_dev") else "A"


def discover(region_name: str, force: bool = False) -> int:
    """Start from the openings: scan the region, write its table and by-hand list, and draft where drafting is allowed."""
    where = region(region_name)
    results = scan(where, [], force)
    report(where, results)
    if where.get("outreach"):
        drafts(where, results)
    else:
        console.print(f"[yellow]{where['label'].capitalize()} is scored only, so no job ask is drafted for it.[/yellow]")
    return 0


def main() -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["scan", "report", "drafts"])
    ap.add_argument("domains", nargs="*", help="scan only: just these companies")
    ap.add_argument("--region", default=DEFAULT_REGION, help="a region in config/regions/ (default: %(default)s)")
    ap.add_argument("--force", action="store_true", help="read every site again, ignoring the 7-day cache")
    args = ap.parse_args()
    where = region(args.region)
    results = scan(where, args.domains, args.force)
    if args.cmd == "report":
        report(where, results)
    elif args.cmd == "drafts":
        drafts(where, results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
