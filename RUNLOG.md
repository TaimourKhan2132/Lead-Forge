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
- **2026-10-10 — Eight verdicts were re-scored after a second read.** Before building packs, the
  top-ranked agencies were checked against the full stored page text, not just the digest. That
  changed facts for eight of them: the "person card" count double-counted one team and counted
  layout tiles on another; one agency turned out to sell data services itself; one has nine
  managers and an overseas delivery office; one names a founder and four staff. The corrected
  verdicts are in `data/scored/_batches/batch_08_rescore.json` and replaced the originals. The
  card count is now treated as a layout hint only, never as a headcount.
- **2026-10-10 — Pack order follows the corrected ranking.** The five packs are built for the five
  highest-scoring tier A agencies after the re-score. One of them sells to contractors, not
  shopfront businesses, so `prospects.py` gained `--signals`: per-agency fit signals read from the
  prospect's own site copy, used alongside the standard gaps.
- **2026-10-10 — Gaps are re-tested in a real browser (`src/verify.py`).** The first pack looked
  right until its "no WhatsApp or chat" claims were checked on the rendered page: several clinics
  had a WhatsApp button that only exists after JavaScript runs. Every gap now has to survive two
  rendered passes (scroll, then wait for late widgets). Across the four gap-based packs this
  removed 41 gaps before any prospect was chosen.
- **2026-10-10 — The booking pattern was too narrow.** It matched "book an appointment" but not
  "book a tour" or "book your appointment", which would have produced false "no way to book"
  claims. It is now deliberately broad, and the three packs already drafted were recomputed and
  re-verified with it. A booking prompt with no booking system is reported as the weaker gap it is.
- **2026-10-10 — "Dead" needs an https retry.** One prospect's listing links to `http://`, which
  times out, while `https://` loads normally. Browsers upgrade that silently, so the "site does
  not load" finding was wrong and the prospect was replaced. `enrich.py` and `verify.py` now retry
  over https before calling a site dead. **Not re-run:** the 22 agencies marked dead in the Phase 3
  crawl were fetched before this fix, so a few may be live. They were excluded from scoring, not
  mis-described. Re-crawl them with `python src/enrich.py data/raw/agencies_gulf.csv --force`.
- **2026-10-10 — Pack niches.** Each pack's niche comes from the agency's own site: a named client
  category in a testimonial, an industry page, a case study, or a product. Where the site names no
  sector, the pack says so in its first paragraph and explains the niche it used instead.
- **2026-10-10 — Tracker test.** One lead was marked `sent` to confirm the follow-up dates are set
  (day 3 and day 7), then reset to `drafted`. Nothing was sent.
- **2026-10-10 — Phase 9 not started,** as instructed. It waits until 10 emails have gone out.

## Open items

- **Docker path is untested.** `discover.py --engine docker` (gosom) is written but has never run
  on this machine, which has no Docker.
- **No Clutch shortlist yet.** Paste `data/raw/clutch_shortlist.csv` (`name,website`), then run
  `merge_clutch.py`, `enrich.py`, `shortlist.py` again.
- **Placeholders are unfilled.** `{{NAME}}`, `{{EMAIL}}`, `{{LINKEDIN}}`, `{{GITHUB}}` remain in the
  packs, drafts and README. Set them in `.env` and run `python src/pack.py fill`.
- **Agency qualification has no browser pass.** Only pack prospects are re-tested in a browser.

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

### 2026-10-10T18:43:43+05:00
- **Command:** `python src/qualify.py ingest data/scored/_batches/batch_08_rescore.json`
- **Counts:** verdicts=8, written=8, rejected=0
- **Failures:** none

### 2026-10-10T18:43:45+05:00
- **Command:** `python src/qualify.py summary --top 15`
- **Counts:** scored=70, tier_A=20, tier_B=42, tier_C=8
- **Failures:** none

