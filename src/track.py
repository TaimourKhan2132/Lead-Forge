"""Outreach tracker: who to email today, which follow-ups are due, who has replied.

    python src/track.py sync                      # pick up every drafted lead (Gulf packs and the US track)
    python src/track.py plan 2026-10-13           # schedule every unsent lead from that day on, best score first
    python src/track.py plan                      # show the plan and each day's load against the caps
    python src/track.py plan 2026-10-13 --keep    # leave dated leads where they are; place only the undated ones
    python src/track.py ready 2026-10-13          # write that day's files to outreach/ready/: follow-ups,
                                                  # lead-pack emails, and job asks (as .md and .csv)
    python src/track.py today                     # follow-ups due first, then new sends
    python src/track.py mark <domain> sent        # sets the day-3 and day-7 follow-up dates
    python src/track.py mark <domain> sent --date 2026-10-12     # for an email scheduled ahead in the mail client
    python src/track.py mark <domain> drafted     # a send was cancelled: clear its dates
    python src/track.py mark <domain> fu1         # follow-up 1 went out (fu2 likewise)
    python src/track.py mark <domain> replied --note "wants the other 7"
    python src/track.py mark <domain> bounced     # the address rejected it: no follow-ups, and it counts below
    python src/track.py bounces                   # bounces by day; two in one day means stop and clean the list
    python src/track.py list                      # every lead, and the reply rate of each offer
    python src/track.py discover --by-hiring --region gulf   # start from the openings: see hiring.py

Send rules, enforced by `plan` and `today`: at most 25 new emails a day and 30 messages a day counting
follow-ups; follow-ups go first; nothing is sent on Saturday or Sunday; a follow-up that lands on a
weekend moves to Monday; follow-ups are due on day 3 and day 7.

Every lead carries the offer its first email made, `lead_pack` or `job_ask` (`build_work` for the US
track), so the two can be compared. An agency gets one offer.

Nothing here sends anything. It only records what you did by hand.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import re
import sqlite3
import sys
from collections import Counter

from rich.console import Console
from rich.table import Table

from common import (DATA, DRAFTS, JOB_WORDING, JOBS, PACKS, ROOT, SCORED, US_TRACK, job_wording, outreach_open,
                    utf8_stdout)
from pack import MAX_AGE_DAYS

DB = DATA / "tracker.db"
READY = ROOT / "outreach" / "ready"
STATUSES = ("drafted", "sent", "replied", "won", "lost", "no_reply", "bounced")
OFFERS = ("lead_pack", "job_ask", "build_work")
NEW_CAP = 25    # first emails in a day
DAILY_CAP = 30  # first emails and follow-ups together
BOUNCE_LIMIT = 2  # this many bounces in one day means the list is bad: stop and clean it
FU1_DAYS, FU2_DAYS = 3, 7
console = Console()

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    domain      TEXT PRIMARY KEY,
    agency      TEXT NOT NULL,
    email       TEXT,
    tier        TEXT,
    score       INTEGER,
    pack_path   TEXT,
    draft_path  TEXT,
    status      TEXT NOT NULL DEFAULT 'drafted'
                CHECK (status IN ('drafted','sent','replied','won','lost','no_reply','bounced')),
    sent_at     TEXT,
    fu1_due     TEXT,
    fu2_due     TEXT,
    fu1_sent_at TEXT,
    fu2_sent_at TEXT,
    notes       TEXT NOT NULL DEFAULT '',
    channel     TEXT NOT NULL DEFAULT 'email',
    blocked     TEXT NOT NULL DEFAULT '',
    planned_send TEXT,
    offer       TEXT NOT NULL DEFAULT 'lead_pack',
    bounced_at  TEXT
);
"""
# An agency can be given a send date before its pack and draft exist, so the plan has its own table.
PLAN_SCHEMA = """
CREATE TABLE IF NOT EXISTS plan (
    domain       TEXT PRIMARY KEY,
    agency       TEXT NOT NULL,
    tier         TEXT,
    score        INTEGER,
    planned_send TEXT NOT NULL
);
"""
# Columns added after the first release, for databases created before them.
# Every email sent before `offer` existed was a lead pack, which is what the default records.
MIGRATIONS = {"channel": "TEXT NOT NULL DEFAULT 'email'", "blocked": "TEXT NOT NULL DEFAULT ''",
              "planned_send": "TEXT", "offer": "TEXT NOT NULL DEFAULT 'lead_pack'", "bounced_at": "TEXT"}
MIN_PLAN_SCORE = 60  # tier A, then tier B down to this score
SKIP_FILE = DATA / "skip.txt"  # one domain per line, optionally "domain  # reason"; never planned


def connect() -> sqlite3.Connection:
    DATA.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    conn.execute(PLAN_SCHEMA)
    have = {row["name"] for row in conn.execute("PRAGMA table_info(leads)")}
    for column, ddl in MIGRATIONS.items():
        if column not in have:
            conn.execute(f"ALTER TABLE leads ADD COLUMN {column} {ddl}")
    made = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'leads'").fetchone()[0]
    if "'bounced'" not in made:
        # The list of statuses is part of the table itself, so admitting a new one means rebuilding it.
        columns = ", ".join(row["name"] for row in conn.execute("PRAGMA table_info(leads)"))
        conn.executescript(f"ALTER TABLE leads RENAME TO leads_old; {SCHEMA} "
                           f"INSERT INTO leads ({columns}) SELECT {columns} FROM leads_old; DROP TABLE leads_old;")
    return conn


