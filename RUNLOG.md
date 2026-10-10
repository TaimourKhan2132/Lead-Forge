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
- **2026-10-10 — `packs/`, `outreach/drafts/` and `queries/packs/` are gitignored** along with
  `data/`. They contain real scraped businesses, or name the agency being pitched. Only the
  fictional example in `examples/` is committed.
- **2026-10-10 — This log names no businesses.** Failure lines identify the site that failed, so
  the detail goes to `data/logs/failures.log` (gitignored) and this file gets grouped reasons only.
  Sample-pack commands have the agency's domain replaced with `<agency>`. The first commit's
  validation entry listed two failing domains; it was rewritten before anything was pushed.
- **2026-10-10 — No Clutch shortlist yet.** `data/raw/clutch_shortlist.csv` did not exist when the
  agency run started, so the run continued on Maps data alone. Paste the file and run
  `python src/merge_clutch.py data/raw/agencies_gulf.csv`, then re-run enrich (cached leads are
  skipped) to bring Clutch leads in at the front of the queue.
- **2026-10-10 — Triage before qualification.** 325 agencies is too many to judge one by one, so
  `src/shortlist.py` applies cheap rules (dead site, outside the Gulf, big-company signals, no
  relevant services) and sends the best 70 to the reasoning layer.

## Runs

### 2026-10-10T18:21:31+05:00
- **Command:** `python src/discover.py queries/validation.txt validation --email`
- **Counts:** queries=1, raw_rows=20, unique=20, with_site=20, platform_only=0, no_website=0, with_email=17, with_review_count=20
- **Failures (2):**
  - 1 × 404
  - 1 × connect: [Errno 11001] getaddrinfo failed
- **Notes:** engine=playwright, output=data/raw/validation.csv

### 2026-10-10T18:22:53+05:00
- **Command:** `python src/enrich.py data/raw/validation.csv --out data/enriched/_validation --force`
- **Counts:** leads=20, dead=1, http_error=1, ok=18
- **Failures:** none

### 2026-10-10T18:24:42+05:00
- **Command:** `python src/discover.py queries/agencies_gulf.txt agencies_gulf --concurrency 2`
- **Counts:** queries=20, raw_rows=418, unique=325, with_site=300, platform_only=1, no_website=24, with_email=0, with_review_count=325
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/agencies_gulf.csv

### 2026-10-10T18:32:10+05:00
- **Command:** `python src/enrich.py data/raw/agencies_gulf.csv`
- **Counts:** leads=325, blocked=15, dead=22, http_error=7, no_website=24, ok=256, platform_only=1
- **Failures:** none

### 2026-10-10T18:32:49+05:00
- **Command:** `python src/shortlist.py --top 70`
- **Counts:** enriched=325, eligible=207, shortlisted=70, batches=7
- **Failures:** none
- **Notes:** skipped: site no_website=24, big-company signal=23, site dead=22, no relevant services found in site copy=19, site blocked=15, site http_error=7, outside UAE/KSA/Qatar=7, site platform_only=1

### 2026-10-10T18:34:32+05:00
- **Command:** `python src/qualify.py ingest data/scored/_batches/batch_01.json`
- **Counts:** verdicts=10, written=10, rejected=0
- **Failures:** none

### 2026-10-10T18:40:06+05:00
- **Command:** `python src/qualify.py ingest data/scored/_batches/batch_02.json`
- **Counts:** verdicts=10, written=10, rejected=0
- **Failures:** none

### 2026-10-10T18:40:07+05:00
- **Command:** `python src/qualify.py ingest data/scored/_batches/batch_03.json`
- **Counts:** verdicts=10, written=10, rejected=0
- **Failures:** none

### 2026-10-10T18:40:09+05:00
- **Command:** `python src/qualify.py ingest data/scored/_batches/batch_04.json`
- **Counts:** verdicts=10, written=10, rejected=0
- **Failures:** none

### 2026-10-10T18:40:10+05:00
- **Command:** `python src/qualify.py ingest data/scored/_batches/batch_05.json`
- **Counts:** verdicts=10, written=10, rejected=0
- **Failures:** none

### 2026-10-10T18:40:11+05:00
- **Command:** `python src/qualify.py ingest data/scored/_batches/batch_06.json`
- **Counts:** verdicts=10, written=10, rejected=0
- **Failures:** none

### 2026-10-10T18:40:13+05:00
- **Command:** `python src/qualify.py ingest data/scored/_batches/batch_07.json`
- **Counts:** verdicts=10, written=10, rejected=0
- **Failures:** none

### 2026-10-10T18:40:18+05:00
- **Command:** `python src/qualify.py summary --top 15`
- **Counts:** scored=70, tier_A=20, tier_B=42, tier_C=8
- **Failures:** none
