"""Check outreach drafts against the house rules before anything is sent by hand.

    python src/lint_drafts.py                    # every draft in outreach/
    python src/lint_drafts.py <file.md> ...      # just these files, checked as Gulf drafts

Rules for outreach/drafts: subjects of 6 words or fewer; email 1 at 120 words or fewer with no
links, the fixed call-to-action and a {{NAME}} sign-off; follow-ups at 50 and 40 words; a LinkedIn
note of 280 characters or fewer; an evidence comment under email 1; none of the banned phrases; and
none of the retired signal wording from signals.py (no booking, no WhatsApp, no chat, no social
profiles and the rest), anywhere in the file. A draft whose header says "Status: BLOCKED" holds no
email and is reported as blocked, not checked.

Rules for outreach/us_track: a contact-form message of 90 words or fewer with no links, the fixed
LeadForge sentence, a fixed-price offer and the fixed call-to-action; a source URL for the hook, or
a header that says no specific hook was found; a LinkedIn note of 280 characters or fewer.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from dotenv import dotenv_values
from rich.console import Console

import signals
from common import DRAFTS, ROOT, US_TRACK, utf8_stdout

BANNED = ["i hope this finds you well", "i hope this email finds you", "i came across your profile",
          "synergy", "quick question", "touching base", "circle back", "game-changer", "game changer"]
CTA = "Want the other 7? Just reply yes."
US_MESSAGE_MAX = 90
US_PROOF = ("I build scraping, data and automation pipelines. My own tool, LeadForge, discovered 325 agencies "
            "across the UAE, KSA and Qatar and scored the best 70 using evidence from their own sites.")
US_CTA = "Is there a piece of a current project I could take off your plate?"
# A draft is signed either with the placeholder or, once `pack.py fill` has run, with the real name.
SIGN_OFFS = [s for s in ("{{NAME}}", (dotenv_values(ROOT / ".env").get("LEADFORGE_NAME") or "").strip()) if s]
console = Console()


def sections(text: str) -> dict[str, str]:
    parts = re.split(r"^## +(.+)$", text, flags=re.M)
    return {parts[i].strip().lower(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def body(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S).strip()


def words(text: str) -> int:
    return len(re.findall(r"[\w'’{}$%-]+", text))


def is_blocked(text: str) -> bool:
    return bool(re.search(r"^- \*\*Status:\*\* *BLOCKED", text.split("\n## ", 1)[0], flags=re.M))


def lint(text: str) -> list[str]:
    if is_blocked(text):
        return []  # nothing to send, so nothing to check
    problems = []
    secs = sections(text)

    def find(prefix: str) -> str | None:
        return next((v for k, v in secs.items() if k.startswith(prefix)), None)

    subjects = find("subject")
    lines = [re.sub(r"^\s*(?:\d+\.|[-*])\s*", "", ln).strip() for ln in (subjects or "").splitlines() if ln.strip()]
    if len(lines) != 3:
        problems.append(f"needs exactly 3 subject lines, found {len(lines)}")
    for line in lines:
        if words(line) > 6:
            problems.append(f"subject over 6 words: {line!r}")

    email = find("email 1")
    if email is None:
        problems.append("missing 'Email 1' section")
    else:
        plain = body(email)
        if words(plain) > 120:
            problems.append(f"email 1 is {words(plain)} words (max 120)")
        if re.search(r"https?://|www\.", plain):
            problems.append("email 1 contains a link")
        if CTA not in plain:
            problems.append(f"email 1 is missing the call-to-action: {CTA!r}")
        if not any(name in plain for name in SIGN_OFFS):
            problems.append("email 1 has no sign-off ({{NAME}}, or the name set in .env)")
        if not re.search(r"<!--.*?https?://.*?-->", email, flags=re.S):
            problems.append("email 1 has no evidence comment with a source URL")

    for prefix, cap in (("follow-up 1", 50), ("follow-up 2", 40)):
        section = find(prefix)
        if section is None:
            problems.append(f"missing '{prefix}' section")
        elif words(body(section)) > cap:
            problems.append(f"{prefix} is {words(body(section))} words (max {cap})")

    note = find("linkedin")
    if note is None:
        problems.append("missing LinkedIn note")
    elif len(body(note)) > 280:
        problems.append(f"LinkedIn note is {len(body(note))} characters (max 280)")

    lowered = body(text).lower()
    problems += [f"banned phrase: {phrase!r}" for phrase in BANNED if phrase in lowered]
    # Checked over the whole file, comments included: a retired signal has no business in the notes either.
    problems += [f"retired signal wording: {name}" for name in signals.retired_in(text)]
    return problems


def lint_us(text: str) -> list[str]:
    """US track: one contact-form message and one LinkedIn note per agency."""
    problems = []
    secs = sections(text)
    header = text.split("\n## ", 1)[0]

    def find(prefix: str) -> str | None:
        return next((v for k, v in secs.items() if k.startswith(prefix)), None)

    for field in ("Agency", "Channel", "To", "Hook"):
        if not re.search(rf"^- \*\*{field}:\*\* *\S", header, flags=re.M):
            problems.append(f"header is missing '- **{field}:**'")
    channel = re.search(r"^- \*\*Channel:\*\* *(\w+)", header, flags=re.M)
    if channel and channel.group(1).lower() not in ("form", "email"):
        problems.append(f"channel must be form or email, got {channel.group(1)!r}")

    message = find("contact form message")
    if message is None:
        problems.append("missing 'Contact form message' section")
    else:
        plain = body(message)
        if words(plain) > US_MESSAGE_MAX:
            problems.append(f"message is {words(plain)} words (max {US_MESSAGE_MAX})")
        if re.search(r"https?://|www\.", plain):
            problems.append("message contains a link")
        for required, label in ((US_PROOF, "the LeadForge sentence"), (US_CTA, "the call-to-action")):
            if required not in " ".join(plain.split()):
                problems.append(f"message is missing {label}: {required!r}")
        if "fixed price" not in plain or "accept" not in plain:
            problems.append("message must offer one scoped task at a fixed price, paid only once accepted")
        # The hook needs a source, unless the header says plainly that none was found.
        has_source = re.search(r"<!--.*?https?://.*?-->", message, flags=re.S)
        if not has_source and "no specific hook" not in header.lower():
            problems.append("no evidence comment with a source URL, and the header does not say 'No specific hook found'")

    note = find("linkedin")
    if note is None:
        problems.append("missing LinkedIn note")
    elif len(body(note)) > 280:
        problems.append(f"LinkedIn note is {len(body(note))} characters (max 280)")

    lowered = body(text).lower()
    problems += [f"banned phrase: {phrase!r}" for phrase in BANNED if phrase in lowered]
    return problems


def main() -> int:
    utf8_stdout()
    failed = total = blocked = 0
    named = [Path(arg) for arg in sys.argv[1:]]
    jobs = ([(path, lint, path.as_posix()) for path in named] if named else
            [(path, check, f"{folder.name}/{path.name}")
             for folder, check in ((DRAFTS, lint), (US_TRACK, lint_us)) for path in sorted(folder.glob("*.md"))])
    for path, check, label in jobs:
        total += 1
        text = path.read_text(encoding="utf-8")
        problems = check(text)
        if is_blocked(text):
            blocked += 1
            console.print(f"[yellow]blocked[/yellow] {label}")
        elif problems:
            failed += 1
            console.print(f"[red]FAIL[/red] {label}")
            for problem in problems:
                console.print(f"   - {problem}")
        else:
            console.print(f"[green]ok[/green]   {label}")
    console.print(f"{total - failed - blocked}/{total} drafts pass, {blocked} blocked")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