def today() -> str:
    return dt.date.today().isoformat()


def workday(day: dt.date) -> dt.date:
    """Saturday and Sunday are never send days. Anything that lands on one moves to Monday."""
    while day.weekday() >= 5:
        day += dt.timedelta(days=1)
    return day


def due(sent: dt.date, days: int) -> str:
    """The day a follow-up goes out: `days` after the send, moved to Monday off a weekend."""
    return workday(sent + dt.timedelta(days=days)).isoformat()


def header_field(text: str, name: str) -> str:
    """Value of a '- **Name:** value' line in a draft's header, or ''."""
    header = text.split("\n## ", 1)[0]
    match = re.search(rf"^- \*\*{re.escape(name)}[^*]*:\*\* *(.+)$", header, flags=re.M)
    return match.group(1).strip() if match else ""


def blocked_reason(text: str) -> str:
    status = header_field(text, "Status")
    return status if status.upper().startswith("BLOCKED") else ""


def sync(conn: sqlite3.Connection) -> int:
    """Add every drafted lead. Existing rows keep their status; the blocked flag follows the draft."""
    added = 0
    for draft in sorted(US_TRACK.glob("*.md")):
        text = draft.read_text(encoding="utf-8")
        channel = header_field(text, "Channel").split()[0].lower() if header_field(text, "Channel") else "form"
        cur = conn.execute(
            "INSERT OR IGNORE INTO leads (domain, agency, email, tier, draft_path, channel, offer) VALUES (?,?,?,?,?,?,'build_work')",
            (draft.stem, header_field(text, "Agency") or draft.stem, header_field(text, "To"), "US",
             draft.relative_to(ROOT).as_posix(), channel))
        added += cur.rowcount
        conn.execute("UPDATE leads SET blocked = ?, channel = ?, email = ?, offer = 'build_work' WHERE domain = ?",
                     (blocked_reason(text), channel, header_field(text, "To"), draft.stem))
    for draft in sorted(DRAFTS.glob("*.md")):
        domain = draft.stem
        text = draft.read_text(encoding="utf-8")
        blocked = blocked_reason(text)
        if blocked and (JOBS / f"{domain}.md").exists():
            continue  # a pack draft that is blocked gives way to a job ask for the same agency
        pack = PACKS / f"{domain}.html"
        scored = SCORED / f"{domain}.json"
        # A blocked draft has no pack to send, so it is tracked without one.
        if not scored.exists() or not (pack.exists() or blocked):
            console.print(f"[yellow]skip {domain}: needs a pack and a scored record as well as a draft[/yellow]")
            continue
        rec = json.loads(scored.read_text(encoding="utf-8"))
        if not outreach_open(rec):
            console.print(f"[yellow]skip {domain}: its region is scored only, so nothing is sent to it yet[/yellow]")
            continue
        pack_path = pack.relative_to(ROOT).as_posix() if pack.exists() else None
        cur = conn.execute(
            "INSERT OR IGNORE INTO leads (domain, agency, email, tier, score, pack_path, draft_path) VALUES (?,?,?,?,?,?,?)",
            (domain, rec["agency"], rec.get("contact_email", "unknown"), rec["tier"], rec["score"],
             pack_path, draft.relative_to(ROOT).as_posix()))
        added += cur.rowcount
        conn.execute("UPDATE leads SET blocked = ?, pack_path = ? WHERE domain = ?", (blocked, pack_path, domain))
    # A job ask that was dropped after it was drafted leaves the tracker with its file.
    for lead in conn.execute("SELECT domain, draft_path FROM leads WHERE offer = 'job_ask' AND status = 'drafted'").fetchall():
        if not (ROOT / lead["draft_path"]).exists():
            conn.execute("DELETE FROM leads WHERE domain = ?", (lead["domain"],))
            conn.execute("DELETE FROM plan WHERE domain = ?", (lead["domain"],))
    for draft in sorted(JOBS.glob("*.md")):
        domain, text = draft.stem, draft.read_text(encoding="utf-8")
        scored = SCORED / f"{domain}.json"
        lead = conn.execute("SELECT status, offer, blocked FROM leads WHERE domain = ?", (domain,)).fetchone()
        if lead and (lead["status"] != "drafted" or (lead["offer"] == "lead_pack" and not lead["blocked"])):
            console.print(f"[yellow]skip jobs/{domain}: it already has a lead-pack email, and an agency gets one offer[/yellow]")
            continue
        # A company found through its careers page may never have been scored. It is tracked without a score.
        named = re.match(r"# Job ask: (.+) \(", text)
        rec = (json.loads(scored.read_text(encoding="utf-8")) if scored.exists() else
               {"agency": named.group(1) if named else domain, "tier": "", "score": None,
                "region": header_field(text, "Region") or None})
        if not outreach_open(rec):
            console.print(f"[yellow]skip jobs/{domain}: its region is scored only, so nothing is sent to it yet[/yellow]")
            continue
        path = draft.relative_to(ROOT).as_posix()
        cur = conn.execute(
            "INSERT OR IGNORE INTO leads (domain, agency, email, tier, score, draft_path, offer) VALUES (?,?,?,?,?,?,'job_ask')",
            (domain, rec["agency"], header_field(text, "To"), rec["tier"], rec["score"], path))
        added += cur.rowcount
        if cur.rowcount or lead["offer"] != "job_ask":
            conn.execute("DELETE FROM plan WHERE domain = ?", (domain,))  # any date it had was for a pack that will not be built
        conn.execute("UPDATE leads SET offer = 'job_ask', email = ?, draft_path = ?, pack_path = NULL, blocked = '' WHERE domain = ?",
                     (header_field(text, "To"), path, domain))
    # A blocked lead has no send date until it is unblocked and the plan is run again.
    conn.execute("DELETE FROM plan WHERE domain IN (SELECT domain FROM leads WHERE blocked <> '' OR status <> 'drafted')")
    conn.execute("UPDATE leads SET planned_send = (SELECT planned_send FROM plan WHERE plan.domain = leads.domain)")
    conn.commit()
    blocked_n = conn.execute("SELECT COUNT(*) FROM leads WHERE blocked <> ''").fetchone()[0]
    jobs_n = conn.execute("SELECT COUNT(*) FROM leads WHERE offer = 'job_ask'").fetchone()[0]
    console.print(f"[bold]sync[/bold] added={added}, total={conn.execute('SELECT COUNT(*) FROM leads').fetchone()[0]}, "
                  f"job_asks={jobs_n}, blocked={blocked_n}")
    return 0


