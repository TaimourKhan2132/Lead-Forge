"""Build the project's live page.

    python docs/make_site.py            # writes _site/
    python docs/make_site.py --check    # the same, then fail on an unfilled marker or a broken local link

GitHub Pages serves _site/ from the gh-pages branch, and the pages workflow rebuilds it on every push
to main. The page is filled from the repository itself, so it cannot drift from the code:

    the pack          examples/northlight-growth.example.html, as pack.py wrote it, with a bar added
    the email         examples/northlight-growth.example.email.md, as draft.py wrote it
    signal wording    signals.py, applied to the example's own signals
    the terminal      the real output of lint_drafts.py on examples/rejected.example.md
    send rules        track.py's caps and its follow-up date rule
    version, tests    CHANGELOG.md, and what pytest collects

Every business on the page is fictional. Nothing here reads data/, packs/ or outreach/.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import lint_drafts  # noqa: E402
import signals  # noqa: E402
import track  # noqa: E402

SITE = ROOT / "docs" / "site"
OUT = ROOT / "_site"
EXAMPLES = ROOT / "examples"
AGENCY = "northlight-growth.example"
REPO = "https://github.com/TaimourKhan2132/Lead-Forge"
SITE_URL = "https://taimourkhan2132.github.io/Lead-Forge/"
REJECTED = "examples/rejected.example.md"
LIMITS = {"email": 120, "fu1": 50, "fu2": 40, "linkedin": 280}  # the caps lint_drafts.py enforces
MONDAY = dt.date(2026, 10, 12)  # any Monday: the week grid only uses the weekday pattern
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
e = html.escape


def sh(*args: str) -> str:
    """A command's output, run from the repository root the way a person would run it."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1", "COLUMNS": "100"}
    done = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    return done.stdout + done.stderr


def version() -> str:
    found = re.search(r"^## \[(\d+\.\d+\.\d+)\]", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), flags=re.M)
    return f"v{found.group(1)}"


def test_count() -> str:
    found = re.search(r"(\d+) tests? collected", sh(sys.executable, "-m", "pytest", "--collect-only", "-q"))
    if not found:
        raise SystemExit("could not count the tests: is pytest installed? (pip install -r requirements-dev.txt)")
    return found.group(1)


def commit() -> str:
    return os.getenv("GITHUB_SHA") or sh("git", "rev-parse", "HEAD").strip()


# --- the email and its check list --------------------------------------------------------------

def checks(text: str) -> tuple[tuple[str, str] | None, list[tuple[str, list[tuple[str, str]]]]]:
    """The 'Check before sending' section: the opening line's check, then (business, [(claim, url)])."""
    line1, groups = None, []
    for line in text.strip().splitlines():
        if found := re.match(r"Line 1 \((.+)\): (\S+)$", line):
            line1 = (found[1], found[2])
        elif found := re.match(r"\d+\. (.+)$", line):
            groups.append((found[1], []))
        elif (found := re.match(r"\s+- (.+): (https?://\S+)$", line)) and groups:
            groups[-1][1].append((found[1], found[2]))
    return line1, groups


def paragraphs(text: str, names: list[str], line1: str = "") -> str:
    """An email body as HTML. A line that opens with a business's name is tied to that business's checks."""
    out = []
    for para in re.split(r"\n\s*\n", text.strip()):
        lines = para.splitlines()
        picked = [next((i for i, name in enumerate(names, 1) if ln.startswith(f"{name}:")), 0) for ln in lines]
        if picked and all(picked):
            spans = "".join(
                f'<span class="pick" data-pick="{i}" tabindex="0"><b>{e(names[i - 1])}:</b>{e(ln[len(names[i - 1]) + 1:])}</span>'
                for i, ln in zip(picked, lines))
            out.append(f'<p class="picks">{spans}</p>')
        elif line1 and para.strip() == line1:
            out.append(f'<p><span class="pick" data-pick="0" tabindex="0">{e(para.strip())}</span></p>')
        else:
            out.append("<p>" + "<br>".join(e(ln) for ln in lines) + "</p>")
    return "\n".join(out)


