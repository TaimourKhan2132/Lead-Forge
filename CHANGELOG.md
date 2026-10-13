# Changelog

Notable changes to LeadForge. No real business is named here or anywhere else in this repository.

## Unreleased

### Added
- A second offer, the job ask (`jobs.py`): the operator asks an agency for part-time remote work.
  `scan` reads each candidate's homepage and careers page in a browser, `build` renders the email
  from the operator's own wording file and the agency's spec, and `quotes` confirms the words the
  opener rests on are still on the agency's page. An agency with no quotable fact gets no email.
- Every lead in the tracker carries the offer its first email made. `track.py list` ends with the
  replies each offer has had, with bounces left out of the count.
- `track.py mark <agency> bounced` and `track.py bounces`. Two bounces in one day print a warning to
  stop and clean the list, wherever the day's sends are shown.
- `track.py plan <date> --keep` places only the leads that have no date, so a day's files do not
  change under the person sending from them.
- `draft.py followups` rewrites only the follow-up sections of a draft that is already built.
- `track.py ready <date>` writes the follow-ups due that day to their own file, ahead of the new
  emails, each with its "Re:" subject. Job asks get a page and a CSV with the same fields.

### Changed
- Send rules: at most 25 new emails a weekday and 30 messages a day with follow-ups. They were 10
  and 15.
- A follow-up has to add something. The linter rejects "just following up", "circling back",
  "bumping this" and "checking in", and a lead-pack follow-up 1 can turn into the job ask.
- `draft.py quotes`: when an agency's page will not load, the last day its words were read is kept,
  and the send file says both. A failed retry used to erase the earlier reading.
- `verify.py` no longer writes the value of `--only` to the run log. Those values are businesses' own
  domains.

## [0.3.0] - 2026-10-13 · A live page

The project now has a page of its own, served by GitHub Pages:
https://taimourkhan2132.github.io/Lead-Forge/

It shows the deliverable instead of its source, and it is filled from the repository, so it cannot
drift from the code.

### Added
- A live page: the example pack served as the page an agency would open, the email beside the list a
  person checks before sending it, the seven signals with the wording `signals.py` writes for each,
  and six invented claims walked through the gates `verify.py` applies.
- `docs/make_site.py`, which builds the page from the committed example pack and email, the linter's
  real output on the draft written to fail, the tracker's caps and its follow-up date rule, the
  version in this file and the number of tests.
- A pages workflow that rebuilds the page on every push to `main` and publishes it to the `gh-pages`
  branch as a single commit attributed to whoever pushed.
- Tests for the page's build, and a step in the checks workflow that builds it.

### Changed
- `audit_public.py` also searches the built page for every name, domain and email in the private data
  folder, since the page is published too. A page that has not been built is reported as skipped,
  not as clean.
- `RUNLOG.md`: decisions that had been run together into one bullet are separate again, and dashes
  saved in the wrong encoding are fixed. No wording changed.

Every business on the page is fictional, as everywhere else in this repository.

## [0.2.0] - 2026-10-11 · Seven signals

The rebuild. A manual check of the first packs found that most "no booking", "no WhatsApp" and "no
chat" claims were false: a page scan cannot see a button that links out, or a widget a script injects
later, so "none found" had been reported as "none there". This release retires every claim of that
kind and replaces how signals are produced, checked and worded.

### Added
- `signals.py`: the only seven signals a pack or an email may use, each one checkable by a person in
  ten seconds on a phone, plus text quoted from the business's own site. It also writes the wording,
  so nothing can be phrased more strongly than it was checked.
- `verify.py`, rewritten: opens the live Google listing and the website in a real browser on the day,
  keeps a signal only when the browser shows it, and requires two visits for any claim that something
  is absent or broken.
- `draft.py`: the three business lines of an email are generated from verified signals, never typed.
  `draft.py quotes` checks the opening line against the agency's own page.
- `track.py ready <date>`: the day's emails in one file, with one line per claim and the exact URL to
  open to confirm it.
- Send rules in the tracker: 10 new emails a day, 15 with follow-ups, follow-ups first, no weekends,
  follow-ups on day 3 and day 7.
- A linter rule that rejects the retired wording anywhere in a draft.
- Tests for the rules, a fictional example email, and a draft written to fail (`examples/`).
- `CLAUDE.md`, an MIT `LICENSE`, this changelog, a checks workflow, and a release workflow that
  publishes a version's entry here when its tag is pushed.
- A README that shows the pipeline running on fictional data, with a script that regenerates its images.

### Changed
- "No https" is claimed only when the https version of the same URL fails to load or has an invalid
  certificate. An https address that answers and redirects is not a failure.
- A 404 on a deep or malformed link is reported as a broken link when the domain's homepage loads.
- When a listing's link lands on a different domain, nothing is said about the page it lands on.
- A low rating is now relative: under 4.0 and at least 0.4 below the median of the pack's listings.

### Removed
- Retired for good: no booking, no online booking, book button with no booking system, no WhatsApp,
  no chat, no enquiry chat, no social profiles linked. Also dropped: no meta description, no mobile
  viewport, listing links to a social profile, no email published.
- The sentence about gaps being "checked twice in a real browser".

### What the rebuild found
- Of 20 packs, 19 were rebuilt from signals verified that day. One was blocked instead of stretched:
  its pool had 8 prospects with a signal the agency could act on, and a pack needs 10.
- The operator spot-checked 7 rebuilt claims by hand. 5 were right and 2 were wrong, both caused by a
  listing link that did not lead where it appeared to. The three "Changed" rules above came from that.

## [0.1.0] - 2026-10-11 · First public version

First public version.

- Google Maps discovery through Playwright and the installed Edge (no Docker needed).
- Site enrichment with an evidence record for every extracted fact.
- A 100-point qualification rubric, judged by an LLM and validated by code.
- Sample packs of ten prospects as Markdown and printable HTML.
- Outreach drafts with a linter, and a SQLite tracker.
- `audit_public.py`: proves nothing from the private data folder ever reached git history.

Its packs relied on signals that 0.2.0 retired. It is kept in the history as the starting point, not
as something to use.

[0.3.0]: https://github.com/TaimourKhan2132/Lead-Forge/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/TaimourKhan2132/Lead-Forge/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/TaimourKhan2132/Lead-Forge/releases/tag/v0.1.0
