"""Optional live verification of deprecation rules against Microsoft Learn.

`--check-learn` fetches each deprecation rule's learn_url and reports whether
the reference is still reachable — a cheap freshness signal for
rules/deprecations.yaml. Purely additive: network failures are reported, never
fatal, and nothing else in docgen depends on this module.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

_TIMEOUT_SECONDS = 10
_USER_AGENT = "docgen-learn-check (documentation tooling; deprecation rule verification)"


@dataclass
class LearnCheckResult:
    rule_id: str
    title: str
    url: str
    status: str  # ok | unreachable | no_url
    detail: str = ""


def check_rule_urls(deprecation_rules: dict) -> list[LearnCheckResult]:
    results: list[LearnCheckResult] = []
    for rule in deprecation_rules.get("deprecations", []):
        rule_id = rule.get("id", "DEP-?")
        title = rule.get("title", "")
        url = rule.get("learn_url")
        if not url:
            results.append(LearnCheckResult(rule_id, title, "", "no_url",
                                            "rule has no learn_url to verify"))
            continue
        try:
            request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT}, method="GET")
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                code = getattr(response, "status", 200)
            results.append(LearnCheckResult(rule_id, title, url, "ok", f"HTTP {code}"))
        except urllib.error.HTTPError as exc:
            results.append(LearnCheckResult(rule_id, title, url, "unreachable", f"HTTP {exc.code}"))
        except Exception as exc:
            results.append(LearnCheckResult(rule_id, title, url, "unreachable", str(exc)))
    return results


def write_report(results: list[LearnCheckResult], out_dir: Path) -> Path:
    lines = ["# Microsoft Learn deprecation-rule check", ""]
    if not results:
        lines.append("No deprecation rules configured.")
    else:
        ok = sum(1 for r in results if r.status == "ok")
        lines.append(
            f"{len(results)} rule(s) checked: {ok} reference(s) reachable, "
            f"{sum(1 for r in results if r.status == 'unreachable')} unreachable, "
            f"{sum(1 for r in results if r.status == 'no_url')} without a URL."
        )
        lines += ["", "Unreachable references may mean the Learn page moved — review whether the "
                      "rule is still current and update rules/deprecations.yaml.", "",
                  "| Rule | Title | Status | Detail | URL |", "| --- | --- | --- | --- | --- |"]
        for r in results:
            lines.append(f"| {r.rule_id} | {r.title} | {r.status} | {r.detail} | {r.url} |")
    path = Path(out_dir) / "learn-check.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path
