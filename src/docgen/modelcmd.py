"""Implementations for the `docgen model` command group.

list / use / key / status — provider and model selection is persisted in
docgen.yaml (comments preserved via ruamel.yaml); API keys are captured with a
hidden prompt and stored in the OS keyring, falling back to a git-ignored .env
file, never in the YAML. See docgen.llm.registry for the provider registry and
docgen.llm.keys for the resolution precedence."""

from __future__ import annotations

import os
from pathlib import Path

import typer

from docgen.config import DocgenConfig
from docgen.llm.keys import (
    ENV_FILE,
    mask_key,
    resolve_api_key,
    store_key_in_env_file,
    store_key_in_keyring,
)
from docgen.llm.registry import (
    PROVIDERS,
    UnknownProviderError,
    get_provider,
    parse_model_string,
)


def _config_target(explicit: Path | None) -> Path:
    return Path(explicit) if explicit is not None else Path.cwd() / "docgen.yaml"


def write_llm_selection(path: Path, provider: str, model: str) -> None:
    """Update llm.provider / llm.model in the YAML, preserving all other
    content and comments (round-trip via ruamel.yaml). Creates the file if
    it does not exist."""
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedMap

    yaml_rt = YAML()
    yaml_rt.preserve_quotes = True
    yaml_rt.indent(mapping=2, sequence=4, offset=2)  # matches the shipped docgen.yaml style
    data = yaml_rt.load(path.read_text(encoding="utf-8")) if path.is_file() else None
    if data is None:
        data = CommentedMap()
    llm = data.get("llm")
    if llm is None:
        llm = CommentedMap()
        data["llm"] = llm
    llm["provider"] = provider
    llm["model"] = model
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        yaml_rt.dump(data, handle)


def run_model_list(cfg: DocgenConfig) -> None:
    """Providers + example model strings, active selection marked."""
    for key in sorted(PROVIDERS):
        spec = PROVIDERS[key]
        active = key == cfg.llm.provider
        marker = "*" if active else " "
        line = f"{marker} {key:<10} {spec.display_name:<20} key: {spec.env_var}"
        typer.secho(line, fg=typer.colors.CYAN if active else None)
        examples = ", ".join(f"{key}/{m}" for m in spec.known_models[:3])
        typer.echo(f"             e.g. {examples}")
    typer.echo(f"\nActive: {cfg.llm.provider}/{cfg.llm.model}  (switch with `docgen model use <provider>/<model>`)")


def run_model_use(selection: str, config_path: Path | None) -> None:
    """Validate provider, warn on unknown model string, persist to docgen.yaml."""
    try:
        spec, model = parse_model_string(selection)
    except (UnknownProviderError, ValueError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    if not any(model == known or model.startswith(known) for known in spec.known_models):
        typer.secho(
            f"  Note: {model!r} is not in the known-models list for {spec.display_name} "
            f"({', '.join(spec.known_models)}). Proceeding anyway — new models ship "
            "faster than registries update.",
            fg=typer.colors.YELLOW,
        )

    target = _config_target(config_path)
    write_llm_selection(target, spec.key, model)
    typer.echo(f"Active model set to {spec.key}/{model} in {target}")
    if resolve_api_key(spec) is None:
        typer.secho(
            f"  No API key found for {spec.display_name} yet. Set {spec.env_var} or run "
            f"`docgen model key {spec.key}`. (--no-llm runs need no key.)",
            fg=typer.colors.YELLOW,
        )


def run_model_key(provider: str) -> None:
    """Secure hidden prompt -> OS keyring, falling back to a git-ignored .env."""
    import getpass

    try:
        spec = get_provider(provider)
    except UnknownProviderError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    value = getpass.getpass(f"API key for {spec.display_name} (input hidden): ").strip()
    if not value:
        typer.secho("No key entered — nothing stored.", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=1)

    if store_key_in_keyring(spec, value):
        typer.echo(f"Stored key for {spec.display_name} ({mask_key(value)}) in the OS keyring.")
    else:
        path = store_key_in_env_file(spec, value)
        typer.secho(
            f"No OS keyring available — stored key for {spec.display_name} "
            f"({mask_key(value)}) in {path} (permissions 0600, git-ignored). "
            "Anyone with read access to this file can read the key; prefer a "
            "keyring-capable environment or a real environment variable where possible.",
            fg=typer.colors.YELLOW,
        )
    env_value = os.environ.get(spec.env_var)
    if env_value and env_value != value:
        typer.secho(
            f"  Note: {spec.env_var} is currently set in this shell and takes precedence "
            "over the stored key.",
            fg=typer.colors.YELLOW,
        )


def run_model_status(cfg: DocgenConfig) -> None:
    """Active provider/model and where its key resolves from (masked)."""
    try:
        spec = get_provider(cfg.llm.provider)
    except UnknownProviderError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    typer.echo(f"Active provider: {spec.display_name} ({spec.key})")
    typer.echo(f"Active model:    {cfg.llm.model}")
    typer.echo(f"LLM tier:        {'enabled' if cfg.llm.enabled else 'disabled in config'}")
    resolved = resolve_api_key(spec)
    if resolved is None:
        typer.secho(
            f"API key:         not found — set {spec.env_var}, or run "
            f"`docgen model key {spec.key}` (checked: environment, OS keyring, {ENV_FILE}). "
            "--no-llm runs work without a key.",
            fg=typer.colors.YELLOW,
        )
    else:
        value, source = resolved
        typer.echo(f"API key:         {mask_key(value)} from {source}")
