# Changelog

Notable changes to LeadForge. No real business is named here or anywhere else in this repository.

## [0.2.0] - 2026-10-11

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
- `CLAUDE.md`, `LICENSE`, this changelog, and a checks workflow.

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

## [0.1.0] - 2026-10-11

First public version.

- Google Maps discovery through Playwright and the installed Edge (no Docker needed).
- Site enrichment with an evidence record for every extracted fact.
- A 100-point qualification rubric, judged by an LLM and validated by code.
- Sample packs of ten prospects as Markdown and printable HTML.
- Outreach drafts with a linter, and a SQLite tracker.
- `audit_public.py`: proves nothing from the private data folder ever reached git history.

Its packs relied on signals that 0.2.0 retired. It is kept in the history as the starting point, not
as something to use.

[0.2.0]: https://github.com/TaimourKhan2132/Lead-Forge/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/TaimourKhan2132/Lead-Forge/releases/tag/v0.1.0
