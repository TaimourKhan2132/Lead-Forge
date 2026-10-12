# LeadForge

Instructions for Claude Code in this repository. This file is public, so it names no real business,
domain or email address. Real agencies, prospects, packs and drafts live under `data/`, `packs/` and
`outreach/` and are gitignored. Look there, never here.

## What LeadForge is

A local pipeline that finds small marketing and automation agencies in the Gulf (UAE, KSA, Qatar),
scores them against a 100-point rubric, and wins a reply by giving each one a free sample: ten
qualified prospects in that agency's own niche and city. It then drafts the outreach that leads
with the sample and tracks sends and follow-ups. The operator sends every message by hand.

Stages: `discover` (Google Maps) → `enrich` (each site, with evidence) → `shortlist` and `qualify`
(rubric, tier A at 70 and above, B at 50 to 69) → `prospects` and `verify` (signals, confirmed in a
browser) → `pack` → `draft` → `track`.

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
   site; say what the link does and what the domain shows.
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

## Send rules

- At most 10 new emails a day.
- At most 15 messages a day counting follow-ups.
- Follow-ups go first. New emails take what is left.
- Nothing is sent on Saturday or Sunday.
- A follow-up that lands on a weekend moves to Monday.
- Follow-ups are due on day 3 and day 7 after the first email.

`track.py plan` and `track.py today` enforce these. Packs and drafts are built in batches of 10, one
batch ahead of each send day.

## Draft format

Three subject lines of 6 words or fewer. Email 1 at 120 words or fewer, plain text, no links, ending
"Want the other 7? Just reply yes." Follow-up 1 at 50 words or fewer, follow-up 2 at 40. A LinkedIn
note of 280 characters or fewer. The three business lines in email 1 are generated from verified
signals by `draft.py`. They are never typed by hand.

## Commands

```bash
python src/discover.py queries/<list>.txt <name>             # Maps searches to data/raw/<name>.csv
python src/merge_clutch.py data/raw/<name>.csv               # merge a hand-made shortlist
python src/enrich.py data/raw/<name>.csv                     # crawl each site, record evidence
python src/enrich.py data/raw/<name>.csv --only-status dead,http_error   # retry failed sites
python src/shortlist.py --top 80                             # triage and write digests to score from
python src/qualify.py ingest data/scored/_batches/<batch>.json   # validate verdicts, compute scores
python src/qualify.py summary --top 15                       # ranked list to data/scored/summary.csv
python src/discover.py queries/packs/<agency>.txt pack_<agency>  # an agency's own niche and city
python src/enrich.py data/raw/pack_<agency>.csv --mode light --out data/enriched/packs/<agency>
python src/prospects.py <agency> --niche "<niche>" --want <signals>   # candidate signals, unverified
python src/verify.py <agency> --want <signals>               # confirm every signal in a browser, today
python src/pack.py build <agency>                            # render the pack (.md and .html)
python src/pack.py fill --readme-no-email                    # fill name and links from .env
python src/draft.py build <agency>                           # render and lint the outreach draft
python src/draft.py quotes [<agency>]                        # is what line 1 quotes on the agency's page today?
python src/lint_drafts.py                                    # check every draft against the rules
python src/track.py sync                                     # pick up new and blocked drafts
python src/track.py plan <YYYY-MM-DD>                        # schedule unsent leads inside the send rules
python src/track.py ready <YYYY-MM-DD>                       # the day's emails and the links to check
python src/track.py today                                    # follow-ups due, then new sends
python src/track.py mark <agency> sent [--date YYYY-MM-DD]   # record a send; sets follow-up dates
python src/track.py mark <agency> drafted                    # a send was cancelled
python src/track.py mark <agency> fu1                        # a follow-up went out (fu2 likewise)
python src/track.py mark <agency> replied --note "<text>"    # also won, lost, no_reply
python src/track.py list                                     # every lead and its status
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
  a broken link, not a dead site.
- **The ready file** (`outreach/ready/<date>.md`) gives, for each claim, the exact URL to open; for
  "no website on the listing" that is the Google Maps link.
- **An opening line may say only what the agency's own page says.** Check it with `draft.py quotes`.
- If a site shows a browser check or does not answer, record it as unread, wait and re-run. Never
  work around it.
- **Verify every signal in a rendered browser on the day** (`verify.py`). Never say in an email how
  or how often something was checked. If the signals do not fit an agency's offer, mark the draft
  `BLOCKED` with the reason. Do not stretch.
- **No LinkedIn scraping.** No logins, no bot-protected directories, no guessed addresses. Small
  crawls: depth 1, at most 4 pages at once, no proxies; stop if Google blocks.
- **Send rules:** max 10 new emails a day; max 15 a day with follow-ups; follow-ups first; no
  Saturday or Sunday sends; a weekend follow-up moves to Monday; follow-ups on day 3 and day 7.
- **Before every push:** `python src/audit_public.py --online` must exit 0. **No `Co-Authored-By`
  lines.** No payment details in the repository.
- **Commands:** `discover.py`, `merge_clutch.py`, `enrich.py`, `shortlist.py`, `qualify.py ingest`
  and `summary`, `prospects.py`, `verify.py`, `pack.py build` and `fill`, `draft.py build` and `quotes`,
  `lint_drafts.py`, `track.py sync`, `plan`, `ready`, `today`, `mark` and `list`, `us_track.py prepare`
  and `digest`, `sample.py --brief`, `audit_public.py --online`, `examples/make_example.py`, `python -m pytest`,
  `docs/make_assets.py`, `docs/make_site.py --check`. Run
  them with `./.venv/Scripts/python.exe`.
- The README's images, the live page and the examples show fictional data only. Never put a real
  business in a screenshot, GIF, test, example or on the page. The page is published from `gh-pages`
  by a workflow on every push to `main`.
- Also keep: which drafts are `BLOCKED` and why, which emails have been sent and on what date, and
  the path of the current ready file.
