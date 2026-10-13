"""A region is a config file, not a branch of the code. These tests read the committed configs."""
import json

import pytest

import common
import jobs
import qualify
import shortlist
import track


@pytest.mark.parametrize("name", common.region_names())
def test_every_region_file_loads_and_has_searches_to_run(name):
    cfg = common.region(name)
    assert cfg["label"] and cfg["countries"] and cfg["address_words"]
    assert cfg["queries"] and all(" in " in query for query in cfg["queries"])
    assert isinstance(cfg["outreach"], bool)


def test_the_two_regions():
    gulf, uk = common.region("gulf"), common.region("uk")
    assert common.region()["name"] == "gulf" == common.DEFAULT_REGION
    assert gulf["countries"] == {"AE", "SA", "QA"} and gulf["outreach"] is True
    assert uk["countries"] == {"GB"}
    assert uk["cities"] == ["London", "Manchester", "Birmingham", "Leeds", "Bristol"]
    assert len(uk["queries"]) == len(uk["cities"]) * len(uk["searches"])
    assert uk["outreach"] is False  # scored only: no emails are drafted for it yet


def test_an_unknown_region_is_an_error_not_a_guess():
    with pytest.raises(SystemExit):
        common.region("atlantis")


def test_a_listing_belongs_to_a_region_by_country_then_by_address():
    assert common.region_of({"country": "GB", "address": "Dubai Marina"}) == "uk"  # the country wins
    assert common.region_of({"country": "QA"}) == "gulf"
    assert common.region_of({"address": "12 Park Row, Leeds LS1"}) == "uk"
    assert common.region_of({"country": "US"}) is None


def test_the_shortlist_only_takes_agencies_inside_its_region():
    agency = {"status": "ok", "maps": {"country": "GB"}}
    points, reason = shortlist.triage(agency, common.region("gulf"))
    assert points == 0 and reason.startswith("outside ")
    assert not shortlist.triage({"status": "dead", "maps": {"country": "GB"}}, common.region("uk"))[1].startswith("outside")


def test_one_regions_agencies_stay_out_of_anothers_ranking(tmp_path, monkeypatch):
    monkeypatch.setattr(qualify, "SCORED", tmp_path)
    base = {"score": 70, "source": "maps", "scores": {"service_fit": 20}}
    for domain, where in (("old.example", None), ("riyadh.example", "gulf"), ("leeds.example", "uk")):
        record = {**base, "domain": domain, **({"region": where} if where else {})}
        (tmp_path / f"{domain}.json").write_text(json.dumps(record), encoding="utf-8")
    assert [r["domain"] for r in qualify.load_scored("gulf")] == ["old.example", "riyadh.example"]  # no region means the first one
    assert [r["domain"] for r in qualify.load_scored("uk")] == ["leeds.example"]


def test_nothing_is_drafted_for_a_region_that_is_scored_only(tmp_path, monkeypatch):
    assert not common.outreach_open({"region": "uk"})
    assert common.outreach_open({"region": "gulf"}) and common.outreach_open({})
    monkeypatch.setattr(track, "DB", tmp_path / "tracker.db")
    monkeypatch.setattr(jobs, "SCORED", tmp_path)
    (tmp_path / "leeds.example.json").write_text(json.dumps({"domain": "leeds.example", "region": "uk"}), encoding="utf-8")
    conn = track.connect()
    try:
        assert "scored only" in jobs.refusal("leeds.example", conn)
    finally:
        conn.close()