def skipped_domains() -> set[str]:
    if not SKIP_FILE.exists():
        return set()
    lines = SKIP_FILE.read_text(encoding="utf-8").splitlines()
    return {ln.split("#")[0].strip().lower() for ln in lines if ln.split("#")[0].strip()}


def owed_follow_ups(conn: sqlite3.Connection) -> Counter:
    """Follow-ups already owed, by the day they are due, for emails that have gone out."""
    owed: Counter = Counter()
    for lead in conn.execute("SELECT * FROM leads WHERE status = 'sent'"):
        for due_day, done in ((lead["fu1_due"], lead["fu1_sent_at"]), (lead["fu2_due"], lead["fu2_sent_at"])):
            if due_day and not done:
                owed[max(due_day, today())] += 1
    return owed


def job_rank(lead: sqlite3.Row) -> int:
    """Among job asks, the better the role on the agency's careers page, the earlier it goes."""
    path = ROOT / (lead["draft_path"] or "")
    score = header_field(path.read_text(encoding="utf-8"), "Hiring score") if path.is_file() else ""
    return -int(score) if score.isdigit() else 0


def plan(conn: sqlite3.Connection, date: str | None, keep: bool = False) -> int:
    """Give every unsent lead a send date from `date` on, inside the send rules.

    A day takes a new email only if it has fewer than 25 already, the day's total stays within 30,
    and the two follow-ups that email will need still fit on their own days. Follow-ups are never
    pushed out to make room for a new email. Packs that are built go first, because a pack goes
    stale; then job asks, the best hiring score first; then agencies whose
    pack is still to build. With `keep`, a lead that already has a date from `date` on stays on it,
    so a day's files do not change under the person sending them.
    """
    if date:
        start = workday(dt.date.fromisoformat(date))
        built = conn.execute("SELECT * FROM leads WHERE status = 'drafted' AND blocked = '' AND tier <> 'US'").fetchall()
        built.sort(key=lambda r: (r["offer"] == "job_ask", job_rank(r) if r["offer"] == "job_ask" else 0, -(r["score"] or 0), r["domain"]))
        known = {row["domain"] for row in conn.execute("SELECT domain FROM leads")}
        with (SCORED / "summary.csv").open(encoding="utf-8", newline="") as fh:
            ranked = list(csv.DictReader(fh))  # already sorted best first by qualify.py
        skip = skipped_domains()
        unbuilt = [r for r in ranked if r["domain"] not in known and r["domain"] not in skip and int(r["score"]) >= MIN_PLAN_SCORE]
        queue = [(r["domain"], r["agency"], r["tier"], int(r["score"] or 0)) for r in [*built, *unbuilt]]
        owed, new, day = owed_follow_ups(conn), Counter(), start
        # An email already scheduled in the mail client for one of these days has taken one of its places.
        for row in conn.execute("SELECT sent_at FROM leads WHERE status = 'sent' AND sent_at >= ?", (start.isoformat(),)):
            new[row["sent_at"]] += 1
        dated = ({row["domain"]: row["planned_send"] for row in
                  conn.execute("SELECT domain, planned_send FROM plan WHERE planned_send >= ?", (start.isoformat(),))} if keep else {})
        conn.execute("DELETE FROM plan")

        def place(lead: tuple, key: str) -> None:
            conn.execute("INSERT INTO plan (domain, agency, tier, score, planned_send) VALUES (?,?,?,?,?)", (*lead, key))
            new[key] += 1
            owed[due(dt.date.fromisoformat(key), FU1_DAYS)] += 1
            owed[due(dt.date.fromisoformat(key), FU2_DAYS)] += 1

        def room(key: str) -> bool:
            return new[key] + owed[key] < DAILY_CAP

        for lead in queue:
            if lead[0] in dated:
                place(lead, dated[lead[0]])
        for lead in queue:
            if lead[0] in dated:
                continue
            while not (new[day.isoformat()] < NEW_CAP and room(day.isoformat())
                       and room(due(day, FU1_DAYS)) and room(due(day, FU2_DAYS))):
                day = workday(day + dt.timedelta(days=1))
            place(lead, day.isoformat())
        conn.execute("UPDATE leads SET planned_send = (SELECT planned_send FROM plan WHERE plan.domain = leads.domain)")
        conn.commit()
        jobs_n = sum(r["offer"] == "job_ask" for r in built)
        console.print(f"[bold]plan[/bold] {len(queue)} agencies scheduled from {start.isoformat()} "
                      f"({len(built) - jobs_n} with a pack and draft, {jobs_n} job asks, {len(unbuilt)} still to build"
                      + (f"; {len(dated)} kept the date they had" if keep else "") + ")")

    rows = conn.execute(
        "SELECT plan.*, leads.status AS status, leads.draft_path AS draft, leads.blocked AS blocked, leads.offer AS offer "
        "FROM plan LEFT JOIN leads ON leads.domain = plan.domain ORDER BY planned_send, score DESC").fetchall()
    table = Table(title=f"Send plan ({len(rows)})", title_justify="left")
    for header in ("Send date", "Day", "Agency", "Offer", "Tier", "Score", "State"):
        table.add_column(header)
    for row in rows:
        state = "pack and draft not built yet" if row["draft"] is None else (row["blocked"] or row["status"])
        table.add_row(row["planned_send"], dt.date.fromisoformat(row["planned_send"]).strftime("%a"), row["agency"],
                      row["offer"] or "lead_pack", row["tier"] or "", str(row["score"]), state)
    console.print(table)
    show_load(conn)
    bounce_check(conn)
    return 0


