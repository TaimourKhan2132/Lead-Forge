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
- **2026-10-11 — Packs 6 to 10, approved by the operator.** Built for the next five tier A
  agencies by score, skipping two the operator ruled out: one sells data services itself, one is
  too large. Same process as packs 1 to 5: the niche comes from the agency's own site (a portfolio
  project, a case study, a line of homepage copy), then discovery, light enrichment, gaps, two
  browser passes, and only then selection. One agency's site names no sector, so its pack says so
  in the first paragraph and explains the niche chosen for it. Across the five packs all 89
  browser-checkable gaps are confirmed; 27 others were dropped in verification. One finding needed
  a closer look: a listing whose website link uses a www host with no DNS record. Two public
  resolvers agreed, and the bare domain resolves, so the pack reports a broken link on the listing
  and not a dead business.
- **2026-10-11 — Re-crawl of the agencies marked dead.** `enrich.py --only-status
  dead,http_error` re-fetched the 22 dead and 7 erroring agencies with the https retry in place.
  Three of the 22 are live: one only answers on https, two had failed transiently the first time.
  19 are still dead and all 7 errors still error. The three were scored through the normal gate:
  two tier B and one tier C (a development shop with an offshore sales line). None reaches tier A,
  so the pack order is unchanged. 73 agencies are now scored: 20 A, 44 B, 9 C.
- **2026-10-11 — Recipient check where the brand and the domain differ.** One tier A agency
  trades under a name that does not match its domain, and its draft goes to an address on that
  domain. Checked on its own site: the site served at the domain carries the brand name in its
  title, og:site_name and footer; its Organization structured data names the brand and gives that
  exact address as the sales contact; the founder's portrait is captioned with his name and the
  brand; and it is the only address published on the homepage and contact page. Confirmed, so the
  draft stays ready. The evidence is recorded under the draft.
- **2026-10-11 — One draft repositioned as white-label capacity.** One tier A agency sells
  outbound lead generation itself, so offering it leads is the wrong pitch. Its draft now offers
  research capacity for its clients' niches, with the pack as a sample of the output and nothing
  more. The email still passes the linter (114 words, no links, fixed call-to-action), and the
  scored record's angle and risks were updated to match. Open question for the operator: a
  white-label pack should probably drop the "Generated by LeadForge" footer, and pricing.md has no
  white-label line yet.
- **2026-10-11 — A separate US track for five shortlisted agencies.** The operator's shortlist
  marks five agencies track=us. They sell to funded companies, not to businesses on Google Maps,
  so they were not scored with the Gulf rubric and got no sample pack. `us_track.py` prepares
  them, `enrich.py --kinds services,about,work,contact,team` reads their sites, and each gets one
  contact-form message (90 words or fewer) and one LinkedIn note, both checked by the linter. They
  are in the tracker as tier US with a channel of form or email. `merge_clutch.py` now leaves
  track=us rows out of the Gulf list. Things the sites themselves showed: one of the five says it
  is based in Lisbon, not the US; one sells on having no offshore handoffs, which is recorded as a
  caution in its draft; three name no founder or CTO on the pages read, so their LinkedIn notes
  carry no name; and two "contact" routes are not message forms at all. One of those publishes an
  address, so its channel became email. The other publishes none and is marked BLOCKED until a
  route is confirmed by hand. The hook for each message is tied to a source URL; two hooks are a
  named case study, one is a named service offer, and two are only a list of services, which the
  drafts say plainly.
- **2026-10-11 — Public-safety audit before any push (`src/audit_public.py`).** The script reads
  everything that must stay private from the local data folder (every domain and business name in
  the raw files, every address found during enrichment, every lead in the tracker) and searches
  each commit's patch and message on every ref for it. It also checks that the private folders are
  ignored and were never committed, and that the README's links resolve. Listing titles made only
  of generic words ("AI Automation Agency") are not treated as names, and form placeholders are
  not treated as addresses; both rules are in the script. Nothing was pushed.
- **2026-10-11 — The audit found a leak on its first full run, and it was removed.** The
  re-crawl digest had been produced with `shortlist.py --domains`, and that command line, with
  three agency domains in it, was written to this log and committed. The audit flagged all three.
  `shortlist.py` now logs the count of domains instead of the domains, and the six unpushed
  commits that carried the line were rewritten. The audit was run again afterwards and the history
  is clean.
- **2026-10-11 — Identity moved to `.env`, placeholders filled.** The operator's details were
  moved out of the tracked example file into `.env`, the LinkedIn value was given its https://
  prefix, and `.env.example` was restored to blanks. `pack.py fill` then filled every pack, draft
  and US-track draft. The public files (README and the example pack) were filled without the email
  address. Pack footers are now real links, and a rebuilt pack keeps the date its searches
  actually ran instead of the rebuild date.
- **2026-10-11 — Starter price raised from $49 to $59** on the operator's instruction, in the
  pricing table and both reply templates. The reason given was a minimum on payment requests plus
  card fees. No payment details are recorded here.
- **2026-10-11 — Volume plan: batches of ten, one send day ahead.** `track.py plan <date>` gives
  the next ten unplanned agencies by score a send date (tier A first, then tier B down to a score
  of 60), skipping the domains in `data/skip.txt`. The ten packs already built are planned for
  Monday 12 October; the next four batches are planned Tuesday to Friday, 39 agencies in all
  because that is how many remain at 60 or above. A third agency went on the skip list: its own
  site sells email databases, which is the rule the operator applied to the first two. The daily
  cap of 15 now counts follow-ups as well as first emails, and follow-ups are shown first. That
  exposes a conflict the operator needs to settle: ten new sends a day plus day-3 follow-ups comes
  to 20 on Thursday and 19 on Friday, so the tracker will hold the overflow of new sends to the
  next day unless the plan or the cap changes.
- **2026-10-11 — `sample.py`: a job description in, a sample and a proposal out.** It reads
  niche, location and requested fields from a pasted brief with plain patterns, prints what it
  understood, runs one search with the email lookup, and keeps the ten rows that fill the most
  requested fields. The proposal is built from the sample's own counts, capped at 120 words, and
  checked against a list of claims it must never make (past clients, reviews, results,
  guarantees). Fields that cannot be sourced honestly are named as missing. The brief itself is
  never written to this log, because a brief can name a client. Tested on one brief: 21 listings,
  10 rows, 9 with an email, 112 words.
- **2026-10-11 — Commit attribution.** The operator asked for the repository to be published
  with no co-author. The co-author trailer was removed from every commit message before the first
  push, and later commits do not carry one.
- **2026-10-11 — Tuesday's batch built: ten more packs and drafts.** The next ten agencies by
  score after the skip list. One was swapped out after its prospects were gathered: its buyers are
  enterprise hospitality and government bodies, the search for them returned 34 listings that were
  mostly large chains, and the booking check cannot see the booking engines hotels use, so most of
  what it flagged could not be defended. It went on the skip list with that reason and the next
  agency by score took its place. The plan was rebuilt: ten for Tuesday, ten for Wednesday, ten
  for Thursday and eight for Friday, which is everything left at a score of 60 or above. Across
  the ten new packs all 182 browser-checkable gaps are confirmed and 77 others were dropped in
  verification. Twenty packs and twenty Gulf drafts now exist; Monday's and Tuesday's batches are
  complete.
- **2026-10-11 — `draft.py`, and two fixes found while building.** Drafts are now rendered from
  a spec and linted in one step, the way packs are. A percent-encoded space in a mailto link
  ("mailto:%20info@...") was being read as part of the address; the crawler now strips it, and no
  pack built so far carries such an address. Known limit, now written down: the booking check
  recognises appointment and table-booking systems but not hotel booking engines, so "no booking
  system" must not be claimed for hotels.
- **2026-10-11: seven signals retired after a manual check found most of them false.** The
  operator opened pack prospects by hand and found booking pages, booking tools that open in a new
  tab, and chat widgets where packs said there were none. Root cause: the detector looked for
  tools embedded in the page, so a button that links out, or a widget a script injects later, read
  as "absent", and the browser pass re-ran the same narrow patterns and "confirmed" them. Retired
  for good: no booking, no online booking, book button with no booking system, no WhatsApp, no
  chat, no enquiry chat, no social profiles linked. Also dropped, because they are not on the
  allowed list: no meta description, no mobile viewport, listing links to a social profile, no
  email published.
- **Allowed signals, each checkable by a person in 10 seconds on a phone** (`src/signals.py`): no
  website on the Google listing; the listing's website link is dead or does not resolve; site
  served without https; footer copyright year 2023 or older; no Google tag, Tag Manager or Meta
  Pixel in the rendered page after 8 seconds; review count or rating against the pack median; text
  quoted from the business's own site. `signals.py` also writes the wording for packs and emails,
  and the linter rejects the retired wording anywhere in a draft.
- **`verify.py` rewritten.** It opens the live Google listing (Website button, review count,
  rating) and the site (8.5 seconds, mouse move and scroll), and keeps a signal only when the
  browser shows it. Tags: `dataLayer`, `gtag`, `fbq` and related globals in every frame, every
  script source, the page code, and the requests the page makes. Absence claims (no tags, dead
  link, no https) need two visits. Dropped as unsettled, never guessed: timeouts and resets, HTTP
  403/5xx, bot walls, pages with almost no text, sites with a consent tool, Shopify sites,
  listings that did not load. A dead link is claimed only on a DNS "does not exist" (confirmed by
  a second resolver call), a 404/410, or a page that says the account is suspended or the domain
  is for sale. Low rating is now relative: under 4.0 and at least 0.4 below the median rating of
  the pack's listings with 15+ reviews.
- **The tag signal is the weakest.** It is the only one that cannot be checked on a phone, and the
  check runs in a headless browser. Emails prefer the other signals when a pack has them.
- **Emails are built from verified data, not typed.** `draft.py` generates the three business
  lines from the signals `verify.py` confirmed, and lists under each email the pages to open to
  check them. The sentence about gaps being checked twice in a real browser is gone from every
  email and follow-up, and the linter rejects it.
- **Opening lines are checked too.** One opening line said something the agency's site does not
  say. Each draft spec now lists the words its first line relies on, and `draft.py quotes`
  confirms they are on the agency's rendered page.
- **Send rules** (`track.py`): at most 10 new emails a day, 15 a day with follow-ups, follow-ups
  first, no Saturday or Sunday sends, a weekend follow-up moves to Monday, follow-ups on day 3 and
  day 7. `plan` schedules a new email only where its two follow-ups will also fit. `ready <date>`
  writes the day's emails and check links to the gitignored `outreach/ready/`.
- **Operator's send status, 2026-10-11:** one email stays scheduled in the mail client for Mon 12
  Oct (its three signals are quoted text, re-checked by hand) and is recorded as sent on that
  date. Four other scheduled sends were cancelled and are back to drafted.
- **2026-10-11, operator spot-check of 7 rebuilt claims: 5 right, 2 wrong.** Both wrong ones came
  from a listing link that does not lead where it appears to. - *No https* was claimed for a
  listing whose link redirects to a different company's domain, which loads fine over https. The
  rule is now: claim it only when the https:// version of the same URL fails to load or has an
  invalid certificate. An https address that answers and redirects is not a failure. Both the link
  on the listing and the page the visitor ends on are tried. - *Dead link (404)* was claimed for a
  listing whose link is malformed (a maps link glued onto the URL). The domain itself serves a
  default WordPress page. That line now says the link is broken and what the domain shows, in the
  operator's wording. `verify.py` now looks behind a 404 on a deep link and reports a broken link
  when the domain's homepage loads. - New guard from the same finding: when a listing's link lands
  on a different domain, nothing is claimed about the page it lands on. Applying it dropped three
  more claims, one of them a "no tags" reading taken from a site builder's "expired" page.
- **Ready file format.** Under each email, one line per claim with the exact URL to open. For "no
  website on the listing" that URL is the Google Maps link.
- **A slow connection during the run** made page loads time out for three agencies. Timeouts drop
  a claim, they never create one, so nothing false came of it; those three were re-run. One page
  hung a run outright, so every browser step now has a hard deadline.
- **Outcome of the rebuild, 2026-10-11.** 19 of 20 packs were rebuilt from signals verified that
  day. One Gulf draft is blocked: a web design studio's pool has 8 prospects with a signal a web
  studio can act on (no website on the listing, or a footer dated 2023 or older) and a pack needs
  10. It was checked twice, the second time on a quiet connection. The other signals in that pool
  (review counts, tags) are not something a web studio sells against, so they were not used.
- **Three packs now rest on quoted text, not gaps.** The contractor pack as before, and two
  rebuilt for agencies that sell a WhatsApp agent and a WhatsApp integration. Their prospects are
  businesses whose own sites tell customers to book or ask on WhatsApp, quoted from the page. That
  is the reverse of the retired claim, and it is something present that a reader can see.
- **Opening lines.** 17 of 18 were confirmed against the agency's own page with `draft.py quotes`.
  One agency's site gave no answer from this machine all evening; its draft and the ready file say
  so, and the operator reads that page before sending.
- **A host's browser check appeared mid-run and was waited out, not worked around.** After several
  hundred page loads, a group of sites began answering the pipeline with a "One moment, please"
  page. Those pages were recorded as unread. About two hours later they answered normally and the
  affected checks were re-run. `verify.py` now waits for such a page the way a visitor's browser
  does and reports the page as unread if it stays.
- **Tag claims named in emails were checked a second way.** All nine were re-run in a visible
  browser window and agreed with the headless result.
- **Ready files** were written for the first two send days of the new plan.
- **2026-10-12: the public page.** The README was rebuilt to show the pipeline at work: a banner,
  three diagrams, and two GIFs. Every image is made from the fictional example by
  `docs/make_assets.py`; the terminal GIF is the real output of three commands, captured when the
  script runs. No real business appears in any image, test or example.
- **The example now includes an email.** `draft.py` and `lint_drafts.py` can run on any folder, so
  the bundled example has an email built by the real builder and a draft written to fail
  (`examples/rejected.example.md`), which the linter refuses with nine reasons.
