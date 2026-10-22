"""Contacts: the email addresses and Facebook and Instagram pages a business publishes itself.

    python src/contacts.py data/raw/<name>.csv                       # every business discover.py found
    python src/contacts.py data/raw/<name>.csv --out <folder>        # results somewhere else (gitignored)
    python src/contacts.py data/raw/<name>.csv --skip-names "great clips,supercuts"   # leave chains out
    python src/contacts.py data/raw/<name>.csv --redo 4 9            # read rows 4 and 9 again

For each business in a discover.py CSV this re-opens its Google Maps listing (name, category, address,
phone, website, coordinates, and whether it is marked closed), then its own website: the home page and
up to three contact, about or location pages on the same site. From those pages it records:

    emails     every address shown as a mailto link or as visible text, with the page it was on. Junk is
               dropped: image file names, platform and error-tracker addresses (wixpress, sentry),
               placeholders (example.com, yourname@, name@). An address is never guessed.
    facebook   links to a Facebook page or profile, and
    instagram  links to an Instagram account, each with the page and the part of it (header, footer,
               body) it was in. Share buttons, posts, reels, tag pages, a platform's own account and the
               bare home page are not business pages and are dropped, with the reason.

Rules it keeps:
    - facebook.com and instagram.com are never opened. A link is taken as the business published it,
      on its own site or as the website on its Maps listing; its query string is dropped, nothing else
      is changed.
    - A page that shows a CAPTCHA or bot check, or asks for a login, is skipped, never worked around.
      A contact form's reCAPTCHA preloads a hidden challenge frame; that alone does not count.
    - robots.txt is obeyed. Only the business's own site is read, one page after another.
    - When a site links several pages of one kind, the one in its header or footer is preferred, and
      a tie is broken only by the words of the business's own name or domain. Anything still
      ambiguous is left blank, with every candidate kept in the JSON for a person to choose.

It writes contacts.json (every page read and every link found; a re-run resumes from it) and
contacts.csv (one row per business, with the chosen email and pages and where each came from) to
--out, by default data/contacts/<name>/. Those folders are gitignored. The run log gets counts only.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from common import DATA, USER_AGENT, log_run, utf8_stdout

CONTACTS = DATA / "contacts"

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
JUNK_EMAIL = re.compile(
    r"\.(png|jpe?g|gif|webp|svg|bmp|ico|css|js|php)$|@\d+x\.|wixpress\.com|sentry|example\.(com|org|net)$|"
    r"@(domain|email|yourdomain|company)\.|^(your|yourname|youremail|name|user|someone|email|test)@|"
    r"godaddy\.com$|squarespace\.com$|wordpress\.(com|org)$|^u00", re.I)
FREE_MAIL = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", "icloud.com", "live.com", "msn.com",
             "me.com", "protonmail.com", "proton.me", "comcast.net", "verizon.net", "att.net", "ymail.com"}
SECONDARY_LOCAL = re.compile(r"^(careers?|jobs|hr|privacy|legal|no-?reply|donotreply|webmaster|abuse|billing|press)\b", re.I)

SOCIAL_HOST = re.compile(r"^(?:[\w-]+\.)?(facebook\.com|fb\.com|instagram\.com)$", re.I)
# Accounts a site builder, booking system or plugin puts on a page; never the business's own.
PLATFORM_ACCOUNTS = {"wix", "squarespace", "godaddy", "shopify", "wordpress", "wordpressdotcom", "weebly", "elementor",
                     "vagaro", "glossgenius", "booksy", "mindbodyonline", "mindbody", "fresha", "styleseat", "zocdoc",
                     "squareup", "square", "toasttab", "opentable", "yelp", "google", "facebook", "instagram", "meta",
                     "zoca", "joinblvd", "phorest", "doordash", "ubereats", "grubhub"}
FB_NOT_A_PAGE = re.compile(r"^/(sharer|share|dialog|plugins|tr|login|l\.php|hashtag|watch|events|groups|photo|photos|"
                           r"story\.php|permalink\.php|policies|privacy|help|marketplace|gaming|ads|business)\b", re.I)
IG_NOT_A_PROFILE = re.compile(r"^/(p|reel|reels|tv|stories|explore|accounts|direct|developer|about|legal|web)\b", re.I)

CONTACT_PAGE = re.compile(r"contact|reach us|get in touch|about|location|visit|find us|connect", re.I)
CHALLENGE = re.compile(r"captcha|verify you are human|are you a robot|just a moment|attention required|"
                       r"checking your browser|access denied|unusual traffic|security check", re.I)
POSITIONS = ("listing", "header", "footer", "body")


# ----- the rules, as pure functions -------------------------------------------------------------------

def clean_email(raw: str) -> str:
    """The address in a mailto link or a piece of text, or '' when it is not a real one."""
    value = unquote(raw or "").strip()
    value = re.sub(r"^mailto:", "", value, flags=re.I).split("?")[0].strip().strip(".,;:()<>[]\"'")
    if not EMAIL.fullmatch(value):
        return ""
    value = value.lower()
    return "" if JUNK_EMAIL.search(value) else value


def emails_on_page(page_url: str, mailtos: list[str], text: str) -> dict[str, dict]:
    """Every address on one page, each with the page and how it was shown (mailto beats text)."""
    found: dict[str, dict] = {}
    for href in mailtos:
        address = clean_email(href)
        if address:
            found[address] = {"page": page_url, "how": "mailto"}
    for raw in EMAIL.findall(text or ""):
        address = clean_email(raw)
        if address and address not in found:
            found[address] = {"page": page_url, "how": "text"}
    return found


def host_of(url: str) -> str:
    return urlsplit(url or "").netloc.lower().removeprefix("www.")


def pick_email(found: dict[str, dict], site_url: str) -> tuple[str, str]:
    """The address to use and why: the site's own domain first, then a free-mail address, then any
    other domain, which is flagged. Careers, privacy and no-reply addresses come last."""
    if not found:
        return "", ""
    site = host_of(site_url)
    ranked = sorted(found, key=lambda a: (bool(SECONDARY_LOCAL.match(a)),
                                          0 if site and (a.endswith("@" + site) or a.endswith("." + site)) else
                                          1 if a.split("@")[1] in FREE_MAIL else 2, a))
    best = ranked[0]
    domain = best.split("@")[1]
    note = "" if (site and site.endswith(domain)) or domain in FREE_MAIL else f"on another domain than the site ({site})"
    return best, note


def social_kind(url: str) -> str:
    match = SOCIAL_HOST.match(urlsplit(url or "").netloc)
    if not match:
        return ""
    return "instagram" if "instagram" in match.group(1).lower() else "facebook"


def profile_url(href: str) -> tuple[str, str]:
    """(the business page as published, minus its query string, '') or ('', why it is not one)."""
    kind = social_kind(href)
    if not kind:
        return "", "not a Facebook or Instagram link"
    parts = urlsplit(href)
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    first = path.strip("/").split("/")[0].lower() if path.strip("/") else ""
    if kind == "facebook":
        if first == "profile.php":
            page_id = parse_qs(parts.query).get("id", [""])[0]
            if not page_id.isdigit():
                return "", "a profile link with no page id"
            return urlunsplit((parts.scheme, parts.netloc, path, urlencode({"id": page_id}), "")), ""
        if parts.path.strip("/").lower().startswith("pg/"):
            return "", "a tab of a page (/pg/...), not the page as published"
        if FB_NOT_A_PAGE.match(path) or "sharer" in path.lower():
            return "", "a share button or a Facebook feature, not a page"
    else:
        if IG_NOT_A_PROFILE.match(path):
            return "", "a post, reel, tag or Instagram feature, not an account"
        if len(path.strip("/").split("/")) > 1:
            return "", "a page inside an account (a post or reel), not the account"
    if not first:
        return "", "the platform's home page"
    if first in PLATFORM_ACCOUNTS:
        return "", f"the platform account {first!r}, not the business"
    return urlunsplit((parts.scheme, parts.netloc, path, "", "")), ""


def _handle(url: str) -> str:
    parts = urlsplit(url)
    return (parse_qs(parts.query).get("id", [""])[0] or parts.path.strip("/").split("/")[0]).lower()


def name_words(name: str, site_url: str) -> set[str]:
    words = re.findall(r"[a-z0-9]{4,}", (name or "").lower()) + re.findall(r"[a-z0-9]{4,}", host_of(site_url).split(".")[0])
    return set(words) - {"salon", "spa", "clinic", "restaurant", "grill", "cafe", "studio", "center", "centre",
                         "group", "company", "llc", "inc", "the", "and", "with", "near", "best", "official"}


def pick_profile(candidates: list[dict], name: str, site_url: str) -> tuple[str, dict | None, str]:
    """(chosen URL, the link it came from, note) from the links one kind of account was found as.

    The listing's own link, then the header, then the footer, then the body: the first position that has
    any wins. Several different pages there are told apart only by the words of the business's name or
    domain in the handle; if that does not settle it, nothing is chosen."""
    usable = [c for c in candidates if c.get("url")]
    for position in POSITIONS:
        here = [c for c in usable if c["where"] == position]
        distinct = {}
        for c in here:
            distinct.setdefault(_handle(c["url"]), c)
        if not distinct:
            continue
        if len(distinct) == 1:
            chosen = next(iter(distinct.values()))
            return chosen["url"], chosen, ""
        words = name_words(name, site_url)
        scored = sorted(((sum(w in handle for w in words), handle) for handle in distinct), reverse=True)
        if scored[0][0] and (len(scored) == 1 or scored[0][0] > scored[1][0]):
            chosen = distinct[scored[0][1]]
            return chosen["url"], chosen, (f"{len(distinct)} different pages in the {position}; this one carries "
                                           f"the most words of the business's name")
        return "", None, f"ambiguous: {len(distinct)} different pages in the {position}; see contacts.json"
    return "", None, ""


def gate_reason(title: str, text: str, visible_challenge: bool = False, password_field: bool = False) -> str:
    """Why a page cannot be read as it is (a bot check, a CAPTCHA, a login), or '' when it can."""
    title, text = title or "", text or ""
    if CHALLENGE.search(title) or (len(text) < 600 and CHALLENGE.search(text)):
        return f"bot check or CAPTCHA ({title[:60]!r})"
    if visible_challenge:
        return "CAPTCHA shown on the page"
    if password_field and len(text) < 1500:
        return "login form"
    return ""


def contact_pages(links: list[tuple[str, str]], home: str, limit: int = 3) -> list[str]:
    """Same-site pages worth reading for contact details, from (href, label) pairs, in page order."""
    site = host_of(home)
    out = []
    for href, label in links:
        href = (href or "").split("#")[0]
        if host_of(href) != site or social_kind(href) or href.rstrip("/") == home.split("#")[0].rstrip("/"):
            continue
        if (CONTACT_PAGE.search(label or "") or CONTACT_PAGE.search(urlsplit(href).path)) and href not in out:
            out.append(href)
    return out[:limit]


def socials_on_page(page_url: str, anchors: list[tuple[str, str, str]]) -> list[dict]:
    """Every Facebook or Instagram link on a page, from (href, label, position) triples, with its verdict."""
    out = []
    for href, label, where in anchors:
        kind = social_kind(href)
        if not kind:
            continue
        url, why = profile_url(href)
        out.append({"kind": kind, "href": href, "url": url, "rejected": why, "where": where,
                    "label": (label or "")[:40], "page": page_url})
    return out


def split_address(address: str) -> dict:
    """{'street', 'city', 'state', 'zip'} for a US address as Maps shows it, or {} when it does not fit."""
    text = re.sub(r",\s*(United States|USA)$", "", (address or "").strip())
    match = re.match(r"^(?P<street>.+),\s*(?P<city>[^,]+),\s*(?P<state>[A-Z]{2})\s+(?P<zip>\d{5})(?:-\d{4})?$", text)
    return match.groupdict() if match else {}


def error_status(status: int | None) -> str:
    """Why a response is an error page and not the site (a 4xx or 5xx, such as a host's 525), or ''."""
    return f"error page (HTTP {status})" if status and status >= 400 else ""


TRANSIENT = re.compile(r"timeout|ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|ERR_TIMED_OUT|ERR_NETWORK|ERR_INTERNET|"
                       r"ERR_ADDRESS_UNREACHABLE|ERR_EMPTY_RESPONSE|ERR_SSL_PROTOCOL", re.I)


def worth_retrying(status: int | None, error: str = "") -> bool:
    """A slow or dropped connection, or the host's server failing for a moment (5xx), is tried again.
    A 4xx is the site's own answer and is not."""
    return bool(TRANSIENT.search(error)) if error else bool(status and status >= 500)


def strip_query(url: str) -> str:
    parts = urlsplit(url or "")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")) if url else ""


# ----- reading pages in the browser -------------------------------------------------------------------

class Robots:
    """robots.txt for each site read, fetched once. A site whose robots.txt cannot be read is allowed."""

    def __init__(self):
        self.parsers: dict[str, RobotFileParser] = {}

    async def allowed(self, client: httpx.AsyncClient, url: str) -> bool:
        parts = urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in self.parsers:
            parser = RobotFileParser()
            try:
                answer = await client.get(f"{host}/robots.txt")
                parser.parse(answer.text.splitlines() if answer.status_code == 200 else [])
            except httpx.HTTPError:
                parser.parse([])
            self.parsers[host] = parser
        return self.parsers[host].can_fetch("LeadForge", url)


async def _text_of(page, selector: str, attr: str | None = None) -> str:
    loc = page.locator(selector).first
    try:
        if await loc.count() == 0:
            return ""
        return ((await loc.get_attribute(attr)) if attr else (await loc.inner_text()) or "").strip()
    except Exception:
        return ""


async def read_listing(page, link: str) -> dict:
    """What a Google Maps listing shows today."""
    await page.goto(link, wait_until="domcontentloaded", timeout=60_000)
    try:
        await page.wait_for_selector("h1", timeout=20_000)
    except Exception:
        return {"listing_state": "did not load"}
    await page.wait_for_timeout(2500)
    for _ in range(10):  # the listing writes its coordinates into the address bar once it has settled
        if "!3d" in page.url:
            break
        await page.wait_for_timeout(1000)
    body = await page.inner_text("body")
    coords = re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", page.url)
    return {
        "listing_state": "ok",
        "name": await _text_of(page, "h1"),
        "category": await _text_of(page, 'button[jsaction*="category"]'),
        "address": (await _text_of(page, 'button[data-item-id="address"]', "aria-label")).replace("Address: ", "").strip(),
        "phone": (await _text_of(page, 'button[data-item-id^="phone:tel:"]', "aria-label")).replace("Phone: ", "").strip(),
        "website": await _text_of(page, 'a[data-item-id="authority"]', "href"),
        "closed": next((w for w in ("Permanently closed", "Temporarily closed") if w in body), ""),
        "latitude": float(coords.group(1)) if coords else None,
        "longitude": float(coords.group(2)) if coords else None,
    }


async def _gate(page) -> str:
    title = await page.title()
    text = await page.inner_text("body") if await page.locator("body").count() else ""
    shown = False
    for frame in await page.locator("iframe[src*='recaptcha/api2/bframe'], iframe[src*='hcaptcha.com'], #challenge-form").all():
        try:
            box = await frame.bounding_box()
            shown = shown or bool(await frame.is_visible() and box and box["width"] > 50 and box["height"] > 50)
        except Exception:
            pass
    password = await page.locator("input[type=password]").count() > 0
    return gate_reason(title, text[:3000], shown, password)


ANCHORS_JS = """els => els.map(e => [e.href, (e.innerText || e.getAttribute('aria-label') || '').trim(),
    e.closest('header, nav') ? 'header' : e.closest('footer') ? 'footer' : 'body'])"""


async def _goto(page, url: str, timeout: int, tries: int = 3):
    """(response, error) for one page, tried again after a pause when the failure looks passing."""
    response, error = None, ""
    for attempt in range(tries):
        if attempt:
            await page.wait_for_timeout(5_000 * attempt)
        try:
            response, error = await page.goto(url, wait_until="domcontentloaded", timeout=timeout), ""
        except Exception as exc:
            response, error = None, str(exc).split("\n")[0][:100]
        if not worth_retrying(response.status if response else None, error):
            break
    return response, error


async def read_site(context, client: httpx.AsyncClient, robots: Robots, url: str) -> dict:
    """The business's own site: home page and up to three contact pages, read one after another."""
    out = {"site_state": "", "pages": [], "emails": {}, "socials": []}
    if not url:
        out["site_state"] = "no website on the listing"
        return out
    if social_kind(url):
        # The listing's website is the social page itself. It is recorded, and not opened.
        out["site_state"] = "the listing's website is a social page"
        out["socials"] = socials_on_page("Google Maps listing (its website link)", [(url, "", "listing")])
        return out
    if not await robots.allowed(client, url):
        out["site_state"] = "robots.txt disallows the home page"
        return out
    page = await context.new_page()
    try:
        response, error = await _goto(page, url, 60_000)
        if error:
            out["site_state"] = "did not load: " + error
            return out
        await page.wait_for_timeout(4000)
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")  # footers that load late
        except Exception:
            pass
        await page.wait_for_timeout(1500)
        failed = error_status(response.status if response else None)
        if failed:
            out["site_state"] = failed
            return out
        gated = await _gate(page)
        if gated:
            out["site_state"] = "skipped: " + gated
            return out
        out["site_state"] = f"loads (HTTP {response.status if response else '?'})"
        home = out["home"] = page.url

        async def take() -> list[tuple[str, str]]:
            anchors = await page.eval_on_selector_all("a[href]", ANCHORS_JS)
            mailtos = [a[0] for a in anchors if a[0].lower().startswith("mailto:")]
            for address, seen in emails_on_page(page.url, mailtos, await page.inner_text("body")).items():
                out["emails"].setdefault(address, seen)
            out["socials"] += socials_on_page(page.url, anchors)
            out["pages"].append(page.url)
            return [(a[0], a[1]) for a in anchors]

        links = await take()
        for target in contact_pages(links, home):
            if not await robots.allowed(client, target):
                out["pages"].append(f"{target} (robots.txt disallows it; not read)")
                continue
            response, error = await _goto(page, target, 60_000, tries=2)
            if error:
                out["pages"].append(f"{target} (did not load: {error[:80]}; not read)")
                continue
            await page.wait_for_timeout(2500)
            why = error_status(response.status if response else None) or await _gate(page)
            if why:
                out["pages"].append(f"{target} ({why}; not read)")
                continue
            await take()
        return out
    finally:
        await page.close()


def summarise(record: dict) -> dict:
    """One CSV row: the chosen email and pages, and where each came from."""
    address = split_address(record.get("address", ""))
    # The site's own domain is the one it lands on, which a redirect can change from the listing's link.
    email, email_note = pick_email(record.get("emails", {}), record.get("home") or record.get("website", ""))
    row = {"name": record.get("name") or record.get("raw_title", ""), "category": record.get("category", ""),
           "address": re.sub(r",\s*United States$", "", record.get("address", "")), "city": address.get("city", ""),
           "state": address.get("state", ""), "zip": address.get("zip", ""), "phone": record.get("phone", ""),
           "website": "" if social_kind(record.get("website", "")) else strip_query(record.get("website", "")),
           "latitude": record.get("latitude") or "", "longitude": record.get("longitude") or "",
           "closed": record.get("closed", ""), "site_state": record.get("dropped") or record.get("site_state", ""),
           "email": email, "email_page": record["emails"][email]["page"] if email else "",
           "email_found_as": record["emails"][email]["how"] if email else ""}
    notes = [f"email {email_note}"] if email_note else []
    for kind in ("facebook", "instagram"):
        url, link, note = pick_profile([s for s in record.get("socials", []) if s["kind"] == kind], row["name"],
                                       record.get("website", ""))
        row[kind], row[f"{kind}_page"] = url, link["page"] if link else ""
        if note:
            notes.append(f"{kind}: {note}")
    row.update(maps_url=record.get("maps_url", ""), checked_at=record.get("checked_at", ""), notes="; ".join(notes))
    return row


# ----- the command ------------------------------------------------------------------------------------

async def run(rows: list[dict], path: Path, skip: list[str], redo: set[str]) -> dict:
    from playwright.async_api import async_playwright

    results = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    robots = Robots()
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=15, follow_redirects=True) as client, \
            async_playwright() as pw:
        browser = await pw.chromium.launch(channel="msedge", headless=True)
        maps = await browser.new_context(locale="en-US", viewport={"width": 1280, "height": 900})
        sites = await browser.new_context(locale="en-US", viewport={"width": 1280, "height": 900})
        page = await maps.new_page()
        for i, row in enumerate(rows):
            key = str(i)
            if key in results and key not in redo:
                continue  # a re-run resumes; rows named with --redo are read again
            chain = next((s for s in skip if s and s in row.get("title", "").lower()), "")
            base = {"raw_title": row.get("title", ""), "query": row.get("query", ""), "maps_url": row.get("link", "")}
            if chain:
                results[key] = {**base, "dropped": f"skipped by name ({chain})"}
            else:
                listing = await read_listing(page, row["link"])
                site = {}
                if listing["listing_state"] == "ok" and not listing["closed"]:
                    site = await read_site(sites, client, robots, listing.get("website") or "")
                results[key] = {**base, **listing, **site, "checked_at": dt.datetime.now().astimezone().isoformat(timespec="seconds")}
            done = results[key]
            print(i, done.get("name") or done["raw_title"], "|", done.get("dropped") or done.get("closed") or done.get("site_state"),
                  "|", len(done.get("emails", {})), "emails,", len([s for s in done.get("socials", []) if s["url"]]), "social links",
                  flush=True)
            path.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        await browser.close()
    return results


