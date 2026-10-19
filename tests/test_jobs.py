"""The job ask, and the send rules that came with it, as tests.

Nothing here touches the network or real data. The agency is invented and the wording is the
example file's, not the operator's.
"""
import json
from pathlib import Path

import pytest

import draft
import jobs
import lint_drafts
import track
from common import job_wording

ROOT = Path(__file__).resolve().parent.parent
WORDING = job_wording(ROOT / "examples" / "job_ask.example.json")
SPEC = {
    "domain": "harbourline.example", "agency": "Harbourline Studio", "to": "hello@harbourline.example", "type": "A",
    "opener": "Your site lists SEO, paid search and web design for clinics in Dubai.",
    "line1_checks": [{"url": "https://harbourline.example/", "quotes": ["SEO, paid search and web design"]}],
    "hiring": {"open": False, "url": ""}, "score": {"score": 71, "tier": "A"},
}
OPEN_ROLE = {"url": "https://harbourline.example/careers", "role": "Automation Engineer", "status": "undated",
             "relevance": "strong", "fits": True, "score": 5}


def rendered(**changes) -> str:
    return jobs.render({**SPEC, **changes}, WORDING, results=Path("never-checked.json"))


@pytest.fixture
def db(tmp_path, monkeypatch):
    """An empty tracker, away from the real one."""
    (tmp_path / "summary.csv").write_text("domain,agency,tier,score\n", encoding="utf-8")
    monkeypatch.setattr(track, "DB", tmp_path / "tracker.db")
    monkeypatch.setattr(track, "SCORED", tmp_path)
    monkeypatch.setattr(track, "SKIP_FILE", tmp_path / "skip.txt")
    conn = track.connect()
    yield conn
    conn.close()


def add(conn, domain, offer="lead_pack", sent=None):
    conn.execute("INSERT INTO leads (domain, agency, tier, score, offer) VALUES (?, ?, 'B', 60, ?)", (domain, domain, offer))
    if sent:
        track.mark(conn, domain, "sent", "", sent)


# --- the email -----------------------------------------------------------------------------------

def test_a_job_ask_passes_its_linter():
    assert lint_drafts.lint_job(rendered(), WORDING) == []
    assert lint_drafts.lint_job(rendered(hiring=OPEN_ROLE), WORDING) == []


def test_the_opener_names_a_role_only_when_the_role_is_work_on_offer():
    fits = rendered(hiring=OPEN_ROLE)
    assert "I saw the Automation Engineer role on your careers page." in fits and WORDING["hiring_line"] in fits
    assert SPEC["opener"] not in fits
    other = rendered(hiring={**OPEN_ROLE, "role": "Account Manager", "fits": False})
    assert "- **Hiring:** yes, Account Manager" in other
    assert SPEC["opener"] in other and WORDING["hiring_line"] not in other and "I saw the" not in other


@pytest.mark.parametrize("kind", ["A", "B", "C"])
def test_each_proof_type_gets_its_own_line_and_a_different_one_in_the_follow_up(kind):
    text = rendered(type=kind)
    email, follow_up = text.split("## Follow-up 1")[0], text.split("## Follow-up 1")[1].split("## Follow-up 2")[0]
    assert WORDING["proof"][kind] in email
    assert WORDING["proof"][kind] not in follow_up and WORDING["proof"][jobs.NEXT_PROOF[kind]] in follow_up
    assert follow_up.strip().splitlines()[-3] == WORDING["ask"]  # it ends on the trial question, above the name
    assert lint_drafts.lint_job(text, WORDING) == []


