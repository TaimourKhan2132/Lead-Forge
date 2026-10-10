"""Fallback Google Maps discovery engine, for machines without Docker.

Drives the system's Edge/Chrome through Playwright. Search results are read from the JSON
payload Maps itself fetches (far more stable than CSS class names), with a DOM parse as a
safety net. Review counts are not in that payload for signed-out sessions, so they come from
a second, throttled pass over the place pages.

Deliberately small: no proxies, no stealth, at most 4 pages at once. If Google challenges the
session we raise GoogleBlocked and the run stops.
"""
from __future__ import annotations

import asyncio
import json
import random
import re
from urllib.parse import quote_plus

from playwright.async_api import BrowserContext, Page, async_playwright
from playwright.async_api import TimeoutError as PWTimeout

SEARCH_URL = "https://www.google.com/maps/search/{q}?hl=en"
PLACE_URL = "https://www.google.com/maps/place/?q=place_id:{pid}"
MAX_CONCURRENCY = 4
_FID = re.compile(r"^0x[0-9a-f]+:0x[0-9a-f]+$")
_REVIEWS = re.compile(r"^([\d,.]+)\s+reviews?$", re.I)


class GoogleBlocked(RuntimeError):
    """Google served a challenge or block page. Stop; do not retry harder."""


def _dig(obj, *path):
    for key in path:
        if not isinstance(obj, list) or not -len(obj) <= key < len(obj):
            return None
        obj = obj[key]
        if obj is None:
            return None
    return obj


def _find_places(node, depth: int = 0):
    """Yield place records from a search payload without relying on their outer position."""
    if not isinstance(node, list):
        return
    fid, name = _dig(node, 10), _dig(node, 11)
    if len(node) > 40 and isinstance(fid, str) and _FID.match(fid) and isinstance(name, str):
        yield node
        return
    if depth < 4:
        for child in node:
            yield from _find_places(child, depth + 1)


def parse_search_payload(text: str) -> list[dict]:
    text = text.lstrip()
    if text.startswith(")]}'"):
        text = text[4:].lstrip()
    try:
        data, _ = json.JSONDecoder().raw_decode(text)
    except ValueError:
        return []
    places = []
    for e in _find_places(data):
        cats = [c for c in (_dig(e, 13) or []) if isinstance(c, str)]
        pid = _dig(e, 78) or ""
        places.append({
            "title": _dig(e, 11),
            "category": cats[0] if cats else "",
            "categories": "; ".join(cats),
            "website": _dig(e, 7, 0) or "",
            "phone": _dig(e, 178, 0, 0) or "",
            "review_rating": _dig(e, 4, 7),
            "review_count": _dig(e, 4, 8),
            "address": _dig(e, 39) or _dig(e, 18) or "",
            "country": _dig(e, 243) or "",
            "latitude": _dig(e, 9, 2),
            "longitude": _dig(e, 9, 3),
            "place_id": pid,
            "link": PLACE_URL.format(pid=pid) if pid else "",
        })
    return places


_DOM_CARDS_JS = """
els => els.filter(e => e.querySelector('a[href*="/maps/place/"]')).map(e => {
  const a = e.querySelector('a[href*="/maps/place/"]');
  const site = e.querySelector('a[data-value="Website"]');
  const star = e.querySelector('span[role="img"][aria-label*="star"]');
  return {title: a.getAttribute('aria-label') || '', link: a.href,
          website: site ? site.href : '', stars: star ? star.getAttribute('aria-label') : '',
          text: e.innerText};
})
"""


def _parse_dom_card(card: dict) -> dict:
    lines = [ln.strip() for ln in card["text"].split("\n") if ln.strip()]
    category = next((ln.split("·")[0].strip() for ln in lines if "·" in ln), "")
    phone = re.search(r"\+?\d[\d\s-]{7,}\d", card["text"])
    rating = re.search(r"([\d.]+)\s+stars?", card.get("stars") or "")
    return {
        "title": card["title"], "category": category, "categories": category,
        "website": card["website"], "phone": phone.group(0) if phone else "",
        "review_rating": float(rating.group(1)) if rating else None, "review_count": None,
        "address": "", "country": "", "latitude": None, "longitude": None,
        "place_id": "", "link": card["link"],
    }


async def _check_blocked(page: Page) -> None:
    if "/sorry/" in page.url or "unusual traffic" in (await page.title()).lower():
        raise GoogleBlocked(f"challenge page at {page.url[:80]}")


async def _dismiss_consent(page: Page) -> None:
    if "consent.google" not in page.url:
        return
    for label in ("Reject all", "Reject All"):  # the privacy-preserving choice
        button = page.locator(f'button:has-text("{label}")').first
        if await button.count():
            await button.click()
            await page.wait_for_load_state("domcontentloaded")
            return


