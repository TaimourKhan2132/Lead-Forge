"""Confirm every signal in a real browser, on the day, before it can go in a pack.

    python src/verify.py <agency-domain> --want no_site,stale --top 26
    python src/verify.py <agency-domain> --signals queries/packs/<agency-domain>.signals.json

For each of the best candidates this opens two things in the installed Edge or Chrome:

1. The Google Maps listing. Is there a Website button? What are the review count and rating today?
2. The website, if the listing has one, left open for 8 seconds with a mouse move and a scroll.
   Does it load, and over https? What year does the footer copyright show? Did a Google tag, Tag
   Manager or Meta Pixel load? That last one checks window.dataLayer, gtag and fbq in every frame,
   every script source, the page's own code, and the requests the page made.

A signal is kept only when the browser shows it. A claim that something is absent or broken (no
tags, a dead link, no https) has to hold on two separate visits. Anything the browser cannot
settle is dropped, not guessed: a page behind a bot check, a consent banner that may be holding
tags back, a link that times out from here but might open elsewhere, a listing that did not load.
Review counts and ratings are replaced with today's.

Nothing here looks for booking tools, chat widgets, WhatsApp buttons or social links. Their absence
cannot be established this way, so those signals no longer exist (see signals.py).
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import random
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import dns.exception
import dns.resolver
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from rich.console import Console

from common import ROOT, SCORED, log_run, root_domain, utf8_stdout
from maps_playwright import _REVIEWS, GoogleBlocked, _check_blocked
from prospects import comparison_gaps, digest_text, gap_score, snippet
from signals import ABSENCE, STALE_MAX_YEAR

SETTLE_MS = 8_500  # how long a page is left open before anything is read from it
TAG_URL = re.compile(r"googletagmanager\.com|google-analytics\.com|analytics\.google\.com|googleadservices\.com|"
                     r"doubleclick\.net|connect\.facebook\.net|facebook\.com/tr\b", re.I)
TAG_CODE = re.compile(r"\bGTM-[A-Z0-9]{4,}\b|\bG-[A-Z0-9]{8,12}\b|\bAW-\d{6,}\b|\bUA-\d{4,}-\d+\b|\bfbq\s*\(|\bgtag\s*\(|google_tag_manager")
CONSENT = re.compile(r"cookiebot|onetrust|cookieyes|cookie-law-info|complianz|cmplz|iubenda|termly|osano|usercentrics|"
                     r"didomi|axeptio|klaro|borlabs|cookie[-_]?notice|cookie[-_]?consent|gdpr-cookie|moove_gdpr|cookie-ba(?:nner|r)", re.I)
BOT_WALL = re.compile(r"just a moment|attention required|access denied|verify you are human|are you a robot|captcha|"
                      r"security check|request blocked|forbidden|ddos", re.I)
GONE = re.compile(r"account (?:has been )?suspended|domain (?:name )?(?:is )?for sale|buy this domain|this domain has expired|"
                  r"domain (?:has )?expired|website (?:has )?expired|website is no longer available|is parked free", re.I)
HOLDING_PAGE = re.compile(r"one moment|just a moment|checking your browser|please wait", re.I)
COPY_MARK = re.compile(r"©|\(c\)|&copy;|\bcopyright\b", re.I)
YEAR = re.compile(r"(?<![\d.,/])(199\d|20[0-3]\d)(?![\d.,/]\d)")
NOT_A_COPYRIGHT_YEAR = re.compile(r"(?:since|est\.?|established|founded|box|no\.?|license|licence|permit)\s*[:#]?\s*$", re.I)
STARS = re.compile(r"^(\d(?:[.,]\d)?)\s+stars?\s*$", re.I)
PROBE = """() => {
  const has = (k) => typeof window[k] !== 'undefined';
  return {
    globals: ['dataLayer', 'gtag', 'fbq', '_fbq', 'google_tag_manager', 'google_tag_data', 'ga', 'GoogleAnalyticsObject'].filter(has),
    consent: ['Cookiebot', 'OneTrust', 'OnetrustActiveGroups', '__tcfapi', 'cmplz_categories', 'CookieConsent', 'cookieyes',
              '_iub', 'klaro', 'Osano', 'axeptio', 'Didomi', 'UC_UI', 'termly'].filter(has),
    shopify: has('Shopify'),
    scripts: Array.from(document.scripts).map(s => [s.src, s.getAttribute('data-src'), s.getAttribute('data-rocket-src')]
      .filter(Boolean).join(' ')).filter(Boolean),
  };
}"""
console = Console()


def copyright_year(text: str) -> dict | None:
    """The newest year in a copyright notice on the page, with the line it came from.

    Only a year that sits beside a copyright mark counts. "PO Box 2015" and "since 1998" do not,
    and if any notice on the page carries a newer year, that newer year is the answer.
    """
    best: dict | None = None
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if not line or len(line) > 400:
            continue
        for mark in COPY_MARK.finditer(line):
            lo = max(0, mark.start() - 14)
            window = line[lo:mark.end() + 70]
            for year in YEAR.finditer(window):
                if NOT_A_COPYRIGHT_YEAR.search(window[:year.start()]):
                    continue
                value = int(year.group(1))
                short = re.match(r"\s*[-\u2013/]\s*(\d\d)(?!\d)", window[year.end():])  # "2016-17" means 2017
                if short and int(short.group(1)) > value % 100:
                    value = value - value % 100 + int(short.group(1))
                if 1995 <= value <= dt.date.today().year and (best is None or value > best["year"]):
                    best = {"year": value, "line": line[:110]}
    return best


def nxdomain(host: str) -> bool:
    """True only when DNS says the name does not exist. A timeout is not an answer."""
    try:
        dns.resolver.resolve(host, "A", lifetime=8)
        return False
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        try:
            dns.resolver.resolve(host, "AAAA", lifetime=8)
            return False
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return True
        except dns.exception.DNSException:
            return False
    except dns.exception.DNSException:
        return False


async def visit(context, url: str) -> dict:
    """Open one page the way a visitor would and report what the browser ends up showing."""
    try:
        return await asyncio.wait_for(_visit(context, url), timeout=150)
    except asyncio.TimeoutError:
        return {"state": "unclear", "why": "the page did not settle in 150 seconds"}


async def _visit(context, url: str) -> dict:
    page = await context.new_page()
    requests: list[str] = []
    page.on("request", lambda r: requests.append(r.url) if TAG_URL.search(r.url) else None)
    try:
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=80_000)
        except Exception as exc:
            message = str(exc)
            host = urlsplit(url).hostname or ""
            if "ERR_NAME_NOT_RESOLVED" in message and nxdomain(host):
                dead = {"state": "dead", "how": "does not resolve"}
                if host.startswith("www.") and not nxdomain(host[4:]):
                    dead["note"] = "The same address without www does resolve."
                return dead
            # Timeouts, resets and refusals can be this machine, this country or a bot filter.
            return {"state": "unclear", "why": message.split("\n")[0][:90]}
        await page.wait_for_timeout(3_000)
        try:  # some sites hold their scripts back until the visitor does something
            await page.mouse.move(320, 300)
            await page.mouse.move(640, 430)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(3_000)
            await page.evaluate("window.scrollTo(0, 0)")
        except Exception:
            pass
        await page.wait_for_timeout(SETTLE_MS - 6_000)

        status = response.status if response else 0
        title = (await page.title())[:120]
        for _ in range(3):  # a host's own "one moment" page reloads into the real one; give it time
            if not HOLDING_PAGE.search(title):
                break
            await page.wait_for_timeout(6_000)
            title = (await page.title())[:120]
        if HOLDING_PAGE.search(title):
            return {"state": "unclear", "why": f"the site kept showing a browser check ({title!r})"}
        try:
            text = await page.inner_text("body", timeout=10_000)
        except Exception:
            text = ""
        gone = GONE.search(title) or (GONE.search(text) if len(text) < 1_500 else None)
        if gone:
            words = gone.group(0).lower()
            kind = ('an "Account Suspended" page' if "suspended" in words else "a parked-domain page" if "parked" in words
                    else 'a "website expired" page' if "website" in words and "expired" in words
                    else 'a "domain expired" page' if "expired" in words
                    else 'a "domain for sale" page' if "sale" in words or "buy" in words
                    else "a page saying the website is no longer available")
            return {"state": "dead", "how": f"opens {kind}"}
        if status in (404, 410):
            return {"state": "dead", "how": f"returns a {status} page"}
        if status >= 400 or BOT_WALL.search(title):
            return {"state": "unclear", "why": f"HTTP {status}, title {title!r}"}
        if len(text) < 200:
            return {"state": "unclear", "why": f"page shows almost no text ({len(text)} characters)"}

        html = await page.content()
        tags, consent, shopify = [], [], False
        for frame in page.frames:
            try:
                probe = await frame.evaluate(PROBE)
                if frame is not page.main_frame:
                    html += await frame.content()
            except Exception:
                continue
            tags += [f"window.{name}" for name in probe["globals"]]
            tags += [f"script {src[:70]}" for src in probe["scripts"] if TAG_URL.search(src) or TAG_CODE.search(src)]
            consent += probe["consent"]
            shopify = shopify or probe["shopify"]
        tags += [f"request {url[:70]}" for url in requests[:2]]
        for pattern in (TAG_URL, TAG_CODE):
            found = pattern.search(html)
            if found:
                tags.append(f"in page code: {found.group(0)}")
        banner = CONSENT.search(html)
        if banner:
            consent.append(banner.group(0))
        return {"state": "ok", "status": status, "final_url": page.url, "title": title, "tags": tags[:5],
                "consent": consent[:3], "shopify": shopify, "copyright": copyright_year(text), "text": text, "html": html}
    finally:
        await page.close()


async def https_answer(strict_context, *urls: str) -> str:
    """What the https:// version of an http page does: 'works', or the way it fails.

    "No https" may be claimed only when the https version of the same URL fails to load or has an
    invalid certificate. If it answers at all, it works, even when it then sends the visitor back to
    http. Both the link on the listing and the page the visitor ends on are tried, and one that works
    settles it.
    """
    answers = []
    for url in dict.fromkeys("https://" + u.split("://", 1)[1] for u in urls if u):
        try:
            answers.append(await asyncio.wait_for(_https_answer(strict_context, url), timeout=75))
        except asyncio.TimeoutError:
            answers.append("unclear")
    for verdict in ("works", "unclear"):
        if verdict in answers:
            return verdict
    return answers[0] if answers else "unclear"


async def _https_answer(strict_context, url: str) -> str:
    page = await strict_context.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        return "works"  # it answered over https, wherever it sent the visitor next
    except Exception as exc:
        message = str(exc)
        if "ERR_CERT" in message:
            return "shows a certificate error"
        if any(code in message for code in ("ERR_SSL", "ERR_CONNECTION_REFUSED", "ERR_CONNECTION_CLOSED", "ERR_CONNECTION_RESET")):
            return "does not load"
        return "unclear"  # a timeout proves nothing
    finally:
        await page.close()


async def listing(context, cand: dict) -> dict:
    """Read the live Google Maps listing: website button, review count, rating."""
    if not cand.get("maps_link"):
        return {"ok": False, "why": "the search result came with no listing link"}
    try:
        return await asyncio.wait_for(_listing(context, cand), timeout=90)
    except asyncio.TimeoutError:
        return {"ok": False, "why": "the listing did not load in 90 seconds"}


async def _listing(context, cand: dict) -> dict:
    page = await context.new_page()
    try:
        link = cand["maps_link"] + ("&" if "?" in cand["maps_link"] else "?") + "hl=en"
        await page.goto(link, wait_until="domcontentloaded", timeout=45_000)
        await _check_blocked(page)
        await page.wait_for_selector('[data-item-id="address"], [data-item-id^="phone"], [data-item-id="authority"]', timeout=20_000)
        await page.wait_for_timeout(1_500)
        names = [n.strip() for n in await page.eval_on_selector_all("h1", "els => els.map(e => e.innerText)") if n.strip()]
        sites = await page.eval_on_selector_all('a[data-item-id="authority"]', "els => els.map(e => e.href)")
        labels = await page.eval_on_selector_all("[aria-label]", "els => els.map(e => e.getAttribute('aria-label'))")
        out = {"ok": True, "name": names[0] if names else "", "website": sites[0] if sites else "", "reviews": None, "rating": None}
        for label in labels:
            label = (label or "").strip()
            if out["reviews"] is None and _REVIEWS.match(label):
                out["reviews"] = int(re.sub(r"[,.]", "", _REVIEWS.match(label).group(1)))
            if out["rating"] is None and STARS.match(label):
                out["rating"] = float(STARS.match(label).group(1).replace(",", "."))
        # The panel has to be this business, or nothing read from it means anything.
        mine = {w for w in re.findall(r"\w{3,}", cand["name"].lower())}
        theirs = {w for w in re.findall(r"\w{3,}", out["name"].lower())}
        if not out["name"] or (mine and not mine & theirs):
            return {"ok": False, "why": f"listing shows {out['name']!r}"}
        return out
    except GoogleBlocked:
        raise
    except Exception as exc:
        return {"ok": False, "why": f"{type(exc).__name__}: {str(exc).splitlines()[0][:70]}"}
    finally:
        await page.close()


def site_signals(cand: dict, first: dict, second: dict | None, https: str | None) -> tuple[list[dict], list[dict]]:
    """Signals the two visits support, and the ones they do not (with the reason)."""
    kept, dropped = [], []
    claimed = {g["key"] for g in cand["gaps"]}
    home = first.get("final_url") or cand["website"]

    def drop(key: str, why: str) -> None:
        if key in claimed:
            dropped.append({"key": key, "why": why})

    if first["state"] == "dead":
        if second and second["state"] == "dead":
            detail = {"how": second["how"], "link": cand["listed_url"]}
            if second.get("note"):
                detail["note"] = second["note"]
            kept.append({"key": "dead_site", "source_url": cand["maps_link"], "detail": detail})
        else:
            drop("dead_site", "failed once, then " + (second or {}).get("state", "was not retried"))
        for key in ("no_ads_tags", "stale", "not_https"):
            drop(key, "the site did not load")
        return kept, dropped
    if first["state"] == "unclear":
        for key in ("dead_site", "no_ads_tags", "stale", "not_https"):
            drop(key, "could not be settled: " + first["why"])
        return kept, dropped

    drop("dead_site", "the site loads in a browser")
    if root_domain(home) != root_domain(cand["listed_url"]):
        # The link on the listing sends visitors to someone else's domain. Whatever that page shows,
        # it is not this business's site, so nothing is said about it.
        for key in ("no_ads_tags", "stale", "not_https"):
            drop(key, f"the listing's link redirects to a different site ({urlsplit(home).netloc})")
        return kept, dropped
    mark = first["copyright"]
    if mark and mark["year"] <= STALE_MAX_YEAR:
        kept.append({"key": "stale", "source_url": home, "detail": mark})
    else:
        drop("stale", f"the rendered footer shows {mark['year']}" if mark else "no copyright year beside a copyright mark")

    if home.startswith("http://") and https and https not in ("works", "unclear"):
        secure = "https://" + home.split("://", 1)[1]
        kept.append({"key": "not_https", "source_url": secure, "detail": {"https": https, "https_url": secure}})
    else:
        drop("not_https", "the site ends up on https" if home.startswith("https://") else f"its https address {https}")

    if "no_ads_tags" in claimed:
        visits = [first] + ([second] if second else [])
        seen = next((v["tags"][0] for v in visits if v["state"] == "ok" and v["tags"]), "")
        if seen:
            drop("no_ads_tags", "tag found: " + seen)
        elif any(v["state"] != "ok" for v in visits) or len(visits) < 2:
            drop("no_ads_tags", "the second visit did not load cleanly")
        elif any(v["consent"] for v in visits):
            drop("no_ads_tags", f"a consent tool is present ({visits[0]['consent'] or visits[1]['consent']}) and may be holding tags back")
        elif any(v["shopify"] for v in visits):
            drop("no_ads_tags", "Shopify loads pixels in a sandbox this check cannot see into")
        else:
            kept.append({"key": "no_ads_tags", "source_url": home, "detail": {}})
    return kept, dropped


async def verify(candidates: list[dict], signals: list[dict], channel: str) -> dict:
    today = dt.date.today().isoformat()
    stats = {"listings_read": 0, "listings_failed": 0, "sites_opened": 0, "sites_unclear": 0, "confirmed": 0, "dropped": 0}
    patterns = {s["key"]: s for s in signals}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel=channel, headless=True)
        # Certificate problems are ignored for reading a page, but never for the https check.
        contexts = {"lenient": await browser.new_context(locale="en-US", viewport={"width": 1280, "height": 900}, ignore_https_errors=True)}
        strict = await browser.new_context(locale="en-US", viewport={"width": 1280, "height": 900})
        maps = await browser.new_context(locale="en-US", viewport={"width": 1280, "height": 900})
        sem = asyncio.Semaphore(4)
        maps_sem = asyncio.Semaphore(2)  # listings are read two at a time: slower, and kinder to Maps

        async def read_listing(cand: dict) -> None:
            async with maps_sem:
                await asyncio.sleep(random.uniform(0.5, 1.5))
                cand["listing"] = await listing(maps, cand)

        async def open_site(cand: dict, slot: str) -> None:
            async with sem:
                seen = cand[slot] = await visit(contexts["lenient"], cand["listed_url"])
                if seen["state"] == "ok" and seen["final_url"].startswith("http://"):
                    cand[slot + "_https"] = await https_answer(strict, seen["final_url"], cand["listed_url"])
                link = urlsplit(cand["listed_url"])
                if seen["state"] == "dead" and seen["how"].startswith("returns a ") and (link.path.strip("/") or link.query):
                    # A 404 on a deep link is a broken link, not a dead site, if the homepage still loads.
                    home = await visit(contexts["lenient"], f"{link.scheme}://{link.netloc}/")
                    if home["state"] == "ok":
                        seen["how"] = f"is broken: it {seen['how']}, though the domain's own homepage loads"

        quote_pages: dict[str, dict] = {}

        async def read_page(url: str) -> None:
            async with sem:
                quote_pages[url] = await visit(contexts["lenient"], url)

        def read_quote(gap: dict) -> None:
            """A quoted signal stands only if the words are on the rendered page today."""
            sig = patterns.get(gap["key"])
            seen = quote_pages.get(gap["source_url"])
            if sig is None or seen is None or seen["state"] != "ok":
                gap["_ok"] = False
                gap["_why"] = "its page could not be read today, so the quote was not confirmed"
                return
            if sig.get("where") == "emails":
                address = gap["label"].split(": ")[-1].rstrip(".")
                gap["_ok"] = address.lower() in seen["text"].lower()
                return
            match = re.search(sig["pattern"], seen["text"], re.I)
            gap["_ok"] = bool(match)
            if match:
                gap["label"] = sig["label"].format(match=snippet(seen["text"], match))

        try:
            await asyncio.gather(*(read_listing(c) for c in candidates))
            # A listing that timed out gets one more try, one at a time. A slow connection should not
            # cost a business its place; a second failure does.
            for cand in candidates:
                if not cand["listing"]["ok"] and cand.get("maps_link"):
                    await asyncio.sleep(2)
                    cand["listing"] = await listing(maps, cand)
            site_keys = {"dead_site", "not_https", "stale", "no_ads_tags"}
            with_site = [c for c in candidates if c.get("listed_url") and c["listing"]["ok"]
                         and any(g["key"] in site_keys for g in c["gaps"])]
            await asyncio.gather(*(open_site(c, "_v1") for c in with_site))
            # Second visit, in a fresh context, for every claim that something is missing or broken.
            again = [c for c in with_site if c["_v1"]["state"] == "dead" or c.get("_v1_https") not in (None, "works", "unclear")
                     or (c["_v1"]["state"] == "ok" and not c["_v1"]["tags"] and any(g["key"] == "no_ads_tags" for g in c["gaps"]))]
            await contexts["lenient"].close()
            contexts["lenient"] = await browser.new_context(locale="en-US", viewport={"width": 1280, "height": 900}, ignore_https_errors=True)
            await asyncio.gather(*(open_site(c, "_v2") for c in again))
            for cand in candidates:  # a homepage already open in this run does not need opening again
                first = cand.get("_v1")
                if first and first["state"] == "ok":
                    quote_pages.update({cand["website"]: first, cand["listed_url"]: first, first["final_url"]: first})
            quoted = [g for c in candidates for g in c["gaps"] if "weight" in g]
            await asyncio.gather(*(read_page(url) for url in sorted({g["source_url"] for g in quoted} - set(quote_pages))))
            for gap in quoted:
                read_quote(gap)
        finally:
            await browser.close()

    for cand in candidates:
        seen = cand.pop("listing")
        first, second = cand.pop("_v1", None), cand.pop("_v2", None)
        answers = [cand.pop("_v1_https", None), cand.pop("_v2_https", None)]
        # No https only counts when its https address failed on both visits, the same way.
        https = answers[1] if answers[0] and answers[0] == answers[1] else ("works" if "works" in answers else "unclear")
        claimed = list(cand["gaps"])
        kept: list[dict] = []
        dropped: list[dict] = []
        if not seen["ok"]:
            # Every line in a pack quotes the listing, so without it the business cannot be used.
            stats["listings_failed"] += 1
            cand["verified_on"] = today
            cand["dropped_signals"] = [{"key": g["key"], "why": "the Google listing could not be read: " + seen["why"]} for g in claimed]
            cand["gaps"] = []
            stats["dropped"] += len(claimed)
            continue
        stats["listings_read"] += 1
        if seen["reviews"] is not None:
            cand["review_count"] = str(seen["reviews"])
        if seen["rating"] is not None:
            cand["review_rating"] = str(seen["rating"])

        if any(g["key"] == "no_site" for g in claimed):
            if seen["website"]:
                dropped.append({"key": "no_site", "why": "the listing has a Website button today"})
            else:
                kept.append({"key": "no_site", "source_url": cand["maps_link"], "detail": {}})
        if first is not None:
            if not seen["website"]:
                dropped += [{"key": g["key"], "why": "the listing no longer shows a website"} for g in claimed
                            if g["key"] in ("dead_site", "not_https", "stale", "no_ads_tags")]
            else:
                stats["sites_opened" if first["state"] != "unclear" else "sites_unclear"] += 1
                site_kept, site_dropped = site_signals(cand, first, second, https)
                kept += site_kept
                dropped += site_dropped
        reviews = float(cand["review_count"]) if str(cand["review_count"]).strip() else None
        rating = float(cand["review_rating"]) if str(cand["review_rating"]).strip() else None
        compared = comparison_gaps(reviews, rating, cand["pool"], cand["maps_link"])
        kept += compared
        dropped += [{"key": g["key"], "why": "today's listing figures no longer support it"} for g in claimed
                    if g["key"] in ("low_reviews", "low_rating") and g["key"] not in {c["key"] for c in compared}]
        for gap in claimed:
            if "weight" in gap and gap.pop("_ok", False):
                kept.append(gap)
            elif "weight" in gap:
                dropped.append({"key": gap["key"], "why": gap.pop("_why", "the quoted words are not on the rendered page today")})
        for gap in kept:
            gap["checked"] = today
        cand["gaps"] = kept
        cand["dropped_signals"] = dropped
        cand["verified_on"] = today
        if first and first["state"] == "ok":
            cand["website"] = first["final_url"]
        if first:
            cand["site_check"] = [{k: v for k, v in seen_page.items() if k not in ("text", "html")}
                                  for seen_page in (first, second) if seen_page]
        stats["confirmed"] += len(kept)
        stats["dropped"] += len(dropped)
    for key in ABSENCE:
        stats[key] = sum(1 for c in candidates for g in c["gaps"] if g["key"] == key)
    return stats


def main() -> int:
    utf8_stdout()
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("agency")
    ap.add_argument("--want", default="", help="same signal keys given to prospects.py")
    ap.add_argument("--top", type=int, default=26, help="verify this many of the best candidates")
    ap.add_argument("--signals", type=Path, help="the custom signals file given to prospects.py, if one was")
    ap.add_argument("--only", default="", help="comma-separated candidate keys: verify just these, whatever their rank")
    args = ap.parse_args()

    path = SCORED / "packs" / f"{args.agency}.candidates.json"
    candidates = json.loads(path.read_text(encoding="utf-8"))
    wanted = {w.strip() for w in args.want.split(",") if w.strip()}
    signals = json.loads(args.signals.read_text(encoding="utf-8")) if args.signals else []
    only = {k.strip() for k in args.only.split(",") if k.strip()}
    todo = [c for c in candidates if not c.get("verified_on") and (not only or c["key"] in only)][:args.top]
    # Candidate keys are the businesses' own domains, so they never go into the public run log.
    command = "python " + " ".join(["src/verify.py"] + sys.argv[1:])
    if args.only:
        command = command.replace(args.only, "<businesses>")
    try:
        stats = asyncio.run(verify(todo, signals, os.getenv("LEADFORGE_BROWSER", "msedge")))
    except GoogleBlocked as exc:
        console.print(f"[red]Google blocked the listing checks: {exc}. Stopped. Nothing was written.[/red]")
        log_run(command, {"verified": 0}, failures=[f"google blocked: {exc}"], redact=(args.agency,))
        return 3

    for cand in candidates:
        cand["gap_score"] = gap_score(cand["gaps"], wanted)
    # Verified candidates with something to say come first. The rest cannot be used at all.
    candidates.sort(key=lambda c: (not (c.get("verified_on") and c["gaps"]), -c["gap_score"], -float(c["review_count"] or 0)))
    path.write_text(json.dumps(candidates, ensure_ascii=False, indent=1), encoding="utf-8")
    header = f"# Candidates for {args.agency} after browser verification on {dt.date.today().isoformat()}"
    usable = [c for c in candidates if c.get("verified_on") and c["gaps"]]
    (SCORED / "packs" / f"{args.agency}.candidates.md").write_text(
        digest_text(usable, set(), header, len(usable)), encoding="utf-8")

    stats["usable"] = len(usable)
    log_run(command, stats, redact=(args.agency,))
    console.print("[bold]verify[/bold] " + ", ".join(f"{k}={v}" for k, v in stats.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