@pytest.mark.parametrize("old, new, complaint", [
    (WORDING["work"], WORDING["work"] + " and https://another.example/page", "one link"),
    (WORDING["proof"]["A"], WORDING["proof"]["B"], "proof line A"),
    (WORDING["ps"], "", "the P.S."),
    (WORDING["pitch"], WORDING["pitch"] + " I also set up n8n and Docker.", "never mention"),
    (SPEC["opener"], "I love the work you do for clinics in Dubai.", "compliments"),
    (SPEC["opener"], "Your site is missing a page about paid search.", "lacks something"),
    (SPEC["opener"], "Your site lists SEO. It also lists web design.", "one sentence"),
    (WORDING["follow_up_2"], "Just following up on my note from last week.", "banned phrase"),
    ("- **Offer:** job_ask", "- **Offer:** lead_pack", "job_ask"),
])
def test_a_job_ask_that_breaks_a_rule_is_refused(old, new, complaint):
    text = rendered()
    assert old in text
    problems = lint_drafts.lint_job(text.replace(old, new), WORDING)
    assert any(complaint in problem for problem in problems), problems


def test_the_line_about_an_open_role_needs_an_open_role():
    text = rendered().replace(WORDING["ask"], f"{WORDING['hiring_line']} {WORDING['ask']}", 1)
    assert any("open role" in problem for problem in lint_drafts.lint_job(text, WORDING))


def test_an_agency_with_no_quotable_fact_gets_no_email(db):
    bare = {k: v for k, v in SPEC.items() if k not in ("opener", "line1_checks")}
    assert any("no quoted words" in problem for problem in jobs.problems(bare, db))
    named = {**SPEC, "first_name": "Sam"}  # a name with no page behind it
    assert any("name_source" in problem for problem in jobs.problems(named, db))


def test_an_agency_gets_one_offer(db):
    add(db, "sent.example", sent="2026-10-13")
    add(db, "queued.example")
    db.execute("INSERT INTO leads (domain, agency, offer, blocked) VALUES ('stuck.example', 'Stuck', 'lead_pack', 'BLOCKED: no pack')")
    assert "already been emailed" in jobs.refusal("sent.example", db)
    assert "one offer" in jobs.refusal("queued.example", db)
    assert jobs.refusal("stuck.example", db) == ""   # its pack could not be built, so the job ask may take it over
    assert jobs.refusal("new.example", db) == ""


# --- follow-ups ----------------------------------------------------------------------------------

@pytest.mark.parametrize("phrase", ["just following up", "circling back", "bumping this", "checking in"])
def test_a_follow_up_that_only_reminds_is_refused(phrase):
    text = (ROOT / "examples" / "northlight-growth.example.email.md").read_text(encoding="utf-8")
    assert f"banned phrase: {phrase!r}" in lint_drafts.lint(text.replace("I will leave it here.", f"I am {phrase}."))


def test_a_lead_pack_follow_up_can_turn_into_the_job_ask():
    spec = {"fu1": "The ten clinics are on one page.", "fu2": "I will leave it here."}
    plain = "\n".join(draft.follow_ups(spec, "Hi Sam,", "Name"))
    turned = "\n".join(draft.follow_ups(spec, "Hi Sam,", "Name", WORDING["pivot"]))
    assert spec["fu1"] in plain and "Shall I send it over?" in plain
    assert WORDING["pivot"] in turned and spec["fu1"] not in turned and "Shall I send it over?" not in turned
    assert spec["fu2"] in turned  # the second follow-up is left as it was


# --- the tracker ---------------------------------------------------------------------------------

def test_the_plan_fills_a_day_to_the_caps_and_leaves_room_for_the_follow_ups(db):
    for i in range(40):
        add(db, f"agency{i:02}.example", "job_ask" if i % 2 else "lead_pack")
    track.plan(db, "2026-10-14")
    days = dict(db.execute("SELECT planned_send, COUNT(*) FROM plan GROUP BY planned_send").fetchall())
    # Wednesday takes 25. Thursday takes 5, because all 30 first follow-ups land on Monday and 30 is the cap.
    assert days["2026-10-14"] == track.NEW_CAP == 25 and days["2026-10-15"] == 5
    assert "2026-10-16" not in days and "2026-10-19" not in days
    packs_first = db.execute("SELECT COUNT(*) FROM plan JOIN leads USING (domain) WHERE plan.planned_send = '2026-10-14' "
                             "AND offer = 'lead_pack'").fetchone()[0]
    assert packs_first == 20  # every pack that is built goes before any job ask


