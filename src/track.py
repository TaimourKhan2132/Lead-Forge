"""Outreach tracker: who to email today, which follow-ups are due, who has replied.

    python src/track.py sync                      # pick up every drafted lead (Gulf packs and the US track)
    python src/track.py plan 2026-10-13           # schedule every unsent lead from that day on, best score first
    python src/track.py plan                      # show the plan and each day's load against the caps
    python src/track.py ready 2026-10-13          # write that day's emails to outreach/ready/2026-10-13.md
    python src/track.py today                     # follow-ups due first, then new sends
    python src/track.py mark <domain> sent        # sets the day-3 and day-7 follow-up dates
    python src/track.py mark <domain> sent --date 2026-10-12     # for an email scheduled ahead in the mail client
    python src/track.py mark <domain> drafted     # a send was cancelled: clear its dates
    python src/track.py mark <domain> fu1         # follow-up 1 went out (fu2 likewise)
    python src/track.py mark <domain> replied --note "wants the other 7"
    python src/track.py list

Send rules, enforced by `plan` and `today`: at most 10 new emails a day and 15 messages a day counting
follow-ups; follow-ups go first; nothing is sent on Saturday or Sunday; a follow-up that lands on a
weekend moves to Monday; follow-ups are due on day 3 and day 7.

Nothing here sends anything. It only records what you did by hand.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sqlite3
import sys
from collections import Counter

from rich.console import Console
from rich.table import Table

from common import DATA, DRAFTS, PACKS, ROOT, SCORED, US_TRACK, utf8_stdout

DB = DATA / "tracker.db"
READY = ROOT / "outreach" / "ready"
STATUSES = ("drafted", "sent", "replied", "won", "lost", "no_reply")
NEW_CAP = 10    # first emails in a day
DAILY_CAP = 15  # first emails and follow-ups together
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
                CHECK (status IN ('drafted','sent','replied','won','lost','no_reply')),
    sent_at     TEXT,
    fu1_due     TEXT,
    fu2_due     TEXT,
    fu1_sent_at TEXT,
    fu2_sent_at TEXT,
    notes       TEXT NOT NULL DEFAULT '',
    channel     TEXT NOT NULL DEFAULT 'email',
    blocked     TEXT NOT NULL DEFAULT '',
    planned_send TEXT
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
MIGRATIONS = {"channel": "TEXT NOT NULL DEFAULT 'email'", "blocked": "TEXT NOT NULL DEFAULT ''",
              "planned_send": "TEXT"}
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
            "INSERT OR IGNORE INTO leads (domain, agency, email, tier, draft_path, channel) VALUES (?,?,?,?,?,?)",
            (draft.stem, header_field(text, "Agency") or draft.stem, header_field(text, "To"), "US",
             draft.relative_to(ROOT).as_posix(), channel))
        added += cur.rowcount
        conn.execute("UPDATE leads SET blocked = ?, channel = ?, email = ? WHERE domain = ?",
                     (blocked_reason(text), channel, header_field(text, "To"), draft.stem))
    for draft in sorted(DRAFTS.glob("*.md")):
        domain = draft.stem
        text = draft.read_text(encoding="utf-8")
        blocked = blocked_reason(text)
        pack = PACKS / f"{domain}.html"
        scored = SCORED / f"{domain}.json"
        # A blocked draft has no pack to send, so it is tracked without one.
        if not scored.exists() or not (pack.exists() or blocked):
            console.print(f"[yellow]skip {domain}: needs a pack and a scored record as well as a draft[/yellow]")
            continue
        rec = json.loads(scored.read_text(encoding="utf-8"))
        pack_path = pack.relative_to(ROOT).as_posix() if pack.exists() else None
        cur = conn.execute(
            "INSERT OR IGNORE INTO leads (domain, agency, email, tier, score, pack_path, draft_path) VALUES (?,?,?,?,?,?,?)",
            (domain, rec["agency"], rec.get("contact_email", "unknown"), rec["tier"], rec["score"],
             pack_path, draft.relative_to(ROOT).as_posix()))
        added += cur.rowcount
        conn.execute("UPDATE leads SET blocked = ?, pack_path = ? WHERE domain = ?", (blocked, pack_path, domain))
    # A blocked lead has no send date until it is unblocked and the plan is run again.
    conn.execute("DELETE FROM plan WHERE domain IN (SELECT domain FROM leads WHERE blocked <> '' OR status <> 'drafted')")
    conn.execute("UPDATE leads SET planned_send = (SELECT planned_send FROM plan WHERE plan.domain = leads.domain)")
    conn.commit()
    blocked_n = conn.execute("SELECT COUNT(*) FROM leads WHERE blocked <> ''").fetchone()[0]
    console.print(f"[bold]sync[/bold] added={added}, total={conn.execute('SELECT COUNT(*) FROM leads').fetchone()[0]}, blocked={blocked_n}")
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


def plan(conn: sqlite3.Connection, date: str | None) -> int:
    """Give every unsent lead a send date from `date` on, best score first, inside the send rules.

    A day takes a new email only if it has fewer than 10 already, the day's total stays within 15,
    and the two follow-ups that email will need still fit on their own days. Follow-ups are never
    pushed out to make room for a new email.
    """
    if date:
        start = workday(dt.date.fromisoformat(date))
        built = conn.execute("SELECT domain, agency, tier, score FROM leads WHERE status = 'drafted' AND blocked = '' "
                             "AND tier <> 'US' ORDER BY score DESC, domain").fetchall()
        known = {row["domain"] for row in conn.execute("SELECT domain FROM leads")}
        with (SCORED / "summary.csv").open(encoding="utf-8", newline="") as fh:
            ranked = list(csv.DictReader(fh))  # already sorted best first by qualify.py
        skip = skipped_domains()
        unbuilt = [r for r in ranked if r["domain"] not in known and r["domain"] not in skip and int(r["score"]) >= MIN_PLAN_SCORE]
        # Agencies with a pack and a draft go first; the rest follow by score and get built a day ahead.
        queue = [(r["domain"], r["agency"], r["tier"], int(r["score"])) for r in [*built, *unbuilt]]
        owed, new, day = owed_follow_ups(conn), Counter(), start
        # An email already scheduled in the mail client for one of these days has taken one of its places.
        for row in conn.execute("SELECT sent_at FROM leads WHERE status = 'sent' AND sent_at >= ?", (start.isoformat(),)):
            new[row["sent_at"]] += 1
        conn.execute("DELETE FROM plan")
        for domain, agency, tier, score in queue:
            while True:
                key, fu1, fu2 = day.isoformat(), due(day, FU1_DAYS), due(day, FU2_DAYS)
                if new[key] < NEW_CAP and new[key] + owed[key] < DAILY_CAP and owed[fu1] < DAILY_CAP and owed[fu2] < DAILY_CAP:
                    break
                day = workday(day + dt.timedelta(days=1))
            conn.execute("INSERT INTO plan (domain, agency, tier, score, planned_send) VALUES (?,?,?,?,?)",
                         (domain, agency, tier, score, key))
            new[key] += 1
            owed[fu1] += 1
            owed[fu2] += 1
        conn.execute("UPDATE leads SET planned_send = (SELECT planned_send FROM plan WHERE plan.domain = leads.domain)")
        conn.commit()
        console.print(f"[bold]plan[/bold] {len(queue)} agencies scheduled from {start.isoformat()} "
                      f"({len(built)} with a pack and draft, {len(unbuilt)} still to build)")

    rows = conn.execute(
        "SELECT plan.*, leads.status AS status, leads.draft_path AS draft, leads.blocked AS blocked "
        "FROM plan LEFT JOIN leads ON leads.domain = plan.domain ORDER BY planned_send, score DESC").fetchall()
    table = Table(title=f"Send plan ({len(rows)})", title_justify="left")
    for header in ("Send date", "Day", "Agency", "Tier", "Score", "State"):
        table.add_column(header)
    for row in rows:
        state = "pack and draft not built yet" if row["draft"] is None else (row["blocked"] or row["status"])
        table.add_row(row["planned_send"], dt.date.fromisoformat(row["planned_send"]).strftime("%a"), row["agency"],
                      row["tier"] or "", str(row["score"]), state)
    console.print(table)
    show_load(conn)
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
                     "fu2_sent_at=NULL WHERE domain=?", (domain,))
    else:
        conn.execute("UPDATE leads SET status=? WHERE domain=?", (status, domain))
    if note:
        conn.execute("UPDATE leads SET notes = trim(notes || char(10) || ?) WHERE domain = ?", (f"{today()}: {note}", domain))
    conn.commit()
    row = conn.execute("SELECT * FROM leads WHERE domain = ?", (domain,)).fetchone()
    console.print(f"[green]{domain}[/green] -> {row['status']}"
                  + (f"  (sent {row['sent_at']}, follow-ups due {row['fu1_due']} and {row['fu2_due']})" if status == "sent" else ""))
    return 0


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
    if weekend:
        console.print("[yellow]Weekend: nothing is sent today. Follow-ups that fell on it are due Monday.[/yellow]")
    _table("Send today", to_send, [("Agency", "agency"), ("Tier", "tier"), ("Channel", "channel"), ("To", "email"),
                                   ("Score", "score"), ("Planned", "planned_send"), ("Draft", "draft_path"),
                                   ("Pack", "pack_path")])
    if held:
        console.print(f"[yellow]{held} more are due but held over: today's room is used up by follow-ups and sends.[/yellow]")
    if later:
        console.print("[dim]Drafted for later: " + ", ".join(f"{row['planned_send']} ({row['n']})" for row in later) + "[/dim]")
    _table("Drafted with no send date", unplanned, [("Agency", "agency"), ("Tier", "tier"), ("Channel", "channel"), ("Draft", "draft_path")])
    _table("Blocked: do not send until resolved", blocked, [("Agency", "agency"), ("Tier", "tier"), ("Reason", "blocked"),
                                                            ("Draft", "draft_path")])
    _table("Follow-up 1 due", fu1, [("Agency", "agency"), ("Email", "email"), ("Sent", "sent_at"), ("Due", "fu1_due"), ("Draft", "draft_path")])
    _table("Follow-up 2 due", fu2, [("Agency", "agency"), ("Email", "email"), ("Sent", "sent_at"), ("Due", "fu2_due"), ("Draft", "draft_path")])
    _table("Replies waiting on you", replies, [("Agency", "agency"), ("Email", "email"), ("Sent", "sent_at"), ("Notes", "notes")])
    _table("No reply 4+ days after follow-up 2 (mark no_reply?)", stale, [("Agency", "agency"), ("Domain", "domain"), ("FU2 sent", "fu2_sent_at")])
    return 0


def show_list(conn: sqlite3.Connection) -> int:
    rows = conn.execute("SELECT * FROM leads ORDER BY status, tier, score DESC").fetchall()
    _table("All leads", rows, [("Domain", "domain"), ("Agency", "agency"), ("Status", "status"), ("Tier", "tier"),
                               ("Channel", "channel"), ("Blocked", "blocked"), ("Planned", "planned_send"), ("Sent", "sent_at"),
                               ("FU1 due", "fu1_due"), ("FU2 due", "fu2_due")])
    return 0


def _section(text: str, prefix: str) -> str:
    parts = re.split(r"^## +(.+)$", text, flags=re.M)
    found = {parts[i].strip().lower(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}
    return next((v for k, v in found.items() if k.startswith(prefix)), "")


def ready(conn: sqlite3.Connection, date: str) -> int:
    """Write the day's emails to one file: who to, the subject, the body, and what to open to check it."""
    day = dt.date.fromisoformat(date)
    rows = conn.execute("SELECT * FROM leads WHERE status = 'drafted' AND blocked = '' AND planned_send = ? "
                        "ORDER BY score DESC, domain", (date,)).fetchall()
    if not rows:
        console.print(f"[yellow]No unblocked drafts are planned for {date}. Run `track.py plan {date}` first.[/yellow]")
        return 1
    out = [f"# Ready to send: {day.strftime('%A %d %B %Y')}", "",
           f"{len(rows)} emails, highest score first. Blocked drafts are left out. Nothing here has been sent.", "",
           "For each one: open the links under it and confirm what the line says, then paste the body into a",
           "plain-text email. If a link shows something different, do not send that email; say so and it gets rebuilt.", ""]
    for i, row in enumerate(rows, 1):
        text = (ROOT / row["draft_path"]).read_text(encoding="utf-8")
        subjects = [re.sub(r"^\s*\d+\.\s*", "", ln).strip() for ln in _section(text, "subject").splitlines() if ln.strip()]
        body = re.sub(r"<!--.*?-->", "", _section(text, "email 1"), flags=re.S).strip()
        checks = _section(text, "check before sending").strip()
        out += ["---", "", f"## {i}. {row['agency']} (score {row['score']}, tier {row['tier']})", "",
                f"**To:** {header_field(text, 'To')}", f"**Subject:** {subjects[0]}", "", "```text", body, "```", "",
                "**Open these to confirm each claim:**", "", checks, ""]
    READY.mkdir(parents=True, exist_ok=True)
    path = READY / f"{date}.md"
    path.write_text("\n".join(out), encoding="utf-8")
    console.print(f"[bold]ready[/bold] wrote {path.relative_to(ROOT).as_posix()} with {len(rows)} emails")
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
    p_ready = sub.add_parser("ready", help="write one day's emails, with the links to check, to outreach/ready/")
    p_ready.add_argument("date", help="YYYY-MM-DD")
    args = ap.parse_args()

    conn = connect()
    try:
        if args.cmd == "sync":
            return sync(conn)
        if args.cmd == "plan":
            return plan(conn, args.date)
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
