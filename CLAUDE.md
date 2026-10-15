# LeadForge

Instructions for Claude Code in this repository. This file is public, so it names no real business,
domain or email address. Real agencies, prospects, packs and drafts live under `data/`, `packs/` and
`outreach/` and are gitignored. Look there, never here.

## What LeadForge is

A local pipeline that finds small marketing and automation agencies in the Gulf (UAE, KSA, Qatar),
scores them against a 100-point rubric, and wins a reply by giving each one a free sample: ten
qualified prospects in that agency's own niche and city. It then drafts the outreach that leads
with the sample and tracks sends and follow-ups. The operator sends every message by hand.

The region is a config value, not a branch: one file per region in `config/regions/`, and the same
code for all of them. `gulf` is the default. `uk` (London, Manchester, Birmingham, Leeds, Bristol)
is discovered and scored with the same rubric, and is marked `outreach: false`: no pack, email or
job ask is drafted for it until the operator says so. Germany and the rest of the EU are left out
for now, because their cold-email rules are stricter.

Stages: `discover` (Google Maps) → `enrich` (each site, with evidence) → `shortlist` and `qualify`
(rubric, tier A at 70 and above, B at 50 to 69) → `prospects` and `verify` (signals, confirmed in a
browser) → `pack` → `draft` → `track`.

There are two offers, and an agency gets one of them. The **lead pack** is the sample above. The
**job ask** (`jobs.py`) asks an agency that has never been emailed for part-time remote work, and
opens with one fact from that agency's own site. The tracker records which offer each first email
made (`lead_pack` or `job_ask`), so their reply rates can be compared with `track.py list`.

## The offer

- **$59** for 50 qualified leads in the buyer's niche and city, paid upfront.
- **$99 a month** for 25 fresh leads a week.
- Custom scrapers, workflows and data pipelines are quoted per project.

Prices come up only after someone replies. They never go in a first email or a follow-up. The text
to use is in `outreach/pricing.md`.

## Hard rules

1. **Never send or submit anything.** No emails, DMs, contact forms or scheduled sends. Draft only.
   The operator sends by hand and schedules outside Claude Code.
2. **Evidence or "unknown".** Every claim about an agency or a prospect traces to a page that was
   fetched, with its URL. If the evidence is missing, write "unknown". Never invent clients, team
   size, tools or pain points. Never claim past clients, reviews or results for LeadForge itself.
3. **Only the allowed signals.** A pack, email, follow-up or LinkedIn note may say only these things
   about a prospect business, and each must be checkable by a person in 10 seconds on a phone:
   - no website on the Google listing (from Maps data)
   - the website link on the listing is dead or does not resolve
   - the site is served without https. Claim it only when the https:// version of the same URL
     fails to load or has an invalid certificate. An https address that loads, or that redirects
     somewhere that loads, is not "no https".
   - the footer copyright year is 2023 or older
   - no Google tag, Tag Manager or Meta Pixel in the rendered page after 8 seconds (check
     `window.dataLayer`, `gtag`, `fbq` and the script sources)
   - review count or rating compared with the pack median
   - text quoted from the business's own site
4. **Retired signals, never to be used again:** no booking, no online booking, book button with no
   booking system, no WhatsApp, no chat, no enquiry chat, no social profiles linked. A manual check
   found most of these claims false, because a page scan cannot see a button that links out or a
   widget a script injects. They must not appear in any pack, email, follow-up or LinkedIn note. Do
   not add a new "X is missing from the site" signal without the operator's say-so.
5. **A listing link that lands on a different domain is not that business's site.** Say nothing
   about the page it lands on. A link that 404s because it is malformed is a broken link, not a dead
   site; say what the link does and what the domain shows. A Wix address with no site behind it
   answers 404 but shows a page saying the domain is not connected: write "opens a 'domain isn't
   connected' page", never "returns a 404 page".
6. **Verify on the day.** Every signal is confirmed in a rendered browser with `verify.py` before a
   pack is built, and again if the pack is more than three days old. Never write "checked twice in a
   real browser" or any other claim about the checking in an email.