def show_load(conn: sqlite3.Connection) -> None:
    """Each day's messages against the caps, counting the follow-ups that the plan itself will create."""
    load: dict[str, list[int]] = {}

    def add(day: str | None, slot: int) -> None:
        if day and day >= today():
            load.setdefault(day, [0, 0, 0])[slot] += 1

    for lead in conn.execute("SELECT * FROM leads WHERE status = 'sent'"):
        add(None if lead["fu1_sent_at"] else lead["fu1_due"], 1)
        add(None if lead["fu2_sent_at"] else lead["fu2_due"], 2)
        add(lead["sent_at"], 0)  # an email scheduled ahead in the mail client still uses that day's room
    for row in conn.execute("SELECT planned_send FROM plan"):
        day = dt.date.fromisoformat(row["planned_send"])
        add(row["planned_send"], 0)
        add(due(day, FU1_DAYS), 1)
        add(due(day, FU2_DAYS), 2)
    if not load:
        return
    table = Table(title=f"Daily load if every planned send goes out on its day (max {NEW_CAP} new, {DAILY_CAP} in all)",
                  title_justify="left")
    for header in ("Date", "Day", "New", "Follow-up 1", "Follow-up 2", "Total", ""):
        table.add_column(header, justify="right" if header not in ("Date", "Day", "") else "left")
    for day in sorted(load):
        new, fu1, fu2 = load[day]
        total = new + fu1 + fu2
        over = f"[red]{total - DAILY_CAP} over the cap[/red]" if total > DAILY_CAP else ""
        table.add_row(day, dt.date.fromisoformat(day).strftime("%a"), str(new), str(fu1), str(fu2), str(total), over)
    console.print(table)


def mark(conn: sqlite3.Connection, domain: str, status: str, note: str, date: str | None) -> int:
    row = conn.execute("SELECT * FROM leads WHERE domain = ?", (domain,)).fetchone()
    if row is None:
        console.print(f"[red]No lead with domain {domain!r}. Run `track.py list`.[/red]")
        return 1
    on = dt.date.fromisoformat(date) if date else dt.date.today()
    if status in ("fu1", "fu2"):
        if row["status"] != "sent":
            console.print(f"[red]{domain} is '{row['status']}', so there is no follow-up to record.[/red]")
            return 1
        conn.execute(f"UPDATE leads SET {status}_sent_at = ? WHERE domain = ?", (on.isoformat(), domain))
    elif status == "bounced":
        if row["status"] != "sent":
            console.print(f"[red]{domain} is '{row['status']}', so there is no sent email to have bounced.[/red]")
            return 1
        # It never arrived, so no follow-up is owed and it is not counted when replies are compared.
        conn.execute("UPDATE leads SET status = 'bounced', bounced_at = ? WHERE domain = ?", (on.isoformat(), domain))
    elif status == "sent":
        if row["blocked"]:
            console.print(f"[red]{domain} is blocked ({row['blocked'][:80]}). It cannot be marked sent.[/red]")
            return 1
        if on.weekday() >= 5:
            console.print(f"[red]{on.isoformat()} is a {on.strftime('%A')}. Nothing is sent on a weekend.[/red]")
            return 1
        conn.execute("UPDATE leads SET status='sent', sent_at=?, fu1_due=?, fu2_due=?, planned_send=NULL WHERE domain=?",
                     (on.isoformat(), due(on, FU1_DAYS), due(on, FU2_DAYS), domain))
        conn.execute("DELETE FROM plan WHERE domain = ?", (domain,))
    elif status == "drafted":
        # A send that was cancelled before it went out: forget its dates.
        conn.execute("UPDATE leads SET status='drafted', sent_at=NULL, fu1_due=NULL, fu2_due=NULL, fu1_sent_at=NULL, "
                     "fu2_sent_at=NULL, bounced_at=NULL WHERE domain=?", (domain,))
    else:
        conn.execute("UPDATE leads SET status=? WHERE domain=?", (status, domain))
    if note:
        conn.execute("UPDATE leads SET notes = trim(notes || char(10) || ?) WHERE domain = ?", (f"{today()}: {note}", domain))
    conn.commit()
    row = conn.execute("SELECT * FROM leads WHERE domain = ?", (domain,)).fetchone()
    console.print(f"[green]{domain}[/green] -> {row['status']}"
                  + (f"  (sent {row['sent_at']}, follow-ups due {row['fu1_due']} and {row['fu2_due']})" if status == "sent" else ""))
    if status == "bounced":
        bounce_check(conn, on.isoformat())
    return 0