def mail() -> dict[str, str]:
    md = (EXAMPLES / f"{AGENCY}.email.md").read_text(encoding="utf-8")
    spec = json.loads((EXAMPLES / "spec" / f"{AGENCY}.draft.json").read_text(encoding="utf-8"))
    secs = lint_drafts.sections(md)

    def find(prefix: str) -> str:
        return lint_drafts.body(next(v for k, v in secs.items() if k.startswith(prefix)))

    line1, groups = checks(find("check before sending"))
    names = [name for name, _ in groups]
    subjects = re.findall(r"^\d+\. (.+)$", find("subject"), flags=re.M)
    others = " · ".join(f"“{e(s)}”" for s in subjects[1:])
    bodies = {"email1": find("email 1"), "fu1": find("follow-up 1"), "fu2": find("follow-up 2"), "linkedin": find("linkedin")}
    head = (f'<dl class="mail-head"><dt>To</dt><dd>{e(track.header_field(md, "To"))}</dd>'
            f'<dt>Subject</dt><dd>{e(subjects[0])}<span class="alt">or {others}</span></dd></dl>')
    feet = {
        "email1": [f"{lint_drafts.words(bodies['email1'])} words · limit {LIMITS['email']}", "plain text", "no links",
                   "ends on the same question every time"],
        "fu1": [f"{lint_drafts.words(bodies['fu1'])} words · limit {LIMITS['fu1']}", "sent on day 3, if there is no reply"],
        "fu2": [f"{lint_drafts.words(bodies['fu2'])} words · limit {LIMITS['fu2']}", "sent on day 7, and it is the last"],
        "linkedin": [f"{len(bodies['linkedin'])} characters · limit {LIMITS['linkedin']}", "written, never sent by the tool"],
    }
    titles = {"email1": "Email 1", "fu1": "Follow-up, day 3", "fu2": "Follow-up, day 7", "linkedin": "LinkedIn note"}
    panels = []
    for key, text in bodies.items():
        foot = "".join(f"<span>{e(item)}</span>" for item in feet[key])
        panels.append(
            f'<div class="mail-panel" role="tabpanel" id="m-{key}" aria-labelledby="t-{key}">'
            f'<h3 class="panel-title">{titles[key]}</h3>{head if key == "email1" else ""}'
            f'<div class="mail-body">\n{paragraphs(text, names, spec["line1"] if key == "email1" else "")}\n</div>'
            f'<div class="mail-foot">{foot}</div></div>')

    items = []
    if line1:
        items.append(f'<li data-pick="0" tabindex="0"><b>The opening line</b><ul><li><span>{e(line1[0])}</span>'
                     f"<code>{e(line1[1])}</code></li></ul></li>")
    for i, (name, claims) in enumerate(groups, 1):
        rows = "".join(f"<li><span>{e(claim)}</span><code>{e(url)}</code></li>" for claim, url in claims)
        items.append(f'<li data-pick="{i}" tabindex="0"><b>{e(name)}</b><ul>{rows}</ul></li>')
    return {"mail_panels": "\n".join(panels), "checklist": '<ol class="check-list">\n' + "\n".join(items) + "\n</ol>"}


# --- the rest of the page ----------------------------------------------------------------------

def wording() -> dict[str, str]:
    """One email phrase per signal, written by signals.py from a signal in the example pack."""
    cands = json.loads((EXAMPLES / "spec" / f"{AGENCY}.candidates.json").read_text(encoding="utf-8"))
    seen = {}
    for cand in cands:
        for gap in cand["gaps"]:
            seen.setdefault(gap["key"], gap)
    missing = [key for key in signals.ALLOWED if key not in seen]
    if missing:
        raise SystemExit(f"the example pack has no {', '.join(missing)} signal to show the wording of")
    out = {f"phrase_{key}": e(signals.phrase(seen[key])) for key in signals.ALLOWED}
    out |= {f"headline_{key}": e(signals.HEADLINES[key]) for key in signals.ALLOWED}
    return out


def terminal() -> str:
    """The linter refusing the draft that was written to fail, as lines of terminal output."""
    command = f"python src/lint_drafts.py {REJECTED}"
    output = [ln.rstrip() for ln in sh(sys.executable, "src/lint_drafts.py", REJECTED).splitlines() if ln.strip()]
    if not output or not output[0].startswith("FAIL"):
        raise SystemExit(f"{REJECTED} was expected to fail the linter, and did not:\n" + "\n".join(output))
    lines = [f'<span class="ln"><span class="p">$</span> <span class="cmd">{e(command)}</span></span>']
    for line in output:
        line = e(line)
        line = re.sub(r"^FAIL\b", '<span class="bad">FAIL</span>', line)
        line = re.sub(r"^(\s+- [^:]+:)", r'<span class="dim">\1</span>', line)
        lines.append(f'<span class="ln">{line}</span>')
    return "".join(lines)


