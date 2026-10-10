"""Check outreach drafts against the house rules before anything is sent by hand.

    python src/lint_drafts.py

Rules: subjects of 6 words or fewer; email 1 at 120 words or fewer with no links, the fixed
call-to-action and a {{NAME}} sign-off; follow-ups at 50 and 40 words; a LinkedIn note of 280
characters or fewer; an evidence comment under email 1; and none of the banned phrases.
"""
from __future__ import annotations

import re
import sys

from rich.console import Console

from common import DRAFTS, utf8_stdout

BANNED = ["i hope this finds you well", "i hope this email finds you", "i came across your profile",
          "synergy", "quick question", "touching base", "circle back", "game-changer", "game changer"]
CTA = "Want the other 7? Just reply yes."
console = Console()


def sections(text: str) -> dict[str, str]:
    parts = re.split(r"^## +(.+)$", text, flags=re.M)
    return {parts[i].strip().lower(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def body(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S).strip()


def words(text: str) -> int:
    return len(re.findall(r"[\w'’{}$%-]+", text))


def lint(text: str) -> list[str]:
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
        if "{{NAME}}" not in plain:
            problems.append("email 1 has no {{NAME}} sign-off")
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
    return problems


def main() -> int:
    utf8_stdout()
    drafts = sorted(DRAFTS.glob("*.md"))
    failed = 0
    for path in drafts:
        problems = lint(path.read_text(encoding="utf-8"))
        if problems:
            failed += 1
            console.print(f"[red]FAIL[/red] {path.name}")
            for problem in problems:
                console.print(f"   - {problem}")
        else:
            console.print(f"[green]ok[/green]   {path.name}")
    console.print(f"{len(drafts) - failed}/{len(drafts)} drafts pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