def bounce_check(conn: sqlite3.Connection, day: str | None = None) -> bool:
    """Two bounces in one day mean the list is bad. Say so wherever the day's sends are shown."""
    day = day or today()
    count = conn.execute("SELECT COUNT(*) FROM leads WHERE bounced_at = ?", (day,)).fetchone()[0]
    if count >= BOUNCE_LIMIT:
        console.print(f"[bold red]STOP: {count} emails bounced on {day}. Send nothing more until the list is cleaned: "
                      "check every address still to be sent against the agency's own site.[/bold red]")
    return count >= BOUNCE_LIMIT


def show_bounces(conn: sqlite3.Connection) -> int:
    rows = conn.execute("SELECT * FROM leads WHERE bounced_at IS NOT NULL ORDER BY bounced_at, domain").fetchall()
    _table("Bounced", rows, [("Bounced on", "bounced_at"), ("Agency", "agency"), ("Email", "email"), ("Offer", "offer"), ("Sent", "sent_at")])
    stops = [bounce_check(conn, day) for day in sorted({row["bounced_at"] for row in rows})]
    return 1 if any(stops) else 0


def _table(title: str, rows: list[sqlite3.Row], columns: list[tuple[str, str]]) -> None:
    if not rows:
        console.print(f"[dim]{title}: none[/dim]")
        return
    table = Table(title=f"{title} ({len(rows)})", title_justify="left")
    for header, _ in columns:
        table.add_column(header, overflow="fold")
    for row in rows:
        table.add_row(*(str(row[key] if row[key] is not None else "") for _, key in columns))
    console.print(table)


def show_today(conn: sqlite3.Connection) -> int:
    now = today()
    weekend = dt.date.today().weekday() >= 5
    # The cap counts every message that leaves today: first emails and both follow-ups.
    new_today = conn.execute("SELECT COUNT(*) FROM leads WHERE sent_at = ?", (now,)).fetchone()[0]
    sent_today = new_today + conn.execute(
        "SELECT (SELECT COUNT(*) FROM leads WHERE fu1_sent_at = :d) + (SELECT COUNT(*) FROM leads WHERE fu2_sent_at = :d)",
        {"d": now}).fetchone()[0]
    fu1 = conn.execute("SELECT * FROM leads WHERE status='sent' AND fu1_sent_at IS NULL AND fu1_due <= ? ORDER BY fu1_due", (now,)).fetchall()
    fu2 = conn.execute("SELECT * FROM leads WHERE status='sent' AND fu1_sent_at IS NOT NULL AND fu2_sent_at IS NULL AND fu2_due <= ? ORDER BY fu2_due", (now,)).fetchall()
    # Follow-ups go first: they are owed to people already contacted. New sends get what is left.
    room = 0 if weekend else max(0, min(NEW_CAP - new_today, DAILY_CAP - sent_today - len(fu1) - len(fu2)))
    is_due = "status='drafted' AND blocked='' AND planned_send IS NOT NULL AND planned_send <= ?"
    to_send = conn.execute(f"SELECT * FROM leads WHERE {is_due} ORDER BY planned_send, score DESC LIMIT ?", (now, room)).fetchall()
    held = conn.execute(f"SELECT COUNT(*) FROM leads WHERE {is_due}", (now,)).fetchone()[0] - len(to_send)
    later = conn.execute("SELECT planned_send, COUNT(*) AS n FROM leads WHERE status='drafted' AND blocked='' AND planned_send > ? "
                         "GROUP BY planned_send ORDER BY planned_send", (now,)).fetchall()
    unplanned = conn.execute("SELECT * FROM leads WHERE status='drafted' AND blocked='' AND planned_send IS NULL ORDER BY tier, domain").fetchall()
    blocked = conn.execute("SELECT * FROM leads WHERE status='drafted' AND blocked<>'' ORDER BY tier, score DESC").fetchall()
    stale = conn.execute("SELECT * FROM leads WHERE status='sent' AND fu2_sent_at IS NOT NULL AND fu2_sent_at <= ?",
                         ((dt.date.today() - dt.timedelta(days=4)).isoformat(),)).fetchall()
    replies = conn.execute("SELECT * FROM leads WHERE status='replied' ORDER BY sent_at").fetchall()

    console.print(f"[bold]{now}[/bold]  sent today: {new_today}/{NEW_CAP} new, {sent_today}/{DAILY_CAP} in all")
    bounce_check(conn)
    if weekend:
        console.print("[yellow]Weekend: nothing is sent today. Follow-ups that fell on it are due Monday.[/yellow]")
    _table("Send today", to_send, [("Agency", "agency"), ("Offer", "offer"), ("Tier", "tier"), ("Channel", "channel"), ("To", "email"),
                                   ("Score", "score"), ("Planned", "planned_send"), ("Draft", "draft_path"),
                                   ("Pack", "pack_path")])
    if held:
        console.print(f"[yellow]{held} more are due but held over: today's room is used up by follow-ups and sends.[/yellow]")
    if later:
        console.print("[dim]Drafted for later: " + ", ".join(f"{row['planned_send']} ({row['n']})" for row in later) + "[/dim]")
    _table("Drafted with no send date", unplanned, [("Agency", "agency"), ("Tier", "tier"), ("Channel", "channel"), ("Draft", "draft_path")])
    _table("Blocked: do not send until resolved", blocked, [("Agency", "agency"), ("Tier", "tier"), ("Reason", "blocked"),
                                                            ("Draft", "draft_path")])
    _table("Follow-up 1 due", fu1, [("Agency", "agency"), ("Offer", "offer"), ("Email", "email"), ("Sent", "sent_at"), ("Due", "fu1_due"), ("Draft", "draft_path")])
    _table("Follow-up 2 due", fu2, [("Agency", "agency"), ("Offer", "offer"), ("Email", "email"), ("Sent", "sent_at"), ("Due", "fu2_due"), ("Draft", "draft_path")])
    _table("Replies waiting on you", replies, [("Agency", "agency"), ("Email", "email"), ("Sent", "sent_at"), ("Notes", "notes")])
    _table("No reply 4+ days after follow-up 2 (mark no_reply?)", stale, [("Agency", "agency"), ("Domain", "domain"), ("FU2 sent", "fu2_sent_at")])
    return 0


