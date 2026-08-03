"""Multi-provider model switcher: registry routing, key precedence, YAML
round-trip, key hygiene, CLI. All mocked — no live provider calls."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from docgen.config import DocgenConfig
from docgen.llm import keys as keys_mod
from docgen.llm.client import (
    CLIENT_CLASSES,
    AnthropicClient,
    GeminiClient,
    OpenAICompatClient,
    create_client,
)
from docgen.llm.keys import (
    mask_key,
    read_env_file,
    resolve_api_key,
    store_key_in_env_file,
)
from docgen.llm.registry import PROVIDERS, UnknownProviderError, get_provider, parse_model_string
from docgen.modelcmd import write_llm_selection

runner = CliRunner()

ALL_ENV_VARS = [spec.env_var for spec in PROVIDERS.values()]


@pytest.fixture()
def no_keys_anywhere(monkeypatch, tmp_path):
    """No env vars, no keyring, empty cwd — key resolution finds nothing."""
    for var in ALL_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(keys_mod, "_keyring_get", lambda spec: None)
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Registry resolution: provider/model strings parse and route for every provider
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider_key", sorted(PROVIDERS))
def test_model_string_parses_and_routes(provider_key):
    spec, model = parse_model_string(f"{provider_key}/{PROVIDERS[provider_key].known_models[0]}")
    assert spec.key == provider_key
    assert model == PROVIDERS[provider_key].known_models[0]
    assert provider_key in CLIENT_CLASSES


def test_model_string_keeps_slashes_in_model():
    spec, model = parse_model_string("openai/ft:gpt-4o/custom")
    assert (spec.key, model) == ("openai", "ft:gpt-4o/custom")


@pytest.mark.parametrize("bad", ["", "anthropic", "/model", "anthropic/"])
def test_malformed_model_string_rejected(bad):
    with pytest.raises((ValueError, UnknownProviderError)):
        parse_model_string(bad)


@pytest.mark.parametrize("provider_key", sorted(PROVIDERS))
def test_create_client_dispatches_every_provider(provider_key, tmp_path, monkeypatch, no_keys_anywhere):
    spec = PROVIDERS[provider_key]
    monkeypatch.setenv(spec.env_var, "test-key-not-real")
    cfg = DocgenConfig()
    cfg.llm.provider = provider_key
    client = create_client(cfg.llm, tmp_path)
    assert isinstance(client, CLIENT_CLASSES[provider_key])
    assert client.spec.key == provider_key
    assert client.key_source == f"environment variable {spec.env_var}"


def test_openai_compatible_providers_use_registry_base_url():
    assert PROVIDERS["deepseek"].base_url == "https://api.deepseek.com/v1"
    assert PROVIDERS["kimi"].base_url == "https://api.moonshot.ai/v1"
    assert PROVIDERS["xai"].base_url == "https://api.x.ai/v1"
    assert PROVIDERS["mistral"].base_url == "https://api.mistral.ai/v1"
    assert PROVIDERS["openai"].base_url is None  # SDK default endpoint


def test_openai_compat_request_shape(tmp_path, monkeypatch, no_keys_anywhere):
    """Mock transport: correct message shape, text + usage extraction."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    cfg = DocgenConfig()
    cfg.llm.provider = "deepseek"
    cfg.llm.model = "deepseek-chat"
    client = create_client(cfg.llm, tmp_path)

    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="  prose  "))],
            usage=SimpleNamespace(prompt_tokens=42, completion_tokens=7),
        )

    client._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    assert client.complete("hld_overview", "SYS", "USER") == "prose"
    assert captured["model"] == "deepseek-chat"
    assert captured["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USER"},
    ]
    assert captured["max_tokens"] == cfg.llm.max_tokens  # deepseek keeps max_tokens
    assert (client.total_input_tokens, client.total_output_tokens) == (42, 7)


def test_openai_itself_uses_max_completion_tokens(tmp_path, monkeypatch, no_keys_anywhere):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    cfg = DocgenConfig()
    cfg.llm.provider = "openai"
    client = create_client(cfg.llm, tmp_path)
    captured = {}
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kw: captured.update(kw) or SimpleNamespace(choices=[], usage=None))))
    client.complete("p", "s", "u")
    assert "max_completion_tokens" in captured and "max_tokens" not in captured