- **The rules are tests.** `tests/test_rules.py` covers the allowed and retired wording, the
  footer-year reader, the median comparisons, the send rules and the builders' refusals. A checks
  workflow runs them on every push.
- **Licence: MIT.** Chosen as the conventional default for a portfolio project; the operator can
  change it.
- **Releases come from the changelog.** Pushing a `v*` tag runs a workflow that publishes that
  version's entry in `CHANGELOG.md` as the release notes. `v0.1.0` marks the first public commit
  and `v0.2.0` the rebuild. The workflow uses the token GitHub gives it, so no credential is
  handled by hand.
- **Left for the operator:** the repository's description, topics and social preview image are set
  in GitHub's own settings, which need a signed-in browser.
- **2026-10-12: a live page, on the operator's instruction.** The project has a page of its own,
  served by GitHub Pages from the `gh-pages` branch. Its source is `docs/site/` and
  `docs/make_site.py` builds it into `_site/`, which is gitignored.
- **The page is filled from the repository, not written twice.** The pack is the committed example
  as `pack.py` wrote it. The email, its follow-ups and its check list are parsed from the example
  `draft.py` wrote. The wording under each signal comes from `signals.py`, the terminal shows what
  `lint_drafts.py` really prints for the draft written to fail, and the caps and the follow-up
  grid come from `track.py`. If any of those change, the page changes with them.
- **Two things are added to the pack on the page, and the page says so.** A bar at the top, and a
  note when a link is clicked, because the businesses are invented and `.example` names resolve
  nowhere.
- **The six claims walked through the gates are invented and labelled as invented.** The gates and
  their order are the ones `verify.py` applies.
- **The page is published by a workflow, never by hand.** Every push to `main` rebuilds it and
  replaces the single commit on `gh-pages`, attributed to whoever pushed, so the operator stays
  the only author. The first publish was pushed from this machine after the audit passed. GitHub
  turned Pages on by itself when the `gh-pages` branch arrived, so no setting was changed by hand,
  and the page answered within a minute.
- **The audit reads the built page too.** `audit_public.py` searches `_site/` for every name,
  domain and email in the private data folder. When the page has not been built it says "skip",
  not "ok".
- **Site tests do not use the working copy of the example pack.** The test fixture rebuilds the
  example unsigned when there is no `.env`, so the checks workflow builds the page before that
  step, from the committed, signed example.
- **This log's Decisions section was tidied.** Earlier entries had been run together into single
  bullets, and dashes had been saved in the wrong encoding. Each decision is a bullet again. No
  wording changed; the script that did it compared the words before and after.
- **2026-10-13: nine first emails recorded as sent, on the operator's word.** One email in that
  batch was held back and is not marked sent. Follow-ups for the nine are due on 2026-10-16 and
  2026-10-20.
- **The next batch was checked again the day before it goes.** The 27 businesses its emails name
  were verified in a browser a second time, two days after the first. 26 still showed their
  signal. One clinic's website link, dead on 2026-10-11, loads again. Its pack keeps the clinic on
  its rating alone, the email names a different clinic whose dead link was confirmed the same day,
  and the other seven businesses in that pack were verified again as well. Opening lines were
  re-read too.
- **A check that could not be read was put back as it was, not dropped.** `verify.py` drops a
  signal it cannot settle, which is right for a first check. On a second check that would throw
  away something already confirmed, so a business whose re-check timed out would have been
  restored and tried again. None needed it this time.
- **One draft is blocked because its opening line cannot be confirmed.** The agency's site gave no
  answer from this machine on two separate days. Nothing was done to get around that. The draft is
  unblocked by reading the page by hand.
- **`draft.py quotes` no longer erases an earlier reading.** One agency's page was read on
  2026-10-11 and would not load on 2026-10-13. The record now keeps the last day the words were
  read, and the send file says both, with an instruction to open the page first.
- **Two more packs and drafts built, on the operator's instruction, to fill the batch to ten.**
  Both are for agencies at 68 that qualification had marked for the second wave. Both packs are
  restaurants and cafes in Dubai, searched in areas no earlier pack used, and no business appears
  in more than one. Two agencies at the same score were passed over: one has an overseas delivery
  office and case studies for developers and universities, the other was already marked for build
  work, not a pack.
- **`verify.py` no longer writes `--only` values to this log.** They are the businesses' own
  domains. Ten such lines from today were scrubbed before anything was committed.
- **2026-10-13: the batch after next was built too, on the operator's instruction.** The plan
  allows four new emails that day, because their follow-ups fall on a Monday that is already full.
  Four packs and drafts were built, each verified in a browser the same day, and each opening line
  was read off the agency's own page.
- **The four were chosen for fit, not strictly by score.** Of the fourteen agencies next in line,
  ten were passed over. Two show clients that are large brands or government bodies, which a pack
  of small local businesses does not fit. Three are large: about fifty staff, or offices in four
  countries. Five are a weaker fit: a solo freelancer who is closer to a peer, a solo founder, one
  whose pack would rest on the tag signal alone, and two with no clear local niche. None was put
  on the skip list. That ruling is the operator's, and the ten are named for him outside this log.
- **Each niche comes from the agency's own page:** the sectors among its featured website builds,
  the label on half of its selected works, a page in its services menu, a page in its industries
  menu.
- **The first follow-up comes due on the same day, and its pack was verified again.** A follow-up
  offers the pack, and this one says two businesses are hiring "now". All ten businesses in that
  pack were checked in a browser again and all still show what the pack says. The pack was
  rebuilt. The email that was already sent was not rebuilt, so the record of what went out is
  unchanged.
- **The send file now lists follow-ups first.** `track.py ready` writes each follow-up due that
  day above the new emails, with the date its pack was last verified and a warning when that is
  more than three days before the send date.
- **About two hundred Maps listings were opened today.** The last verification run had five
  listings fail to load. Nothing was blocked, and no further Maps runs were started.
- **2026-10-13: a second offer was added, the job ask, on the operator's brief.** The first ten
  lead-pack emails drew one reply. It declined the leads and asked for the operator's CV. So a
  second first email now asks an agency for part-time remote work. The lead-pack track is
  unchanged, and the tracker records which offer each first email made, so the two can be
  compared.
- **An agency gets one offer.** A job ask goes only to an agency that has never been emailed, is
  not on the skip list and has no lead-pack draft waiting to go. The two agencies whose pack
  drafts were blocked were given a job ask instead: neither block had anything to do with a job
  ask.
- **Candidates came from the agencies already scored.** 44 were eligible. 38 were read in a
  browser on the day: the homepage, and any careers page it links to. Four homepages timed out and
  were left unread, so those agencies got no email. No new discovery was needed.
- **17 were chosen: those with an open role first, then by score.** Dropped, with the reason kept
  outside this log: teams above the size sought (three at fifty or more, one at a hundred or
  more), one solo freelancer, an EU-registered firm, an agency whose own site places it in another
  country, firms that are not agencies of the three kinds sought (a call-centre and
  mystery-shopping firm, a robotics maker, an ERP vendor, a smart-home installer, a network
  integrator, a branding studio), one with no working address, one barely active, and one whose
  careers page would not load and whose address sits on a different domain from its site.
- **"Hiring" was decided from the careers page as it read on the day, not from the earlier
  crawl.** The crawl of 10 October had found role names on eleven sites. On the day, four agencies
  listed open roles and three of those roles are development or data work. Two sites that had
  seemed to list roles show none: the names had come from a form's drop-down. One site lists roles
  under "disciplines we want to meet", each with an apply link; it is counted as hiring, and the
  draft carries a note asking the operator to read the page and decide.
- **A named contact from the earlier scoring was wrong, and was caught.** One record named a
  "co-founder" who is a client quoted in a testimonial. That email now opens "Hi there". The three
  names that are used were read again on the pages that give them.
- **The operator's wording is not in this repository.** The subject, the pitch, the three proof
  lines, the trial question, the P.S. and the follow-up sentences live in a gitignored file, and
  the linter checks each draft against it word for word. An example file with invented wording is
  committed so the tests can run.
- **Two sentences in that file are not the operator's.** His brief gave no lead-in for the day-3
  follow-up and no sentence to carry the recording link, so one of each was written. They are
  named for him outside this log.
- **Send limits were raised on the operator's instruction:** 25 new emails a weekday and 30
  messages a day with follow-ups, from 10 and 15. Two bounces in a day now print a warning to
  stop.
- **Not all 17 fit on the first day.** Ten lead-pack emails were already set for it, so the day
  takes 15 job asks. First follow-ups from Wednesday, Thursday and Friday all land on the Monday,
  which caps those three days at 29 new emails between them; 31 were ready. The two lowest-ranked
  job asks moved to the next day with room. Moving two lead-pack emails instead would have let
  their packs go stale.
- **Lead-pack follow-up 1 now turns into the job ask**, with the operator's sentence. Only the
  follow-up sections of the 23 built drafts were rewritten. The emails above them, ten of which
  have gone out, were not touched. One sent draft has no spec to rebuild from and keeps its old
  follow-up.
- **The send file became three.** Follow-ups due on a day get their own file, with the "Re:"
  subject of the email they answer. Lead-pack emails keep theirs. Job asks get a page and a CSV
  with the same fields.
- **2026-10-13: the region became a config value.** One file per region in `config/regions/` says
  which countries it covers, what to search for and whether outreach is drafted for it.
  `discover.py`, `shortlist.py` and `qualify.py summary` take `--region`. The Gulf search list
  moved out of `queries/` into the Gulf's file, and the Gulf stays the default, so every earlier
  command behaves as it did.
- **A scored record carries its region.** `qualify.py ingest` stamps it from the listing's
  country, so it cannot be set wrongly by hand. The send plan reads only the first region's
  ranking, and another region's ranking goes to a file of its own. A record with no region on it
  belongs to the Gulf: all 73 scored before today.
- **The UK was added as "scored only".** Its file sets `outreach: false`. `jobs.py` refuses to
  draft for an agency in such a region and `track.py sync` will not take a draft for one, so
  nothing can reach a send file by accident. Germany and the rest of the EU were left out on the
  operator's instruction, because their cold-email rules are stricter. One Gulf candidate was
  dropped from the job ask for the same reason: its operating company is registered in the EU.
- **UK discovery ran on search pages only.** Fifteen searches (five cities, three kinds of agency)
  returned 276 listings, 253 after duplicates. The pass that opens every listing for its review
  count was skipped: about two hundred listings had already been opened that day and a few had
  failed to load. Review counts came from the search results instead, and 235 of the 253 have one.
  Nothing was blocked.
- **192 of the 253 sites could be read.** 30 refused the crawler and were left alone, 19 listings
  have no website, and the rest were dead or errored. 26 listings carried neither a country nor an
  address and could not be placed in the region, so they were left out.
- **40 UK agencies were scored with the same rubric:** 19 in tier A and 21 in tier B. The rubric
  still favours 2 to 15 people, so agencies of 20 to 30 lose points on size although the
  operator's range for this region runs to 30. Four of the 40 are outside that range and are kept
  for the record: one shows 73 people, one calls itself a large agency, one is a solo freelancer
  and one has offices in three EU capitals.
- **The crawl's guess at a founder was wrong five times in 40, and each was corrected before
  ingest.** In every case the name belonged to a client quoted in a testimonial. Names were
  checked against the page text wherever the snippet did not carry a title.
- **"Hiring" in the UK records is the crawl's reading, not a confirmed open role.** Each verdict
  says so. It would be checked in a browser on the day, as it was for the Gulf job asks, before
  anything was drafted.
- **2026-10-14: the operator's review of the first job asks was applied before anything went
  out.** The agency that replied was recorded, so no follow-up goes to it. One lead-pack draft was
  held: one of its three businesses has a listing that links to a site on another country's
  domain, and another's site loads once www is dropped. The third proof line was shortened in the
  operator's wording file.
- **A job ask's opener now prefers a named case study, client or project.** Fifteen openers that
  do not name a role were looked at again. Nine now rest on a named client, case study or project
  quoted from the agency's site. Six still rest on the services listed, because nothing else on
  those sites could be quoted. Every quote was read on its page again the same day.
- **Hiring became a signal with a status, not a yes or no.** `hiring.py` reads roles from a
  company's own careers page, or from the public board API of a job system the page points at. A
  role with a posting date in the last 60 days is fresh. One with no date is undated. A list of
  roles a company "would like to hear about" is a talent pool, not an opening. A role posted
  earlier than that, or past its closing date, is dropped.
- **The email says no more than the status allows.** Only a fresh role is called hiring. An
  undated one is "the role on your careers page". A talent-pool one is "listed among the roles",
  and the line about helping before the hire is left out, because no hire has been announced. The
  linter refuses any other pairing. That last omission was a judgement; the operator's brief did
  not rule on it.
- **Three of yesterday's readings changed under the new rules.** One role is undated, so its email
  no longer says the agency is hiring. One page is a talent pool, as the operator said. One role
  was posted ten months ago and was dropped, and that email now opens on a named client instead.
- **Yesterday's log was wrong about one site.** It said two sites that had seemed to list roles
  showed none. One of them does list roles, in a section that opens when clicked, which the
  reading of the visible text had missed. One of those roles is a strong match, and that agency's
  email now names it.
- **Both regions were scanned: 427 companies, every one whose site could be read.** 165 have a
  careers page. 59 list at least one role. Three use a job system, none of them one with a public
  API, so those boards were recorded to be read by hand. 13 sites could not be read and were left
  alone; one homepage is disallowed by its robots.txt, which was obeyed.
- **Roles found: 8 fresh, 187 undated and 12 in talent pools; 6 were dropped as stale.** Most are
  undated because a role's own page was not opened: the scan stops at the careers page, to keep
  the crawl small, and the date is usually one click further in. 11 roles are a strong match and
  19 are adjacent, at 16 companies.