def show_list(conn: sqlite3.Connection) -> int:
    rows = conn.execute("SELECT * FROM leads ORDER BY status, tier, score DESC").fetchall()
    _table("All leads", rows, [("Domain", "domain"), ("Agency", "agency"), ("Offer", "offer"), ("Status", "status"), ("Tier", "tier"),
                               ("Channel", "channel"), ("Blocked", "blocked"), ("Planned", "planned_send"), ("Sent", "sent_at"),
                               ("FU1 due", "fu1_due"), ("FU2 due", "fu2_due")])
    show_rates(conn)
    return 0


def rates(conn: sqlite3.Connection) -> dict[str, dict]:
    """Replies per offer. A bounce never arrived, so it is left out of what the replies are measured against."""
    out = {}
    for offer in OFFERS:
        statuses = [row["status"] for row in conn.execute("SELECT status FROM leads WHERE offer = ? AND sent_at IS NOT NULL", (offer,))]
        bounced = statuses.count("bounced")
        replied = sum(status in ("replied", "won", "lost") for status in statuses)
        out[offer] = {"sent": len(statuses), "bounced": bounced, "replied": replied,
                      "rate": replied / (len(statuses) - bounced) if len(statuses) > bounced else None}
    return out


def show_rates(conn: sqlite3.Connection) -> None:
    table = Table(title="Replies by offer (replied, won or lost, out of the emails that arrived)", title_justify="left")
    for header in ("Offer", "Sent", "Bounced", "Replied", "Reply rate"):
        table.add_column(header, justify="left" if header == "Offer" else "right")
    for offer, n in rates(conn).items():
        if n["sent"]:
            table.add_row(offer, str(n["sent"]), str(n["bounced"]), str(n["replied"]), "-" if n["rate"] is None else f"{n['rate']:.0%}")
    if table.row_count:
        console.print(table)