### 2026-10-10T18:45:19+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=5, raw_rows=110, unique=94, with_site=85, platform_only=0, no_website=9, with_email=0, with_review_count=94
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-10T18:46:22+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=5, raw_rows=110, unique=94, with_site=76, platform_only=9, no_website=9, with_email=0, with_review_count=94
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-10T18:47:08+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=5, raw_rows=110, unique=85, with_site=76, platform_only=0, no_website=9, with_email=0, with_review_count=85
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-10T18:47:43+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --out data/enriched/packs/<agency>`
- **Counts:** leads=94, blocked=6, dead=4, no_website=9, ok=75
- **Failures:** none

### 2026-10-10T18:47:48+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=5, raw_rows=100, unique=61, with_site=52, platform_only=0, no_website=9, with_email=0, with_review_count=61
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-10T18:48:50+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=5, raw_rows=104, unique=82, with_site=71, platform_only=0, no_website=11, with_email=0, with_review_count=82
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-10T18:48:52+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --out data/enriched/packs/<agency>`
- **Counts:** leads=94, blocked=3, dead=5, no_website=9, ok=66, platform_only=11
- **Failures:** none

### 2026-10-10T18:48:55+05:00
- **Command:** `python src/prospects.py <agency> --niche dental clinic --want no_chat,no_booking,booking_cta_only`
- **Counts:** listings=94, candidates=87, dropped=7, median_reviews=333
- **Failures:** none

### 2026-10-10T18:48:58+05:00
- **Command:** `python src/prospects.py <agency> --niche spa --want no_ads_tags,no_chat,no_booking`
- **Counts:** listings=94, candidates=83, dropped=11, median_reviews=105
- **Failures:** none

### 2026-10-10T18:49:26+05:00
- **Command:** `python src/prospects.py <agency> --niche dental clinic --want no_chat,no_booking,booking_cta_only --min-reviews 40 --digest 26`
- **Counts:** listings=94, candidates=80, dropped=14, median_reviews=333
- **Failures:** none

### 2026-10-10T18:50:08+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --out data/enriched/packs/<agency>`
- **Counts:** leads=85, blocked=4, dead=3, no_website=9, ok=69
- **Failures:** none

### 2026-10-10T18:50:48+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --out data/enriched/packs/<agency>`
- **Counts:** leads=61, blocked=2, dead=1, http_error=1, no_website=9, ok=46, placeholder=2
- **Failures:** none

### 2026-10-10T18:51:44+05:00
- **Command:** `python src/verify.py <agency> --want no_chat,no_booking,booking_cta_only --top 26`
- **Counts:** rendered=25, render_failed=1, gaps_confirmed=55, gaps_removed=17
- **Failures:** none

### 2026-10-10T18:52:36+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-10T18:52:45+05:00
- **Command:** `python src/prospects.py <agency> --niche spa --want no_ads_tags,no_chat,no_booking,booking_cta_only --min-reviews 30 --max-reviews 2500`
- **Counts:** listings=94, candidates=73, dropped=21, median_reviews=105
- **Failures:** none

### 2026-10-10T18:52:51+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode full --out data/enriched/packs/<agency>`
- **Counts:** leads=82, blocked=6, dead=5, http_error=1, no_website=11, ok=58, placeholder=1
- **Failures:** none

### 2026-10-10T18:54:28+05:00
- **Command:** `python src/verify.py <agency> --want no_ads_tags,no_chat,no_booking,booking_cta_only --top 30`
- **Counts:** rendered=29, render_failed=1, gaps_confirmed=80, gaps_removed=5
- **Failures:** none

### 2026-10-10T18:55:09+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-10T18:55:11+05:00
- **Command:** `python src/prospects.py <agency> --niche school and nursery --want no_ads_tags,no_chat,no_booking,booking_cta_only --min-reviews 20 --max-reviews 1500`
- **Counts:** listings=85, candidates=52, dropped=33, median_reviews=60
- **Failures:** none

### 2026-10-10T18:57:25+05:00
- **Command:** `python src/verify.py <agency> --want no_ads_tags,no_chat,no_booking,booking_cta_only --top 28`
- **Counts:** rendered=22, render_failed=6, gaps_confirmed=60, gaps_removed=5
- **Failures:** none

### 2026-10-10T18:58:24+05:00
- **Command:** `python src/prospects.py <agency> --niche dental clinic --want no_chat,no_booking,booking_cta_only --min-reviews 40 --max-reviews 2500`
- **Counts:** listings=94, candidates=76, dropped=18, median_reviews=333
- **Failures:** none

### 2026-10-10T18:59:33+05:00
- **Command:** `python src/verify.py <agency> --want no_chat,no_booking,booking_cta_only --top 30`
- **Counts:** rendered=29, render_failed=1, gaps_confirmed=60, gaps_downgraded=3, gaps_removed=16
- **Failures:** none