- **Five companies found only through their openings were given job asks**, each naming an undated
  role. None had been scored. Two more matches were left without a draft because the only address
  on the site is on a different domain. Two agencies with matching roles are already in the
  lead-pack track, and an agency gets one offer. No draft was written for the UK, which is still
  scored only.
- **Searching job boards for companies never seen before was skipped.** Greenhouse, Lever and
  Workable publish no directory of their boards, and none can be searched by city. Finding boards
  would mean scraping a search engine or a job site, whose terms are unclear or forbid it.
  `track.py discover --by-hiring` reads any board named in a region's file; none is named yet.
- **The parser was corrected four times against real pages, and the pages with roles were read
  again each time.** It had taken a row's whole text for a title, counted staff testimonials as
  vacancies, cited a social network's jobs tab as a role's own page, and listed a declared role
  twice. Those 66 sites were fetched three times in the day. Everything else was fetched once.

## Open items

- **Docker path is untested.** `discover.py --engine docker` (gosom) is written but has never run
  on this machine, which has no Docker.
- **No Gulf rows on the Clutch shortlist.** The shortlist that arrived on 2026-10-11 holds only
  track=us agencies, which went to the US track. Nothing was merged into the Gulf list.
- **Two pack drafts stay blocked, and both agencies were given a job ask instead.** One pack has only 8
  prospects with a signal a web studio can act on. The other draft's opening line was never
  confirmed, because that site gave no answer from this machine on two days. Its careers page did
  load on 2026-10-13, on the second try. A third agency's page was read on 2026-10-11 and would not
  load on 2026-10-13; its email stays in the batch and the send file says to open the page first.
- **One US-track draft is blocked** until a way to deliver its message is confirmed by hand.
- **The tag signal is checked in a headless browser only.** It is the one allowed signal that cannot
  be confirmed on a phone. A site that serves a headless browser different code would fool it. Emails
  use it only when a pack has nothing stronger, and the ready file says how to confirm it on a desktop.
- **Quoted-text packs depend on the page staying as it was.** Three packs are built on words quoted
  from the prospect's own site. `verify.py` re-reads them on the day; a site can still change before
  the email is sent.
- **Later batches are planned but not built.** Nothing new is built until the operator says so. Each
  batch is built one send day ahead, with the allowed signals only.
- **The plan is throttled by follow-ups.** Follow-ups from Wednesday, Thursday and Friday sends all
  land on the following Monday. With 30 messages a day allowed, those three days can take 29 or 30
  new emails between them, however many each day could hold on its own.
- **Heavy runs trip a browser check on some hosts.** On 2026-10-11 page loads timed out in bursts and
  one host showed a holding page for about two hours. Both only ever drop a claim, but they cost
  candidates. Spread verification over smaller runs, and re-run what was dropped as unread.
- **Agency qualification has no browser pass.** Opening lines are checked against the agency's page
  with `draft.py quotes`, but the rubric evidence is still read from server-rendered HTML.
- **19 agencies are still unreachable** after the re-crawl, and 15 refuse the crawler outright.
  They are unscored, not mis-described.
- **The repository's About box is still empty.** Description, topics, the social preview image and
  now the page's address are set in GitHub's own settings, which need the operator's signed-in
  browser.
- **The job ask's first follow-up waits on a recording.** Until the link is set in `.env` it uses
  a proof line the first email did not.
- **The size criterion and the UK's size range disagree.** The rubric gives full marks at 2 to 15
  people; the operator's range for the UK is 2 to 30. The scores follow the rubric.
- **UK discovery is one pass of fifteen searches at depth 1.** London returned 54 listings and one
  of them reached the 40 scored, because the triage favours small teams with a named founder.
- **Most roles are undated.** Opening each role's own page would date many of them, at one more
  request per role. The operator has not asked for it.
- **The role parser still makes mistakes.** It reads titles from page structure, and a few entries
  in the hiring tables are not vacancies. Every role an email names is checked by hand and then
  confirmed on its page by `jobs.py quotes`.
- **Two cases that held a draft are not yet rules.** A listing that links to another country's
  domain, and a site that loads without www, are both still allowed by `verify.py`. They were
  handled by hand this time.

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

### 2026-10-11T12:31:29+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=5, raw_rows=107, unique=89, with_site=79, platform_only=1, no_website=9, with_email=0, with_review_count=87
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-11T12:32:36+05:00
- **Command:** `python src/enrich.py data/raw/agencies_gulf.csv --only-status dead,http_error`
- **Counts:** leads=29, dead=19, http_error=7, ok=3
- **Failures:** none

### 2026-10-11T12:32:57+05:00
- **Command:** `python src/shortlist.py --domains <3 domains> --name recrawl`
- **Counts:** enriched=3, eligible=3, shortlisted=3, batches=1
- **Failures:** none
- **Notes:** skipped: none

### 2026-10-11T12:33:22+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --out data/enriched/packs/<agency>`
- **Counts:** leads=89, blocked=6, dead=3, no_website=9, ok=69, parked=1, platform_only=1
- **Failures:** none

### 2026-10-11T12:33:25+05:00
- **Command:** `python src/prospects.py <agency> --niche car rental --want no_booking,booking_cta_only,low_rating,no_site,platform_site,dead_site,no_meta_description,no_ads_tags --min-reviews 20 --max-reviews 3000 --digest 30`
- **Counts:** listings=89, candidates=74, dropped=15, median_reviews=206
- **Failures:** none

### 2026-10-11T12:33:26+05:00
- **Command:** `python src/qualify.py ingest data/scored/_batches/batch_09_recrawl.json`
- **Counts:** verdicts=3, written=3, rejected=0
- **Failures:** none

### 2026-10-11T12:33:29+05:00
- **Command:** `python src/qualify.py summary --top 15`
- **Counts:** scored=73, tier_A=20, tier_B=44, tier_C=9
- **Failures:** none

### 2026-10-11T12:35:47+05:00
- **Command:** `python src/verify.py <agency> --want no_booking,booking_cta_only,low_rating,no_site,platform_site,dead_site,no_meta_description,no_ads_tags --top 30`
- **Counts:** rendered=24, render_failed=0, gaps_confirmed=68, gaps_downgraded=1, gaps_removed=3
- **Failures:** none

### 2026-10-11T12:35:51+05:00
- **Command:** `python src/us_track.py prepare`
- **Counts:** shortlist_rows=5, us_rows=5
- **Failures:** none

### 2026-10-11T12:36:01+05:00
- **Command:** `python src/enrich.py data/raw/us_track.csv --out data/enriched/us --kinds services,about,work,contact,team`
- **Counts:** leads=5, ok=5
- **Failures:** none

### 2026-10-11T12:37:37+05:00
- **Command:** `python src/verify.py <agency> --want no_booking,booking_cta_only,low_rating,no_site,platform_site,dead_site,no_meta_description,no_ads_tags --top 30 --force`
- **Counts:** rendered=23, render_failed=0, gaps_confirmed=66, gaps_downgraded=0, gaps_removed=1
- **Failures:** none

### 2026-10-11T12:38:20+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=5, raw_rows=102, unique=94, with_site=88, platform_only=0, no_website=6, with_email=0, with_review_count=94
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-11T12:39:09+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T12:39:25+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T12:39:34+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --out data/enriched/packs/<agency>`
- **Counts:** leads=94, blocked=2, dead=3, http_error=1, no_website=6, ok=82
- **Failures:** none

### 2026-10-11T12:39:37+05:00
- **Command:** `python src/prospects.py <agency> --niche real estate agency --want no_ads_tags,no_socials,no_meta_description,stale,no_site,platform_site,dead_site,low_reviews --min-reviews 15 --max-reviews 600 --digest 30`
- **Counts:** listings=94, candidates=80, dropped=14, median_reviews=89
- **Failures:** none

### 2026-10-11T12:41:29+05:00
- **Command:** `python src/verify.py <agency> --want no_ads_tags,no_socials,no_meta_description,stale,no_site,platform_site,dead_site,low_reviews --top 30`
- **Counts:** rendered=25, render_failed=1, gaps_confirmed=76, gaps_downgraded=1, gaps_removed=5
- **Failures:** none

### 2026-10-11T12:43:12+05:00
- **Command:** `python src/verify.py <agency> --want no_ads_tags,no_socials,no_meta_description,stale,no_site,platform_site,dead_site,low_reviews --top 30 --force`
- **Counts:** rendered=25, render_failed=0, gaps_confirmed=77, gaps_downgraded=0, gaps_removed=0
- **Failures:** none

### 2026-10-11T12:43:58+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=5, raw_rows=104, unique=102, with_site=71, platform_only=8, no_website=23, with_email=0, with_review_count=102
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-11T12:44:11+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T12:44:50+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --out data/enriched/packs/<agency>`
- **Counts:** leads=102, blocked=4, dead=3, no_website=23, ok=63, placeholder=1, platform_only=8
- **Failures:** none

### 2026-10-11T12:44:52+05:00
- **Command:** `python src/prospects.py <agency> --niche beauty salon --want no_meta_description,no_ads_tags,no_socials,no_site,platform_site,dead_site,low_reviews,no_booking --min-reviews 20 --max-reviews 2500 --digest 30`
- **Counts:** listings=102, candidates=91, dropped=11, median_reviews=298
- **Failures:** none

### 2026-10-11T12:46:09+05:00
- **Command:** `python src/verify.py <agency> --want no_meta_description,no_ads_tags,no_socials,no_site,platform_site,dead_site,low_reviews,no_booking --top 30`
- **Counts:** rendered=18, render_failed=0, gaps_confirmed=52, gaps_downgraded=0, gaps_removed=6
- **Failures:** none

### 2026-10-11T12:47:20+05:00
- **Command:** `python src/verify.py <agency> --want no_meta_description,no_ads_tags,no_socials,no_site,platform_site,dead_site,low_reviews,no_booking --top 30 --force`
- **Counts:** rendered=17, render_failed=0, gaps_confirmed=51, gaps_downgraded=0, gaps_removed=0
- **Failures:** none

### 2026-10-11T12:48:14+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=5, raw_rows=104, unique=66, with_site=60, platform_only=0, no_website=6, with_email=0, with_review_count=66
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-11T12:48:25+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T12:48:52+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --out data/enriched/packs/<agency>`
- **Counts:** leads=66, blocked=2, dead=3, no_website=6, ok=55
- **Failures:** none

### 2026-10-11T12:48:54+05:00
- **Command:** `python src/prospects.py <agency> --niche cleaning company --want no_chat,no_ads_tags,no_meta_description,no_booking,low_reviews,no_site,platform_site,dead_site --min-reviews 15 --max-reviews 3000 --digest 30`
- **Counts:** listings=66, candidates=54, dropped=12, median_reviews=199
- **Failures:** none

### 2026-10-11T12:50:32+05:00
- **Command:** `python src/verify.py <agency> --want no_chat,no_ads_tags,no_meta_description,no_booking,low_reviews,no_site,platform_site,dead_site --top 30`
- **Counts:** rendered=24, render_failed=0, gaps_confirmed=55, gaps_downgraded=0, gaps_removed=4
- **Failures:** none

### 2026-10-11T12:52:14+05:00
- **Command:** `python src/verify.py <agency> --want no_chat,no_ads_tags,no_meta_description,no_booking,low_reviews,no_site,platform_site,dead_site --top 30 --force`
- **Counts:** rendered=24, render_failed=0, gaps_confirmed=55, gaps_downgraded=0, gaps_removed=0
- **Failures:** none

### 2026-10-11T12:53:10+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T12:53:11+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=5, raw_rows=78, unique=52, with_site=39, platform_only=2, no_website=11, with_email=0, with_review_count=52
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-11T12:53:38+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --out data/enriched/packs/<agency>`
- **Counts:** leads=52, dead=2, no_website=11, ok=37, platform_only=2
- **Failures:** none

### 2026-10-11T12:53:40+05:00
- **Command:** `python src/prospects.py <agency> --niche veterinary and pet care --want no_meta_description,no_ads_tags,no_booking,booking_cta_only,no_site,platform_site,dead_site,low_reviews --min-reviews 15 --max-reviews 3000 --digest 30`
- **Counts:** listings=52, candidates=50, dropped=2, median_reviews=217
- **Failures:** none

### 2026-10-11T12:54:54+05:00
- **Command:** `python src/verify.py <agency> --want no_meta_description,no_ads_tags,no_booking,booking_cta_only,no_site,platform_site,dead_site,low_reviews --top 30`
- **Counts:** rendered=19, render_failed=0, gaps_confirmed=43, gaps_downgraded=3, gaps_removed=8
- **Failures:** none

### 2026-10-11T12:56:06+05:00
- **Command:** `python src/verify.py <agency> --want no_meta_description,no_ads_tags,no_booking,booking_cta_only,no_site,platform_site,dead_site,low_reviews --top 30 --force`
- **Counts:** rendered=17, render_failed=1, gaps_confirmed=45, gaps_downgraded=0, gaps_removed=0
- **Failures:** none

### 2026-10-11T12:57:00+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T12:57:26+05:00
- **Command:** `python src/qualify.py ingest data/scored/_batches/batch_10_reposition.json`
- **Counts:** verdicts=1, written=1, rejected=0
- **Failures:** none

### 2026-10-11T12:57:27+05:00
- **Command:** `python src/qualify.py summary --top 15`
- **Counts:** scored=73, tier_A=20, tier_B=44, tier_C=9
- **Failures:** none

### 2026-10-11T13:10:43+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T13:10:44+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T13:10:45+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T13:10:45+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T13:10:46+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T13:10:46+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T13:10:47+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T13:10:47+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T13:10:48+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T13:10:49+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T13:14:52+05:00
- **Command:** `python src/sample.py --brief <brief>`
- **Counts:** listings=21, sample_rows=10, fields=6, with_email=9, proposal_words=112
- **Failures:** none

