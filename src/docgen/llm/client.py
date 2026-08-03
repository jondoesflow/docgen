"""Provider-agnostic LLM client layer.

LlmClient owns everything providers share: API-key resolution, call and token
accounting, and the llm-log.jsonl audit trail in the output folder — the only
record of what left the machine, alongside redaction-log.md. A subclass
implements _connect/_request for one provider's transport; create_client
dispatches on the provider configured in docgen.yaml (llm.provider).

Transports: AnthropicClient (native SDK), GeminiClient (google-genai SDK), and
OpenAICompatClient for every provider speaking the OpenAI chat-completions
dialect (OpenAI itself plus DeepSeek, Kimi, Mistral and xAI via base_url)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from docgen.llm.keys import resolve_api_key
from docgen.llm.registry import ProviderSpec, get_provider


class MissingApiKeyError(RuntimeError):
    pass


class LlmClient:
    """Base class. Subclasses implement _connect() and _request()."""

    def __init__(self, spec: ProviderSpec, model: str, max_tokens: int, out_dir: Path):
        resolved = resolve_api_key(spec)
        if resolved is None:
            raise MissingApiKeyError(
                f"No API key found for {spec.display_name}. Set the {spec.env_var} "
                f"environment variable, or store a key with `docgen model key {spec.key}`. "
                "Running with --no-llm still works fully offline."
            )
        api_key, self.key_source = resolved
        self.spec = spec
        self.model = model
        self.max_tokens = max_tokens
        self._log_path = Path(out_dir) / "llm-log.jsonl"
        # Run totals for the end-of-run cost summary
        self.calls = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self._connect(api_key)

    def _connect(self, api_key: str) -> None:
        raise NotImplementedError

    def _request(self, system: str, user: str) -> tuple[str, int | None, int | None]:
        """One completion call: (text, input_tokens, output_tokens)."""
        raise NotImplementedError

    def complete(self, purpose: str, system: str, user: str) -> str:
        text, input_tokens, output_tokens = self._request(system, user)
        self._log(purpose, user, text, input_tokens, output_tokens)
        return text.strip()

    def _log(self, purpose: str, user_prompt: str, text: str,
             input_tokens: int | None, output_tokens: int | None) -> None:
        self.calls += 1
        self.total_input_tokens += input_tokens or 0
        self.total_output_tokens += output_tokens or 0
        try:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "purpose": purpose,
                "provider": self.spec.key,
                "model": self.model,
                "prompt_sha256": hashlib.sha256(user_prompt.encode("utf-8")).hexdigest(),
                "prompt_chars": len(user_prompt),
                "response_chars": len(text),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(entry) + "\n")
        except OSError:
            pass  # logging must never fail a documentation run


class AnthropicClient(LlmClient):
    def _connect(self, api_key: str) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key, max_retries=3)

    def _request(self, system: str, user: str) -> tuple[str, int | None, int | None]:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        usage = getattr(response, "usage", None)
        return text, getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None)


class OpenAICompatClient(LlmClient):
    """OpenAI chat-completions dialect; base_url from the registry selects the
    provider (None = api.openai.com)."""

    def _connect(self, api_key: str) -> None:
        import openai

        self._client = openai.OpenAI(api_key=api_key, base_url=self.spec.base_url, max_retries=3)

    def _request(self, system: str, user: str) -> tuple[str, int | None, int | None]:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            **{self.spec.max_tokens_param: self.max_tokens},
        )
        choice = response.choices[0] if getattr(response, "choices", None) else None
        text = (getattr(getattr(choice, "message", None), "content", None) or "") if choice else ""
        usage = getattr(response, "usage", None)
        return text, getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None)


class GeminiClient(LlmClient):
    def _connect(self, api_key: str) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key)

    def _request(self, system: str, user: str) -> tuple[str, int | None, int | None]:
        from google.genai import types

        response = self._client.models.generate_content(
            model=self.model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=self.max_tokens,
            ),
        )
        text = getattr(response, "text", None) or ""
        usage = getattr(response, "usage_metadata", None)
        return (
            text,
            getattr(usage, "prompt_token_count", None),
            getattr(usage, "candidates_token_count", None),
        )


# provider key -> client class; every PROVIDERS entry must have one
CLIENT_CLASSES: dict[str, type[LlmClient]] = {
    "anthropic": AnthropicClient,
    "openai": OpenAICompatClient,
    "deepseek": OpenAICompatClient,
    "kimi": OpenAICompatClient,
    "gemini": GeminiClient,
    "mistral": OpenAICompatClient,
    "xai": OpenAICompatClient,
}


def create_client(llm_cfg, out_dir: Path) -> LlmClient:
    """Build the client for the configured provider (llm.provider in docgen.yaml)."""
    spec = get_provider(llm_cfg.provider)
    return CLIENT_CLASSES[spec.key](spec, llm_cfg.model, llm_cfg.max_tokens, out_dir)