def test_gemini_request_shape(tmp_path, monkeypatch, no_keys_anywhere):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    cfg = DocgenConfig()
    cfg.llm.provider = "gemini"
    cfg.llm.model = "gemini-2.5-flash"
    client = create_client(cfg.llm, tmp_path)
    captured = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            text="gemini prose",
            usage_metadata=SimpleNamespace(prompt_token_count=10, candidates_token_count=3),
        )

    client._client = SimpleNamespace(models=SimpleNamespace(generate_content=fake_generate))
    assert client.complete("p", "SYS", "USER") == "gemini prose"
    assert captured["model"] == "gemini-2.5-flash"
    assert captured["contents"] == "USER"
    assert captured["config"].system_instruction == "SYS"
    assert (client.total_input_tokens, client.total_output_tokens) == (10, 3)


# ---------------------------------------------------------------------------
# Key precedence: env var beats keyring beats .env; sources reported honestly
# ---------------------------------------------------------------------------


def test_env_var_beats_keyring_beats_env_file(monkeypatch, tmp_path):
    spec = get_provider("anthropic")
    store_key_in_env_file(spec, "from-dotenv-file", tmp_path)
    monkeypatch.setattr(keys_mod, "_keyring_get", lambda s: "from-keyring")
    monkeypatch.setenv(spec.env_var, "from-environment")

    assert resolve_api_key(spec, env_dir=tmp_path) == (
        "from-environment", f"environment variable {spec.env_var}")

    monkeypatch.delenv(spec.env_var)
    assert resolve_api_key(spec, env_dir=tmp_path) == ("from-keyring", "OS keyring")

    monkeypatch.setattr(keys_mod, "_keyring_get", lambda s: None)
    assert resolve_api_key(spec, env_dir=tmp_path) == ("from-dotenv-file", ".env file")

    (tmp_path / ".env").unlink()
    assert resolve_api_key(spec, env_dir=tmp_path) is None


def test_env_file_written_with_0600_and_gitignored(tmp_path):
    spec = get_provider("deepseek")
    path = store_key_in_env_file(spec, "secret-one", tmp_path)
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert (tmp_path / ".gitignore").read_text().splitlines() == [".env"]
    # update-in-place, other keys untouched, .gitignore not duplicated
    store_key_in_env_file(get_provider("xai"), "secret-two", tmp_path)
    store_key_in_env_file(spec, "secret-three", tmp_path)
    values = read_env_file(tmp_path)
    assert values["DEEPSEEK_API_KEY"] == "secret-three"
    assert values["XAI_API_KEY"] == "secret-two"
    assert (tmp_path / ".gitignore").read_text().splitlines() == [".env"]


def test_mask_key_shows_last_four_only():
    assert mask_key("sk-ant-abcdefghij1234") == "****1234"
    assert mask_key("short") == "****"


# ---------------------------------------------------------------------------
# YAML round-trip: model use updates llm: without disturbing the rest
# ---------------------------------------------------------------------------


def test_write_llm_selection_preserves_comments_and_content(tmp_path):
    config = tmp_path / "docgen.yaml"
    config.write_text(
        "# Engagement config — do not commit client names\n"
        "output_dir: out  # per-engagement output\n"
        "default_docs:\n"
        "  - hld  # always ship the HLD\n"
        "\n"
        "llm:\n"
        "  provider: anthropic\n"
        "  model: claude-sonnet-4-6\n"
        "  max_tokens: 4096  # keep narratives short\n",
        encoding="utf-8",
    )
    write_llm_selection(config, "deepseek", "deepseek-chat")
    text = config.read_text(encoding="utf-8")
    assert "# Engagement config — do not commit client names" in text
    assert "# per-engagement output" in text
    assert "# always ship the HLD" in text
    assert "# keep narratives short" in text
    assert "provider: deepseek" in text and "model: deepseek-chat" in text
    assert "max_tokens: 4096" in text

    from docgen.config import load_config

    cfg = load_config(config)
    assert (cfg.llm.provider, cfg.llm.model, cfg.llm.max_tokens) == ("deepseek", "deepseek-chat", 4096)


def test_write_llm_selection_creates_missing_file(tmp_path):
    config = tmp_path / "docgen.yaml"
    write_llm_selection(config, "gemini", "gemini-2.5-flash")
    from docgen.config import load_config

    cfg = load_config(config)
    assert (cfg.llm.provider, cfg.llm.model) == ("gemini", "gemini-2.5-flash")


