"""Shared paths and helpers for the LeadForge pipeline."""
from __future__ import annotations

import datetime as dt
import json
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
JOBS = ROOT / "outreach" / "jobs"
JOB_WORDING = ROOT / "outreach" / "job_ask.json"  # the operator's own wording; gitignored
RUNLOG = ROOT / "RUNLOG.md"
REGIONS = ROOT / "config" / "regions"
DEFAULT_REGION = "gulf"  # what a record with no region on it belongs to: the first one LeadForge worked

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


def region(name: str | None = None) -> dict:
    """One region's settings: where it is, what to search for, and whether outreach is drafted for it.

    The region is a value read from config/regions/<name>.yaml. The code is the same for all of them.
    """
    import yaml

    name = (name or DEFAULT_REGION).lower()
    path = REGIONS / f"{name}.yaml"
    if not path.exists():
        raise SystemExit(f"No region {name!r}. Known regions: {', '.join(region_names())}")
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    cfg["name"] = name
    cfg["countries"] = {code.upper() for code in cfg["countries"]}
    cfg["queries"] = list(cfg.get("queries") or []) + [
        f"{search} in {city}" for search in cfg.get("searches") or [] for city in cfg.get("cities") or []]
    return cfg


def region_names() -> list[str]:
    return sorted(path.stem for path in REGIONS.glob("*.yaml"))


def in_region(maps: dict, cfg: dict) -> bool:
    """Is a Maps listing inside the region? By its country when it carries one, otherwise by its address."""
    if maps.get("country"):
        return maps["country"].upper() in cfg["countries"]
    return any(word in (maps.get("address") or "").lower() for word in cfg["address_words"])


def region_of(maps: dict) -> str | None:
    """The region a listing falls in, or None when it is in none of them."""
    return next((name for name in region_names() if in_region(maps, region(name))), None)


def outreach_open(record: dict) -> bool:
    """May anything be drafted for this scored agency? Not while its region is "scored only"."""
    return bool(region(record.get("region") or DEFAULT_REGION).get("outreach"))


def job_wording(path: Path = JOB_WORDING) -> dict:
    """The operator's wording for the job ask: subject, pitch, proof lines, follow-ups."""
    if not path.exists():
        raise SystemExit(f"{path.name} is missing. Copy examples/job_ask.example.json to outreach/job_ask.json "
                         "and put your own wording in it.")
    return json.loads(path.read_text(encoding="utf-8"))


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