def test_keep_leaves_dated_leads_where_they_are(db):
    for i in range(6):
        add(db, f"agency{i}.example")
    track.plan(db, "2026-10-15")
    add(db, "late.example", "job_ask")
    track.plan(db, "2026-10-14", keep=True)
    days = dict(db.execute("SELECT domain, planned_send FROM plan").fetchall())
    assert all(days[f"agency{i}.example"] == "2026-10-15" for i in range(6))
    assert days["late.example"] == "2026-10-14"


def test_two_bounces_in_a_day_stop_the_sends(db):
    for name in ("a", "b", "c"):
        add(db, f"{name}.example", sent="2026-10-14")
    track.mark(db, "a.example", "bounced", "", "2026-10-15")
    assert not track.bounce_check(db, "2026-10-15")
    track.mark(db, "b.example", "bounced", "", "2026-10-15")
    assert track.bounce_check(db, "2026-10-15")
    assert not track.bounce_check(db, "2026-10-16")
    # A bounce never arrived: no follow-up is owed for it.
    assert [lead["domain"] for _, lead in track.follow_ups_due(db, "2026-10-19")] == ["c.example"]


def test_replies_are_compared_by_offer_and_a_bounce_is_not_counted_as_sent(db):
    for i in range(4):
        add(db, f"pack{i}.example", "lead_pack", sent="2026-10-13")
    for i in range(4):
        add(db, f"job{i}.example", "job_ask", sent="2026-10-14")
    track.mark(db, "pack0.example", "replied", "", None)
    track.mark(db, "job0.example", "bounced", "", "2026-10-14")
    track.mark(db, "job1.example", "replied", "", None)
    found = track.rates(db)
    assert (found["lead_pack"]["sent"], found["lead_pack"]["replied"], found["lead_pack"]["rate"]) == (4, 1, 0.25)
    assert (found["job_ask"]["bounced"], found["job_ask"]["replied"]) == (1, 1)
    assert found["job_ask"]["rate"] == pytest.approx(1 / 3)


def test_a_tracker_made_before_offers_existed_is_brought_up_to_date(tmp_path, monkeypatch):
    import sqlite3
    old = sqlite3.connect(tmp_path / "tracker.db")
    old.execute("CREATE TABLE leads (domain TEXT PRIMARY KEY, agency TEXT NOT NULL, email TEXT, tier TEXT, score INTEGER, "
                "pack_path TEXT, draft_path TEXT, status TEXT NOT NULL DEFAULT 'drafted' "
                "CHECK (status IN ('drafted','sent','replied','won','lost','no_reply')), sent_at TEXT, fu1_due TEXT, "
                "fu2_due TEXT, fu1_sent_at TEXT, fu2_sent_at TEXT, notes TEXT NOT NULL DEFAULT '')")
    old.execute("INSERT INTO leads (domain, agency, status, sent_at) VALUES ('early.example', 'Early', 'sent', '2026-10-12')")
    old.commit()
    old.close()
    monkeypatch.setattr(track, "DB", tmp_path / "tracker.db")
    conn = track.connect()
    try:
        lead = conn.execute("SELECT * FROM leads").fetchone()
        assert (lead["offer"], lead["status"], lead["sent_at"]) == ("lead_pack", "sent", "2026-10-12")
        assert track.mark(conn, "early.example", "bounced", "", "2026-10-13") == 0  # the new status is accepted
    finally:
        conn.close()


def test_the_days_job_asks_are_written_as_a_page_and_as_a_sheet(db, tmp_path, monkeypatch):
    monkeypatch.setattr(track, "ROOT", tmp_path)
    monkeypatch.setattr(track, "READY", tmp_path / "ready")
    (tmp_path / "job.md").write_text(rendered(hiring=OPEN_ROLE), encoding="utf-8")
    add(db, SPEC["domain"], "job_ask")
    db.execute("UPDATE leads SET draft_path = 'job.md', planned_send = '2026-10-14'")
    assert track.ready(db, "2026-10-14") == 0
    page = (tmp_path / "ready" / "2026-10-14-jobs.md").read_text(encoding="utf-8")
    sheet = (tmp_path / "ready" / "2026-10-14-jobs.csv").read_text(encoding="utf-8-sig")
    assert "- **Offer:** job_ask" in page and "- **Hiring:** yes, Automation Engineer (https://harbourline.example/careers)" in page
    assert sheet.splitlines()[0] == ",".join(track.JOB_COLUMNS)
    assert not (tmp_path / "ready" / "2026-10-14.md").exists()  # no lead-pack email that day, so no file for one
    assert json.dumps("job_ask")[1:-1] in sheet


