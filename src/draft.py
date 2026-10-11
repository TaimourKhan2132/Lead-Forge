"""Outreach drafts: render one agency's draft from a spec, then lint it.

    python src/draft.py build <agency-domain>     # needs data/scored/drafts/<agency-domain>.draft.json

The spec is the reasoning layer's wording: the subject lines, the opening line about the agency
(with the evidence for it), the three prospects to name, and the follow-ups. This script lays it
out in the house format, signs it, adds the score from the scored record, and runs the same
linter that checks every other draft. A draft that fails the linter is still written, so it can
be fixed, but the command exits non-zero.

Nothing is sent. The file is for a person to read, copy and send by hand.
"""
from __future__ import annotations

import argparse
import json
import sys

from dotenv import dotenv_values
from rich.console import Console

from common import DRAFTS, ROOT, SCORED, log_run, utf8_stdout
from lint_drafts import lint

SPECS = SCORED / "drafts"
PROOF = "Every site gap was checked twice in a real browser and comes with the page link."
CTA = "Want the other 7? Just reply yes."
console = Console()


def render(spec: dict) -> str:
    domain = spec["domain"]
    scored = json.loads((SCORED / f"{domain}.json").read_text(encoding="utf-8"))
    name = (dotenv_values(ROOT / ".env").get("LEADFORGE_NAME") or "").strip() or "{{NAME}}"
    greeting = spec.get("greeting", "Hello,")
    header = [
        f"# Outreach: {spec['agency']} ({domain})", "",
        f"- **To:** {spec['to']}",
        f"- **Addressed to:** {spec['addressed_to']}",
        f"- **Pack:** `packs/{domain}.html` ({spec['pack_note']}). Do not attach it to email 1.",
        f"- **Score:** {scored['score']}, tier {scored['tier']}",
    ]
    header += [f"- {note}" for note in spec.get("notes", [])]
    header += ["", "Send as plain text." if name != "{{NAME}}" else "Send as plain text. Replace `{{NAME}}` before sending.", ""]
    subjects = ["## Subject lines", ""] + [f"{i}. {s}" for i, s in enumerate(spec["subjects"], 1)] + [""]
    email = ["## Email 1", "", greeting, "", spec["line1"], "", spec["line2"], ""] + spec["items"] + [
        "", spec.get("proof", PROOF), "", CTA, "", name, "", "<!--"] + spec["evidence"] + ["-->", ""]
    follow_ups = [
        "## Follow-up 1 (day 3)", "", greeting, "", spec["fu1"], "", "Shall I send it over?", "", name, "",
        "## Follow-up 2 (day 7)", "", greeting, "", spec["fu2"], "", name, "",
        "## LinkedIn connection note", "", spec["linkedin"], "",
    ]
    return "\n".join(header + subjects + email + follow_ups)


def build(domain: str) -> int:
    spec = json.loads((SPECS / f"{domain}.draft.json").read_text(encoding="utf-8"))
    text = render(spec)
    DRAFTS.mkdir(parents=True, exist_ok=True)
    (DRAFTS / f"{domain}.md").write_text(text, encoding="utf-8")
    problems = lint(text)
    log_run(f"python src/draft.py build {domain}", {"lint_problems": len(problems)}, redact=(domain,))
    if problems:
        console.print(f"[red]FAIL[/red] outreach/drafts/{domain}.md")
        for problem in problems:
            console.print(f"   - {problem}")
        return 1
    console.print(f"[green]ok[/green]   outreach/drafts/{domain}.md")
    return 0


def main() -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_build = sub.add_parser("build", help="render and lint one agency's draft")
    p_build.add_argument("agency")
    args = ap.parse_args()
    return build(args.agency)


if __name__ == "__main__":
    sys.exit(main())
