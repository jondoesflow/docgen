"""Anonymisation pass applied to every payload before it reaches the Anthropic
API, driven by redact.yaml. Named replacements are reversed in responses so
local documents show real names while the API only ever sees placeholders.
Regex patterns are one-way. Every substitution is logged to the output folder."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class RedactionEvent:
    rule: str
    count: int


@dataclass
class Redactor:
    replacements: list[tuple[str, str]] = field(default_factory=list)  # (match, replace)
    patterns: list[tuple[re.Pattern, str]] = field(default_factory=list)
    events: list[RedactionEvent] = field(default_factory=list)

    @classmethod
    def from_file(cls, path: Path | None) -> "Redactor":
        if path is None or not Path(path).is_file():
            return cls()
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        replacements = [(str(r["match"]), str(r["replace"]))
                        for r in data.get("replacements", []) if r.get("match") and r.get("replace")]
        patterns = []
        for p in data.get("patterns", []):
            if p.get("regex"):
                try:
                    patterns.append((re.compile(p["regex"]), str(p.get("replace", "[REDACTED]"))))
                except re.error:
                    continue
        return cls(replacements=replacements, patterns=patterns)

    def redact(self, text: str) -> str:
        for match, replace in self.replacements:
            count = text.count(match)
            if count:
                text = text.replace(match, replace)
                self.events.append(RedactionEvent(rule=f"replace {match!r} -> {replace!r}", count=count))
        for pattern, replace in self.patterns:
            text, count = pattern.subn(replace, text)
            if count:
                self.events.append(RedactionEvent(rule=f"pattern /{pattern.pattern}/ -> {replace!r}", count=count))
        return text

    def unredact(self, text: str) -> str:
        """Reverse the named replacements (patterns are irreversible by design)."""
        for match, replace in reversed(self.replacements):
            text = text.replace(replace, match)
        return text

    def write_log(self, out_dir: Path) -> Path | None:
        log_path = Path(out_dir) / "redaction-log.md"
        lines = ["# Redaction log", "",
                 "Substitutions applied to snapshot content before it was sent to the Anthropic API.", ""]
        if not self.replacements and not self.patterns:
            lines.append("No redaction rules configured (no redact.yaml).")
        elif not self.events:
            lines.append("Redaction rules were configured but nothing matched in the content sent.")
        else:
            totals: dict[str, int] = {}
            for event in self.events:
                totals[event.rule] = totals.get(event.rule, 0) + event.count
            lines.append("| Rule | Substitutions |")
            lines.append("| --- | --- |")
            for rule, count in totals.items():
                lines.append(f"| {rule} | {count} |")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        return log_path
