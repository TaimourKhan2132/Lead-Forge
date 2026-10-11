"""Publish a GitHub release for every version tag that has an entry in CHANGELOG.md and no release yet.

    python .github/release_notes.py             # in the release workflow, with GH_TOKEN set
    python .github/release_notes.py --dry-run   # print what would be published

The notes are the changelog entry, word for word. Nothing is written here that is not in the changelog.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "TaimourKhan2132/Lead-Forge"
HEADING = re.compile(r"^## \[(\d+\.\d+\.\d+)\] - (\d{4}-\d{2}-\d{2})(?: · (.+))?$", flags=re.M)
SAMPLE = ROOT / "examples" / "northlight-growth.example.html"  # attached to the release being cut


def entries(changelog: str) -> list[dict]:
    """Every version in the changelog, oldest first: its number, date, title and notes."""
    found = list(HEADING.finditer(changelog))
    out = []
    for i, match in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(changelog)
        body = re.sub(r"^\[[^\]]+\]: \S+$", "", changelog[match.end():end], flags=re.M).strip()
        out.append({"version": match.group(1), "date": match.group(2), "title": match.group(3) or "", "notes": body})
    return sorted(out, key=lambda e: tuple(int(n) for n in e["version"].split(".")))


def sh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=check)


def main() -> int:
    dry = "--dry-run" in sys.argv
    tags = set(sh("git", "tag", "-l", "v*").stdout.split())
    current = os.getenv("GITHUB_REF_NAME", "")
    versions = entries((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    newest = versions[-1]["version"]
    for i, entry in enumerate(versions):
        tag = f"v{entry['version']}"
        if tag not in tags:
            print(f"{tag}: no such tag yet, skipped")
            continue
        if not dry and sh("gh", "release", "view", tag, "--repo", REPO, check=False).returncode == 0:
            print(f"{tag}: already released")
            continue
        notes = entry["notes"]
        if i:
            previous = f"v{versions[i - 1]['version']}"
            notes += f"\n\n**Full diff:** https://github.com/{REPO}/compare/{previous}...{tag}"
        title = f"{tag} · {entry['title']}" if entry["title"] else tag
        if dry:
            print(f"{tag}: would publish {title!r} ({len(notes.split())} words, latest={entry['version'] == newest})")
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
            fh.write(notes + "\n")
        command = ["gh", "release", "create", tag, "--repo", REPO, "--title", title, "--notes-file", fh.name,
                   f"--latest={'true' if entry['version'] == newest else 'false'}"]
        if tag == current and SAMPLE.exists():
            command.append(f"{SAMPLE}#Example pack (fictional data, printable HTML)")
        done = sh(*command, check=False)
        print(f"{tag}: {done.stdout.strip() or done.stderr.strip()}")
        if done.returncode:
            return done.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