def _section(text: str, prefix: str) -> str:
    parts = re.split(r"^## +(.+)$", text, flags=re.M)
    found = {parts[i].strip().lower(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}
    return next((v for k, v in found.items() if k.startswith(prefix)), "")


def pack_checked(domain: str, pack_dir=SCORED / "packs") -> str:
    """The oldest check among the ten businesses in an agency's pack, or '' if any has none on record.

    A follow-up offers the pack, so the pack has to be fit to send on the day the follow-up goes.
    """
    spec, pool = pack_dir / f"{domain}.pack.json", pack_dir / f"{domain}.candidates.json"
    if not (spec.exists() and pool.exists()):
        return ""
    keys = {prospect["key"] for prospect in json.loads(spec.read_text(encoding="utf-8"))["prospects"]}
    days = [cand.get("verified_on") or "" for cand in json.loads(pool.read_text(encoding="utf-8")) if cand["key"] in keys]
    return min(days) if len(days) == len(keys) and all(days) else ""


JOB_COLUMNS = ("n", "agency", "domain", "to", "subject", "body", "offer", "proof_type", "opener_quote", "evidence_url",
               "hiring", "hiring_url", "role", "role_status", "hiring_score", "names_the_role", "score", "tier")


def _subject(text: str) -> str:
    lines = [re.sub(r"^\s*\d+\.\s*", "", ln).strip() for ln in _section(text, "subject").splitlines() if ln.strip()]
    return lines[0] if lines else ""


def _body(text: str, section: str) -> str:
    return re.sub(r"<!--.*?-->", "", _section(text, section), flags=re.S).strip()


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def follow_ups_due(conn: sqlite3.Connection, date: str) -> list[tuple[int, sqlite3.Row]]:
    """Follow-ups to send on that day: those due on it, and any that are already overdue and have not gone.

    One that falls due on a day between today and that day is left to its own day's file. The second
    follow-up is listed once the first has gone, or was due on an earlier day.
    """
    days = {"day": date, "now": today()}
    owed = [(1, lead) for lead in conn.execute(
        "SELECT * FROM leads WHERE status = 'sent' AND fu1_sent_at IS NULL AND (fu1_due = :day OR fu1_due < :now) "
        "ORDER BY fu1_due, domain", days)]
    return owed + [(2, lead) for lead in conn.execute(
        "SELECT * FROM leads WHERE status = 'sent' AND fu2_sent_at IS NULL AND (fu2_due = :day OR fu2_due < :now) "
        "AND (fu1_sent_at IS NOT NULL OR fu1_due < :day) ORDER BY fu2_due, domain", days)]


def follow_up_file(day: dt.date, owed: list, total: str) -> str:
    pivot = job_wording().get("pivot", "") if JOB_WORDING.exists() else ""
    out = [f"# Follow-ups due: {day.strftime('%A %d %B %Y')}", "",
           f"{_plural(len(owed), 'follow-up')}. These go before any new email. Nothing here has been sent.", "", total, "",
           'Each one is a reply in the thread of the first email, so its subject is "Re:" and the subject that email went',
           "out with. The subject shown is the one recorded as sent (the draft's \"Sent subject\"), otherwise the first of",
           "the draft's subject lines; if you sent it under another, keep yours.", ""]
    for i, (number, lead) in enumerate(owed, 1):
        text = (ROOT / lead["draft_path"]).read_text(encoding="utf-8")
        body = _body(text, f"follow-up {number}")
        out += ["---", "", f"## {i}. Follow-up {number} to {lead['agency']} (first email sent {lead['sent_at']}, offer {lead['offer']})", "",
                f"**To:** {header_field(text, 'To')}", f"**Subject:** Re: {header_field(text, 'Sent subject') or _subject(text)}", "", "```text", body, "```", ""]
        if lead["offer"] == "lead_pack" and not (pivot and pivot in body):
            # Unless it has turned into the job ask, this follow-up offers the pack, so the pack has to be fit
            # to send on the day it goes.
            checked = pack_checked(lead["domain"])
            if not checked:
                out += ["The pack it offers has no verification date on record. Verify it before sending.", ""]
            elif (day - dt.date.fromisoformat(checked)).days > MAX_AGE_DAYS:
                out += [f"The pack it offers was last verified on {checked}, more than {MAX_AGE_DAYS} days before this date. "
                        "Run `verify.py` on it again before sending, in case a reply asks for it.", ""]
            else:
                out += [f"The pack it offers was last verified on {checked}.", ""]
    return "\n".join(out)


def pack_file(day: dt.date, rows: list, total: str, first: str) -> str:
    out = [f"# Ready to send: {day.strftime('%A %d %B %Y')}", "",
           f"{_plural(len(rows), 'lead-pack email')}, highest score first. Blocked drafts are left out. Nothing here has been sent.", "",
           total, *first, "",
           "For each new email: open the links under it and confirm what the line says, then paste the body into a",
           "plain-text email. If a link shows something different, do not send that email; say so and it gets rebuilt.", ""]
    for i, row in enumerate(rows, 1):
        text = (ROOT / row["draft_path"]).read_text(encoding="utf-8")
        out += ["---", "", f"## {i}. {row['agency']} (score {row['score']}, tier {row['tier']})", "",
                f"**To:** {header_field(text, 'To')}", f"**Subject:** {_subject(text)}", "", "```text", _body(text, "email 1"), "```", "",
                "**Open these to confirm each claim:**", "", _section(text, "check before sending").strip(), ""]
    return "\n".join(out)


def job_files(day: dt.date, rows: list, total: str, first: str) -> tuple[str, str]:
    """The day's job asks twice over: a page to read and check from, and the same fields as a CSV."""
    out = [f"# Job asks ready to send: {day.strftime('%A %d %B %Y')}", "",
           f"{_plural(len(rows), 'job-ask email')}. The best hiring score comes first, then the agency's own score. "
           "Nothing here has been sent.", "",
           total, *first, "",
           "For each: open the links under it and confirm the quoted words are on the page, then paste the body into a",
           "plain-text email with no attachment. If a page shows something different, do not send that email; say so",
           "and it gets rebuilt or dropped.", ""]
    table = io.StringIO()
    sheet = csv.DictWriter(table, fieldnames=JOB_COLUMNS, lineterminator="\n")
    sheet.writeheader()
    for i, row in enumerate(rows, 1):
        text = (ROOT / row["draft_path"]).read_text(encoding="utf-8")
        hiring, page = header_field(text, "Hiring"), header_field(text, "Careers page")
        record = {"n": i, "agency": row["agency"], "domain": row["domain"], "to": header_field(text, "To"),
                  "subject": _subject(text), "body": _body(text, "email 1"), "offer": row["offer"],
                  "proof_type": header_field(text, "Proof")[:1], "opener_quote": header_field(text, "Opener quote"),
                  "evidence_url": header_field(text, "Evidence"),
                  "hiring": "yes" if hiring.startswith("yes") else "talent_pool" if hiring.startswith("talent pool") else "no",
                  "hiring_url": page if page.startswith("http") else "", "role": hiring.partition(", ")[2],
                  "role_status": header_field(text, "Role status"), "hiring_score": header_field(text, "Hiring score"),
                  "names_the_role": header_field(text, "Names the role"), "score": row["score"], "tier": row["tier"]}
        sheet.writerow(record)
        out += ["---", "", f"## {i}. {row['agency']}", "",
                f"- **To:** {record['to']}", f"- **Subject:** {record['subject']}", f"- **Offer:** {record['offer']}",
                f"- **Proof type:** {header_field(text, 'Proof')}", f"- **Opener quote:** {record['opener_quote']}",
                f"- **Evidence URL:** {record['evidence_url']}",
                f"- **Hiring:** {hiring}" + (f" ({page})" if hiring != "no" else f" (careers page: {page})"),
                f"- **Role status:** {record['role_status']}, hiring score {record['hiring_score'] or 0}",
                f"- **Opener names the role:** {record['names_the_role']}",
                f"- **Score:** {row['score']}, tier {row['tier']}",
                # Anything the draft flags for the person sending it, such as a careers page worth a second look.
                *(f"- **Note:** {line[2:]}" for line in text.split("\n## ", 1)[0].splitlines()
                  if line.startswith("- ") and not line.startswith("- **")),
                "", "```text", record["body"], "```", "",
                "**Open these to confirm:**", "", _section(text, "check before sending").strip(), ""]
    return "\n".join(out), table.getvalue()


def ready(conn: sqlite3.Connection, date: str) -> int:
    """Write the day's files: the follow-ups due, the lead-pack emails, and the job asks (as .md and .csv)."""
    day = dt.date.fromisoformat(date)
    rows = conn.execute("SELECT * FROM leads WHERE status = 'drafted' AND blocked = '' AND planned_send = ? "
                        "ORDER BY score DESC, domain", (date,)).fetchall()
    packs = [row for row in rows if row["offer"] != "job_ask"]
    jobs = sorted((row for row in rows if row["offer"] == "job_ask"), key=lambda r: (job_rank(r), -(r["score"] or 0), r["domain"]))
    owed = follow_ups_due(conn, date)
    if not rows and not owed:
        console.print(f"[yellow]No unblocked drafts are planned for {date} and no follow-up is due. "
                      f"Run `track.py plan {date}` first.[/yellow]")
        return 1
    count = len(owed) + len(rows)
    total = (f"The day in all: {_plural(len(owed), 'follow-up')}, {_plural(len(packs), 'lead-pack email')} and "
             f"{_plural(len(jobs), 'job ask')}. That is {count} of the {DAILY_CAP} messages a day allows, and "
             f"{len(rows)} of the {NEW_CAP} new ones." + (" THIS IS OVER THE CAP: hold the lowest-ranked back." if
                                                          count > DAILY_CAP or len(rows) > NEW_CAP else ""))
    first = [f"{_plural(len(owed), 'follow-up')} due that day: send {'it' if len(owed) == 1 else 'them'} first. "
             f"See `{date}-followups.md`."] if owed else []
    job_md, job_csv = job_files(day, jobs, total, first) if jobs else (None, None)
    files = {"-followups.md": follow_up_file(day, owed, total) if owed else None,
             ".md": pack_file(day, packs, total, first) if packs else None, "-jobs.md": job_md, "-jobs.csv": job_csv}
    READY.mkdir(parents=True, exist_ok=True)
    for suffix, content in files.items():
        path = READY / f"{date}{suffix}"
        if content is None:
            if path.exists():
                path.unlink()  # written by an earlier run; nothing of that kind is due on this day any more
                console.print(f"[yellow]removed {path.relative_to(ROOT).as_posix()}: nothing of that kind is due on {date} now[/yellow]")
            continue
        # The CSV carries a byte-order mark so a spreadsheet opens its accents and Arabic correctly.
        path.write_text(content, encoding="utf-8-sig" if suffix.endswith(".csv") else "utf-8", newline="" if suffix.endswith(".csv") else None)
        console.print(f"[bold]ready[/bold] wrote {path.relative_to(ROOT).as_posix()}")
    console.print(f"[bold]ready[/bold] {date}: {_plural(len(owed), 'follow-up')}, {_plural(len(packs), 'lead-pack email')}, "
                  f"{_plural(len(jobs), 'job ask')}")
    bounce_check(conn)
    return 0


def main() -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync", help="add agencies that have a pack and a draft")
    sub.add_parser("today", help="what to do today")
    sub.add_parser("list", help="every lead and its status")
    p_mark = sub.add_parser("mark", help="record a status change")
    p_mark.add_argument("domain")
    p_mark.add_argument("status", choices=STATUSES + ("fu1", "fu2"))
    p_mark.add_argument("--note", default="")
    p_mark.add_argument("--date", help="YYYY-MM-DD the message goes out, if not today (an email scheduled ahead)")
    p_plan = sub.add_parser("plan", help="schedule every unsent lead from a date on, or show the plan")
    p_plan.add_argument("date", nargs="?", help="YYYY-MM-DD to schedule from; omit to only show the plan")
    p_plan.add_argument("--keep", action="store_true", help="leave leads that already have a date where they are")
    sub.add_parser("bounces", help="bounced emails by day; warns when a day has two or more")
    p_find = sub.add_parser("discover", help="find companies by what their careers pages list (hiring.py)")
    p_find.add_argument("--by-hiring", action="store_true", required=True, help="the only way of discovering this command has")
    p_find.add_argument("--region", default="gulf", help="a region in config/regions/")
    p_ready = sub.add_parser("ready", help="write one day's follow-ups, lead-pack emails and job asks to outreach/ready/")
    p_ready.add_argument("date", help="YYYY-MM-DD")
    args = ap.parse_args()

    if args.cmd == "discover":
        import hiring
        return hiring.discover(args.region)
    conn = connect()
    try:
        if args.cmd == "sync":
            return sync(conn)
        if args.cmd == "plan":
            return plan(conn, args.date, args.keep)
        if args.cmd == "bounces":
            return show_bounces(conn)
        if args.cmd == "ready":
            return ready(conn, args.date)
        if args.cmd == "today":
            return show_today(conn)
        if args.cmd == "list":
            return show_list(conn)
        return mark(conn, args.domain, args.status, args.note, args.date)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