REPORT = {**WORDING, "report_lead": "One more example of my work:",
          "follow_up_role": "With the {role} role in mind, one more example of my work:",
          "follow_up_report": "a demo report for a fictional clinic, white-labelled for an agency.",
          "report_link": "{{REPORT_LINK}}"}


def test_follow_up_1_can_carry_the_demo_report_and_names_the_role_again():
    named = jobs.render({**SPEC, "hiring": OPEN_ROLE}, REPORT, results=Path("never-checked.json"))
    plain = jobs.render(SPEC, REPORT, results=Path("never-checked.json"))
    first = lint_drafts.sections(named)["follow-up 1 (day 3)"]
    assert "With the Automation Engineer role in mind, one more example of my work: a demo report" in first
    assert first.count("{{REPORT_LINK}}") == 1 and first.strip().splitlines()[-3] == REPORT["ask"]
    assert "One more example of my work: a demo report" in lint_drafts.sections(plain)["follow-up 1 (day 3)"]
    assert lint_drafts.lint_job(named, REPORT) == [] and lint_drafts.lint_job(plain, REPORT) == []


def test_a_lead_pack_follow_up_that_turns_into_the_job_ask_can_carry_the_report_too():
    spec = {"fu1": "The ten clinics are on one page.", "fu2": "I will leave it here."}
    report = draft._report("", REPORT)
    turned = "\n".join(draft.follow_ups(spec, "Hi Sam,", "Name", WORDING["pivot"], report))
    assert turned.index(WORDING["pivot"]) < turned.index(report) and turned.count("{{REPORT_LINK}}") == 1
    assert draft._report("", WORDING) == ""  # no report in the wording file, no report in the follow-up


def test_a_follow_up_moves_only_to_a_weekday_and_in_order(db):
    add(db, "a.example", sent="2026-10-14")  # follow-ups due Mon 19 and Wed 21
    assert track.move(db, "a.example", "fu1", "2026-10-24", "") == 1  # a Saturday
    assert track.move(db, "a.example", "fu1", "2026-10-21", "") == 1  # not before follow-up 2
    assert track.move(db, "a.example", "fu1", "2026-10-14", "") == 1  # not on or before the first email
    assert track.move(db, "a.example", "fu2", "2026-10-26", "") == 0
    assert track.move(db, "a.example", "fu1", "2026-10-21", "operator's call") == 0
    row = db.execute("SELECT fu1_due, fu2_due, notes FROM leads WHERE domain = 'a.example'").fetchone()
    assert (row["fu1_due"], row["fu2_due"]) == ("2026-10-21", "2026-10-26") and "operator's call" in row["notes"]
    track.mark(db, "a.example", "fu1", "", "2026-10-21")
    assert track.move(db, "a.example", "fu1", "2026-10-22", "") == 1  # a follow-up that went out stays put


def test_a_send_file_from_an_earlier_run_is_archived_not_deleted(db, tmp_path, monkeypatch):
    monkeypatch.setattr(track, "ROOT", tmp_path)
    monkeypatch.setattr(track, "READY", tmp_path / "ready")
    (tmp_path / "ready").mkdir()
    (tmp_path / "ready" / "2026-10-20-jobs.md").write_text("what went out early", encoding="utf-8")
    assert track.ready(db, "2026-10-20") == 1  # nothing is due that day any more
    assert not (tmp_path / "ready" / "2026-10-20-jobs.md").exists()
    kept = list((tmp_path / "ready" / "archive").glob("2026-10-20-jobs.superseded-*.md"))
    assert len(kept) == 1 and kept[0].read_text(encoding="utf-8") == "what went out early"
