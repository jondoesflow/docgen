"""Prompt caching: request shape, cache-usage accounting, cache-aware cost
estimates. All mocked — no live calls."""

from types import SimpleNamespace

import pytest

from docgen.config import DocgenConfig
from docgen.llm import keys as keys_mod
from docgen.llm.client import create_client
from docgen.llm.pricing import estimate_cost, usage_summary_line


@pytest.fixture()
def isolated_keys(monkeypatch, tmp_path):
    monkeypatch.setattr(keys_mod, "_keyring_get", lambda spec: None)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _anthropic_client(tmp_path, monkeypatch, *, cache: bool):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    cfg = DocgenConfig()
    cfg.llm.cache = cache
    return create_client(cfg.llm, tmp_path)


def _fake_anthropic_response(**usage):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text="prose")],
        usage=SimpleNamespace(
            input_tokens=usage.get("input_tokens", 100),
            output_tokens=usage.get("output_tokens", 20),
            cache_creation_input_tokens=usage.get("cache_creation_input_tokens", 0),
            cache_read_input_tokens=usage.get("cache_read_input_tokens", 0),
        ),
    )


def test_anthropic_system_prompt_carries_cache_breakpoint(tmp_path, monkeypatch, isolated_keys):
    client = _anthropic_client(tmp_path, monkeypatch, cache=True)
    captured = {}
    client._client = SimpleNamespace(messages=SimpleNamespace(
        create=lambda **kw: captured.update(kw) or _fake_anthropic_response()))
    client.complete("hld_overview", "SYSTEM PROMPT", "USER")
    assert captured["system"] == [
        {"type": "text", "text": "SYSTEM PROMPT", "cache_control": {"type": "ephemeral"}}
    ]


def test_cache_disabled_sends_plain_system_string(tmp_path, monkeypatch, isolated_keys):
    client = _anthropic_client(tmp_path, monkeypatch, cache=False)
    captured = {}
    client._client = SimpleNamespace(messages=SimpleNamespace(
        create=lambda **kw: captured.update(kw) or _fake_anthropic_response()))
    client.complete("hld_overview", "SYSTEM PROMPT", "USER")
    assert captured["system"] == "SYSTEM PROMPT"


def test_cache_usage_accumulated_and_logged(tmp_path, monkeypatch, isolated_keys):
    client = _anthropic_client(tmp_path, monkeypatch, cache=True)
    responses = iter([
        _fake_anthropic_response(cache_creation_input_tokens=1200, cache_read_input_tokens=0),
        _fake_anthropic_response(cache_creation_input_tokens=0, cache_read_input_tokens=1200),
    ])
    client._client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: next(responses)))
    client.complete("first", "SYS", "U1")
    client.complete("second", "SYS", "U2")
    assert client.total_cache_write_tokens == 1200
    assert client.total_cache_read_tokens == 1200
    import json

    entries = [json.loads(line) for line in (tmp_path / "llm-log.jsonl").read_text().splitlines()]
    assert entries[0]["cache_write_tokens"] == 1200
    assert entries[1]["cache_read_tokens"] == 1200


def test_openai_and_deepseek_cache_hits_captured(tmp_path, monkeypatch, isolated_keys):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    cfg = DocgenConfig()
    cfg.llm.provider = "deepseek"
    client = create_client(cfg.llm, tmp_path)

    def deepseek_style(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="x"))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=5,
                                  prompt_cache_hit_tokens=64),
        )

    client._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=deepseek_style)))
    client.complete("p", "s", "u")
    assert client.total_cache_read_tokens == 64

    def openai_style(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="x"))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=5,
                                  prompt_tokens_details=SimpleNamespace(cached_tokens=32)),
        )

    client._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=openai_style)))
    client.complete("p", "s", "u")
    assert client.total_cache_read_tokens == 64 + 32


def test_estimate_cost_applies_cache_multipliers():
    # sonnet-4-6: $3/MTok input. 1M cache-write = 1.25x, 1M cache-read = 0.1x.
    plain = estimate_cost("claude-sonnet-4-6", 1_000_000, 0)
    written = estimate_cost("claude-sonnet-4-6", 0, 0, cache_write_tokens=1_000_000)
    read = estimate_cost("claude-sonnet-4-6", 0, 0, cache_read_tokens=1_000_000)
    assert plain == 3.00
    assert written == pytest.approx(3.75)
    assert read == pytest.approx(0.30)


def test_summary_line_reports_cache_traffic():
    line = usage_summary_line("claude-sonnet-4-6", 9, 10_000, 4_000,
                              cache_write_tokens=1_200, cache_read_tokens=9_600)
    assert "prompt cache: 1,200 written + 9,600 read" in line
    assert "estimated cost $" in line
    # and stays silent when caching never engaged
    quiet = usage_summary_line("claude-sonnet-4-6", 9, 10_000, 4_000)
    assert "prompt cache" not in quiet
