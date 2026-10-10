"""Verify pack candidates in a real browser before anything is claimed about them.

    python src/verify.py <agency-domain> --want no_chat,no_booking --top 26
    python src/verify.py <agency-domain> --want no_chat,no_booking --top 26 --force    # second pass

enrich.py reads raw HTML. A WhatsApp button, chat widget, booking widget or ad tag that is injected
by JavaScript would be invisible to it, and "no chat on your site" would then be wrong. This step
loads each candidate's homepage in the installed Edge or Chrome, waits for scripts to run, and
re-tests the same patterns against the rendered page.

A gap the rendered page contradicts is removed from the candidate. A gap that survives is marked
as confirmed in its wording. One page per site, 4 at a time.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys

from dotenv import load_dotenv
from playwright.async_api import async_playwright
from rich.console import Console

from common import ROOT, SCORED, log_run, utf8_stdout
from enrich import BOOKING_CTA, SOCIALS, SOURCE_SIGNALS
from prospects import digest_text, gap_score

CONFIRMED = " Confirmed on the rendered homepage as well."
# Widgets that only show up as DOM nodes once their script has run.
RENDERED_CHAT = r"joinchat|chaty|wa-chat|whatsapp-(?:button|float|widget|chat)|wa__btn|click-to-chat|chat-widget|chatbot-widget|tawk|crisp-client|intercom-|tidio|zsiq|landbot|drift-widget|fb-customerchat|hubspot-messages"
console = Console()


async def render(context, url: str) -> tuple[str, str] | None:
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=35_000)
        await page.wait_for_timeout(4_500)
        # Chat and WhatsApp widgets often wait for a scroll or an idle timer before they mount.
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(4_500)
        return await page.content(), await page.inner_text("body")
    except Exception:
        return None
    finally:
        await page.close()


def contradicted(key: str, html: str, text: str) -> str:
    """Return what the rendered page shows that contradicts this gap, or "" if the gap stands."""
    def found(name: str) -> str:
        match = re.search(SOURCE_SIGNALS[name], html, re.I)
        return match.group(0)[:40] if match else ""

    if key == "no_chat":
        widget = re.search(RENDERED_CHAT, html, re.I)
        return found("whatsapp_link") or found("chat_widget") or (widget.group(0) if widget else "")
    if key == "no_booking":
        cta = re.search(BOOKING_CTA, text, re.I)
        return found("booking_system") or (" ".join(cta.group(0).split()) if cta else "")
    if key == "booking_cta_only":
        return found("booking_system")
    if key == "no_ads_tags":
        return found("meta_pixel") or found("google_ads_tag") or found("gtm")
    if key == "no_viewport":
        return "viewport meta" if re.search(r"<meta[^>]+name=[\"']viewport", html, re.I) else ""
    if key == "no_meta_description":
        match = re.search(r"<meta[^>]+name=[\"']description[\"'][^>]*content=[\"']([^\"']{10,})", html, re.I)
        return "meta description" if match else ""
    if key == "no_socials":
        for pattern in SOCIALS.values():
            if re.search(r"href=[\"'][^\"']*" + pattern, html, re.I):
                return "social link"
    return ""


CHECKABLE = {"no_chat", "no_booking", "booking_cta_only", "no_ads_tags", "no_viewport", "no_meta_description", "no_socials"}


async def verify(candidates: list[dict], channel: str, force: bool = False) -> dict:
    stats = {"rendered": 0, "render_failed": 0, "gaps_confirmed": 0, "gaps_downgraded": 0, "gaps_removed": 0}
    sem = asyncio.Semaphore(4)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel=channel, headless=True)
        context = await browser.new_context(locale="en-US", viewport={"width": 1280, "height": 900},
                                            ignore_https_errors=True)

        async def one(cand: dict) -> None:
            if (cand.get("rendered") and not force) or not cand.get("website"):
                return
            if cand.get("status") in ("dead", "http_error", "parked", "placeholder"):
                # The crawler could not load it. If a real browser can, the site is not down.
                async with sem:
                    result = await render(context, cand["website"])
                    if not (result and len(result[1]) > 300) and cand["website"].startswith("http://"):
                        # Real browsers upgrade http links to https before giving up. So must we.
                        result = await render(context, "https://" + cand["website"][7:])
                cand["rendered"] = True
                if result and len(result[1]) > 300:
                    stats["gaps_removed"] += 1
                    cand["gaps"] = [g for g in cand["gaps"] if g["key"] != "dead_site"]
                    cand.setdefault("removed_gaps", []).append({"key": "dead_site", "rendered_page_shows": "page loads in a browser"})
                else:
                    stats["gaps_confirmed"] += 1
                    for gap in cand["gaps"]:
                        if gap["key"] == "dead_site" and "browser" not in gap["label"]:
                            gap["label"] += " It did not load in a real browser either."
                return
            if cand.get("status") != "ok":
                return
            async with sem:
                result = await render(context, cand["website"])
            if result is None:
                stats["render_failed"] += 1
                return
            html, text = result
            stats["rendered"] += 1
            cand["rendered"] = True
            kept = []
            for gap in cand["gaps"]:
                if gap["key"] not in CHECKABLE:
                    kept.append(gap)
                    continue
                seen = contradicted(gap["key"], html, text)
                if seen and gap["key"] == "no_booking" and not re.search(SOURCE_SIGNALS["booking_system"], html, re.I):
                    # There is a booking prompt after all, but still no booking system: a weaker gap.
                    stats["gaps_downgraded"] += 1
                    kept.append({"key": "booking_cta_only", "source_url": gap["source_url"], "label": (
                        f"The site has a booking or enquiry prompt (\"{seen}\") but no booking system on the "
                        "rendered homepage, so requests most likely go to a form or a phone call.")})
                    continue
                if seen:
                    stats["gaps_removed"] += 1
                    cand.setdefault("removed_gaps", []).append({"key": gap["key"], "rendered_page_shows": seen})
                else:
                    stats["gaps_confirmed"] += 1
                    if CONFIRMED not in gap["label"]:
                        gap["label"] += CONFIRMED
                    kept.append(gap)
            cand["gaps"] = kept

        try:
            await asyncio.gather(*(one(c) for c in candidates))
        finally:
            await browser.close()
    return stats


def main() -> int:
    utf8_stdout()
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("agency")
    ap.add_argument("--want", default="", help="same gap keys given to prospects.py")
    ap.add_argument("--top", type=int, default=26, help="verify this many of the best candidates")
    ap.add_argument("--force", action="store_true",
                    help="render again even if already checked; a gap then has to survive both passes")
    args = ap.parse_args()

    path = SCORED / "packs" / f"{args.agency}.candidates.json"
    candidates = json.loads(path.read_text(encoding="utf-8"))
    wanted = {w.strip() for w in args.want.split(",") if w.strip()}
    relevant = [c for c in candidates if not wanted or any(g["key"] in wanted or "weight" in g for g in c["gaps"])]
    stats = asyncio.run(verify(relevant[:args.top], os.getenv("LEADFORGE_BROWSER", "msedge"), args.force))

    for cand in candidates:
        cand["gap_score"] = gap_score(cand["gaps"], wanted)
    # Verified candidates first: an unverified gap should never be picked over a confirmed one.
    candidates = [c for c in candidates if c["gaps"]]
    candidates.sort(key=lambda c: (not c.get("rendered", c["status"] != "ok"), -c["gap_score"]))
    path.write_text(json.dumps(candidates, ensure_ascii=False, indent=1), encoding="utf-8")
    header = f"# Candidates for {args.agency} after browser verification"
    (SCORED / "packs" / f"{args.agency}.candidates.md").write_text(
        digest_text(candidates, wanted, header, args.top), encoding="utf-8")

    log_run("python " + " ".join(["src/verify.py"] + sys.argv[1:]), stats, redact=(args.agency,))
    console.print("[bold]verify[/bold] " + ", ".join(f"{k}={v}" for k, v in stats.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
