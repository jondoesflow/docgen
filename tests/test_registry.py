"""Provider registry + client factory tests (phase 1: Anthropic only, no network)."""

from pathlib import Path

import pytest

from docgen.config import ConfigError, DocgenConfig, load_config
from docgen.llm.client import AnthropicClient, CLIENT_CLASSES, MissingApiKeyError, create_client
from docgen.llm.registry import PROVIDERS, UnknownProviderError, get_provider


def test_get_provider_anthropic():
    spec = get_provider("anthropic")
    assert spec.display_name == "Anthropic"
    assert spec.env_var == "ANTHROPIC_API_KEY"


def test_get_provider_unknown_raises():
    with pytest.raises(UnknownProviderError) as exc:
        get_provider("acme-ai")
    assert "acme-ai" in str(exc.value)
    assert "anthropic" in str(exc.value)  # lists supported providers


def test_every_provider_has_a_client_class():
    assert set(PROVIDERS) == set(CLIENT_CLASSES)


def test_config_default_provider_is_anthropic():
    assert DocgenConfig().llm.provider == "anthropic"


def test_config_rejects_unknown_provider(tmp_path: Path):
    cfg_file = tmp_path / "docgen.yaml"
    cfg_file.write_text("llm:\n  provider: acme-ai\n", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_config(cfg_file)
    assert "acme-ai" in str(exc.value)


def test_repo_example_config_loads():
    example = Path(__file__).resolve().parents[1] / "docgen.yaml"
    cfg = load_config(example)
    assert cfg.llm.provider == "anthropic"


def test_create_client_missing_key_message(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(MissingApiKeyError) as exc:
        create_client(DocgenConfig().llm, tmp_path)
    message = str(exc.value)
    assert "ANTHROPIC_API_KEY" in message  # names the exact env var
    assert "--no-llm" in message  # reminds about the offline path


def test_create_client_dispatches_to_anthropic(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    client = create_client(DocgenConfig().llm, tmp_path)
    assert isinstance(client, AnthropicClient)
    assert client.spec.key == "anthropic"
    assert client.key_source == "environment variable ANTHROPIC_API_KEY"
    assert client.model == "claude-sonnet-4-6"