### 2026-10-11T13:18:43+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=4, raw_rows=82, unique=80, with_site=69, platform_only=3, no_website=8, with_email=0, with_review_count=80
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-11T13:19:34+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --out data/enriched/packs/<agency>`
- **Counts:** leads=80, blocked=4, dead=1, no_website=8, ok=62, parked=1, placeholder=1, platform_only=3
- **Failures:** none

### 2026-10-11T13:19:37+05:00
- **Command:** `python src/prospects.py <agency> --niche aesthetic clinic --want no_ads_tags,no_socials,no_meta_description,low_reviews,no_site,platform_site,no_booking --min-reviews 20 --max-reviews 3000 --digest 24`
- **Counts:** listings=80, candidates=67, dropped=13, median_reviews=215
- **Failures:** none

### 2026-10-11T13:20:38+05:00
- **Command:** `python src/verify.py <agency> --want no_ads_tags,no_socials,no_meta_description,low_reviews,no_site,platform_site,no_booking --top 26`
- **Counts:** rendered=16, render_failed=0, gaps_confirmed=45, gaps_downgraded=0, gaps_removed=2
- **Failures:** none

### 2026-10-11T13:21:38+05:00
- **Command:** `python src/verify.py <agency> --want no_ads_tags,no_socials,no_meta_description,low_reviews,no_site,platform_site,no_booking --top 26 --force`
- **Counts:** rendered=16, render_failed=0, gaps_confirmed=45, gaps_downgraded=0, gaps_removed=0
- **Failures:** none

### 2026-10-11T13:22:13+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=4, raw_rows=82, unique=70, with_site=54, platform_only=2, no_website=14, with_email=0, with_review_count=70
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-11T13:22:23+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T13:22:24+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T13:22:57+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --out data/enriched/packs/<agency>`
- **Counts:** leads=70, blocked=3, http_error=1, no_website=14, ok=50, platform_only=2
- **Failures:** none

### 2026-10-11T13:23:00+05:00
- **Command:** `python src/prospects.py <agency> --niche car service centre --want no_chat,no_booking,booking_cta_only,no_site,platform_site,low_reviews --min-reviews 20 --max-reviews 3000 --digest 24`
- **Counts:** listings=70, candidates=59, dropped=11, median_reviews=244
- **Failures:** none

### 2026-10-11T13:24:10+05:00
- **Command:** `python src/verify.py <agency> --want no_chat,no_booking,booking_cta_only,no_site,platform_site,low_reviews --top 26`
- **Counts:** rendered=16, render_failed=0, gaps_confirmed=34, gaps_downgraded=2, gaps_removed=8
- **Failures:** none

### 2026-10-11T13:25:17+05:00
- **Command:** `python src/verify.py <agency> --want no_chat,no_booking,booking_cta_only,no_site,platform_site,low_reviews --top 26 --force`
- **Counts:** rendered=13, render_failed=0, gaps_confirmed=32, gaps_downgraded=0, gaps_removed=0
- **Failures:** none

### 2026-10-11T13:25:48+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=4, raw_rows=80, unique=46, with_site=40, platform_only=0, no_website=6, with_email=0, with_review_count=46
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-11T13:26:01+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T13:26:01+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T13:26:20+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --out data/enriched/packs/<agency>`
- **Counts:** leads=46, blocked=1, no_website=6, ok=39
- **Failures:** none

### 2026-10-11T13:26:22+05:00
- **Command:** `python src/prospects.py <agency> --niche training institute --want no_site,platform_site,dead_site,stale,no_viewport,not_https,no_meta_description --min-reviews 15 --max-reviews 3000 --digest 24`
- **Counts:** listings=46, candidates=39, dropped=7, median_reviews=114
- **Failures:** none

### 2026-10-11T13:27:45+05:00
- **Command:** `python src/verify.py <agency> --want no_site,platform_site,dead_site,stale,no_viewport,not_https,no_meta_description --top 26`
- **Counts:** rendered=17, render_failed=0, gaps_confirmed=40, gaps_downgraded=0, gaps_removed=4
- **Failures:** none

### 2026-10-11T13:29:04+05:00
- **Command:** `python src/verify.py <agency> --want no_site,platform_site,dead_site,stale,no_viewport,not_https,no_meta_description --top 26 --force`
- **Counts:** rendered=17, render_failed=0, gaps_confirmed=40, gaps_downgraded=0, gaps_removed=0
- **Failures:** none

### 2026-10-11T13:29:39+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=4, raw_rows=81, unique=55, with_site=39, platform_only=3, no_website=13, with_email=0, with_review_count=55
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-11T13:29:46+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T13:29:47+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T13:30:11+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --out data/enriched/packs/<agency>`
- **Counts:** leads=55, blocked=1, dead=1, http_error=1, no_website=13, ok=35, placeholder=1, platform_only=3
- **Failures:** none

### 2026-10-11T13:30:13+05:00
- **Command:** `python src/prospects.py <agency> --niche medical clinic --want no_meta_description,no_ads_tags,no_socials,no_booking,booking_cta_only,low_reviews,no_site --min-reviews 20 --max-reviews 4000 --digest 24`
- **Counts:** listings=55, candidates=50, dropped=5, median_reviews=327
- **Failures:** none

### 2026-10-11T13:31:19+05:00
- **Command:** `python src/verify.py <agency> --want no_meta_description,no_ads_tags,no_socials,no_booking,booking_cta_only,low_reviews,no_site --top 26`
- **Counts:** rendered=17, render_failed=0, gaps_confirmed=51, gaps_downgraded=0, gaps_removed=5
- **Failures:** none

### 2026-10-11T13:32:16+05:00
- **Command:** `python src/verify.py <agency> --want no_meta_description,no_ads_tags,no_socials,no_booking,booking_cta_only,low_reviews,no_site --top 26 --force`
- **Counts:** rendered=15, render_failed=0, gaps_confirmed=49, gaps_downgraded=0, gaps_removed=0
- **Failures:** none

### 2026-10-11T13:32:58+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T13:32:59+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T13:33:09+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=4, raw_rows=80, unique=77, with_site=60, platform_only=4, no_website=13, with_email=0, with_review_count=77
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-11T13:33:56+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --out data/enriched/packs/<agency>`
- **Counts:** leads=77, blocked=1, dead=3, http_error=2, no_website=13, ok=54, platform_only=4
- **Failures:** none

### 2026-10-11T13:33:59+05:00
- **Command:** `python src/prospects.py <agency> --niche restaurant and cafe --want no_socials,no_site,platform_site,low_reviews,no_meta_description,no_ads_tags --min-reviews 50 --max-reviews 2500 --digest 24`
- **Counts:** listings=77, candidates=51, dropped=26, median_reviews=1173
- **Failures:** none

### 2026-10-11T13:35:08+05:00
- **Command:** `python src/verify.py <agency> --want no_socials,no_site,platform_site,low_reviews,no_meta_description,no_ads_tags --top 26`
- **Counts:** rendered=16, render_failed=1, gaps_confirmed=48, gaps_downgraded=1, gaps_removed=8
- **Failures:** none

### 2026-10-11T13:35:57+05:00
- **Command:** `python src/verify.py <agency> --want no_socials,no_site,platform_site,low_reviews,no_meta_description,no_ads_tags --top 26 --force`
- **Counts:** rendered=14, render_failed=0, gaps_confirmed=48, gaps_downgraded=0, gaps_removed=0
- **Failures:** none

### 2026-10-11T13:36:46+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T13:36:47+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T13:36:54+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=4, raw_rows=80, unique=77, with_site=37, platform_only=15, no_website=25, with_email=0, with_review_count=77
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-11T13:37:33+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --out data/enriched/packs/<agency>`
- **Counts:** leads=77, blocked=1, dead=6, no_website=25, ok=30, platform_only=15
- **Failures:** none

### 2026-10-11T13:37:36+05:00
- **Command:** `python src/prospects.py <agency> --niche restaurant and cafe --want no_site,platform_site,no_chat,no_booking,no_socials,no_meta_description --min-reviews 30 --max-reviews 3000 --digest 24`
- **Counts:** listings=77, candidates=69, dropped=8, median_reviews=416
- **Failures:** none

### 2026-10-11T13:38:25+05:00
- **Command:** `python src/verify.py <agency> --want no_site,platform_site,no_chat,no_booking,no_socials,no_meta_description --top 26`
- **Counts:** rendered=14, render_failed=0, gaps_confirmed=51, gaps_downgraded=0, gaps_removed=10
- **Failures:** none

### 2026-10-11T13:39:28+05:00
- **Command:** `python src/verify.py <agency> --want no_site,platform_site,no_chat,no_booking,no_socials,no_meta_description --top 26 --force`
- **Counts:** rendered=12, render_failed=0, gaps_confirmed=48, gaps_downgraded=0, gaps_removed=0
- **Failures:** none

### 2026-10-11T13:40:11+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T13:40:12+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T13:40:15+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=4, raw_rows=88, unique=34, with_site=30, platform_only=0, no_website=4, with_email=0, with_review_count=34
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-11T13:40:38+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --out data/enriched/packs/<agency>`
- **Counts:** leads=34, blocked=8, no_website=4, ok=21, parked=1
- **Failures:** none

### 2026-10-11T13:40:41+05:00
- **Command:** `python src/prospects.py <agency> --niche hotel --want no_booking,booking_cta_only,no_ads_tags,no_chat,no_meta_description,stale --min-reviews 30 --max-reviews 5000 --digest 24`
- **Counts:** listings=34, candidates=11, dropped=23, median_reviews=7038
- **Failures:** none

### 2026-10-11T13:41:32+05:00
- **Command:** `python src/verify.py <agency> --want no_booking,booking_cta_only,no_ads_tags,no_chat,no_meta_description,stale --top 26`
- **Counts:** rendered=10, render_failed=0, gaps_confirmed=22, gaps_downgraded=0, gaps_removed=7
- **Failures:** none

### 2026-10-11T13:42:17+05:00
- **Command:** `python src/verify.py <agency> --want no_booking,booking_cta_only,no_ads_tags,no_chat,no_meta_description,stale --top 26 --force`
- **Counts:** rendered=9, render_failed=1, gaps_confirmed=19, gaps_downgraded=0, gaps_removed=0
- **Failures:** none

### 2026-10-11T13:42:52+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=4, raw_rows=86, unique=73, with_site=67, platform_only=0, no_website=6, with_email=0, with_review_count=73
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-11T13:43:35+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --out data/enriched/packs/<agency>`
- **Counts:** leads=73, blocked=7, dead=3, http_error=1, no_website=6, ok=56
- **Failures:** none

### 2026-10-11T13:43:38+05:00
- **Command:** `python src/prospects.py <agency> --niche law firm --want no_ads_tags,no_meta_description,low_reviews,no_site,stale --min-reviews 10 --max-reviews 1500 --digest 24`
- **Counts:** listings=73, candidates=60, dropped=13, median_reviews=63
- **Failures:** none

### 2026-10-11T13:45:03+05:00
- **Command:** `python src/verify.py <agency> --want no_ads_tags,no_meta_description,low_reviews,no_site,stale --top 26`
- **Counts:** rendered=21, render_failed=0, gaps_confirmed=53, gaps_downgraded=1, gaps_removed=9
- **Failures:** none

### 2026-10-11T13:46:22+05:00
- **Command:** `python src/verify.py <agency> --want no_ads_tags,no_meta_description,low_reviews,no_site,stale --top 26 --force`
- **Counts:** rendered=21, render_failed=0, gaps_confirmed=54, gaps_downgraded=0, gaps_removed=0
- **Failures:** none

### 2026-10-11T13:47:19+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=4, raw_rows=80, unique=72, with_site=69, platform_only=0, no_website=3, with_email=0, with_review_count=72
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-11T13:47:25+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T13:47:26+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T13:49:06+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --out data/enriched/packs/<agency>`
- **Counts:** leads=72, blocked=2, dead=4, http_error=2, no_website=3, ok=59, parked=1, placeholder=1
- **Failures:** none

### 2026-10-11T13:49:09+05:00
- **Command:** `python src/prospects.py <agency> --niche logistics company --want no_ads_tags,no_meta_description,stale,no_site,low_reviews,not_https --min-reviews 10 --max-reviews 2000 --digest 24`
- **Counts:** listings=72, candidates=69, dropped=3, median_reviews=72
- **Failures:** none

### 2026-10-11T13:50:46+05:00
- **Command:** `python src/verify.py <agency> --want no_ads_tags,no_meta_description,stale,no_site,low_reviews,not_https --top 26`
- **Counts:** rendered=24, render_failed=0, gaps_confirmed=76, gaps_downgraded=2, gaps_removed=4
- **Failures:** none

### 2026-10-11T13:52:41+05:00
- **Command:** `python src/verify.py <agency> --want no_ads_tags,no_meta_description,stale,no_site,low_reviews,not_https --top 26 --force`
- **Counts:** rendered=23, render_failed=0, gaps_confirmed=76, gaps_downgraded=0, gaps_removed=0
- **Failures:** none

### 2026-10-11T13:53:24+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T13:53:24+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T13:53:42+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=4, raw_rows=82, unique=71, with_site=54, platform_only=2, no_website=15, with_email=0, with_review_count=69
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-11T13:55:17+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --out data/enriched/packs/<agency>`
- **Counts:** leads=71, blocked=3, dead=4, http_error=1, no_website=15, ok=45, placeholder=1, platform_only=2
- **Failures:** none

### 2026-10-11T13:55:20+05:00
- **Command:** `python src/prospects.py <agency> --niche real estate agency --want no_meta_description,no_ads_tags,no_socials,low_reviews,no_site,stale --min-reviews 10 --max-reviews 800 --digest 24`
- **Counts:** listings=71, candidates=49, dropped=22, median_reviews=85
- **Failures:** none

### 2026-10-11T13:56:40+05:00
- **Command:** `python src/verify.py <agency> --want no_meta_description,no_ads_tags,no_socials,low_reviews,no_site,stale --top 26`
- **Counts:** rendered=21, render_failed=0, gaps_confirmed=56, gaps_downgraded=1, gaps_removed=17
- **Failures:** none