7. **If a signal will not stretch to fit an agency's offer, do not stretch it.** Mark the draft
   `BLOCKED` with the reason and move on.
8. **No LinkedIn scraping or automation.** No scraping behind logins. No scraping of review
   directories that sit behind bot protection. A founder's name comes from the agency's own site.
9. **Business contact addresses only**, published on the company's own site. Never guess an address.
10. **Small crawls.** Depth 1, at most 4 pages at once, no proxies, no stealth. If Google blocks, stop
   and report. Do not escalate.
11. **No real data in git.** Secrets go in `.env`. Scraped data, packs, drafts and send files stay in
    the gitignored folders. `RUNLOG.md` and commit messages name no business.
12. **Audit before every push:** `python src/audit_public.py --online` must exit 0.
13. **No `Co-Authored-By` lines** and no tool attribution in commits or pull requests. The operator
    is the only author.
14. **No payment details anywhere in this repository.**
15. Banned in outreach: "I hope this finds you well", "I came across your profile", flattery,
    "synergy", "quick question", made-up statistics.
16. **The job ask opens with one factual sentence about the agency**, resting on words quoted from
    its own site, with the page's URL. Prefer a named case study, client or project. Fall back to
    the services it lists only when nothing else can be quoted. No compliments. Nothing about the
    agency's product being weak or missing something. No quotable fact, no email: drop the agency
    and say why. Never guess.
17. **Everything the job ask says about the operator comes word for word from his wording file**,
    `outreach/job_ask.json` (gitignored): the pitch, one of three proof lines chosen by agency type
    (A marketing, SEO and ads; B AI, automation and software; C web development), the trial question
    and the P.S. Never write a new proof line. No attachments, and no link except the one in that
    file. Never mention n8n, Docker or Looker Studio.
18. **A role has a status, and the email says no more than the status allows.** `hiring.py` reads
    roles from a company's own careers page or its public job system and records the exact text.
    - `fresh`: a posting date in the last 60 days. Only this may be called hiring: "I saw you're
      hiring a {title}".
    - `undated`: listed as open with no date. "I saw the {title} role on your careers page".
    - `talent_pool`: "roles we'd like to hear about", "disciplines we want to meet". Not an
      opening. "I saw {title} listed among the roles on your careers page", and no line about
      helping before the hire.
    - A posting date older than 60 days, or a closing date that has passed, drops the role.
    The opener names a role only when it is `strong` (data, automation, Python, scraping,
    reporting and BI, backend, ML) or `adjacent` (full-stack, web developer, CRM or marketing
    operations). A role that is on site only or needs a visa is flagged and ranked lower, not
    dropped.
19. **An agency gets one offer.** A job ask goes only to an agency that has never been emailed, is
    not in `data/skip.txt` and has no lead-pack draft waiting to go.
20. **Careers pages are read politely, and nothing is ever applied for.** Public pages only.
    `robots.txt` is obeyed. One request at a time per site, results kept for 7 days, the browser
    only for a page that shows nothing without JavaScript. A job system is read through its
    public board API where it has one (Greenhouse, Lever, Workable, Recruitee). Never LinkedIn,
    Indeed or Bayt. If a source's terms are unclear, skip it and say so. An Apply link goes in
    `outreach/apply_by_hand.md` for the operator to use himself; never submit a form.

## Send rules

- At most 25 new emails a weekday.
- At most 30 messages a day counting follow-ups.
- Follow-ups go first. New emails take what is left.
- Nothing is sent on Saturday or Sunday.
- A follow-up that lands on a weekend moves to Monday.
- Follow-ups are due on day 3 and day 7 after the first email.
- Two or more bounces in one day: stop, and clean the list before anything else goes. Record each
  with `track.py mark <agency> bounced`; `track.py bounces` shows them by day.

`track.py plan` and `track.py today` enforce these. Packs and drafts are built one batch ahead of
each send day.

## Follow-ups

