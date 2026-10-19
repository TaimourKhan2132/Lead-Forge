"""Check outreach drafts against the house rules before anything is sent by hand.

    python src/lint_drafts.py                    # every draft in outreach/
    python src/lint_drafts.py <file.md> ...      # just these files, checked as Gulf drafts

Rules for outreach/drafts: subjects of 6 words or fewer; email 1 at 120 words or fewer with no
links, the fixed call-to-action and a {{NAME}} sign-off; follow-ups at 70 and 40 words; a LinkedIn
note of 280 characters or fewer; an evidence comment under email 1; none of the banned phrases; and
none of the retired signal wording from signals.py (no booking, no WhatsApp, no chat, no social
profiles and the rest), anywhere in the file. A draft whose header says "Status: BLOCKED" holds no
email and is reported as blocked, not checked.

A follow-up has to add something, so the reminders that add nothing are banned everywhere: "just
following up", "circling back", "bumping this", "checking in".

Rules for outreach/jobs (the job ask): the header names the offer, the proof type, whether the agency
is hiring and the quoted evidence for the opener; one subject line; email 1 carries the operator's
pitch, exactly one proof line (the one the header names), the trial question, the link to the work
and the P.S., word for word from outreach/job_ask.json, and no other link; the opener is one sentence
with no compliment and no remark that the agency lacks something; when the opener names a role it
is worded to match the role's status, and only a role with a recent posting date is called
"hiring"; the line offering help before the hire is there for a fresh or undated role and nowhere
else; follow-up 1 at 70 words or fewer, ending on the trial question; follow-up 2 at 40; and no
mention of n8n, Docker or Looker Studio.

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
from common import DRAFTS, JOB_WORDING, JOBS, ROOT, US_TRACK, job_wording, utf8_stdout

BANNED = ["i hope this finds you well", "i hope this email finds you", "i came across your profile",
          "synergy", "quick question", "touching base", "circle back", "game-changer", "game changer",
          # A follow-up that only reminds adds nothing, so it is not sent.
          "just following up", "circling back", "bumping this", "checking in"]
CTA = "Want the other 7? Just reply yes."
US_MESSAGE_MAX = 90
US_PROOF = ("I build scraping, data and automation pipelines. My own tool, LeadForge, discovered 325 agencies "
            "across the UAE, KSA and Qatar and scored the best 70 using evidence from their own sites.")
US_CTA = "Is there a piece of a current project I could take off your plate?"
# A draft is signed either with the placeholder or, once `pack.py fill` has run, with the real name.
SIGN_OFFS = [s for s in ("{{NAME}}", (dotenv_values(ROOT / ".env").get("LEADFORGE_NAME") or "").strip()) if s]
JOB_NEVER = ("n8n", "docker", "looker studio")  # tools the job ask never mentions
JOB_FU1_MAX, JOB_FU2_MAX = 70, 40
FU1_MAX, FU2_MAX = 70, 40  # lead-pack drafts; follow-up 1 may turn into the job ask and carry a new piece of proof
JOB_OPENERS = {"fresh": "hiring_opener", "undated": "undated_opener", "talent_pool": "talent_pool_opener"}
PRAISE = re.compile(r"\b(love[ds]?|impress\w*|amazing|awesome|great|beautiful|stunning|admir\w*|fantastic|excellent|"
                    r"incredible|brilliant|outstanding)\b", re.I)
FAULT = re.compile(r"\b(missing|lacks?|lacking|weak|outdated|slow|broken|poor|without|doesn['’]?t|does not|isn['’]?t|"
                   r"is not|no longer)\b", re.I)
OTHER_LINK = re.compile(r"https?://|www\.|\b[\w-]+\.(?:com|io|net|org|dev|co|ae|sa|qa|uk|example)\b", re.I)
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

    for prefix, cap in (("follow-up 1", FU1_MAX), ("follow-up 2", FU2_MAX)):
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


def lint_job(text: str, wording: dict) -> list[str]:
    """The job ask: one email and two follow-ups per agency, in the operator's own fixed wording."""
    problems = []
    secs = sections(text)
    header = text.split("\n## ", 1)[0]

    def find(prefix: str) -> str | None:
        return next((v for k, v in secs.items() if k.startswith(prefix)), None)

    def field(name: str) -> str:
        match = re.search(rf"^- \*\*{re.escape(name)}:\*\* *(.+)$", header, flags=re.M)
        return match.group(1).strip() if match else ""

    def flat(section: str | None) -> str:
        return " ".join(body(section or "").split())

    if field("Offer") != "job_ask":
        problems.append("header must say '- **Offer:** job_ask'")
    kind = field("Proof")[:1]
    if kind not in wording["proof"]:
        problems.append(f"header needs '- **Proof:**' with one of {', '.join(wording['proof'])}")
    hiring, names_role = field("Hiring"), field("Names the role") == "yes"
    role, state = hiring.partition(", ")[2], field("Role status").split(" ")[0]
    if not re.match(r"(yes|talent pool), \S|no$", hiring):
        problems.append("header needs '- **Hiring:**' as 'no', 'yes, <role>' or 'talent pool, <role>'")
    if role and not field("Careers page").startswith("http"):
        problems.append("a role is named but the header gives no careers page URL")
    if (state == "talent_pool") != hiring.startswith("talent pool") or (state == "none") != (hiring == "no"):
        problems.append("'- **Role status:**' and '- **Hiring:**' disagree")
    if names_role and state not in JOB_OPENERS:
        problems.append("the opener names a role, so its status must be fresh, undated or talent_pool")
    if '"' not in field("Opener quote") or not field("Evidence").startswith("http"):
        problems.append("the opener needs its quoted words and the URL of the page they are on")

    subject = [ln.strip() for ln in (find("subject") or "").splitlines() if ln.strip()]
    stem = wording["subject"].split("{agency}")[0]
    if len(subject) != 1 or not subject[0].startswith(stem) or len(subject[0]) <= len(stem):
        problems.append(f"needs exactly one subject line, {wording['subject']!r}")

    email = find("email 1")
    if email is None:
        problems.append("missing 'Email 1' section")
    else:
        plain = flat(email)
        for key, label in (("pitch", "the pitch"), ("ask", "the trial question"), ("work", "the link to the work"), ("ps", "the P.S.")):
            if wording[key] not in plain:
                problems.append(f"email 1 is missing {label}, word for word")
        used = [k for k, line in wording["proof"].items() if line in plain]
        if used != [kind]:
            problems.append(f"email 1 must carry proof line {kind} and no other; found {', '.join(used) or 'none'}")
        if (wording["hiring_line"] in plain) != (names_role and state in ("fresh", "undated")):
            problems.append("the line about the open role belongs in email 1 only when the opener names a fresh or undated role")
        if plain.count(wording["link"]) != 1 or OTHER_LINK.search(plain.replace(wording["link"], "")):
            problems.append("email 1 may hold one link, the one to the work")
        if not any(name in plain for name in SIGN_OFFS):
            problems.append("email 1 has no sign-off ({{NAME}}, or the name set in .env)")
        paragraphs = [" ".join(part.split()) for part in body(email).split("\n\n") if part.strip()]
        opener = paragraphs[1] if len(paragraphs) > 1 else ""
        if len(re.findall(r"[.!?](?=\s|$)", opener)) != 1:
            problems.append("the opener must be one sentence")
        if names_role and state in JOB_OPENERS:
            a = "an" if role[:1].lower() in "aeiou" else "a"
            if opener != wording[JOB_OPENERS[state]].format(a=a, role=role):
                problems.append(f"the opener is not the wording for a {state} role")
        if "hiring" in opener.lower() and state != "fresh":
            problems.append("only a role with a posting date in the last 60 days may be called hiring")
        for pattern, what in ((PRAISE, "compliments the agency"), (FAULT, "says the agency lacks something")):
            found = pattern.search(opener)
            if found:
                problems.append(f"the opener {what}: {found.group(0)!r}")

    first, second = find("follow-up 1"), find("follow-up 2")
    if first is None or second is None:
        problems.append("needs a 'Follow-up 1' and a 'Follow-up 2' section")
    else:
        if words(body(first)) > JOB_FU1_MAX:
            problems.append(f"follow-up 1 is {words(body(first))} words (max {JOB_FU1_MAX})")
        if wording["ask"] not in flat(first):
            problems.append("follow-up 1 must end on the trial question")
        if words(body(second)) > JOB_FU2_MAX:
            problems.append(f"follow-up 2 is {words(body(second))} words (max {JOB_FU2_MAX})")

    sent = " ".join(flat(part) for part in (email, first, second)).lower()
    problems += [f"never mention {tool!r}" for tool in JOB_NEVER if tool in sent]
    problems += [f"banned phrase: {phrase!r}" for phrase in BANNED if phrase in sent]
    return problems


def main() -> int:
    utf8_stdout()
    failed = total = blocked = 0
    named = [Path(arg) for arg in sys.argv[1:]]
    folders = [(DRAFTS, lint), (US_TRACK, lint_us)]
    if JOB_WORDING.exists():
        wording = job_wording()
        folders.append((JOBS, lambda text: lint_job(text, wording)))
    jobs = ([(path, lint, path.as_posix()) for path in named] if named else
            [(path, check, f"{folder.name}/{path.name}") for folder, check in folders for path in sorted(folder.glob("*.md"))])
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
