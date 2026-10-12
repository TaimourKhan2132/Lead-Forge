"""The live page is built from the repository, so its build is under test as well.

Nothing here touches the network. The page is written to a temporary folder, never to _site/.
"""
import importlib.util
from pathlib import Path

import pytest

import signals

ROOT = Path(__file__).resolve().parent.parent
PACK = "<!doctype html><html><head><title>A pack</title></head><body><div class=page></div></body></html>"


@pytest.fixture(scope="module")
def site():
    spec = importlib.util.spec_from_file_location("make_site", ROOT / "docs" / "make_site.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_page_builds_with_nothing_unfilled_and_no_broken_links(site, tmp_path, monkeypatch):
    # The pack page has its own tests below. Without a .env, the fixture in test_rules.py rebuilds the
    # example unsigned, so the {{NAME}} sign-off is the one marker let through here.
    real = site.pack_page
    monkeypatch.setattr(site, "pack_page", lambda: real(PACK))
    out = site.build(tmp_path / "site")
    assert [problem for problem in site.problems(out) if "{{NAME}}" not in problem] == []
    page = (out / "index.html").read_text(encoding="utf-8")
    assert "<b>Marina Pearl Dental Studio:</b>" in page  # the email's generated lines
    assert 'class="pick" data-pick="3"' in page          # three businesses, each tied to its checks
    assert "retired signal wording" in page              # what the linter really printed
    assert (out / ".nojekyll").exists() and (out / "404.html").exists()


def test_every_signal_is_shown_with_the_wording_signals_py_writes(site):
    wording = site.wording()
    assert {f"phrase_{key}" for key in signals.ALLOWED} | {f"headline_{key}" for key in signals.ALLOWED} == set(wording)
    assert not any(signals.retired_in(text) for text in wording.values())


def test_the_week_grid_follows_the_trackers_date_rule(site):
    grid = site.week_grid()
    assert grid.count('<span class="d s">') == 5   # one first email for each weekday
    assert grid.count('<span class="d f">') == 10  # and its two follow-ups, none of them on a weekend


def test_the_pack_page_is_the_builders_html_with_a_bar_added(site):
    page = site.pack_page(PACK)
    assert page.index("<body>") < page.index('<div class="lf-bar">') < page.index("<div class=page></div>")
    assert page.count('<div class="lf-bar">') == 1


def test_an_unsigned_example_pack_is_not_published(site):
    with pytest.raises(SystemExit):
        site.pack_page(PACK.replace("</body>", "{{NAME}}</body>"))


def test_a_blanked_quotation_or_a_missing_file_is_reported(site, tmp_path):
    (tmp_path / "index.html").write_text('<p>It said “”.</p><a href="missing.html">x</a>', encoding="utf-8")
    found = site.problems(tmp_path)
    assert any("quotation" in problem for problem in found) and any("missing.html" in problem for problem in found)