### 2026-10-11T13:58:47+05:00
- **Command:** `python src/verify.py <agency> --want no_meta_description,no_ads_tags,no_socials,low_reviews,no_site,stale --top 26 --force`
- **Counts:** rendered=17, render_failed=0, gaps_confirmed=53, gaps_downgraded=0, gaps_removed=0
- **Failures:** none

### 2026-10-11T13:59:35+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T13:59:36+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T13:59:46+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=4, raw_rows=80, unique=65, with_site=55, platform_only=0, no_website=10, with_email=0, with_review_count=65
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-11T14:00:25+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --out data/enriched/packs/<agency>`
- **Counts:** leads=65, blocked=2, dead=1, http_error=5, no_website=10, ok=45, placeholder=2
- **Failures:** none

### 2026-10-11T14:00:28+05:00
- **Command:** `python src/prospects.py <agency> --niche medical clinic --want no_meta_description,no_ads_tags,no_socials,low_reviews,low_rating,no_site,stale,no_viewport,not_https --min-reviews 20 --max-reviews 4000 --digest 24`
- **Counts:** listings=65, candidates=52, dropped=13, median_reviews=542
- **Failures:** none

### 2026-10-11T14:01:45+05:00
- **Command:** `python src/verify.py <agency> --want no_meta_description,no_ads_tags,no_socials,low_reviews,low_rating,no_site,stale,no_viewport,not_https --top 26`
- **Counts:** rendered=18, render_failed=0, gaps_confirmed=39, gaps_downgraded=3, gaps_removed=10
- **Failures:** none

### 2026-10-11T14:02:59+05:00
- **Command:** `python src/verify.py <agency> --want no_meta_description,no_ads_tags,no_socials,low_reviews,low_rating,no_site,stale,no_viewport,not_https --top 26 --force`
- **Counts:** rendered=17, render_failed=1, gaps_confirmed=40, gaps_downgraded=0, gaps_removed=0
- **Failures:** none

### 2026-10-11T14:03:42+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T14:03:43+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T18:06:32+05:00
- **Command:** `python src/prospects.py <agency> --niche dental clinic --want no_site,dead_site,stale,no_ads_tags --min-reviews 40 --max-reviews 2500`
- **Counts:** listings=94, candidates=47, dropped=47, median_reviews=333, median_rating=4.9
- **Failures:** none

### 2026-10-11T18:08:19+05:00
- **Command:** `python src/verify.py <agency> --want no_site,dead_site,stale,no_ads_tags --top 12`
- **Counts:** listings_read=8, listings_failed=4, sites_opened=2, sites_unclear=1, confirmed=10, dropped=10, dead_site=1, not_https=0, no_ads_tags=1, usable=7
- **Failures:** none

### 2026-10-11T18:10:15+05:00
- **Command:** `python src/prospects.py <agency> --niche spa --min-reviews 30 --max-reviews 2500 --want no_ads_tags,no_site,low_rating`
- **Counts:** listings=94, candidates=40, dropped=54, median_reviews=105, median_rating=4.6
- **Failures:** none

### 2026-10-11T18:14:59+05:00
- **Command:** `python src/verify.py <agency> --want no_ads_tags,no_site,low_rating --top 34`
- **Counts:** listings_read=30, listings_failed=4, sites_opened=21, sites_unclear=6, confirmed=20, dropped=20, dead_site=0, not_https=0, no_ads_tags=12, usable=18
- **Failures:** none

### 2026-10-11T18:15:02+05:00
- **Command:** `python src/prospects.py <agency> --niche school and nursery --min-reviews 20 --max-reviews 1500 --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating`
- **Counts:** listings=85, candidates=21, dropped=64, median_reviews=60, median_rating=4.8
- **Failures:** none

### 2026-10-11T18:17:34+05:00
- **Command:** `python src/verify.py <agency> --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating --top 30`
- **Counts:** listings_read=21, listings_failed=0, sites_opened=18, sites_unclear=2, confirmed=13, dropped=16, dead_site=0, not_https=0, no_ads_tags=5, usable=12
- **Failures:** none

### 2026-10-11T18:17:36+05:00
- **Command:** `python src/prospects.py <agency> --niche travel agency and tour operator --min-reviews 15 --max-reviews 3000 --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating`
- **Counts:** listings=61, candidates=37, dropped=24, median_reviews=194, median_rating=4.7
- **Failures:** none

### 2026-10-11T18:21:06+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T18:21:06+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T18:21:07+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T18:21:08+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T18:21:26+05:00
- **Command:** `python src/verify.py <agency> --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating --top 34`
- **Counts:** listings_read=34, listings_failed=0, sites_opened=25, sites_unclear=2, confirmed=35, dropped=17, dead_site=1, not_https=0, no_ads_tags=10, usable=23
- **Failures:** none

### 2026-10-11T18:21:29+05:00
- **Command:** `python src/prospects.py <agency> --niche car rental --min-reviews 20 --max-reviews 3000 --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating`
- **Counts:** listings=89, candidates=45, dropped=44, median_reviews=206, median_rating=4.8
- **Failures:** none

### 2026-10-11T18:23:51+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T18:23:52+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T18:25:03+05:00
- **Command:** `python src/verify.py <agency> --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating --top 34`
- **Counts:** listings_read=34, listings_failed=0, sites_opened=25, sites_unclear=1, confirmed=38, dropped=15, dead_site=2, not_https=0, no_ads_tags=8, usable=29
- **Failures:** none

### 2026-10-11T18:25:05+05:00
- **Command:** `python src/prospects.py <agency> --niche real estate agency --min-reviews 15 --max-reviews 600 --want no_ads_tags,no_site,low_rating`
- **Counts:** listings=94, candidates=52, dropped=42, median_reviews=89, median_rating=4.7
- **Failures:** none

### 2026-10-11T18:29:23+05:00
- **Command:** `python src/verify.py <agency> --want no_ads_tags,no_site,low_rating --top 34`
- **Counts:** listings_read=32, listings_failed=2, sites_opened=25, sites_unclear=2, confirmed=39, dropped=19, dead_site=2, not_https=1, no_ads_tags=11, usable=28
- **Failures:** none

### 2026-10-11T18:29:25+05:00
- **Command:** `python src/prospects.py <agency> --niche beauty salon --min-reviews 20 --max-reviews 2500 --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating`
- **Counts:** listings=102, candidates=56, dropped=46, median_reviews=298, median_rating=4.8
- **Failures:** none

### 2026-10-11T18:30:15+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T18:30:15+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T18:30:16+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T18:30:17+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=1
- **Failures:** none

### 2026-10-11T18:30:24+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T18:30:25+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T18:30:25+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T18:30:26+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T18:31:41+05:00
- **Command:** `python src/verify.py <agency> --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating --top 36`
- **Counts:** listings_read=33, listings_failed=3, sites_opened=11, sites_unclear=4, confirmed=34, dropped=19, dead_site=2, not_https=0, no_ads_tags=3, usable=27
- **Failures:** none

### 2026-10-11T18:31:43+05:00
- **Command:** `python src/prospects.py <agency> --niche cleaning company --min-reviews 15 --max-reviews 3000 --want no_ads_tags,no_site,low_rating`
- **Counts:** listings=66, candidates=36, dropped=30, median_reviews=199, median_rating=4.7
- **Failures:** none

### 2026-10-11T18:35:39+05:00
- **Command:** `python src/verify.py <agency> --want no_ads_tags,no_site,low_rating --top 34`
- **Counts:** listings_read=34, listings_failed=0, sites_opened=20, sites_unclear=2, confirmed=34, dropped=13, dead_site=2, not_https=0, no_ads_tags=7, usable=26
- **Failures:** none

### 2026-10-11T18:35:41+05:00
- **Command:** `python src/prospects.py <agency> --niche veterinary and pet care --min-reviews 15 --max-reviews 3000 --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating`
- **Counts:** listings=52, candidates=30, dropped=22, median_reviews=217, median_rating=4.6
- **Failures:** none

### 2026-10-11T18:36:37+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T18:36:38+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T18:36:39+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T18:36:39+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T18:38:32+05:00
- **Command:** `python src/verify.py <agency> --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating --top 32`
- **Counts:** listings_read=29, listings_failed=1, sites_opened=13, sites_unclear=2, confirmed=37, dropped=6, dead_site=1, not_https=1, no_ads_tags=9, usable=25
- **Failures:** none

### 2026-10-11T18:38:35+05:00
- **Command:** `python src/prospects.py <agency> --niche aesthetic clinic --min-reviews 20 --max-reviews 3000 --want no_ads_tags,no_site,low_rating`
- **Counts:** listings=80, candidates=40, dropped=40, median_reviews=215, median_rating=4.8
- **Failures:** none

### 2026-10-11T18:46:55+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T18:46:55+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=1
- **Failures:** none

### 2026-10-11T18:47:07+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T18:47:07+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T18:50:40+05:00
- **Command:** `python src/prospects.py <agency> --niche training institute --min-reviews 15 --max-reviews 3000 --want no_site,dead_site,not_https,stale`
- **Counts:** listings=46, candidates=28, dropped=18, median_reviews=114, median_rating=4.8
- **Failures:** none

### 2026-10-11T18:55:42+05:00
- **Command:** `python src/verify.py <agency> --want no_site,dead_site,not_https,stale --top 30`
- **Counts:** listings_read=28, listings_failed=0, sites_opened=8, sites_unclear=14, confirmed=15, dropped=19, dead_site=0, not_https=0, no_ads_tags=2, usable=11
- **Failures:** none

### 2026-10-11T18:55:44+05:00
- **Command:** `python src/prospects.py <agency> --niche medical centre --min-reviews 20 --max-reviews 4000 --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating`
- **Counts:** listings=55, candidates=36, dropped=19, median_reviews=327, median_rating=4.6
- **Failures:** none

### 2026-10-11T19:00:43+05:00
- **Command:** `python src/verify.py <agency> --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating --top 34`
- **Counts:** listings_read=33, listings_failed=1, sites_opened=8, sites_unclear=13, confirmed=31, dropped=20, dead_site=0, not_https=0, no_ads_tags=4, usable=22
- **Failures:** none

### 2026-10-11T19:00:46+05:00
- **Command:** `python src/prospects.py <agency> --niche restaurant and cafe --min-reviews 50 --max-reviews 2500 --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating`
- **Counts:** listings=77, candidates=42, dropped=35, median_reviews=1173, median_rating=4.7
- **Failures:** none

### 2026-10-11T19:04:03+05:00
- **Command:** `python src/verify.py <agency> --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating --top 34`
- **Counts:** listings_read=34, listings_failed=0, sites_opened=17, sites_unclear=6, confirmed=46, dropped=13, dead_site=2, not_https=0, no_ads_tags=9, usable=32
- **Failures:** none

### 2026-10-11T19:04:06+05:00
- **Command:** `python src/prospects.py <agency> --niche restaurant and cafe --min-reviews 30 --max-reviews 3000 --want no_site,dead_site,not_https,stale`
- **Counts:** listings=77, candidates=51, dropped=26, median_reviews=416, median_rating=4.5
- **Failures:** none

### 2026-10-11T19:05:04+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T19:05:06+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T19:07:58+05:00
- **Command:** `python src/verify.py <agency> --want no_site,dead_site,not_https,stale --top 36`
- **Counts:** listings_read=36, listings_failed=0, sites_opened=11, sites_unclear=2, confirmed=47, dropped=5, dead_site=3, not_https=2, no_ads_tags=6, usable=32
- **Failures:** none

### 2026-10-11T19:08:01+05:00
- **Command:** `python src/prospects.py <agency> --niche law firm --min-reviews 10 --max-reviews 1500 --want no_ads_tags,no_site,low_rating`
- **Counts:** listings=73, candidates=43, dropped=30, median_reviews=63, median_rating=4.8
- **Failures:** none

### 2026-10-11T19:08:35+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T19:08:36+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T19:13:20+05:00
- **Command:** `python src/verify.py <agency> --want no_ads_tags,no_site,low_rating --top 34`
- **Counts:** listings_read=32, listings_failed=2, sites_opened=23, sites_unclear=6, confirmed=26, dropped=21, dead_site=1, not_https=0, no_ads_tags=8, usable=19
- **Failures:** none

### 2026-10-11T19:13:22+05:00
- **Command:** `python src/prospects.py <agency> --niche logistics company --min-reviews 10 --max-reviews 2000 --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating`
- **Counts:** listings=72, candidates=51, dropped=21, median_reviews=72, median_rating=4.5
- **Failures:** none

### 2026-10-11T19:14:08+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T19:14:08+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T19:17:48+05:00
- **Command:** `python src/verify.py <agency> --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating --top 34`
- **Counts:** listings_read=34, listings_failed=0, sites_opened=27, sites_unclear=4, confirmed=44, dropped=17, dead_site=6, not_https=0, no_ads_tags=9, usable=28
- **Failures:** none

### 2026-10-11T19:17:51+05:00
- **Command:** `python src/prospects.py <agency> --niche real estate agency --min-reviews 10 --max-reviews 800 --want no_ads_tags,no_site,low_rating`
- **Counts:** listings=71, candidates=34, dropped=37, median_reviews=85, median_rating=4.7
- **Failures:** none

### 2026-10-11T19:18:24+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T19:18:25+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T19:21:49+05:00
- **Command:** `python src/verify.py <agency> --want no_ads_tags,no_site,low_rating --top 34`
- **Counts:** listings_read=34, listings_failed=0, sites_opened=23, sites_unclear=4, confirmed=37, dropped=14, dead_site=1, not_https=0, no_ads_tags=11, usable=23
- **Failures:** none

### 2026-10-11T19:21:54+05:00
- **Command:** `python src/prospects.py <agency> --niche medical centre --min-reviews 20 --max-reviews 4000 --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating`
- **Counts:** listings=65, candidates=38, dropped=27, median_reviews=542, median_rating=4.6
- **Failures:** none

### 2026-10-11T19:26:03+05:00
- **Command:** `python src/verify.py <agency> --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating --top 34`
- **Counts:** listings_read=34, listings_failed=0, sites_opened=20, sites_unclear=6, confirmed=38, dropped=12, dead_site=2, not_https=0, no_ads_tags=7, usable=24
- **Failures:** none

### 2026-10-11T19:26:06+05:00
- **Command:** `python src/prospects.py <agency> --niche dental clinic --min-reviews 40 --max-reviews 2500 --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating`
- **Counts:** listings=94, candidates=47, dropped=47, median_reviews=333, median_rating=4.9
- **Failures:** none

### 2026-10-11T19:27:08+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T19:27:10+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T19:27:11+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T19:27:12+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T19:27:13+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T19:27:14+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T19:27:16+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T19:27:17+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T19:27:18+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T19:27:19+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T19:28:00+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T19:28:02+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T19:28:36+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T19:28:37+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T19:30:11+05:00
- **Command:** `python src/verify.py <agency> --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating --top 34`
- **Counts:** listings_read=30, listings_failed=4, sites_opened=20, sites_unclear=5, confirmed=24, dropped=27, dead_site=2, not_https=0, no_ads_tags=7, usable=20
- **Failures:** none

### 2026-10-11T19:30:15+05:00
- **Command:** `python src/prospects.py <agency> --niche car service centre --min-reviews 20 --max-reviews 3000 --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating`
- **Counts:** listings=70, candidates=33, dropped=37, median_reviews=244, median_rating=4.8
- **Failures:** none

### 2026-10-11T19:34:31+05:00
- **Command:** `python src/verify.py <agency> --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating --top 34`
- **Counts:** listings_read=12, listings_failed=21, sites_opened=2, sites_unclear=1, confirmed=19, dropped=29, dead_site=0, not_https=0, no_ads_tags=0, usable=11
- **Failures:** none

### 2026-10-11T19:34:36+05:00
- **Command:** `python src/prospects.py <agency> --niche contractor --signals queries/packs/<agency>.signals.json --require-signal --min-reviews 5 --digest 30`
- **Counts:** listings=82, candidates=43, dropped=39, median_reviews=40, median_rating=4.4
- **Failures:** none

### 2026-10-11T19:54:42+05:00
- **Command:** `python src/verify.py <agency> --signals queries/packs/<agency>.signals.json --top 45`
- **Counts:** listings_read=43, listings_failed=0, sites_opened=14, sites_unclear=20, confirmed=53, dropped=63, dead_site=0, not_https=0, no_ads_tags=9, usable=29
- **Failures:** none

### 2026-10-11T19:54:45+05:00
- **Command:** `python src/prospects.py <agency> --niche aesthetic clinic --min-reviews 20 --max-reviews 3000 --want no_ads_tags,no_site,low_rating`
- **Counts:** listings=80, candidates=40, dropped=40, median_reviews=215, median_rating=4.8
- **Failures:** none

### 2026-10-11T19:55:33+05:00
- **Command:** `python src/draft.py quotes`
- **Counts:** drafts=18, failed=7
- **Failures:** none

### 2026-10-11T19:58:48+05:00
- **Command:** `python src/verify.py <agency> --want no_ads_tags,no_site,low_rating --top 34`
- **Counts:** listings_read=32, listings_failed=2, sites_opened=17, sites_unclear=5, confirmed=23, dropped=18, dead_site=1, not_https=0, no_ads_tags=6, usable=20
- **Failures:** none

### 2026-10-11T19:58:50+05:00
- **Command:** `python src/prospects.py <agency> --niche training institute --min-reviews 15 --max-reviews 3000 --want no_site,dead_site,not_https,stale`
- **Counts:** listings=46, candidates=28, dropped=18, median_reviews=114, median_rating=4.8
- **Failures:** none

### 2026-10-11T19:59:25+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T19:59:25+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:03:54+05:00
- **Command:** `python src/verify.py <agency> --want no_site,dead_site,not_https,stale --top 30`
- **Counts:** listings_read=28, listings_failed=0, sites_opened=16, sites_unclear=6, confirmed=19, dropped=15, dead_site=0, not_https=0, no_ads_tags=4, usable=15
- **Failures:** none

### 2026-10-11T20:03:56+05:00
- **Command:** `python src/prospects.py <agency> --niche medical centre --min-reviews 20 --max-reviews 4000 --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating`
- **Counts:** listings=55, candidates=36, dropped=19, median_reviews=327, median_rating=4.6
- **Failures:** none

### 2026-10-11T20:07:37+05:00
- **Command:** `python src/verify.py <agency> --want no_site,dead_site,not_https,stale,no_ads_tags,low_rating --top 36`
- **Counts:** listings_read=35, listings_failed=1, sites_opened=16, sites_unclear=6, confirmed=38, dropped=16, dead_site=2, not_https=0, no_ads_tags=7, usable=27
- **Failures:** none

### 2026-10-11T20:07:39+05:00
- **Command:** `python src/prospects.py <agency> --niche dental clinic --signals queries/packs/<agency>.signals.json --require-signal --min-reviews 40 --max-reviews 2500 --digest 40`
- **Counts:** listings=94, candidates=22, dropped=72, median_reviews=333, median_rating=4.9
- **Failures:** none

### 2026-10-11T20:08:18+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:08:18+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:08:19+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:12:50+05:00
- **Command:** `python src/verify.py <agency> --signals queries/packs/<agency>.signals.json --top 30`
- **Counts:** listings_read=22, listings_failed=0, sites_opened=4, sites_unclear=0, confirmed=16, dropped=12, dead_site=0, not_https=0, no_ads_tags=3, usable=13
- **Failures:** none

### 2026-10-11T20:12:52+05:00
- **Command:** `python src/prospects.py <agency> --niche car service centre --signals queries/packs/<agency>.signals.json --require-signal --min-reviews 20 --max-reviews 3000 --digest 40`
- **Counts:** listings=70, candidates=20, dropped=50, median_reviews=244, median_rating=4.8
- **Failures:** none

### 2026-10-11T20:13:40+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:13:41+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=2
- **Failures:** none

### 2026-10-11T20:13:55+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:13:56+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:16:52+05:00
- **Command:** `python src/verify.py <agency> --signals queries/packs/<agency>.signals.json --top 30`
- **Counts:** listings_read=20, listings_failed=0, sites_opened=6, sites_unclear=1, confirmed=19, dropped=13, dead_site=0, not_https=0, no_ads_tags=3, usable=14
- **Failures:** none

### 2026-10-11T20:16:58+05:00
- **Command:** `python src/prospects.py <agency> --niche contractor --signals queries/packs/<agency>.signals.json --require-signal --min-reviews 5 --digest 30`
- **Counts:** listings=82, candidates=43, dropped=39, median_reviews=40, median_rating=4.4
- **Failures:** none

### 2026-10-11T20:17:34+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:17:34+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=1
- **Failures:** none

### 2026-10-11T20:17:42+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:17:42+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:17:57+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:17:58+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:17:58+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:17:59+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:18:00+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:18:01+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:18:01+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:18:02+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:18:03+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:18:03+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:18:04+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:18:05+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:18:05+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:18:06+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:18:06+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:18:07+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:18:08+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:18:08+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:18:09+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:18:10+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:18:11+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:18:11+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:18:12+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:18:12+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:18:13+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:18:14+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:18:15+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:18:15+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:18:16+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:18:17+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:18:17+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:18:18+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:18:19+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:18:20+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:18:20+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:18:21+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:18:22+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:25:08+05:00
- **Command:** `python src/verify.py <agency> --signals queries/packs/<agency>.signals.json --top 45`
- **Counts:** listings_read=43, listings_failed=0, sites_opened=20, sites_unclear=14, confirmed=64, dropped=52, dead_site=0, not_https=0, no_ads_tags=12, usable=31
- **Failures:** none

### 2026-10-11T20:26:42+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:28:23+05:00
- **Command:** `python src/draft.py quotes`
- **Counts:** drafts=18, failed=4
- **Failures:** none

### 2026-10-11T20:30:51+05:00
- **Command:** `python src/draft.py quotes`
- **Counts:** drafts=4, failed=4
- **Failures:** none

### 2026-10-11T20:32:24+05:00
- **Command:** `python src/draft.py quotes`
- **Counts:** drafts=18, failed=4
- **Failures:** none

### 2026-10-11T20:33:21+05:00
- **Command:** `python src/draft.py quotes`
- **Counts:** drafts=4, failed=4
- **Failures:** none

### 2026-10-11T20:33:21+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:33:22+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:33:22+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:33:23+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:33:23+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:33:24+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:33:24+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:33:25+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:33:25+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:33:26+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:33:26+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:33:27+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:33:27+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:33:28+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:33:28+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:33:29+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:33:30+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:33:30+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:33:31+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:33:31+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:33:32+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:33:32+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:33:33+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:33:33+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:33:34+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:33:34+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:33:35+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:33:35+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:33:36+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:33:37+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:33:37+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:33:38+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:33:38+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:33:39+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:33:39+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:33:40+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:33:40+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T20:34:35+05:00
- **Command:** `python src/draft.py quotes`
- **Counts:** drafts=1, failed=1
- **Failures:** none

### 2026-10-11T20:34:36+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T20:34:36+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T22:43:39+05:00
- **Command:** `python src/draft.py quotes`
- **Counts:** drafts=4, failed=1
- **Failures:** none

### 2026-10-11T22:46:05+05:00
- **Command:** `python src/draft.py quotes`
- **Counts:** drafts=1, failed=1
- **Failures:** none

### 2026-10-11T22:49:42+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T22:49:48+05:00
- **Command:** `python src/prospects.py <agency> --niche training institute --min-reviews 15 --max-reviews 3000 --want no_site,dead_site,not_https,stale`
- **Counts:** listings=46, candidates=28, dropped=18, median_reviews=114, median_rating=4.8
- **Failures:** none

### 2026-10-11T22:54:22+05:00
- **Command:** `python src/verify.py <agency> --want no_site,dead_site,not_https,stale --top 30`
- **Counts:** listings_read=28, listings_failed=0, sites_opened=21, sites_unclear=1, confirmed=23, dropped=11, dead_site=0, not_https=0, no_ads_tags=7, usable=19
- **Failures:** none

### 2026-10-11T22:54:42+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T22:54:42+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T22:54:43+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T22:54:43+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T22:54:44+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T22:54:45+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T22:54:45+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T22:54:46+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T22:54:46+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T22:54:47+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T22:54:48+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T22:54:48+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T22:54:49+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T22:54:49+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T22:54:50+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T22:54:51+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T22:54:51+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T22:54:52+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T22:54:53+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T22:54:53+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T22:54:54+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T22:54:54+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T22:54:55+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T22:54:56+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T22:54:56+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T22:54:57+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T22:54:58+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T22:54:58+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T22:54:59+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T22:55:00+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T22:55:00+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T22:55:01+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T22:55:01+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T22:55:02+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T22:55:03+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T22:55:03+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T22:55:04+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T22:55:05+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T22:55:18+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-11T22:55:19+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-11T22:55:19+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T13:44:16+05:00
- **Command:** `python src/verify.py <agency> --only <businesses>`
- **Counts:** listings_read=3, listings_failed=0, sites_opened=2, sites_unclear=0, confirmed=4, dropped=0, dead_site=1, not_https=1, no_ads_tags=0, usable=25
- **Failures:** none

### 2026-10-13T13:44:54+05:00
- **Command:** `python src/verify.py <agency> --only <businesses>`
- **Counts:** listings_read=3, listings_failed=0, sites_opened=2, sites_unclear=0, confirmed=3, dropped=0, dead_site=1, not_https=0, no_ads_tags=1, usable=20
- **Failures:** none

### 2026-10-13T13:45:28+05:00
- **Command:** `python src/draft.py quotes`
- **Counts:** drafts=1, failed=1
- **Failures:** none

### 2026-10-13T13:46:01+05:00
- **Command:** `python src/verify.py <agency> --only <businesses>`
- **Counts:** listings_read=3, listings_failed=0, sites_opened=2, sites_unclear=0, confirmed=4, dropped=0, dead_site=0, not_https=0, no_ads_tags=2, usable=32
- **Failures:** none

### 2026-10-13T13:46:38+05:00
- **Command:** `python src/verify.py <agency> --only <businesses>`
- **Counts:** listings_read=3, listings_failed=0, sites_opened=2, sites_unclear=0, confirmed=3, dropped=1, dead_site=0, not_https=0, no_ads_tags=0, usable=27
- **Failures:** none

### 2026-10-13T13:47:09+05:00
- **Command:** `python src/verify.py <agency> --only <businesses>`
- **Counts:** listings_read=3, listings_failed=0, sites_opened=2, sites_unclear=0, confirmed=4, dropped=0, dead_site=1, not_https=1, no_ads_tags=1, usable=31
- **Failures:** none

### 2026-10-13T13:47:48+05:00
- **Command:** `python src/verify.py <agency> --only <businesses>`
- **Counts:** listings_read=3, listings_failed=0, sites_opened=2, sites_unclear=0, confirmed=3, dropped=0, dead_site=1, not_https=0, no_ads_tags=1, usable=19
- **Failures:** none

### 2026-10-13T13:48:34+05:00
- **Command:** `python src/verify.py <agency> --only <businesses>`
- **Counts:** listings_read=3, listings_failed=0, sites_opened=2, sites_unclear=0, confirmed=5, dropped=0, dead_site=0, not_https=0, no_ads_tags=2, usable=23
- **Failures:** none

### 2026-10-13T13:49:20+05:00
- **Command:** `python src/verify.py <agency> --only <businesses>`
- **Counts:** listings_read=3, listings_failed=0, sites_opened=3, sites_unclear=0, confirmed=4, dropped=0, dead_site=1, not_https=0, no_ads_tags=1, usable=28
- **Failures:** none

### 2026-10-13T13:49:45+05:00
- **Command:** `python src/verify.py <agency> --only <businesses>`
- **Counts:** listings_read=3, listings_failed=0, sites_opened=2, sites_unclear=0, confirmed=3, dropped=0, dead_site=1, not_https=0, no_ads_tags=0, usable=24
- **Failures:** none

### 2026-10-13T13:51:22+05:00
- **Command:** `python src/verify.py <agency> --only <businesses>`
- **Counts:** listings_read=7, listings_failed=0, sites_opened=4, sites_unclear=0, confirmed=8, dropped=0, dead_site=1, not_https=0, no_ads_tags=3, usable=27
- **Failures:** none

### 2026-10-13T13:52:15+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=4, raw_rows=83, unique=81, with_site=72, platform_only=1, no_website=8, with_email=0, with_review_count=81
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-13T13:52:20+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-13T13:52:20+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T13:52:21+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-13T13:52:21+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T13:52:22+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-13T13:52:22+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T13:52:23+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-13T13:52:23+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T13:52:24+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-13T13:52:24+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T13:52:25+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-13T13:52:25+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T13:52:26+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-13T13:52:26+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T13:52:27+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-13T13:52:27+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T13:52:28+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T13:53:42+05:00
- **Command:** `python src/draft.py quotes`
- **Counts:** drafts=8, failed=1
- **Failures:** none

### 2026-10-13T13:53:54+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --concurrency 4 --out data/enriched/packs/<agency>`
- **Counts:** leads=81, blocked=6, dead=3, http_error=1, no_website=8, ok=60, parked=1, placeholder=1, platform_only=1
- **Failures:** none