def test_repo_example_config_round_trips_unchanged_apart_from_llm():
    """The shipped docgen.yaml survives a rewrite with only llm: touched."""
    import shutil
    import tempfile

    src = Path(__file__).resolve().parents[1] / "docgen.yaml"
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "docgen.yaml"
        shutil.copy(src, target)
        write_llm_selection(target, "anthropic", "claude-sonnet-4-6")
        before, after = src.read_text().strip(), target.read_text().strip()
        assert before == after  # same selection written back => byte-identical


# ---------------------------------------------------------------------------
# CLI + key hygiene
# ---------------------------------------------------------------------------


def _cli():
    from docgen.cli import app

    return app


def _all_output(result) -> str:
    out = result.output
    try:
        out += result.stderr
    except (AttributeError, ValueError):  # older click mixes stderr into output
        pass
    return out


def test_model_list_marks_active(no_keys_anywhere):
    result = runner.invoke(_cli(), ["model", "list"])
    assert result.exit_code == 0
    assert "* anthropic" in result.output
    assert "deepseek/deepseek-chat" in result.output


def test_model_use_unknown_provider_blocks(no_keys_anywhere):
    result = runner.invoke(_cli(), ["model", "use", "acme/gpt-1"])
    assert result.exit_code == 2
    assert "Unknown LLM provider" in _all_output(result)


def test_model_use_unknown_model_warns_but_proceeds(no_keys_anywhere):
    result = runner.invoke(_cli(), ["model", "use", "deepseek/deepseek-v99"])
    assert result.exit_code == 0
    assert "not in the known-models list" in result.output
    assert "provider: deepseek" in (no_keys_anywhere / "docgen.yaml").read_text()


def test_model_status_reports_source_and_masks_key(no_keys_anywhere, monkeypatch):
    secret = "sk-ant-verysecretkey-9876"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    result = runner.invoke(_cli(), ["model", "status"])
    assert result.exit_code == 0
    assert "environment variable ANTHROPIC_API_KEY" in result.output
    assert "****9876" in result.output
    assert secret not in result.output  # key hygiene: never echo the key


def test_model_status_no_key_names_env_var_and_fallbacks(no_keys_anywhere):
    result = runner.invoke(_cli(), ["model", "status"])
    assert result.exit_code == 0
    assert "ANTHROPIC_API_KEY" in result.output
    assert "docgen model key anthropic" in result.output
    assert "--no-llm" in result.output


def test_model_key_falls_back_to_env_file(no_keys_anywhere, monkeypatch):
    secret = "sk-ds-secret-abcd4321"
    monkeypatch.setattr(keys_mod, "store_key_in_keyring", lambda spec, value: False)
    monkeypatch.setattr("docgen.modelcmd.store_key_in_keyring", lambda spec, value: False)
    result = runner.invoke(_cli(), ["model", "key", "deepseek"], input=secret + "\n")
    assert result.exit_code == 0
    assert secret not in result.output  # hidden prompt, masked confirmation
    assert "****4321" in result.output
    assert read_env_file(no_keys_anywhere)["DEEPSEEK_API_KEY"] == secret
    assert ".env" in (no_keys_anywhere / ".gitignore").read_text()


def test_provider_error_paths_never_leak_key(no_keys_anywhere, built_fixtures, tmp_path, monkeypatch, capsys):
    """An API failure degrades to a placeholder without the key in any output."""
    from docgen.parsers import parse_solution

    snapshot = parse_solution(built_fixtures / "rich.zip")
    secret = "sk-ds-secret-leakcheck-7777"
    monkeypatch.setenv("DEEPSEEK_API_KEY", secret)
    cfg = DocgenConfig()
    cfg.llm.provider = "deepseek"
    client = create_client(cfg.llm, tmp_path)

    def explode(**kwargs):
        raise RuntimeError("401 unauthorized")

    client._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=explode)))

    from docgen.llm import make_narrative_provider

    provider = make_narrative_provider(snapshot, cfg, tmp_path, client=client)
    assert provider("hld_overview", {"x": 1}) is None
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err
    log = tmp_path / "llm-log.jsonl"
    if log.exists():
        assert secret not in log.read_text()


def test_no_llm_render_needs_no_keys_at_all(no_keys_anywhere, built_fixtures, tmp_path):
    """--no-llm end-to-end with every provider key absent."""
    from docgen.commands import render_documents
    from docgen.parsers import parse_solution

    snapshot = parse_solution(built_fixtures / "rich.zip")
    written = render_documents(snapshot, ["hld"], ["md"], tmp_path, DocgenConfig(), no_llm=True)
    assert written and (tmp_path / "hld.md").is_file()