### 2026-10-10T18:59:35+05:00
- **Command:** `python src/prospects.py <agency> --niche spa --want no_ads_tags,no_chat,no_booking,booking_cta_only --min-reviews 30 --max-reviews 2500`
- **Counts:** listings=94, candidates=73, dropped=21, median_reviews=105
- **Failures:** none

### 2026-10-10T19:01:10+05:00
- **Command:** `python src/verify.py <agency> --want no_ads_tags,no_chat,no_booking,booking_cta_only --top 32`
- **Counts:** rendered=31, render_failed=1, gaps_confirmed=81, gaps_downgraded=0, gaps_removed=6
- **Failures:** none

### 2026-10-10T19:01:12+05:00
- **Command:** `python src/prospects.py <agency> --niche school and nursery --want no_ads_tags,no_chat,no_booking,booking_cta_only --min-reviews 20 --max-reviews 1500`
- **Counts:** listings=85, candidates=52, dropped=33, median_reviews=60
- **Failures:** none

### 2026-10-10T19:02:42+05:00
- **Command:** `python src/verify.py <agency> --want no_ads_tags,no_chat,no_booking,booking_cta_only --top 30`
- **Counts:** rendered=29, render_failed=1, gaps_confirmed=67, gaps_downgraded=2, gaps_removed=7
- **Failures:** none

### 2026-10-10T19:04:40+05:00
- **Command:** `python src/verify.py <agency> --want no_chat,no_booking,booking_cta_only --top 30 --force`
- **Counts:** rendered=29, render_failed=1, gaps_confirmed=63, gaps_downgraded=0, gaps_removed=0
- **Failures:** none

### 2026-10-10T19:06:56+05:00
- **Command:** `python src/verify.py <agency> --want no_ads_tags,no_chat,no_booking,booking_cta_only --top 32 --force`
- **Counts:** rendered=31, render_failed=1, gaps_confirmed=80, gaps_downgraded=0, gaps_removed=1
- **Failures:** none

### 2026-10-10T19:08:55+05:00
- **Command:** `python src/verify.py <agency> --want no_ads_tags,no_chat,no_booking,booking_cta_only --top 30 --force`
- **Counts:** rendered=30, render_failed=0, gaps_confirmed=71, gaps_downgraded=0, gaps_removed=1
- **Failures:** none

### 2026-10-10T19:10:14+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-10T19:10:15+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-10T19:10:15+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-10T19:10:18+05:00
- **Command:** `python src/prospects.py <agency> --niche contractor --signals queries/packs/<agency>.signals.json --require-signal --min-reviews 5 --digest 30`
- **Counts:** listings=82, candidates=43, dropped=39, median_reviews=40
- **Failures:** none

### 2026-10-10T19:11:19+05:00
- **Command:** `python src/prospects.py <agency> --niche travel and tour --want no_booking,booking_cta_only,no_chat,no_ads_tags,no_site,platform_site,dead_site,no_meta_description --min-reviews 15 --max-reviews 3000`
- **Counts:** listings=61, candidates=53, dropped=8, median_reviews=194
- **Failures:** none

### 2026-10-10T19:13:16+05:00
- **Command:** `python src/verify.py <agency> --want no_booking,booking_cta_only,no_chat,no_ads_tags,no_site,platform_site,dead_site,no_meta_description --top 30`
- **Counts:** rendered=24, render_failed=1, gaps_confirmed=58, gaps_downgraded=2, gaps_removed=10
- **Failures:** none

### 2026-10-10T19:15:25+05:00
- **Command:** `python src/verify.py <agency> --want no_booking,booking_cta_only,no_chat,no_ads_tags,no_site,platform_site,dead_site,no_meta_description --top 30 --force`
- **Counts:** rendered=17, render_failed=4, gaps_confirmed=48, gaps_downgraded=0, gaps_removed=1
- **Failures:** none

### 2026-10-10T19:16:24+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-10T19:16:24+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-10T19:17:37+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-10T19:17:58+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-10T19:18:14+05:00
- **Command:** `python src/prospects.py <agency> --niche contractor --signals queries/packs/<agency>.signals.json --require-signal --min-reviews 5 --digest 30`
- **Counts:** listings=82, candidates=43, dropped=39, median_reviews=40
- **Failures:** none

### 2026-10-10T19:18:14+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-10T19:21:18+05:00
- **Command:** `python src/qualify.py summary --top 15`
- **Counts:** scored=70, tier_A=20, tier_B=42, tier_C=8
- **Failures:** none
