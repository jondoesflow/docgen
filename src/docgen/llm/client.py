"""Provider-agnostic LLM client layer.

LlmClient owns everything providers share: API-key resolution, call and token
accounting, and the llm-log.jsonl audit trail in the output folder — the only
record of what left the machine, alongside redaction-log.md. A subclass
implements _connect/_request for one provider's transport; create_client
dispatches on the provider configured in docgen.yaml (llm.provider).

Transports: AnthropicClient (native SDK), GeminiClient (google-genai SDK), and
OpenAICompatClient for every provider speaking the OpenAI chat-completions
dialect (OpenAI itself plus DeepSeek, Kimi, Mistral and xAI via base_url).

Prompt caching: the system prompt is the only content shared by every docgen
call (payload slices all differ), so on Anthropic it carries a cache_control
breakpoint — calls after the first read it from cache at ~0.1x the input
price. Anthropic silently skips caching below a model-dependent minimum
prefix (1,024 tokens on claude-sonnet-4-6), so on small system prompts this
is a no-op, never a cost. OpenAI, DeepSeek and Gemini cache server-side
automatically with no request opt-in; their cache-hit counts are captured
from the usage payload the same way. llm.cache: false in docgen.yaml turns
the Anthropic breakpoint off."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from docgen.llm.keys import resolve_api_key
from docgen.llm.registry import ProviderSpec, get_provider


class MissingApiKeyError(RuntimeError):
    pass


@dataclass
class CallUsage:
    """Token accounting for one completion call.

    input_tokens follows each provider's own convention (Anthropic excludes
    cached tokens from it; OpenAI-style providers include them) — docgen
    reports what the provider reports. cache_write_tokens is Anthropic-only;
    cache_read_tokens is filled for any provider that reports cache hits."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_write_tokens: int | None = None
    cache_read_tokens: int | None = None


class LlmClient:
    """Base class. Subclasses implement _connect() and _request()."""

    def __init__(self, spec: ProviderSpec, model: str, max_tokens: int, out_dir: Path,
                 cache_prompts: bool = True):
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
        self.cache_prompts = cache_prompts
        self._log_path = Path(out_dir) / "llm-log.jsonl"
        # Run totals for the end-of-run cost summary
        self.calls = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cache_write_tokens = 0
        self.total_cache_read_tokens = 0
        self._connect(api_key)

    def _connect(self, api_key: str) -> None:
        raise NotImplementedError

    def _request(self, system: str, user: str) -> tuple[str, CallUsage]:
        """One completion call: (text, usage)."""
        raise NotImplementedError

    def complete(self, purpose: str, system: str, user: str) -> str:
        text, usage = self._request(system, user)
        self._log(purpose, user, text, usage)
        return text.strip()

    def _log(self, purpose: str, user_prompt: str, text: str, usage: CallUsage) -> None:
        self.calls += 1
        self.total_input_tokens += usage.input_tokens or 0
        self.total_output_tokens += usage.output_tokens or 0
        self.total_cache_write_tokens += usage.cache_write_tokens or 0
        self.total_cache_read_tokens += usage.cache_read_tokens or 0
        try:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "purpose": purpose,
                "provider": self.spec.key,
                "model": self.model,
                "prompt_sha256": hashlib.sha256(user_prompt.encode("utf-8")).hexdigest(),
                "prompt_chars": len(user_prompt),
                "response_chars": len(text),
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_write_tokens": usage.cache_write_tokens,
                "cache_read_tokens": usage.cache_read_tokens,
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

    def _request(self, system: str, user: str) -> tuple[str, CallUsage]:
        if self.cache_prompts:
            # Prefix breakpoint on the (static) system prompt: every call in a
            # run shares it, so calls after the first read it at ~0.1x input
            # price once it clears the model's minimum cacheable size.
            system_param = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        else:
            system_param = system
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_param,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        usage = getattr(response, "usage", None)
        return text, CallUsage(
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", None),
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", None),
        )


class OpenAICompatClient(LlmClient):
    """OpenAI chat-completions dialect; base_url from the registry selects the
    provider (None = api.openai.com). Prompt caching is automatic and
    server-side on these providers — no request opt-in exists; cache hits are
    read back from the usage payload (OpenAI: prompt_tokens_details.cached_tokens,
    DeepSeek: prompt_cache_hit_tokens)."""

    def _connect(self, api_key: str) -> None:
        import openai

        self._client = openai.OpenAI(api_key=api_key, base_url=self.spec.base_url, max_retries=3)

    def _request(self, system: str, user: str) -> tuple[str, CallUsage]:
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
        details = getattr(usage, "prompt_tokens_details", None)
        cache_read = getattr(details, "cached_tokens", None)
        if cache_read is None:  # DeepSeek's automatic context caching
            cache_read = getattr(usage, "prompt_cache_hit_tokens", None)
        return text, CallUsage(
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            cache_read_tokens=cache_read,
        )


class GeminiClient(LlmClient):
    def _connect(self, api_key: str) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key)

    def _request(self, system: str, user: str) -> tuple[str, CallUsage]:
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
        return text, CallUsage(
            input_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
            cache_read_tokens=getattr(usage, "cached_content_token_count", None),
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
    return CLIENT_CLASSES[spec.key](
        spec, llm_cfg.model, llm_cfg.max_tokens, out_dir,
        cache_prompts=getattr(llm_cfg, "cache", True),
    )