def main() -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("businesses", type=Path, help="a CSV written by discover.py")
    ap.add_argument("--out", type=Path, help="folder for contacts.json and contacts.csv (default data/contacts/<name>/)")
    ap.add_argument("--skip-names", default="", help="comma-separated words; a business whose name has one is left out")
    ap.add_argument("--redo", nargs="*", default=[], help="row numbers to read again")
    args = ap.parse_args()

    with args.businesses.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = args.out or CONTACTS / args.businesses.stem
    out.mkdir(parents=True, exist_ok=True)
    skip = [s.strip().lower() for s in args.skip_names.split(",") if s.strip()]
    results = asyncio.run(run(rows, out / "contacts.json", skip, set(args.redo)))

    summary = [summarise(results[str(i)]) for i in range(len(rows)) if str(i) in results]
    with (out / "contacts.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(summary[0]) if summary else ["name"])
        writer.writeheader()
        writer.writerows(summary)
    counts = {"businesses": len(rows), "skipped_by_name": sum(r["site_state"].startswith("skipped by name") for r in summary),
              "closed": sum(bool(r["closed"]) for r in summary), "with_site": sum(bool(r["website"]) for r in summary),
              "gated": sum(r["site_state"].startswith("skipped:") for r in summary),
              "with_email": sum(bool(r["email"]) for r in summary), "with_facebook": sum(bool(r["facebook"]) for r in summary),
              "with_instagram": sum(bool(r["instagram"]) for r in summary)}
    # The input and output paths can name a client's project, so the log shows neither.
    log_run("python src/contacts.py <businesses.csv>", counts, notes="robots.txt obeyed; facebook.com and instagram.com never opened")
    print("contacts " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    print(f"wrote {out / 'contacts.json'} and {out / 'contacts.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