- Never write "just following up", "circling back", "bumping this" or "checking in". Every
  follow-up adds something new, or it is not sent.
- A follow-up is a reply in the thread of the first email. Its subject is "Re:" and the original
  subject, never a new one.
- **Job ask, day 3:** one new piece of proof in two or three lines: the screen recording of the
  pipeline when `LEADFORGE_DEMO_URL` is set in `.env`, otherwise a proof line the first email did
  not use. It ends on the same trial question.
- **Job ask, day 7:** close the loop, in under 40 words.
- **Lead pack, day 3:** turn it into the job ask, with the `pivot` sentence from the wording file.
  `draft.py followups` rewrites only the follow-ups of a draft that is already built. The email
  above them is the record of what was sent, and is never rebuilt.

## Draft format

Three subject lines of 6 words or fewer. Email 1 at 120 words or fewer, plain text, no links, ending
"Want the other 7? Just reply yes." Follow-up 1 at 50 words or fewer, follow-up 2 at 40. A LinkedIn
note of 280 characters or fewer. The three business lines in email 1 are generated from verified
signals by `draft.py`. They are never typed by hand.

A job ask has one subject line, the email, the pages to open to check it, and two follow-ups (60
words and 40). `jobs.py build` writes it from the wording file and the agency's spec, and
`lint_drafts.py` checks it.

## Commands

```bash
python src/discover.py --region <region>                     # a region's searches to data/raw/agencies_<region>.csv
python src/discover.py queries/<list>.txt <name>             # any list of Maps searches to data/raw/<name>.csv
python src/merge_clutch.py data/raw/<name>.csv               # merge a hand-made shortlist
python src/enrich.py data/raw/<name>.csv                     # crawl each site, record evidence
python src/enrich.py data/raw/<name>.csv --only-status dead,http_error   # retry failed sites
python src/shortlist.py --top 80                             # triage and write digests to score from
python src/shortlist.py --region uk --top 40                 # another region; its files carry the region's name
python src/qualify.py ingest data/scored/_batches/<batch>.json   # validate verdicts, compute scores
python src/qualify.py summary --top 15                       # ranked list to data/scored/summary.csv
python src/qualify.py summary --region uk                    # another region's ranking, to summary_uk.csv
python src/discover.py queries/packs/<agency>.txt pack_<agency>  # an agency's own niche and city
python src/enrich.py data/raw/pack_<agency>.csv --mode light --out data/enriched/packs/<agency>
python src/prospects.py <agency> --niche "<niche>" --want <signals>   # candidate signals, unverified
python src/verify.py <agency> --want <signals>               # confirm every signal in a browser, today
python src/pack.py build <agency>                            # render the pack (.md and .html)
python src/pack.py fill --readme-no-email                    # fill name and links from .env
python src/draft.py build <agency>                           # render and lint the outreach draft
python src/draft.py quotes [<agency>]                        # is what line 1 quotes on the agency's page today?
python src/draft.py followups [<agency> ...]                 # rewrite only the follow-ups of drafts already built
python src/hiring.py scan --region <region>                  # careers pages and job systems of every discovered company
python src/hiring.py report --region <region>                # data/scored/hiring_<region>.csv and outreach/apply_by_hand.md
python src/hiring.py drafts --region <region>                # job-ask specs for the strong and adjacent matches
python src/track.py discover --by-hiring --region <region>   # the three above, in one go
python src/jobs.py scan [<agency> ...]                       # the job ask: read each candidate's homepage and careers page
python src/jobs.py build [<agency> ...]                      # render and lint the job-ask drafts in outreach/jobs/
python src/jobs.py quotes [<agency> ...]                     # are the opener's quoted words on the agency's page today?
python src/lint_drafts.py                                    # check every draft against the rules
python src/track.py sync                                     # pick up new and blocked drafts
python src/track.py plan <YYYY-MM-DD>                        # schedule unsent leads inside the send rules
python src/track.py plan <YYYY-MM-DD> --keep                 # place only undated leads; dated ones stay where they are
python src/track.py ready <YYYY-MM-DD>                       # the day's files: follow-ups, lead-pack emails, job asks
python src/track.py today                                    # follow-ups due, then new sends
python src/track.py mark <agency> sent [--date YYYY-MM-DD]   # record a send; sets follow-up dates
python src/track.py mark <agency> drafted                    # a send was cancelled
python src/track.py mark <agency> fu1                        # a follow-up went out (fu2 likewise)
python src/track.py mark <agency> replied --note "<text>"    # also won, lost, no_reply
python src/track.py mark <agency> bounced                    # the address rejected it; no follow-up is owed
python src/track.py bounces                                  # bounces by day; two in a day means stop
python src/track.py list                                     # every lead, its offer and status, and replies by offer
python src/us_track.py prepare                               # second track: agencies that buy build work
python src/us_track.py digest                                # what their own sites say, to write from
python src/sample.py --brief "<job description>"             # a 10-row sample and a short proposal
python src/audit_public.py --online                          # must pass before every push
python examples/make_example.py                              # rebuild the fictional example pack and email
python src/lint_drafts.py <file.md>                          # lint one file (examples/rejected.example.md must fail)
python -m pytest                                             # the rules, as tests (needs requirements-dev.txt)
python docs/make_assets.py                                   # regenerate the README's GIFs from fictional data
python docs/make_site.py --check                             # build the live page into _site/ and check its links
```

