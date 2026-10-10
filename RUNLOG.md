# RUNLOG

Every pipeline run appends an entry here: the command, the counts, and any failures.
Counts only. No lead names or scraped data are written to this file, so it is safe to publish.

## Decisions

- **2026-10-10 — Discovery engine: Playwright fallback instead of gosom in Docker.**
  Docker is not installed on this machine and neither is WSL (Windows 11 Home, so Docker Desktop
  would need a WSL2 install and a reboot). The brief says not to spend time on that and to drop a
  tool that fights back. `src/discover.py` keeps the gosom Docker path (`--engine docker`, used
  automatically when the daemon is running) but that path is **untested here**. The fallback in
  `src/maps_playwright.py` drives the installed Edge, reads results from the JSON payload Maps
  itself fetches, and writes the same schema.
- **2026-10-10 — Review counts need a second pass.** Maps omits review counts from search results
  for signed-out sessions, so the fallback engine visits each place page once (4 at a time, images
  blocked) to read them.
- **2026-10-10 — "depth 1" in the fallback engine** means the first results page plus one scroll,
  roughly 20 to 40 places per query.
- **2026-10-10 — Emails come from enrichment, not discovery, on full runs.** `--email` on
  `discover.py` does a homepage-only lookup (used for the validation scrape). The full agency run
  skips it because `enrich.py` fetches the same pages anyway and checks MX records.
- **2026-10-10 — Listings whose "website" is a social or directory profile** (Instagram, Facebook,
  Linktree and so on) are tagged `website_kind=platform` and never used as a dedupe key.
- **2026-10-10 — `packs/` and `outreach/drafts/` are gitignored** along with `data/`. They contain
  real scraped businesses. Only the anonymized example in `examples/` is committed.

## Runs

### 2026-10-10T18:21:31+05:00
- **Command:** `python src/discover.py queries/validation.txt validation --email`
- **Counts:** queries=1, raw_rows=20, unique=20, with_site=20, platform_only=0, no_website=0, with_email=17, with_review_count=20
- **Failures (2):**
  - 1 × 404
  - 1 × connect: [Errno 11001] getaddrinfo failed
- **Notes:** engine=playwright, output=data/raw/validation.csv
