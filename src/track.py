"""Outreach tracker: who to email today, which follow-ups are due, who has replied.

    python src/track.py sync                      # pick up every drafted lead (Gulf packs and the US track)
    python src/track.py today                     # today's sends (max 15), follow-ups due, replies waiting
    python src/track.py mark <domain> sent        # sets the day-3 and day-7 follow-up dates
    python src/track.py mark <domain> fu1         # follow-up 1 went out (fu2 likewise)
    python src/track.py mark <domain> replied --note "wants the other 7"
    python src/track.py list

Nothing here sends anything. It only records what you did by hand.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
import sys

from rich.console import Console
from rich.table import Table

from common import DATA, DRAFTS, PACKS, ROOT, SCORED, US_TRACK, utf8_stdout

DB = DATA / "tracker.db"
STATUSES = ("drafted", "sent", "replied", "won", "lost", "no_reply")
DAILY_CAP = 15
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
    blocked     TEXT NOT NULL DEFAULT ''
);
"""
# Columns added after the first release, for databases created before them.
MIGRATIONS = {"channel": "TEXT NOT NULL DEFAULT 'email'", "blocked": "TEXT NOT NULL DEFAULT ''"}


def connect() -> sqlite3.Connection:
    DATA.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    have = {row["name"] for row in conn.execute("PRAGMA table_info(leads)")}
    for column, ddl in MIGRATIONS.items():
        if column not in have:
            conn.execute(f"ALTER TABLE leads ADD COLUMN {column} {ddl}")
    return conn


def today() -> str:
    return dt.date.today().isoformat()


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
        pack = PACKS / f"{domain}.html"
        scored = SCORED / f"{domain}.json"
        if not pack.exists() or not scored.exists():
            console.print(f"[yellow]skip {domain}: needs a pack and a scored record as well as a draft[/yellow]")
            continue
        rec = json.loads(scored.read_text(encoding="utf-8"))
        cur = conn.execute(
            "INSERT OR IGNORE INTO leads (domain, agency, email, tier, score, pack_path, draft_path) VALUES (?,?,?,?,?,?,?)",
            (domain, rec["agency"], rec.get("contact_email", "unknown"), rec["tier"], rec["score"],
             pack.relative_to(ROOT).as_posix(), draft.relative_to(ROOT).as_posix()))
        added += cur.rowcount
        conn.execute("UPDATE leads SET blocked = ? WHERE domain = ?",
                     (blocked_reason(draft.read_text(encoding="utf-8")), domain))
    conn.commit()
    console.print(f"[bold]sync[/bold] added={added}, total={conn.execute('SELECT COUNT(*) FROM leads').fetchone()[0]}")
    return 0


def mark(conn: sqlite3.Connection, domain: str, status: str, note: str) -> int:
    row = conn.execute("SELECT * FROM leads WHERE domain = ?", (domain,)).fetchone()
    if row is None:
        console.print(f"[red]No lead with domain {domain!r}. Run `track.py list`.[/red]")
        return 1
    now = today()
    if status in ("fu1", "fu2"):
        if row["status"] != "sent":
            console.print(f"[red]{domain} is '{row['status']}', so there is no follow-up to record.[/red]")
            return 1
        conn.execute(f"UPDATE leads SET {status}_sent_at = ? WHERE domain = ?", (now, domain))
    elif status == "sent":
        sent = dt.date.today()
        conn.execute("UPDATE leads SET status='sent', sent_at=?, fu1_due=?, fu2_due=? WHERE domain=?",
                     (now, (sent + dt.timedelta(days=FU1_DAYS)).isoformat(),
                      (sent + dt.timedelta(days=FU2_DAYS)).isoformat(), domain))
    else:
        conn.execute("UPDATE leads SET status=? WHERE domain=?", (status, domain))
    if note:
        conn.execute("UPDATE leads SET notes = trim(notes || char(10) || ?) WHERE domain = ?", (f"{now}: {note}", domain))
    conn.commit()
    row = conn.execute("SELECT * FROM leads WHERE domain = ?", (domain,)).fetchone()
    console.print(f"[green]{domain}[/green] -> {row['status']}"
                  + (f"  (follow-ups due {row['fu1_due']} and {row['fu2_due']})" if status == "sent" else ""))
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
    sent_today = conn.execute("SELECT COUNT(*) FROM leads WHERE sent_at = ?", (now,)).fetchone()[0]
    room = max(0, DAILY_CAP - sent_today)
    to_send = conn.execute(
        "SELECT * FROM leads WHERE status='drafted' AND blocked='' ORDER BY tier, score DESC LIMIT ?", (room,)).fetchall()
    blocked = conn.execute("SELECT * FROM leads WHERE status='drafted' AND blocked<>'' ORDER BY tier, domain").fetchall()
    fu1 = conn.execute("SELECT * FROM leads WHERE status='sent' AND fu1_sent_at IS NULL AND fu1_due <= ? ORDER BY fu1_due", (now,)).fetchall()
    fu2 = conn.execute("SELECT * FROM leads WHERE status='sent' AND fu1_sent_at IS NOT NULL AND fu2_sent_at IS NULL AND fu2_due <= ? ORDER BY fu2_due", (now,)).fetchall()
    stale = conn.execute("SELECT * FROM leads WHERE status='sent' AND fu2_sent_at IS NOT NULL AND fu2_sent_at <= ?",
                         ((dt.date.today() - dt.timedelta(days=4)).isoformat(),)).fetchall()
    replies = conn.execute("SELECT * FROM leads WHERE status='replied' ORDER BY sent_at").fetchall()

    console.print(f"[bold]{now}[/bold]  sent today: {sent_today}/{DAILY_CAP}")
    _table("Send today", to_send, [("Agency", "agency"), ("Tier", "tier"), ("Channel", "channel"), ("To", "email"),
                                   ("Score", "score"), ("Draft", "draft_path"), ("Pack", "pack_path")])
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
                               ("Channel", "channel"), ("Blocked", "blocked"), ("Sent", "sent_at"),
                               ("FU1 due", "fu1_due"), ("FU2 due", "fu2_due")])
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
    args = ap.parse_args()

    conn = connect()
    try:
        if args.cmd == "sync":
            return sync(conn)
        if args.cmd == "today":
            return show_today(conn)
        if args.cmd == "list":
            return show_list(conn)
        return mark(conn, args.domain, args.status, args.note)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