The live page is served by GitHub Pages from the `gh-pages` branch. The pages workflow rebuilds and
publishes it on every push to `main`, so it is never edited or pushed by hand. Its source is
`docs/site/`, and `make_site.py` fills it from the committed example, so it shows fictional data only.

Use `./.venv/Scripts/python.exe` on this machine. There is no Docker, so discovery runs through the
Playwright engine and the installed Edge. Log every run in `RUNLOG.md` (the scripts do this) and
commit after each phase.

## Compact Instructions

When this conversation is compacted, keep all of the following word for word in the summary.

- **LeadForge** finds small Gulf agencies, scores them, and wins a reply with a free pack of ten
  prospects in the agency's own niche and city. Real names, domains and emails are only in `data/`,
  `packs/` and `outreach/`; none may reach git, `RUNLOG.md` or a commit message.
- **Offer:** $59 for 50 leads; $99 a month for 25 a week; custom work quoted. Prices only after a reply.
- **Regions are config, not branches:** `config/regions/gulf.yaml` (the default) and `uk.yaml`, used
  with `--region` on `discover.py`, `shortlist.py` and `qualify.py summary`. The UK is scored only
  (`outreach: false`): draft nothing for it until the operator says so. No Germany or other EU
  country for now; their cold-email rules are stricter.
- **A second offer, the job ask** (`jobs.py`), asks an agency for part-time remote work. An agency
  gets one offer: a job ask goes only to one never emailed, not skipped, with no lead-pack draft
  waiting. Its opener is one factual sentence resting on words quoted from the agency's own site,
  with the URL; no compliments, nothing about a weakness; no quotable fact, no email. What it says
  about the operator comes word for word from `outreach/job_ask.json`: never a new proof line, no
  attachment, no other link, never n8n, Docker or Looker Studio. "Hiring" means an open role on the
  agency's own careers page today; the opener names it only for data, automation, scraping,
  reporting or development work. Drafts are in `outreach/jobs/`; both are private. Prefer a named
  case study, client or project for the opener; services only as a fallback.
- **Hiring signals** (`hiring.py`, `track.py discover --by-hiring`): roles read from careers pages
  and public job-board APIs, robots.txt obeyed, one request at a time per site, cached 7 days. A
  role is `fresh` (posted in the last 60 days: the only one that may be called "hiring"), `undated`
  ("the {title} role on your careers page"), or `talent_pool` ("listed among the roles", and no
  line about the hire); older or closed roles are dropped. Relevance is strong, adjacent or none.
  Never LinkedIn, Indeed or Bayt. Never submit a form: Apply links go in
  `outreach/apply_by_hand.md` for the operator.