### 2026-10-13T13:53:57+05:00
- **Command:** `python src/prospects.py <agency> --niche restaurant and cafe --want no_site,low_reviews,no_ads_tags,low_rating,dead_site,stale --min-reviews 50 --max-reviews 4000 --digest 24`
- **Counts:** listings=81, candidates=46, dropped=35, median_reviews=1893, median_rating=4.7
- **Failures:** none

### 2026-10-13T13:54:40+05:00
- **Command:** `python src/draft.py quotes`
- **Counts:** drafts=1, failed=1
- **Failures:** none

### 2026-10-13T13:56:31+05:00
- **Command:** `python src/verify.py <agency> --want no_site,low_reviews,no_ads_tags,low_rating,dead_site,stale --top 26`
- **Counts:** listings_read=24, listings_failed=2, sites_opened=17, sites_unclear=3, confirmed=36, dropped=12, dead_site=4, not_https=0, no_ads_tags=7, usable=22
- **Failures:** none

### 2026-10-13T13:57:06+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=4, raw_rows=80, unique=79, with_site=60, platform_only=8, no_website=11, with_email=0, with_review_count=79
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-13T13:58:11+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-13T13:58:11+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T13:58:13+05:00
- **Command:** `python src/draft.py quotes`
- **Counts:** drafts=1, failed=0
- **Failures:** none

