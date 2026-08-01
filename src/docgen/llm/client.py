"""Thin wrapper over the official Anthropic SDK.

API key strictly from the ANTHROPIC_API_KEY environment variable. Every call
is logged (purpose, prompt hash, token usage) to llm-log.jsonl in the output
folder — the only record of what left the machine, alongside redaction-log.md."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


class MissingApiKeyError(RuntimeError):
    pass


class LlmClient:
    def __init__(self, model: str, max_tokens: int, out_dir: Path):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise MissingApiKeyError(
                "ANTHROPIC_API_KEY is not set. Export it to use the LLM tier, or run with --no-llm."
            )
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key, max_retries=3)
        self.model = model
        self.max_tokens = max_tokens
        self._log_path = Path(out_dir) / "llm-log.jsonl"

    def complete(self, purpose: str, system: str, user: str) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        self._log(purpose, user, response, text)
        return text.strip()

    def _log(self, purpose: str, user_prompt: str, response, text: str) -> None:
        try:
            usage = getattr(response, "usage", None)
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "purpose": purpose,
                "model": self.model,
                "prompt_sha256": hashlib.sha256(user_prompt.encode("utf-8")).hexdigest(),
                "prompt_chars": len(user_prompt),
                "response_chars": len(text),
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            }
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(entry) + "\n")
        except OSError:
            pass  # logging must never fail a documentation run