def week_grid() -> str:
    """Two working weeks, one row per send day: where track.py puts the first email and its two follow-ups."""
    cells = ['<div class="wk" role="img" aria-label="A row for each weekday an email could be sent, showing the '
             'days its two follow-ups fall on across two working weeks.">', '<span class="h r"></span>']
    for week in range(2):
        cells += [f'<span class="h">{day}</span>' for day in DAYS]
        if not week:
            cells.append('<span class="gap" aria-hidden="true"></span>')
    for offset, day in enumerate(DAYS):
        sent = MONDAY + dt.timedelta(days=offset)
        marks = {sent.isoformat(): ("s", "sent"),
                 track.due(sent, track.FU1_DAYS): ("f", "1"),
                 track.due(sent, track.FU2_DAYS): ("f", "2")}
        cells.append(f'<span class="r">Sent {day}</span>')
        for week in range(2):
            for d in range(5):
                kind, text = marks.get((MONDAY + dt.timedelta(days=7 * week + d)).isoformat(), ("", ""))
                cells.append(f'<span class="d {kind}">{text}</span>')
            if not week:
                cells.append('<span class="gap" aria-hidden="true"></span>')
    cells.append("</div>")
    cells.append('<p class="key"><span><i class="d s">sent</i>the first email</span>'
                 '<span><i class="d f">1</i><i class="d f">2</i>its follow-ups</span>'
                 '<span><i class="gap" aria-hidden="true"></i>the weekend</span></p>')
    return "\n".join(cells)


def pack_page(page: str | None = None) -> str:
    """The example pack exactly as pack.py wrote it, plus a bar and a note for links that lead nowhere."""
    if page is None:
        page = (EXAMPLES / f"{AGENCY}.html").read_text(encoding="utf-8")
    if "{{" in page:
        raise SystemExit("the example pack is unsigned ({{NAME}} and its links are unfilled): run "
                         "`python src/pack.py fill --readme-no-email`, or restore it with `git checkout -- examples/`")
    bar = (SITE / "pack-bar.html").read_text(encoding="utf-8")
    page = page.replace("</title>", '</title><link rel="icon" href="favicon.svg" type="image/svg+xml">'
                        '<meta name="description" content="An example LeadForge pack: ten fictional dental clinics '
                        'in Dubai, each with what can be checked and the link to check it.">', 1)
    if page.count("<body>") != 1:
        raise SystemExit("the example pack's HTML has changed shape: expected one <body>")
    return page.replace("<body>", "<body>" + bar, 1)


def _writable(function, path, _error) -> None:
    """Windows marks a .git folder's files read-only; clear that and remove the file again."""
    os.chmod(path, stat.S_IWRITE)
    function(path)


def build(out: Path = OUT) -> Path:
    sha = commit()
    values = {
        "repo": REPO, "site_url": SITE_URL, "version": version(), "tests": test_count(),
        "sha": sha, "sha_short": sha[:7], "built_on": dt.date.today().strftime("%d %b %Y").lstrip("0"),
        "terminal": terminal(), "week_grid": week_grid(), "stale_year": str(signals.STALE_MAX_YEAR),
        "new_cap": str(track.NEW_CAP), "daily_cap": str(track.DAILY_CAP),
        **mail(), **wording(),
    }
    if out.exists():
        shutil.rmtree(out, onerror=_writable)
    out.mkdir(parents=True)
    for name in ("index.html", "404.html"):
        page = (SITE / name).read_text(encoding="utf-8")
        page = re.sub(r"\[\[(\w+)\]\]", lambda found: values[found.group(1)], page)
        (out / name).write_text(page, encoding="utf-8")
    for name in ("site.css", "site.js", "favicon.svg"):
        shutil.copyfile(SITE / name, out / name)
    shutil.copyfile(ROOT / "docs" / "assets" / "social-preview.png", out / "social-preview.png")
    (out / "pack.html").write_text(pack_page(), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")  # serve the files as they are
    return out


def problems(out: Path) -> list[str]:
    """Unfilled markers, and links or images that point at a file the site does not have."""
    found = []
    for path in sorted(out.glob("*.html")):
        text = path.read_text(encoding="utf-8")
        found += [f"{path.name}: unfilled marker {marker}" for marker in sorted(set(re.findall(r"\[\[\w+\]\]|\{\{\w+\}\}", text)))]
        if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", text):
            found.append(f"{path.name}: contains a control character")
        if "“”" in text or "<q></q>" in text:
            found.append(f"{path.name}: has an empty pair of quotation marks")
        for target in re.findall(r"""(?:src|href)=["']([^"'#][^"']*)["']""", text):
            if re.match(r"[a-z]+:", target):
                continue
            local = target.split("#")[0].split("?")[0]
            if local in ("", "./"):
                continue
            if not (out / local).is_file():
                found.append(f"{path.name}: {target} is not in the site")
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="fail on an unfilled marker or a broken local link")
    ap.add_argument("--out", type=Path, default=OUT, help="where to write the site (default: _site/)")
    args = ap.parse_args()
    out = build(args.out.resolve())
    files = sorted(p for p in out.iterdir() if p.is_file())
    print(f"site wrote {len(files)} files to {out.name}/ ({sum(p.stat().st_size for p in files) / 1024:.0f} KB)")
    if args.check:
        found = problems(out)
        for problem in found:
            print(f"   - {problem}")
        return 1 if found else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
