"""--check-learn: mocked (no network) verification of the Learn reference checker."""

import urllib.request
from pathlib import Path

from docgen.config import DocgenConfig
from docgen.learn_check import check_rule_urls, write_report
from docgen.rules_io import load_rules


class _FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_all_shipped_rules_have_urls_and_report_ok(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: _FakeResponse())
    rules = load_rules(DocgenConfig())["deprecations"]
    results = check_rule_urls(rules)
    assert results and all(r.status == "ok" for r in results)
    report = write_report(results, tmp_path)
    text = report.read_text(encoding="utf-8")
    assert "DEP-001" in text and "reachable" in text


def test_unreachable_url_reported_not_fatal(monkeypatch, tmp_path: Path):
    def boom(req, timeout=0):
        raise OSError("no network")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    rules = {"deprecations": [{"id": "DEP-X", "title": "Test", "learn_url": "https://learn.microsoft.com/x"}]}
    results = check_rule_urls(rules)
    assert results[0].status == "unreachable"
    text = write_report(results, tmp_path).read_text(encoding="utf-8")
    assert "unreachable" in text


def test_rule_without_url_reported():
    results = check_rule_urls({"deprecations": [{"id": "DEP-Y", "title": "No URL"}]})
    assert results[0].status == "no_url"