### 2026-10-13T13:59:34+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --concurrency 4 --out data/enriched/packs/<agency>`
- **Counts:** leads=79, blocked=6, dead=2, http_error=5, no_website=11, ok=46, platform_only=9
- **Failures:** none

### 2026-10-13T13:59:36+05:00
- **Command:** `python src/prospects.py <agency> --niche restaurant and cafe --want no_site,dead_site,stale,not_https --min-reviews 80 --max-reviews 5000 --digest 24`
- **Counts:** listings=79, candidates=41, dropped=38, median_reviews=2005, median_rating=4.6
- **Failures:** none

### 2026-10-13T14:02:40+05:00
- **Command:** `python src/verify.py <agency> --want no_site,dead_site,stale,not_https --top 26`
- **Counts:** listings_read=26, listings_failed=0, sites_opened=16, sites_unclear=3, confirmed=30, dropped=11, dead_site=4, not_https=0, no_ads_tags=4, usable=22
- **Failures:** none

### 2026-10-13T14:03:44+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-13T14:03:45+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=1
- **Failures:** none

### 2026-10-13T14:03:46+05:00
- **Command:** `python src/draft.py quotes`
- **Counts:** drafts=1, failed=0
- **Failures:** none

### 2026-10-13T14:03:56+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-13T14:03:56+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T14:04:47+05:00
- **Command:** `python src/draft.py quotes`
- **Counts:** drafts=1, failed=1
- **Failures:** none

### 2026-10-13T14:05:27+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T14:05:28+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T14:05:28+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T14:05:29+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T14:05:29+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T14:05:30+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T14:05:30+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T14:05:31+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T14:05:31+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T14:05:32+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T14:16:21+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=4, raw_rows=80, unique=78, with_site=74, platform_only=0, no_website=4, with_email=0, with_review_count=78
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-13T14:18:15+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --concurrency 4 --out data/enriched/packs/<agency>`
- **Counts:** leads=78, dead=7, http_error=2, no_website=4, ok=65
- **Failures:** none

### 2026-10-13T14:18:17+05:00
- **Command:** `python src/prospects.py <agency> --niche real estate agency --want no_site,dead_site,stale,not_https,no_ads_tags,low_reviews --min-reviews 10 --max-reviews 1500 --digest 24`
- **Counts:** listings=78, candidates=53, dropped=25, median_reviews=106, median_rating=4.7
- **Failures:** none

### 2026-10-13T14:21:19+05:00
- **Command:** `python src/verify.py <agency> --want no_site,dead_site,stale,not_https,no_ads_tags,low_reviews --top 26`
- **Counts:** listings_read=26, listings_failed=0, sites_opened=16, sites_unclear=6, confirmed=32, dropped=15, dead_site=3, not_https=0, no_ads_tags=5, usable=20
- **Failures:** none

### 2026-10-13T14:21:51+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=4, raw_rows=78, unique=37, with_site=33, platform_only=0, no_website=4, with_email=0, with_review_count=37
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-13T14:22:22+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --concurrency 4 --out data/enriched/packs/<agency>`
- **Counts:** leads=37, blocked=1, dead=1, no_website=4, ok=30, placeholder=1
- **Failures:** none

### 2026-10-13T14:22:24+05:00
- **Command:** `python src/prospects.py <agency> --niche pest control company --want low_reviews,low_rating,no_site,dead_site,stale,not_https --min-reviews 10 --max-reviews 3000 --digest 24`
- **Counts:** listings=37, candidates=17, dropped=20, median_reviews=59, median_rating=4.8
- **Failures:** none

### 2026-10-13T14:24:45+05:00
- **Command:** `python src/verify.py <agency> --want low_reviews,low_rating,no_site,dead_site,stale,not_https --top 26`
- **Counts:** listings_read=17, listings_failed=0, sites_opened=14, sites_unclear=1, confirmed=14, dropped=8, dead_site=1, not_https=0, no_ads_tags=6, usable=11
- **Failures:** none

### 2026-10-13T14:25:18+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=4, raw_rows=72, unique=67, with_site=43, platform_only=2, no_website=22, with_email=0, with_review_count=67
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-13T14:25:43+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-13T14:25:44+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T14:25:45+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-13T14:25:45+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=1
- **Failures:** none

### 2026-10-13T14:25:55+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-13T14:25:55+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T14:25:56+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-13T14:25:57+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T14:26:22+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --concurrency 4 --out data/enriched/packs/<agency>`
- **Counts:** leads=67, dead=1, http_error=1, no_website=22, ok=40, placeholder=1, platform_only=2
- **Failures:** none

### 2026-10-13T14:26:25+05:00
- **Command:** `python src/prospects.py <agency> --niche gym and fitness studio --want no_site,dead_site,stale,no_ads_tags,low_reviews,low_rating --min-reviews 15 --max-reviews 3000 --digest 24`
- **Counts:** listings=67, candidates=38, dropped=29, median_reviews=42, median_rating=4.7
- **Failures:** none

### 2026-10-13T14:28:55+05:00
- **Command:** `python src/verify.py <agency> --want no_site,dead_site,stale,no_ads_tags,low_reviews,low_rating --top 26`
- **Counts:** listings_read=26, listings_failed=0, sites_opened=12, sites_unclear=1, confirmed=30, dropped=6, dead_site=2, not_https=0, no_ads_tags=5, usable=24
- **Failures:** none

### 2026-10-13T14:29:27+05:00
- **Command:** `python src/discover.py queries/packs/<agency>.txt pack_<agency> --concurrency 2`
- **Counts:** queries=4, raw_rows=67, unique=66, with_site=46, platform_only=7, no_website=13, with_email=0, with_review_count=66
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/pack_<agency>.csv

### 2026-10-13T14:29:42+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-13T14:29:42+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=2
- **Failures:** none

### 2026-10-13T14:30:14+05:00
- **Command:** `python src/enrich.py data/raw/pack_<agency>.csv --mode light --concurrency 4 --out data/enriched/packs/<agency>`
- **Counts:** leads=66, blocked=2, no_website=13, ok=42, platform_only=9
- **Failures:** none

### 2026-10-13T14:30:17+05:00
- **Command:** `python src/prospects.py <agency> --niche beauty salon and spa --want no_site,dead_site,stale,no_ads_tags,low_reviews,low_rating --min-reviews 30 --max-reviews 3000 --digest 24`
- **Counts:** listings=66, candidates=44, dropped=22, median_reviews=214, median_rating=4.8
- **Failures:** none

### 2026-10-13T14:32:47+05:00
- **Command:** `python src/verify.py <agency> --want no_site,dead_site,stale,no_ads_tags,low_reviews,low_rating --top 26`
- **Counts:** listings_read=21, listings_failed=5, sites_opened=13, sites_unclear=0, confirmed=19, dropped=13, dead_site=0, not_https=0, no_ads_tags=3, usable=15
- **Failures:** none

### 2026-10-13T14:33:54+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-13T14:33:54+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T14:33:55+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-13T14:33:55+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T14:34:02+05:00
- **Command:** `python src/draft.py quotes`
- **Counts:** drafts=4, failed=0
- **Failures:** none

### 2026-10-13T14:34:10+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T14:34:10+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T14:34:11+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T14:34:11+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-13T14:37:20+05:00
- **Command:** `python src/verify.py <agency> --only <businesses> --signals queries/packs/<agency>.signals.json`
- **Counts:** listings_read=10, listings_failed=0, sites_opened=7, sites_unclear=0, confirmed=28, dropped=0, dead_site=0, not_https=0, no_ads_tags=7, usable=32
- **Failures:** none

### 2026-10-13T14:37:28+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-13T18:27:55+05:00
- **Command:** `python src/jobs.py scan`
- **Counts:** agencies=38, homepage_unread=4, careers_page_read=14
- **Failures:** none
- **Notes:** A homepage that would not load is left unread; that agency gets no email until it can be read.

### 2026-10-13T18:32:59+05:00
- **Command:** `python src/jobs.py quotes`
- **Counts:** drafts=18, failed=0
- **Failures:** none

### 2026-10-13T18:33:46+05:00
- **Command:** `python src/jobs.py quotes`
- **Counts:** drafts=3, failed=0
- **Failures:** none

### 2026-10-13T18:33:47+05:00
- **Command:** `python src/jobs.py build`
- **Counts:** drafts=17, refused=0
- **Failures:** none

### 2026-10-13T18:34:11+05:00
- **Command:** `python src/jobs.py build`
- **Counts:** drafts=17, refused=0
- **Failures:** none

### 2026-10-13T18:34:11+05:00
- **Command:** `python src/draft.py followups`
- **Counts:** drafts=25, rewritten=23, failed=0
- **Failures:** none

### 2026-10-13T18:43:55+05:00
- **Command:** `python src/discover.py --region uk --no-reviews --concurrency 2`
- **Counts:** queries=15, raw_rows=276, unique=253, with_site=230, platform_only=2, no_website=21, with_email=0, with_review_count=235
- **Failures:** none
- **Notes:** engine=playwright, output=data/raw/agencies_uk.csv

### 2026-10-13T18:51:22+05:00
- **Command:** `python src/enrich.py data/raw/agencies_uk.csv --concurrency 4`
- **Counts:** leads=253, blocked=30, cached=2, dead=3, http_error=4, no_website=19, ok=192, placeholder=1, platform_only=2
- **Failures:** none

### 2026-10-13T18:51:45+05:00
- **Command:** `python src/shortlist.py --region uk --top 40`
- **Counts:** enriched=227, eligible=161, shortlisted=40, batches=4
- **Failures:** none
- **Notes:** skipped: site blocked=27, site no_website=19, no relevant services found in site copy=7, big-company signal=7, site dead=3, site http_error=3

### 2026-10-13T18:52:54+05:00
- **Command:** `python src/qualify.py ingest data/scored/_batches/uk_01.json`
- **Counts:** verdicts=10, written=10, rejected=0
- **Failures:** none

### 2026-10-13T18:53:43+05:00
- **Command:** `python src/qualify.py ingest data/scored/_batches/uk_02.json`
- **Counts:** verdicts=10, written=10, rejected=0
- **Failures:** none

### 2026-10-13T18:54:35+05:00
- **Command:** `python src/qualify.py ingest data/scored/_batches/uk_01.json`
- **Counts:** verdicts=10, written=10, rejected=0
- **Failures:** none

### 2026-10-13T18:54:37+05:00
- **Command:** `python src/qualify.py ingest data/scored/_batches/uk_02.json`
- **Counts:** verdicts=10, written=10, rejected=0
- **Failures:** none

### 2026-10-13T18:55:08+05:00
- **Command:** `python src/qualify.py ingest data/scored/_batches/uk_03.json`
- **Counts:** verdicts=10, written=10, rejected=0
- **Failures:** none

### 2026-10-13T18:56:07+05:00
- **Command:** `python src/qualify.py ingest data/scored/_batches/uk_04.json`
- **Counts:** verdicts=10, written=10, rejected=0
- **Failures:** none

### 2026-10-13T18:56:09+05:00
- **Command:** `python src/qualify.py summary --top 12 --region uk`
- **Counts:** scored=40, tier_A=19, tier_B=21, tier_C=0
- **Failures:** none

### 2026-10-14T00:26:17+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-14T00:35:16+05:00
- **Command:** `python src/jobs.py quotes`
- **Counts:** drafts=17, failed=1
- **Failures:** none