- **Follow-ups** are replies in the first email's thread ("Re:" and its subject). Never "just
  following up", "circling back", "bumping this" or "checking in": each adds something new or is
  not sent. Job ask: day 3 one new piece of proof and the trial question, day 7 close the loop in
  under 40 words. Lead pack: day 3 turns into the job ask. Never rebuild a draft that has been
  sent; `draft.py followups` rewrites only its follow-ups.
- **Never send or submit anything.** Draft only. The operator sends by hand.
- **Evidence or "unknown".** No invented facts. No claims of past clients, reviews or results.
- **Allowed signals only**, each checkable in 10 seconds on a phone: no website on the Google
  listing; the listing's website link is dead or does not resolve; site served without https (only
  when the https:// version of the same URL fails to load or has an invalid certificate); footer
  copyright year 2023 or older; no Google tag, Tag Manager or Meta Pixel in the rendered page after
  8 seconds (`window.dataLayer`, `gtag`, `fbq`, script sources); review count or rating against the
  pack median; text quoted from the business's own site.
- **Retired, never use:** no booking, no online booking, book button with no booking system, no
  WhatsApp, no chat, no enquiry chat, no social profiles linked. Not in any pack, email, follow-up
  or LinkedIn note.
- A listing link that lands on another domain says nothing about the business. A malformed link is
  a broken link, not a dead site. A Wix domain with no site "opens a 'domain isn't connected'
  page", never "returns a 404 page".
- **The ready files** for a day are `outreach/ready/<date>-followups.md`, `<date>.md` (lead-pack
  emails) and `<date>-jobs.md` with `<date>-jobs.csv`. Each gives, for each claim, the exact URL to
  open; for "no website on the listing" that is the Google Maps link.
- **An opening line may say only what the agency's own page says.** Check it with `draft.py quotes`.
- If a site shows a browser check or does not answer, record it as unread, wait and re-run. Never
  work around it.
- **Verify every signal in a rendered browser on the day** (`verify.py`). Never say in an email how
  or how often something was checked. If the signals do not fit an agency's offer, mark the draft
  `BLOCKED` with the reason. Do not stretch.
- **No LinkedIn scraping.** No logins, no bot-protected directories, no guessed addresses. Small
  crawls: depth 1, at most 4 pages at once, no proxies; stop if Google blocks.
- **Send rules:** max 25 new emails a weekday; max 30 a day with follow-ups; follow-ups first; no
  Saturday or Sunday sends; a weekend follow-up moves to Monday; follow-ups on day 3 and day 7; two
  bounces in one day means stop and clean the list.
- **Before every push:** `python src/audit_public.py --online` must exit 0. **No `Co-Authored-By`
  lines.** No payment details in the repository.
- **Commands:** `discover.py`, `merge_clutch.py`, `enrich.py`, `shortlist.py`, `qualify.py ingest`
  and `summary`, `prospects.py`, `verify.py`, `pack.py build` and `fill`, `draft.py build`, `quotes` and
  `followups`, `jobs.py scan`, `build` and `quotes`, `hiring.py scan`, `report` and `drafts`,
  `lint_drafts.py`, `track.py sync`, `plan` (`--keep`), `ready`, `today`, `mark`, `bounces`, `list`
  and `discover --by-hiring`, `us_track.py prepare`
  and `digest`, `sample.py --brief`, `audit_public.py --online`, `examples/make_example.py`, `python -m pytest`,
  `docs/make_assets.py`, `docs/make_site.py --check`. Run
  them with `./.venv/Scripts/python.exe`.
- The README's images, the live page and the examples show fictional data only. Never put a real
  business in a screenshot, GIF, test, example or on the page. The page is published from `gh-pages`
  by a workflow on every push to `main`.
- Also keep: which drafts are `BLOCKED` and why, which emails have been sent, on what date and with
  which offer, who has replied or bounced, and the paths of the current ready files.