async def _search(context: BrowserContext, query: str, depth: int) -> list[dict]:
    page = await context.new_page()
    payloads: list[str] = []

    async def on_response(resp):
        if "tbm=map" in resp.url:
            try:
                payloads.append(await resp.text())
            except Exception:
                pass

    page.on("response", on_response)
    try:
        await page.goto(SEARCH_URL.format(q=quote_plus(query)), wait_until="domcontentloaded", timeout=60_000)
        await _dismiss_consent(page)
        await _check_blocked(page)
        try:
            await page.wait_for_selector('div[role="feed"]', timeout=30_000)
        except PWTimeout:
            await _check_blocked(page)
            return []  # a single-result or zero-result query has no feed
        await page.wait_for_timeout(2_000)
        for _ in range(depth):
            await page.eval_on_selector('div[role="feed"]', "el => el.scrollBy(0, el.scrollHeight)")
            await page.wait_for_timeout(2_200 + random.randint(0, 600))

        places: dict[str, dict] = {}
        for body in payloads:
            for place in parse_search_payload(body):
                places.setdefault(place["place_id"] or place["title"], place)
        if not places:  # payload shape changed: fall back to what is on screen
            cards = await page.eval_on_selector_all('div[role="feed"] > div', _DOM_CARDS_JS)
            for card in cards:
                place = _parse_dom_card(card)
                places.setdefault(place["link"], place)
        for place in places.values():
            place["query"] = query
        return list(places.values())
    finally:
        await page.close()


async def _review_count(context: BrowserContext, place: dict) -> None:
    """Fill place['review_count'] from its place page. Leaves None when it can't be read."""
    if place.get("review_count") is not None:
        return
    if place.get("review_rating") is None:
        place["review_count"] = 0  # no rating shown means no reviews
        return
    if not place.get("link"):
        return
    page = await context.new_page()
    try:
        await page.goto(place["link"] + "&hl=en" if "?" in place["link"] else place["link"],
                        wait_until="domcontentloaded", timeout=45_000)
        await _check_blocked(page)
        await page.wait_for_selector('[aria-label$="reviews"], [aria-label$="review"]', timeout=15_000)
        labels = await page.eval_on_selector_all("[aria-label]", "els => els.map(e => e.getAttribute('aria-label'))")
        for label in labels:
            match = _REVIEWS.match((label or "").strip())
            if match:
                place["review_count"] = int(re.sub(r"[,.]", "", match.group(1)))
                return
    except PWTimeout:
        pass
    finally:
        await page.close()


async def _block_heavy(route):
    if route.request.resource_type in ("image", "media", "font"):
        await route.abort()
    else:
        await route.continue_()


async def discover(queries: list[str], depth: int = 1, concurrency: int = 2, reviews: bool = True,
                   channel: str = "msedge", on_progress=None) -> tuple[list[dict], list[str]]:
    """Run every query. Returns (places, failures). Raises GoogleBlocked on a challenge."""
    concurrency = max(1, min(concurrency, MAX_CONCURRENCY))
    failures: list[str] = []
    results: list[dict] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel=channel, headless=True)
        context = await browser.new_context(locale="en-US", viewport={"width": 1280, "height": 900})
        await context.route("**/*", _block_heavy)
        sem = asyncio.Semaphore(concurrency)

        async def run_query(query: str):
            async with sem:
                await asyncio.sleep(random.uniform(0.5, 1.5))
                try:
                    found = await _search(context, query, depth)
                except GoogleBlocked:
                    raise
                except Exception as exc:
                    failures.append(f"query '{query}': {type(exc).__name__}: {str(exc)[:120]}")
                    found = []
                if on_progress:
                    on_progress("query", query, len(found))
                return found

        try:
            for batch in await asyncio.gather(*(run_query(q) for q in queries)):
                results.extend(batch)

            if reviews:
                # One visit per place even when several queries returned it.
                unique: dict[str, dict] = {}
                for place in results:
                    unique.setdefault(place["place_id"] or place["link"], place)
                review_sem = asyncio.Semaphore(MAX_CONCURRENCY)

                async def run_review(place: dict):
                    async with review_sem:
                        await asyncio.sleep(random.uniform(0.2, 0.8))
                        try:
                            await _review_count(context, place)
                        except GoogleBlocked:
                            raise
                        except Exception as exc:
                            failures.append(f"reviews '{place['title'][:40]}': {type(exc).__name__}")
                        if on_progress:
                            on_progress("reviews", place["title"], place.get("review_count"))

                await asyncio.gather(*(run_review(p) for p in unique.values()))
                for place in results:
                    place["review_count"] = unique[place["place_id"] or place["link"]].get("review_count")
        finally:
            await browser.close()
    return results, failures