### 2026-10-14T00:35:17+05:00
- **Command:** `python src/jobs.py build`
- **Counts:** drafts=17, refused=0
- **Failures:** none

### 2026-10-14T00:35:38+05:00
- **Command:** `python src/jobs.py quotes`
- **Counts:** drafts=1, failed=0
- **Failures:** none

### 2026-10-14T00:35:52+05:00
- **Command:** `python src/jobs.py build`
- **Counts:** drafts=17, refused=0
- **Failures:** none

### 2026-10-14T00:39:51+05:00
- **Command:** `python src/hiring.py scan <companies>`
- **Counts:** companies=8, read_now=8, from_cache=0, careers_page=6, unread=2, job_system=0, with_roles=2, fresh=0, undated=14, talent_pool=0, stale_dropped=1, strong=2, adjacent=2
- **Failures:** none
- **Notes:** One request at a time per site, robots.txt respected, results kept for 7 days.

### 2026-10-14T00:40:46+05:00
- **Command:** `python src/hiring.py scan <companies>`
- **Counts:** companies=3, read_now=3, from_cache=0, careers_page=3, unread=0, job_system=0, with_roles=2, fresh=0, undated=4, talent_pool=10, stale_dropped=0, strong=2, adjacent=2
- **Failures:** none
- **Notes:** One request at a time per site, robots.txt respected, results kept for 7 days.

### 2026-10-14T00:41:21+05:00
- **Command:** `python src/hiring.py scan <companies>`
- **Counts:** companies=4, read_now=4, from_cache=0, careers_page=4, unread=0, job_system=0, with_roles=4, fresh=0, undated=10, talent_pool=11, stale_dropped=0, strong=2, adjacent=2
- **Failures:** none
- **Notes:** One request at a time per site, robots.txt respected, results kept for 7 days.

### 2026-10-14T00:56:43+05:00
- **Command:** `python src/hiring.py scan --region gulf`
- **Counts:** companies=252, read_now=245, from_cache=7, careers_page=90, unread=10, job_system=1, with_roles=34, fresh=4, undated=145, talent_pool=11, stale_dropped=5, strong=10, adjacent=14
- **Failures:** none
- **Notes:** One request at a time per site, robots.txt respected, results kept for 7 days.

### 2026-10-14T01:05:34+05:00
- **Command:** `python src/hiring.py scan --region uk`
- **Counts:** companies=175, read_now=174, from_cache=1, careers_page=75, unread=3, job_system=2, with_roles=28, fresh=4, undated=54, talent_pool=1, stale_dropped=1, strong=1, adjacent=9
- **Failures:** none
- **Notes:** One request at a time per site, robots.txt respected, results kept for 7 days.

### 2026-10-14T01:08:09+05:00
- **Command:** `python src/hiring.py scan <companies>`
- **Counts:** companies=66, read_now=66, from_cache=0, careers_page=66, unread=0, job_system=0, with_roles=60, fresh=8, undated=191, talent_pool=12, stale_dropped=6, strong=11, adjacent=22
- **Failures:** none
- **Notes:** One request at a time per site, robots.txt respected, results kept for 7 days.

### 2026-10-14T01:08:10+05:00
- **Command:** `python src/hiring.py scan --region gulf`
- **Counts:** companies=252, read_now=0, from_cache=252, careers_page=90, unread=10, job_system=1, with_roles=34, fresh=4, undated=140, talent_pool=11, stale_dropped=5, strong=10, adjacent=13
- **Failures:** none
- **Notes:** One request at a time per site, robots.txt respected, results kept for 7 days.

### 2026-10-14T01:08:12+05:00
- **Command:** `python src/hiring.py scan --region uk`
- **Counts:** companies=175, read_now=0, from_cache=175, careers_page=75, unread=3, job_system=2, with_roles=26, fresh=4, undated=51, talent_pool=1, stale_dropped=1, strong=1, adjacent=9
- **Failures:** none
- **Notes:** One request at a time per site, robots.txt respected, results kept for 7 days.

### 2026-10-14T01:12:03+05:00
- **Command:** `python src/hiring.py scan <companies>`
- **Counts:** companies=64, read_now=64, from_cache=0, careers_page=64, unread=0, job_system=0, with_roles=59, fresh=8, undated=187, talent_pool=12, stale_dropped=6, strong=11, adjacent=19
- **Failures:** none
- **Notes:** One request at a time per site, robots.txt respected, results kept for 7 days.

### 2026-10-14T01:12:04+05:00
- **Command:** `python src/hiring.py scan --region gulf`
- **Counts:** companies=252, read_now=0, from_cache=252, careers_page=90, unread=10, job_system=1, with_roles=34, fresh=4, undated=140, talent_pool=11, stale_dropped=5, strong=10, adjacent=13
- **Failures:** none
- **Notes:** One request at a time per site, robots.txt respected, results kept for 7 days.

### 2026-10-14T01:12:05+05:00
- **Command:** `python src/hiring.py scan --region uk`
- **Counts:** companies=175, read_now=0, from_cache=175, careers_page=75, unread=3, job_system=2, with_roles=25, fresh=4, undated=47, talent_pool=1, stale_dropped=1, strong=1, adjacent=6
- **Failures:** none
- **Notes:** One request at a time per site, robots.txt respected, results kept for 7 days.

### 2026-10-14T01:12:19+05:00
- **Command:** `python src/hiring.py scan --region gulf`
- **Counts:** companies=252, read_now=0, from_cache=252, careers_page=90, unread=10, job_system=1, with_roles=34, fresh=4, undated=140, talent_pool=11, stale_dropped=5, strong=10, adjacent=13
- **Failures:** none
- **Notes:** One request at a time per site, robots.txt respected, results kept for 7 days.

### 2026-10-14T01:15:05+05:00
- **Command:** `python src/jobs.py quotes`
- **Counts:** drafts=22, failed=0
- **Failures:** none

### 2026-10-14T01:15:06+05:00
- **Command:** `python src/jobs.py build`
- **Counts:** drafts=22, refused=0
- **Failures:** none

### 2026-10-15T12:00:34+05:00
- **Command:** `python src/verify.py <agency> --only <businesses>`
- **Counts:** listings_read=3, listings_failed=0, sites_opened=2, sites_unclear=0, confirmed=3, dropped=0, dead_site=0, not_https=0, no_ads_tags=0, usable=15
- **Failures:** none

### 2026-10-15T12:01:07+05:00
- **Command:** `python src/verify.py <agency> --only <businesses>`
- **Counts:** listings_read=3, listings_failed=0, sites_opened=2, sites_unclear=0, confirmed=3, dropped=0, dead_site=1, not_https=0, no_ads_tags=0, usable=24
- **Failures:** none

### 2026-10-15T12:01:37+05:00
- **Command:** `python src/verify.py <agency> --only <businesses>`
- **Counts:** listings_read=3, listings_failed=0, sites_opened=2, sites_unclear=0, confirmed=5, dropped=0, dead_site=1, not_https=0, no_ads_tags=0, usable=20
- **Failures:** none

### 2026-10-15T12:02:15+05:00
- **Command:** `python src/verify.py <agency> --only <businesses>`
- **Counts:** listings_read=3, listings_failed=0, sites_opened=2, sites_unclear=0, confirmed=5, dropped=0, dead_site=0, not_https=0, no_ads_tags=1, usable=11
- **Failures:** none

### 2026-10-15T12:03:09+05:00
- **Command:** `python src/verify.py <agency> --signals queries/packs/<agency>.signals.json --only <businesses>`
- **Counts:** listings_read=2, listings_failed=0, sites_opened=1, sites_unclear=0, confirmed=6, dropped=0, dead_site=0, not_https=0, no_ads_tags=1, usable=32
- **Failures:** none

### 2026-10-15T12:03:45+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-15T12:03:46+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-15T12:03:46+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-15T12:03:47+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-15T12:03:48+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-15T12:03:48+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-15T12:03:49+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-15T12:03:49+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-15T12:03:50+05:00
- **Command:** `python src/draft.py build <agency>`
- **Counts:** lint_problems=0
- **Failures:** none

### 2026-10-15T12:04:03+05:00
- **Command:** `python src/draft.py quotes`
- **Counts:** drafts=4, failed=0
- **Failures:** none

### 2026-10-15T13:16:52+05:00
- **Command:** `python src/verify.py <agency> --only <businesses>`
- **Counts:** listings_read=1, listings_failed=0, sites_opened=1, sites_unclear=0, confirmed=1, dropped=0, dead_site=1, not_https=0, no_ads_tags=0, usable=24
- **Failures:** none

### 2026-10-15T13:16:57+05:00
- **Command:** `python src/pack.py build <agency>`
- **Counts:** prospects=10, files=2
- **Failures:** none

### 2026-10-19T23:31:33+05:00
- **Command:** `python src/hiring.py scan <companies>`
- **Counts:** companies=9, read_now=9, from_cache=0, careers_page=5, unread=0, job_system=0, with_roles=1, fresh=0, undated=5, talent_pool=0, stale_dropped=0, strong=0, adjacent=1
- **Failures:** none
- **Notes:** One request at a time per site, robots.txt respected, results kept for 7 days.

### 2026-10-19T23:32:34+05:00
- **Command:** `python src/jobs.py quotes`
- **Counts:** drafts=1, failed=0
- **Failures:** none

### 2026-10-19T23:35:09+05:00
- **Command:** `python src/hiring.py scan <companies>`
- **Counts:** companies=1, read_now=1, from_cache=0, careers_page=1, unread=0, job_system=0, with_roles=0, fresh=0, undated=0, talent_pool=0, stale_dropped=0, strong=0, adjacent=0
- **Failures:** none
- **Notes:** One request at a time per site, robots.txt respected, results kept for 7 days.

### 2026-10-19T23:37:09+05:00
- **Command:** `python src/draft.py followups`
- **Counts:** drafts=21, rewritten=21, failed=0
- **Failures:** none

### 2026-10-19T23:37:16+05:00
- **Command:** `python src/jobs.py followups`
- **Counts:** drafts=22, rewritten=22, failed=0
- **Failures:** none

### 2026-10-19T23:39:51+05:00
- **Command:** `python src/jobs.py followups`
- **Counts:** drafts=22, rewritten=0, failed=0
- **Failures:** none

### 2026-10-19T23:39:52+05:00
- **Command:** `python src/draft.py followups`
- **Counts:** drafts=21, rewritten=0, failed=0
- **Failures:** none

### 2026-10-21T20:28:16+05:00
- **Command:** `python src/discover.py <upwork sample queries> <name> --engine playwright --depth 1 --concurrency 2`
- **Counts:** queries=6, raw_rows=81, unique=77, with_site=48, platform_only=8, no_website=21, with_email=0, with_review_count=77
- **Failures:** none
- **Notes:** engine=playwright, an Upwork sample; output moved to the gitignored upwork/ folder

### 2026-10-22T16:48:29+05:00
- **Command:** `python src/discover.py <upwork sample query> <name> --engine playwright --depth 2 --concurrency 1 --no-reviews`
- **Counts:** queries=1, raw_rows=20, unique=19, with_site=18, platform_only=1, no_website=0, with_email=0, with_review_count=19
- **Failures:** none
- **Notes:** engine=playwright, an Upwork sample; output moved to the gitignored upwork/ folder

### 2026-10-22T16:48:53+05:00
- **Command:** `python src/discover.py <upwork sample query> <name> --engine playwright --depth 3 --concurrency 1 --no-reviews`
- **Counts:** queries=1, raw_rows=20, unique=20, with_site=17, platform_only=1, no_website=2, with_email=0, with_review_count=20
- **Failures:** none
- **Notes:** engine=playwright, an Upwork sample; output moved to the gitignored upwork/ folder

### 2026-10-23T00:18:31+05:00
- **Command:** `python src/discover.py <upwork sample queries> <name> --engine playwright --depth 3 --concurrency 1 --no-reviews`
- **Counts:** queries=3, raw_rows=53, unique=45, with_site=43, platform_only=0, no_website=2, with_email=0, with_review_count=44
- **Failures:** none
- **Notes:** engine=playwright, an Upwork sample; output moved to the gitignored upwork/ folder

### 2026-10-23T00:34:38+05:00
- **Command:** `python src/discover.py <upwork sample queries> <name> --engine playwright --depth 8 --concurrency 1 --no-reviews`
- **Counts:** queries=2, raw_rows=35, unique=27, with_site=23, platform_only=0, no_website=4, with_email=0, with_review_count=26
- **Failures:** none
- **Notes:** engine=playwright, an Upwork sample; output moved to the gitignored upwork/ folder

### 2026-10-23T01:19:47+05:00
- **Command:** `python src/contacts.py <businesses.csv>`
- **Counts:** businesses=45, skipped_by_name=7, closed=1, with_site=36, gated=5, with_email=12, with_facebook=16, with_instagram=20
- **Failures:** none
- **Notes:** robots.txt obeyed; facebook.com and instagram.com never opened

### 2026-10-23T01:24:21+05:00
- **Command:** `python src/contacts.py <businesses.csv>`
- **Counts:** businesses=45, skipped_by_name=7, closed=1, with_site=36, gated=5, with_email=13, with_facebook=16, with_instagram=20
- **Failures:** none
- **Notes:** robots.txt obeyed; facebook.com and instagram.com never opened

### 2026-10-23T01:25:03+05:00
- **Command:** `python src/contacts.py <businesses.csv>`
- **Counts:** businesses=39, skipped_by_name=1, closed=0, with_site=34, gated=1, with_email=21, with_facebook=20, with_instagram=28
- **Failures:** none
- **Notes:** robots.txt obeyed; facebook.com and instagram.com never opened

### 2026-10-23T01:25:38+05:00
- **Command:** `python src/contacts.py <businesses.csv>`
- **Counts:** businesses=45, skipped_by_name=7, closed=1, with_site=36, gated=5, with_email=14, with_facebook=16, with_instagram=20
- **Failures:** none
- **Notes:** robots.txt obeyed; facebook.com and instagram.com never opened
