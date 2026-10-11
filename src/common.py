"""Shared paths and helpers for the LeadForge pipeline."""
from __future__ import annotations

import datetime as dt
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlunparse

import tldextract

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
ENRICHED = DATA / "enriched"
SCORED = DATA / "scored"
PACKS = ROOT / "packs"
DRAFTS = ROOT / "outreach" / "drafts"
US_TRACK = ROOT / "outreach" / "us_track"
RUNLOG = ROOT / "RUNLOG.md"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36 LeadForge/0.1 (small-batch lead research; one visit per site)"
)

# A "website" on a Maps listing that is really a profile on someone else's platform.
# These must never be used as a dedupe key, and for sample packs they are a finding in themselves.
PLATFORM_DOMAINS = {
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com", "tiktok.com",
    "youtube.com", "wa.me", "whatsapp.com", "linktr.ee", "google.com", "goo.gl", "g.page",
    "business.site", "bit.ly", "t.me", "snapchat.com", "pinterest.com", "beacons.ai",
    "taplink.cc", "bio.link", "canva.site", "talabat.com", "zomato.com", "tripadvisor.com",
    "booking.com", "fresha.com", "vagaro.com", "bayut.com", "propertyfinder.ae", "dubizzle.com",
    "yellowpages.ae", "practo.com", "okadoc.com", "linkin.bio", "msha.ke", "carrd.co",
}

_extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)  # bundled snapshot, no network


def utf8_stdout() -> None:
    """Windows consoles default to cp1252; business names here are often Arabic."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def clean_url(url: str | None) -> str:
    """Normalise a listing's website: unwrap Google redirects, drop tracking params and fragments."""
    if not url:
        return ""
    url = url.strip()
    if url.startswith("/url?") or "google.com/url?" in url:
        target = parse_qs(urlparse(url).query).get("q")
        if target:
            url = target[0]
    if not re.match(r"^https?://", url, re.I):
        url = "http://" + url
    parts = urlparse(url)
    if not parts.netloc:
        return ""
    return urlunparse((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", "", "", ""))


def root_domain(url: str | None) -> str:
    """Registrable domain ("www.shop.example.co.uk" -> "example.co.uk"), or "" if there isn't one."""
    if not url:
        return ""
    ext = _extract(url)
    if not ext.domain or not ext.suffix:
        return ""
    return f"{ext.domain}.{ext.suffix}".lower()


def is_platform(domain: str) -> bool:
    return domain in PLATFORM_DOMAINS or any(domain.endswith("." + p) for p in PLATFORM_DOMAINS)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "unnamed"


def log_run(command: str, counts: dict, failures: list[str] | None = None, notes: str = "",
            redact: tuple[str, ...] = ()) -> None:
    """Append one entry to RUNLOG.md. Counts only: no lead names, so the log stays publishable.

    `redact` lists strings (a target agency's domain, say) to blank out of the command line.
    """
    for secret in redact:
        if secret:
            command = command.replace(secret, "<agency>")
            notes = notes.replace(secret, "<agency>")
    stamp = now_iso()
    lines = [f"\n### {stamp}", f"- **Command:** `{command}`"]
    lines.append("- **Counts:** " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    if failures:
        # Failure lines name the site that failed, so the detail stays in gitignored data/ and
        # the public log only gets the reasons, grouped.
        detail = DATA / "logs" / "failures.log"
        detail.parent.mkdir(parents=True, exist_ok=True)
        with detail.open("a", encoding="utf-8") as fh:
            fh.write(f"\n## {stamp}  {command}\n" + "\n".join(failures) + "\n")
        reasons = Counter(re.sub(r"\s+", " ", f.split(": ", 1)[-1])[:70] for f in failures)
        lines.append(f"- **Failures ({len(failures)}, detail in data/logs/failures.log):**")
        lines.extend(f"  - {n} × {reason}" for reason, n in reasons.most_common(8))
        if len(reasons) > 8:
            lines.append(f"  - ...and {len(reasons) - 8} other reasons")
    else:
        lines.append("- **Failures:** none")
    if notes:
        lines.append(f"- **Notes:** {notes}")
    with RUNLOG.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
