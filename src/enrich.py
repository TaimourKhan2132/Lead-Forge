"""Enrichment: fetch a handful of pages per lead site and extract evidence-backed signals.

    python src/enrich.py data/raw/agencies_gulf.csv                 # full: up to 6 pages per site
    python src/enrich.py data/raw/pack_x.csv --mode light --out data/enriched/packs/x

Writes one JSON per lead. Every extracted claim is also recorded in `evidence` as
{field, value, source_url, snippet}, so nothing downstream has to be taken on trust.
Polite by design: one pass per site, a labelled user agent, no SMTP probing, no logins.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin, urlparse

import dns.asyncresolver
import dns.exception
import dns.resolver
import httpx
import pandas as pd
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import Progress

from common import ENRICHED, USER_AGENT, is_platform, log_run, now_iso, root_domain, slugify, utf8_stdout

TIMEOUT = 15.0
MAX_PAGES = 6
TEXT_CAP = 6000
MAX_HTML = 2_000_000
THIS_YEAR = dt.date.today().year
console = Console()

# Page kinds in fetch-priority order: (kind, path pattern).
PAGE_KINDS = [
    ("contact", r"contact|get-in-touch|reach-us|lets-talk|talk-to-us"),
    ("about", r"about|who-we-are|our-story"),
    ("services", r"services?|what-we-do|solutions|capabilities"),
    ("team", r"team|people|leadership"),
    ("careers", r"careers?|jobs|join-us|hiring|vacanc"),
    ("work", r"case-stud|portfolio|our-work|/work|projects|success-stor"),
    ("clients", r"clients|customers|testimonials"),
    ("industries", r"industries|sectors"),
]
PROBE_PATHS = {"contact": ["/contact", "/contact-us"], "about": ["/about", "/about-us"]}

SERVICES = {
    "seo": r"\bseo\b|search engine optimi[sz]ation",
    "paid_ads": r"\bppc\b|google ads|paid (?:media|search|social|ads|advertising)|performance marketing|meta ads|facebook ads",
    "social_media": r"social media (?:marketing|management|agency)|\bsmm\b",
    "web_design_dev": r"web(?:site)? (?:design|development)|web developers?",
    "ecommerce": r"e-?commerce|shopify|woocommerce|magento",
    "branding": r"\bbranding\b|brand identity|brand strategy",
    "content": r"content (?:marketing|creation|writing|production)|copywriting",
    "email_marketing": r"e-?mail marketing",
    "lead_generation": r"lead generation|lead gen\b|b2b leads|appointment setting|outbound",
    "crm": r"\bcrm\b|hubspot|salesforce|zoho|gohighlevel|go high ?level",
    "automation": r"\bautomation\b|\bautomate\b|\bn8n\b|zapier",
    "ai": r"\bai\b|artificial intelligence|machine learning|\bllms?\b|generative",
    "chatbots": r"chatbots?|conversational ai|whatsapp (?:bot|automation|business api|api)",
    "app_dev": r"mobile apps?|app development|ios app|android app",
    "software_dev": r"software development|custom software|\bmvp\b|\berp\b",
    "video_photo": r"video production|videography|photography",
    "influencer_pr": r"influencer marketing|public relations",
    "data_analytics": r"data analytics|business intelligence|power bi|web scraping|data scraping|data engineering",
}
INDUSTRIES = {
    "real_estate": r"real estate|property developers?|brokerages?|realtors?",
    "healthcare": r"healthcare|clinics?|dental|dentists?|medical|hospitals?|aesthetics?|dermatolog",
    "hospitality_fnb": r"restaurants?|hospitality|hotels?|caf[eé]s?|f&b|food (?:and|&) beverage",
    "ecommerce_retail": r"e-?commerce (?:brands?|stores?|business)|retail(?:ers)?|online stores?|\bd2c\b|\bdtc\b",
    "education": r"education|schools?|universit|training (?:cent(?:er|re)s?|institutes?)|e-learning",
    "finance": r"fintech|financial services|banking|insurance|accounting firms?",
    "automotive": r"automotive|car (?:dealers?|rental|showrooms?)",
    "legal": r"law firms?|legal services|lawyers?",
    "construction_interiors": r"construction|contractors?|interior design|fit-?out|architecture",
    "beauty_wellness": r"salons?|beauty|\bspas?\b|wellness|gyms?|fitness",
    "logistics": r"logistics|shipping|freight|supply chain",
    "travel_tourism": r"travel|tourism|tour operators?",
    "b2b_saas": r"\bsaas\b|\bb2b\b|startups?",
    "government": r"government|public sector|ministr(?:y|ies)",
}
TOOLS = {
    "n8n": r"\bn8n\b",
    "make": r"\bmake\.com\b|integromat",
    "zapier": r"zapier",
    "hubspot": r"hubspot|hs-scripts\.com|hsforms",
    "gohighlevel": r"gohighlevel|go high ?level|leadconnector|msgsndr",
    "openai": r"openai|chatgpt|\bgpt-?[345]",
    "chatbot": r"chatbots?",
    "whatsapp_api": r"whatsapp (?:business )?api|whatsapp automation",
    "salesforce": r"salesforce",
    "zoho": r"\bzoho\b",
    "odoo": r"\bodoo\b",
    "shopify": r"shopify",
    "wordpress": r"wordpress|wp-content",
    "webflow": r"webflow",
    "wix": r"wix\.com|wixstatic",
    "framer": r"framerusercontent|framer\.com",
    "klaviyo": r"klaviyo",
    "mailchimp": r"mailchimp",
    "apollo": r"apollo\.io",
    "airtable": r"airtable",
}
# Things detectable from page source. Used for agencies' own sites and, more importantly,
# as the observable "gaps" on prospects in a sample pack.
SOURCE_SIGNALS = {
    "chat_widget": r"tawk\.to|intercom|crisp\.chat|tidio|drift\.com|zdassets|livechat(?:inc)?\.com|freshchat|olark|manychat|respond\.io|wati\.io|chatbase|botpress|voiceflow|hs-scripts\.com|zopim|elfsight",
    "whatsapp_link": r"wa\.me/|api\.whatsapp\.com/send|whatsapp://send|web\.whatsapp\.com/send",
    "booking_system": r"calendly\.com|cal\.com/|acuityscheduling|setmore|fresha\.com|booksy|vagaro|simplybook|zocdoc|okadoc|practo|mindbody|sevenrooms|opentable|eatapp|resdiary|squareup\.com/appointments|bookingengine|tidycal|youcanbook|hubspot\.com/meetings|meetings\.hubspot",
    "meta_pixel": r"fbq\(|connect\.facebook\.net/[a-z_A-Z]+/fbevents",
    "google_ads_tag": r"googleadservices|google_conversion|gtag\(\s*['\"]config['\"]\s*,\s*['\"]AW-|[\"']AW-\d{6,}",
    "gtm": r"googletagmanager\.com/gtm\.js|GTM-[A-Z0-9]{5,}",
    "ga4": r"gtag/js\?id=G-|[\"']G-[A-Z0-9]{8,}[\"']",
    "tiktok_pixel": r"analytics\.tiktok\.com",
    "snap_pixel": r"sc-static\.net/scevent",
    "linkedin_insight": r"snap\.licdn\.com",
}
# Deliberately broad. A false "they have a booking prompt" costs nothing; a false "no way to book"
# would put a wrong claim in front of a prospect.
BOOKING_CTA = (r"\bbook(?:ing)?\s+(?:now|online|here|today|(?:an?|your|my|the)\s+[\w-]+)"
               r"|\bbook\s+(?:appointment|consultation|tour|visit|session|table|class)"
               r"|schedule\s+(?:an?\s+|your\s+)?(?:appointment|consultation|call|tour|visit|viewing)"
               r"|request\s+(?:an?\s+)?(?:appointment|tour|callback|call back|quote)"
               r"|arrange\s+an?\s+(?:tour|visit|viewing|call)"
               r"|reserve\s+(?:now|online|a\s+\w+|your\s+\w+)|online\s+booking|make\s+a\s+reservation"
               r"|appointment\s+(?:form|request)|enquire\s+now|enquiry\s+form|get\s+a\s+(?:free\s+)?quote")
PARKED = r"domain (?:is|may be) for sale|buy this domain|domain parking|parked free|sedoparking|hugedomains|afternic|godaddy\.com/forsale|is available for purchase|account (?:has been )?suspended|website (?:has )?expired|this site can.t be reached"
PLACEHOLDER = r"coming soon|under construction|launching soon|site is being updated"
HIRING = r"we.re hiring|we are hiring|join our team|open positions?|current openings?|vacanc(?:y|ies)|job openings?|open roles?|apply now|send (?:us )?your (?:cv|resume)"
NOT_HIRING = r"no (?:open|current) (?:positions|openings|vacancies)|not (?:currently )?hiring"
ROLE = r"\b((?:senior |junior |lead |head of )?(?:seo|ppc|social media|digital marketing|performance marketing|content|account|project|business development|sales|marketing|graphic|ui/ux|ux|web|frontend|front-end|backend|back-end|full[- ]stack|software|data|ai|automation|crm|video|motion)[\w /&-]{0,30}?(?:specialist|manager|executive|developer|designer|engineer|strategist|analyst|writer|editor|lead|intern|coordinator|consultant))\b"
TEAM_SIZE = [
    r"(?:team of|over|more than|with)\s+(\d{1,4})\+?\s+(?:[\w-]+\s){0,2}?(?:people|professionals|experts|specialists|employees|members|creatives|marketers|developers|engineers|staff|consultants)",
    r"\b([1-9]\d{0,3})\+?\s+(?:team members|employees|professionals|experts|specialists|in-house [\w-]+)",
    r"(?:team members?|employees|staff)\s*:?\s*([1-9]\d{1,3})\s*\+",  # counter widgets: "Team members 80+"
]
OFFICES = r"offices? (?:in|across|located in)\s+([^.|]{5,160})"
GLOBAL = r"global offices|offices (?:worldwide|around the world|across the globe)|(\d{1,3})\+?\s+countries"
PLACES_ABROAD = ["usa", "united states", "uk", "united kingdom", "london", "new york", "india", "pakistan",
                 "singapore", "canada", "australia", "germany", "france", "egypt", "lebanon", "jordan",
                 "turkey", "china", "hong kong", "malaysia", "philippines", "south africa", "nigeria",
                 "kenya", "netherlands", "spain", "italy", "russia", "ukraine", "bangladesh", "sri lanka"]
OFFSHORE = r"\b(india|pakistan|bangladesh|philippines|sri lanka|vietnam|ukraine|egypt)\b"
FOUNDER_TITLES = r"(?:Co-?Founder(?: (?:&|and) (?:CEO|CTO|Managing Director))?|Founder(?: (?:&|and) (?:CEO|Managing Director|Director))?|CEO|Chief Executive Officer|Managing Director|Managing Partner|Owner)"
NAME = r"[A-Z][a-z]{1,15}(?: (?:[A-Z]\.|(?:Al|El|Bin|Abu|De|Van) )?[A-Z][a-zA-Z'\-]{1,18}){1,2}"
NOT_NAMES = {"Our", "The", "Meet", "About", "From", "Message", "Team", "Contact", "Read", "View", "And",
             "Digital", "Marketing", "Agency", "Company", "Dubai", "Abu", "Home", "Services", "With",
             "Your", "Chief", "Managing", "Founder", "Director", "Head", "Senior", "Get", "Learn", "Why",
             "Google", "Maps", "Join", "Us", "Designer", "Operations", "Working", "Domain", "Manager",
             "Business", "Creative", "Social", "Media", "Group", "Solutions", "Technologies", "Global"}

EMAIL_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._%+\-]*@[a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)*\.[a-zA-Z]{2,}")
JUNK_TLDS = {"png", "jpg", "jpeg", "gif", "webp", "svg", "css", "js", "avif", "woff", "woff2", "ico"}
JUNK_EMAIL_DOMAINS = {"sentry.io", "wixpress.com", "example.com", "domain.com", "email.com", "yourdomain.com",
                      "company.com", "mysite.com", "website.com", "test.com", "sentry-next.wixpress.com",
                      "godaddy.com", "yoursite.com", "mail.com", "address.com", "yourcompany.com", "abc.com"}
JUNK_LOCAL = {"your", "name", "email", "user", "you", "yourname", "youremail", "your-email", "your.email",
              "example", "johndoe", "john.doe", "janedoe", "jane.doe", "username", "someone", "abc", "xyz"}
FREEMAIL = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "live.com", "ymail.com"}
GENERIC_LOCAL = {"info", "hello", "contact", "sales", "support", "admin", "office", "enquiries", "enquiry",
                 "inquiry", "inquiries", "marketing", "team", "hi", "hey", "mail", "business", "careers",
                 "jobs", "career", "cv", "recruitment", "privacy", "legal", "webmaster", "hr", "media", "press", "booking", "bookings", "reception", "reservations",
                 "appointments", "care", "customercare", "service", "help", "connect", "ask", "biz",
                 "partnerships", "projects", "work", "social", "accounts", "billing", "news", "newbusiness"}
SOCIALS = {"linkedin": r"linkedin\.com/(?:company|in|school)/", "instagram": r"instagram\.com/",
           "facebook": r"facebook\.com/", "x": r"(?:twitter|x)\.com/", "youtube": r"youtube\.com/",
           "tiktok": r"tiktok\.com/@"}
SHARE_LINK = r"sharer|share\?|intent/tweet|shareArticle|/share/|/p/|/reel/|/watch\?|/hashtag/|/explore/"


# --------------------------------------------------------------------------- fetching

class Fetched:
    __slots__ = ("url", "status", "html", "error")

    def __init__(self, url: str, status: int = 0, html: str = "", error: str = ""):
        self.url, self.status, self.html, self.error = url, status, html, error

    @property
    def ok(self) -> bool:
        return self.status == 200 and bool(self.html)


async def fetch(client: httpx.AsyncClient, insecure: httpx.AsyncClient, url: str, flags: set) -> Fetched:
    """GET with one retry. A bad certificate is recorded as a flag, then retried unverified."""
    last = Fetched(url, error="not attempted")
    for attempt in range(2):
        try:
            resp = await client.get(url)
        except httpx.ConnectError as exc:
            if "CERTIFICATE" in str(exc).upper() or "SSL" in str(exc).upper():
                flags.add("ssl_invalid")
                client = insecure
                last = Fetched(url, error="ssl")
                continue
            last = Fetched(url, error=f"connect: {str(exc)[:60]}")
        except httpx.TimeoutException:
            last = Fetched(url, error="timeout")
        except (httpx.HTTPError, ValueError, UnicodeError) as exc:
            last = Fetched(url, error=f"{type(exc).__name__}")
        else:
            ctype = resp.headers.get("content-type", "")
            if resp.status_code == 200 and "html" not in ctype and ctype:
                return Fetched(str(resp.url), resp.status_code, "", "not html")
            return Fetched(str(resp.url), resp.status_code, resp.text[:MAX_HTML] if resp.status_code == 200 else "")
        if attempt == 0:
            await asyncio.sleep(1.0)
    return last


def make_clients() -> tuple[httpx.AsyncClient, httpx.AsyncClient]:
    kwargs = dict(follow_redirects=True, timeout=TIMEOUT, max_redirects=5,
                  headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9",
                           "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"},
                  limits=httpx.Limits(max_connections=40, max_keepalive_connections=10))
    return httpx.AsyncClient(**kwargs), httpx.AsyncClient(verify=False, **kwargs)


# --------------------------------------------------------------------------- extraction helpers

def visible_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg", "template", "iframe"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))


def snippet(text: str, start: int, end: int, width: int = 80) -> str:
    left, right = max(0, start - width), min(len(text), end + width)
    return ("…" if left else "") + text[left:right].strip() + ("…" if right < len(text) else "")


def _decode_cfemail(hexstr: str) -> str:
    try:
        key = int(hexstr[:2], 16)
        return "".join(chr(int(hexstr[i:i + 2], 16) ^ key) for i in range(2, len(hexstr), 2))
    except ValueError:
        return ""


def find_emails(html: str, soup: BeautifulSoup, text: str) -> list[str]:
    found: list[str] = []
    for a in soup.find_all("a", href=re.compile(r"^\s*mailto:", re.I)):
        found.append(a["href"].strip()[7:].split("?")[0].replace("%20", "").strip())
    for tag in soup.find_all(attrs={"data-cfemail": True}):
        found.append(_decode_cfemail(tag["data-cfemail"]))
    found += EMAIL_RE.findall(text)
    found += [m for m in EMAIL_RE.findall(html) if not m.lower().startswith(("u00", "x22", "22"))]
    # Form hints ("yourname@gmail.com") are not contact addresses.
    placeholders = {m.lower() for tag in soup.find_all(attrs={"placeholder": True})
                    for m in EMAIL_RE.findall(str(tag["placeholder"]))}
    clean: dict[str, None] = {}
    for raw in found:
        match = EMAIL_RE.search(raw or "")
        if not match:
            continue
        email = match.group(0).lower().strip(".")
        local, _, domain = email.partition("@")
        if email in placeholders or domain.rsplit(".", 1)[-1] in JUNK_TLDS or domain in JUNK_EMAIL_DOMAINS:
            continue
        if re.fullmatch(r"[0-9a-f]{20,}", local) or len(local) > 40 or local in JUNK_LOCAL:
            continue
        clean[email] = None
    return list(clean)


def classify_email(email: str, site_domain: str) -> str:
    local, _, domain = email.partition("@")
    if domain in FREEMAIL:
        return "freemail"
    if root_domain(domain) != site_domain:
        return "other_domain"
    return "generic" if local in GENERIC_LOCAL else "named"


_mx_cache: dict[str, bool | None] = {}


async def has_mx(domain: str) -> bool | None:
    """True/False from DNS, None when the lookup itself failed. No SMTP is ever spoken."""
    if domain not in _mx_cache:
        try:
            answer = await dns.asyncresolver.resolve(domain, "MX", lifetime=6.0)
            _mx_cache[domain] = len(answer) > 0
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            _mx_cache[domain] = False
        except (dns.exception.DNSException, OSError):
            _mx_cache[domain] = None
    return _mx_cache[domain]


def classify_link(path: str) -> str | None:
    path = path.lower()
    for kind, pattern in PAGE_KINDS:
        if re.search(pattern, path):
            return kind
    return None


def pick_pages(home_url: str, soup: BeautifulSoup, site_domain: str, wanted: list[str]) -> dict[str, str]:
    """Choose one internal URL per page kind, preferring the shallowest path the site links to."""
    best: dict[str, str] = {}
    home_path = urlparse(home_url).path.rstrip("/")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#", "whatsapp:")):
            continue
        url = urljoin(home_url, href).split("#")[0]
        parts = urlparse(url)
        if parts.scheme not in ("http", "https") or root_domain(url) != site_domain:
            continue
        path = parts.path.rstrip("/")
        if not path or path == home_path or re.search(r"\.(pdf|jpg|png|zip|docx?)$", path, re.I):
            continue
        kind = classify_link(path)
        if kind in wanted and (kind not in best or len(path) < len(urlparse(best[kind]).path)):
            best[kind] = url
    return best


def count_matches(patterns: dict[str, str], text: str) -> dict[str, tuple[int, re.Match]]:
    out = {}
    for name, pattern in patterns.items():
        matches = list(re.finditer(pattern, text, re.I))
        if matches:
            out[name] = (len(matches), matches[0])
    return out


# --------------------------------------------------------------------------- per-site enrichment

async def enrich_site(client, insecure, lead: dict, mode: str) -> dict:
    site_domain = lead.get("root_domain") or root_domain(lead.get("website", ""))
    record = {
        "domain": site_domain, "name": lead.get("title", ""), "source": lead.get("source", "maps"),
        "mode": mode, "fetched_at": now_iso(), "status": "ok", "flags": [],
        "maps": {k: lead.get(k, "") for k in ("title", "category", "categories", "website", "website_kind",
                                             "phone", "review_count", "review_rating", "address", "country",
                                             "place_id", "link", "query")},
        "pages": [], "contact": {"emails": [], "phones": [], "whatsapp": [], "socials": {}},
        "offer": {"services": {}, "industries": {}, "case_study_count": 0},
        "team": {"size_hints": [], "team_cards": None, "founder_hints": []},
        "hiring": {"careers_page": None, "signals": [], "roles": []},
        "tools": {}, "site": {}, "big_company": [], "offshore_hints": [], "evidence": [],
    }
    evidence, flags = record["evidence"], set()

    def ev(field: str, value, url: str, snip: str = "") -> None:
        evidence.append({"field": field, "value": value, "source_url": url, "snippet": snip})

    kind = lead.get("website_kind") or ("site" if site_domain else "none")
    if kind != "site" or not lead.get("website"):
        record["status"] = "platform_only" if kind == "platform" else "no_website"
        ev("website", lead.get("website") or "none listed", lead.get("link", ""),
           "Maps listing links to a social/directory profile, not a website" if kind == "platform"
           else "Maps listing has no website")
        return record

    home = await fetch(client, insecure, lead["website"], flags)
    if not home.ok and lead["website"].startswith("http://") and home.status == 0:
        # Plenty of listings still carry an http:// link to a site that only answers on https.
        # Browsers upgrade that silently, so calling the site dead would be wrong.
        retry = await fetch(client, insecure, "https://" + lead["website"][7:], flags)
        if retry.ok:
            home = retry
            flags.add("http_link_only_works_on_https")
    if not home.ok:
        if home.status in (401, 403, 406, 429, 503):
            record["status"] = "blocked"
        elif home.status >= 400:
            record["status"] = "http_error"
        else:
            record["status"] = "dead"
        record["flags"] = sorted(flags | {f"home:{home.status or home.error}"})
        ev("site_status", record["status"], lead["website"], f"homepage returned {home.status or home.error}")
        return record

    final_domain = root_domain(home.url)
    if final_domain and final_domain != site_domain:
        flags.add(f"redirects_to:{final_domain}")
        if is_platform(final_domain):
            record["status"] = "platform_only"
            ev("website", home.url, lead["website"], "site redirects to a social/directory profile")
            record["flags"] = sorted(flags)
            return record

    home_soup = BeautifulSoup(home.html, "lxml")
    wanted = ["contact"] if mode == "light" else [k for k, _ in PAGE_KINDS]
    links = pick_pages(home.url, home_soup, final_domain or site_domain, wanted)
    fetched: list[tuple[str, Fetched]] = [("home", home)]
    budget = (2 if mode == "light" else MAX_PAGES) - 1
    for page_kind in wanted:
        if budget <= 0:
            break
        candidates = [links[page_kind]] if page_kind in links else [
            urljoin(home.url, p) for p in PROBE_PATHS.get(page_kind, [])]
        for url in candidates:
            page = await fetch(client, insecure, url, flags)
            if page.ok and page.url.rstrip("/") not in {f.url.rstrip("/") for _, f in fetched}:
                fetched.append((page_kind, page))
                budget -= 1
                break

    # ---- per-page parsing
    all_text_parts, all_html_parts, case_links, cards_best = [], [], set(), 0
    emails: dict[str, str] = {}
    phones: dict[str, str] = {}
    whatsapp: dict[str, str] = {}
    years: list[tuple[int, str]] = []
    dated: list[tuple[str, str]] = []
    for page_kind, page in fetched:
        soup = BeautifulSoup(page.html, "lxml")
        raw_soup = BeautifulSoup(page.html, "lxml") if page_kind == "home" else None
        title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            low = href.lower()
            if low.startswith("tel:"):
                number = re.sub(r"[^\d+]", "", href[4:])
                if len(number) >= 8:
                    phones.setdefault(number, page.url)
            wa = re.search(r"(?:wa\.me/|whatsapp\.com/send/?\?phone=|whatsapp://send\?phone=)\+?(\d{8,15})", low)
            if wa:
                whatsapp.setdefault("+" + wa.group(1), page.url)
            for network, pattern in SOCIALS.items():
                if re.search(pattern, low) and not re.search(SHARE_LINK, href) and network not in record["contact"]["socials"]:
                    record["contact"]["socials"][network] = href.split("?")[0]
                    ev(f"social_{network}", href.split("?")[0], page.url)
            full = urljoin(page.url, href)
            if re.search(r"/(?:case-stud(?:y|ies)|portfolio|work|our-work|projects?|success-stor(?:y|ies))/[^/?#]{3,}/?$",
                         urlparse(full).path, re.I) and root_domain(full) == (final_domain or site_domain):
                case_links.add(urlparse(full).path.rstrip("/"))
        for tag in soup.find_all("time", datetime=True):
            if re.match(r"\d{4}-\d{2}", tag["datetime"]):
                dated.append((tag["datetime"][:10], page.url))
        if page_kind in ("team", "about"):
            groups = Counter()
            for el in soup.find_all(class_=re.compile(r"team|member|staff|person|people", re.I)):
                if el.find("img") and 3 < len(el.get_text(" ", strip=True)) < 160:
                    groups[" ".join(el.get("class", []))] += 1
            if groups:
                top = groups.most_common(1)[0][1]
                if top > cards_best:
                    cards_best = top
                    record["team"]["team_cards"] = {"count": top, "source_url": page.url}
        text = visible_text(soup)
        for email in find_emails(page.html, soup, text):
            emails.setdefault(email, page.url)
        for match in re.finditer(r"(?:©|&copy;|\(c\)|copyright)\s*(?:20\d{2}\s*[-–—]\s*)?(20\d{2})", text, re.I):
            year = int(match.group(1))
            if 2005 <= year <= THIS_YEAR + 1:
                years.append((year, page.url))
        record["pages"].append({"url": page.url, "kind": page_kind, "status": page.status,
                                "title": title[:200], "text": text[:TEXT_CAP]})
        all_text_parts.append((page_kind, page.url, text[:TEXT_CAP * 2]))
        all_html_parts.append((page.url, page.html))
        if raw_soup is not None:
            html_tag = raw_soup.find("html")
            desc = raw_soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
            gen = raw_soup.find("meta", attrs={"name": re.compile("^generator$", re.I)})
            arabic = len(re.findall(r"[؀-ۿ]", text))
            record["site"].update({
                "final_url": page.url, "https": page.url.startswith("https://"), "title": title[:200],
                "meta_description": (desc.get("content") or "").strip()[:300] if desc else "",
                "lang": (html_tag.get("lang") or "").lower() if html_tag else "",
                "arabic_ratio": round(arabic / max(len(text), 1), 3),
                "has_viewport_meta": bool(raw_soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)})),
                "generator": (gen.get("content") or "")[:60] if gen else "",
                "h1_count": len(raw_soup.find_all("h1")), "home_text_chars": len(text),
                "hreflang": sorted({l.get("hreflang", "").lower() for l in raw_soup.find_all("link", hreflang=True)} - {""})[:8],
            })

    home_text = all_text_parts[0][2]
    home_html = all_html_parts[0][1]
    if re.search(PARKED, home_text, re.I) or re.search(PARKED, home_html[:20000], re.I):
        record["status"] = "parked"
        ev("site_status", "parked", home.url, "parking / suspended wording on homepage")
    elif len(home_text) < 600 and re.search(PLACEHOLDER, home_text, re.I):
        record["status"] = "placeholder"
        ev("site_status", "placeholder", home.url, home_text[:160])
    if len(home_text) < 300:
        flags.add("thin_html")  # probably rendered client-side; text-based signals will be weak

    # ---- contact
    for email, url in emails.items():
        kind_ = classify_email(email, final_domain or site_domain)
        mx = await has_mx(email.split("@")[1])
        record["contact"]["emails"].append({"email": email, "kind": kind_, "mx": mx, "source_url": url})
        ev("email", email, url, f"{kind_}; mx={mx}")
    order = {"named": 0, "generic": 1, "freemail": 2, "other_domain": 3}
    record["contact"]["emails"].sort(key=lambda e: (e["mx"] is False, order[e["kind"]]))
    record["contact"]["phones"] = [{"phone": p, "source_url": u} for p, u in list(phones.items())[:5]]
    record["contact"]["whatsapp"] = [{"number": n, "source_url": u} for n, u in list(whatsapp.items())[:3]]
    for item in record["contact"]["whatsapp"]:
        ev("whatsapp", item["number"], item["source_url"])

    # ---- offer, tools, source-level signals
    def scan(patterns: dict[str, str], field: str, target: dict) -> None:
        totals: dict[str, int] = Counter()
        first: dict[str, tuple[str, str]] = {}
        for _kind, url, text in all_text_parts:
            for name, (count, match) in count_matches(patterns, text).items():
                totals[name] += count
                first.setdefault(name, (url, snippet(text, match.start(), match.end())))
        for name, count in sorted(totals.items(), key=lambda kv: -kv[1]):
            target[name] = count
            ev(field, f"{name} (x{count})", first[name][0], first[name][1])

    scan(SERVICES, "service", record["offer"]["services"])
    scan(INDUSTRIES, "industry", record["offer"]["industries"])
    record["offer"]["case_study_count"] = len(case_links)
    if case_links:
        ev("case_study_count", len(case_links), home.url, "; ".join(sorted(case_links)[:6]))

    for name, pattern in TOOLS.items():
        for _kind, url, text in all_text_parts:
            match = re.search(pattern, text, re.I)
            if match:
                record["tools"][name] = "mentioned"
                ev("tool", f"{name} (mentioned in copy)", url, snippet(text, match.start(), match.end()))
                break
        else:
            for url, html in all_html_parts:
                if re.search(pattern, html, re.I):
                    record["tools"][name] = "in_source"
                    ev("tool", f"{name} (in page source)", url)
                    break
    for name, pattern in SOURCE_SIGNALS.items():
        hit = next(((url, m) for url, html in all_html_parts if (m := re.search(pattern, html, re.I))), None)
        record["site"][name] = bool(hit)
        ev(f"site_{name}", bool(hit), hit[0] if hit else home.url,
           f"matched '{hit[1].group(0)[:40]}' in page source" if hit else f"no match in source of {len(fetched)} page(s)")
    cta = next(((url, m, text) for _k, url, text in all_text_parts if (m := re.search(BOOKING_CTA, text, re.I))), None)
    record["site"]["booking_cta"] = bool(cta)
    ev("site_booking_cta", bool(cta), cta[0] if cta else home.url,
       snippet(cta[2], cta[1].start(), cta[1].end(), 50) if cta else "no booking wording on fetched pages")

    # ---- staleness
    if years:
        newest = max(years)
        record["site"]["copyright_year"] = newest[0]
        ev("copyright_year", newest[0], newest[1])
    else:
        record["site"]["copyright_year"] = None
    if dated:
        newest_date = max(dated)
        record["site"]["latest_dated_content"] = newest_date[0]
        ev("latest_dated_content", newest_date[0], newest_date[1], "newest <time datetime> on fetched pages")

    # ---- team, founders, hiring
    for page_kind, url, text in all_text_parts:
        for pattern in TEAM_SIZE:
            for match in re.finditer(pattern, text, re.I):
                number = int(match.group(1))
                if 2 <= number <= 5000 and not any(h["number"] == number for h in record["team"]["size_hints"]):
                    hint = {"number": number, "snippet": snippet(text, match.start(), match.end(), 60), "source_url": url}
                    record["team"]["size_hints"].append(hint)
                    ev("team_size_hint", number, url, hint["snippet"])
        if page_kind in ("home", "about", "team"):
            for pattern, name_group in ((rf"({NAME})\s*[,\-–|]?\s*({FOUNDER_TITLES})\b", 1),
                                        (rf"\b({FOUNDER_TITLES})\s*[:\-–|,]?\s*({NAME})", 2)):
                for match in re.finditer(pattern, text):
                    name = match.group(name_group).strip()
                    if set(name.split()) & NOT_NAMES or len(record["team"]["founder_hints"]) >= 5:
                        continue
                    if not any(h["name"] == name for h in record["team"]["founder_hints"]):
                        hint = {"name": name, "snippet": snippet(text, match.start(), match.end(), 50), "source_url": url}
                        record["team"]["founder_hints"].append(hint)
                        ev("founder_hint", name, url, hint["snippet"])
        for match in re.finditer(HIRING, text, re.I):
            if len(record["hiring"]["signals"]) < 3:
                record["hiring"]["signals"].append({"snippet": snippet(text, match.start(), match.end(), 60), "source_url": url})
        if page_kind == "careers":
            record["hiring"]["careers_page"] = url
            record["hiring"]["roles"] = sorted({m.group(1).strip().title() for m in re.finditer(ROLE, text, re.I)})[:12]
            record["hiring"]["says_no_openings"] = bool(re.search(NOT_HIRING, text, re.I))
            ev("careers_page", url, url, "roles seen: " + (", ".join(record["hiring"]["roles"]) or "none parsed"))
        if cards_best and record["team"]["team_cards"] and record["team"]["team_cards"]["source_url"] == url:
            ev("team_cards", cards_best, url, "repeated person-card elements on this page (a hint, not a headcount)")
        for match in re.finditer(OFFICES, text, re.I):
            listed = {p for p in PLACES_ABROAD if re.search(rf"\b{re.escape(p)}\b", match.group(1), re.I)}
            if len(listed) >= 3:
                record["big_company"].append({"signal": "multi_country_offices", "snippet": snippet(text, match.start(), match.end(), 30), "source_url": url})
        for match in re.finditer(GLOBAL, text, re.I):
            if match.group(1) is None or int(match.group(1)) >= 5:
                record["big_company"].append({"signal": "global_footprint", "snippet": snippet(text, match.start(), match.end(), 60), "source_url": url})
        if page_kind in ("home", "contact", "about"):
            for match in re.finditer(OFFSHORE, text, re.I):
                place = match.group(1).title()
                if len(record["offshore_hints"]) < 4 and not any(h["place"] == place for h in record["offshore_hints"]):
                    record["offshore_hints"].append({"place": match.group(1).title(), "snippet": snippet(text, match.start(), match.end(), 60), "source_url": url})
    for hint in record["team"]["size_hints"]:
        if hint["number"] > 50:
            record["big_company"].append({"signal": "staff_over_50", "snippet": hint["snippet"], "source_url": hint["source_url"]})
    record["big_company"] = record["big_company"][:4]
    for item in record["big_company"]:
        ev("big_company_signal", item["signal"], item["source_url"], item["snippet"])
    for item in record["hiring"]["signals"]:
        ev("hiring_signal", "hiring wording", item["source_url"], item["snippet"])
    for item in record["offshore_hints"]:
        ev("offshore_hint", item["place"], item["source_url"], item["snippet"])

    record["flags"] = sorted(flags)
    return record


# --------------------------------------------------------------------------- batch + CLI

def output_name(lead: dict) -> str:
    return lead.get("root_domain") or slugify(lead.get("title", "")) + "-" + (lead.get("place_id", "")[-6:] or "x")


async def enrich_all(leads: list[dict], out_dir: Path, mode: str, concurrency: int, force: bool) -> tuple[Counter, list[str]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    failures: list[str] = []
    sem = asyncio.Semaphore(concurrency)
    client, insecure = make_clients()

    async def one(lead: dict, progress, task) -> None:
        path = out_dir / f"{output_name(lead)}.json"
        if path.exists() and not force:
            counts["cached"] += 1
            progress.advance(task)
            return
        async with sem:
            try:
                record = await asyncio.wait_for(enrich_site(client, insecure, lead, mode), timeout=150)
            except Exception as exc:  # one bad site must not sink the batch
                failures.append(f"{output_name(lead)}: {type(exc).__name__}: {str(exc)[:80]}")
                record = {"domain": lead.get("root_domain", ""), "name": lead.get("title", ""),
                          "status": "error", "flags": [type(exc).__name__], "maps": lead, "evidence": []}
        counts[record["status"]] += 1
        path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        progress.advance(task)

    try:
        with Progress(console=console, transient=True) as progress:
            task = progress.add_task(f"enrich ({mode})", total=len(leads))
            await asyncio.gather(*(one(lead, progress, task) for lead in leads))
    finally:
        await client.aclose()
        await insecure.aclose()
    return counts, failures


async def quick_emails(urls: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    """Homepage-only email lookup, used by discover.py --email."""
    client, insecure = make_clients()
    sem = asyncio.Semaphore(8)
    found: dict[str, list[str]] = {}
    failures: list[str] = []

    async def one(url: str) -> None:
        async with sem:
            page = await fetch(client, insecure, url, set())
        if not page.ok:
            failures.append(f"email fetch {root_domain(url)}: {page.status or page.error}")
            return
        soup = BeautifulSoup(page.html, "lxml")
        emails = find_emails(page.html, soup, visible_text(soup))
        if emails:
            found[url] = emails[:5]

    try:
        await asyncio.gather(*(one(u) for u in urls))
    finally:
        await client.aclose()
        await insecure.aclose()
    return found, failures


def main() -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path, help="a data/raw/*.csv produced by discover.py")
    ap.add_argument("--mode", choices=["full", "light"], default="full",
                    help="full: up to 6 pages; light: homepage + contact page")
    ap.add_argument("--out", type=Path, default=ENRICHED)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--force", action="store_true", help="re-fetch leads that already have a JSON")
    args = ap.parse_args()

    leads = pd.read_csv(args.csv, dtype=str).fillna("").to_dict("records")
    if args.limit:
        leads = leads[:args.limit]
    counts, failures = asyncio.run(enrich_all(leads, args.out, args.mode, min(args.concurrency, 8), args.force))
    summary = {"leads": len(leads), **dict(sorted(counts.items()))}
    # Sample-pack runs are named after the agency they are for; keep that out of the public log.
    redact = (args.csv.stem[5:],) if args.csv.stem.startswith("pack_") else ()
    log_run("python " + " ".join(["src/enrich.py"] + sys.argv[1:]), summary, failures, redact=redact)
    console.print("[bold]enrich[/bold] " + ", ".join(f"{k}={v}" for k, v in summary.items()))
    for failure in failures[:10]:
        console.print(f"[yellow]! {failure}[/yellow]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
