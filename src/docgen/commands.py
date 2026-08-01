"""Command implementations behind the CLI. Milestone stubs are replaced as parsers
and renderers land; keeping them here keeps cli.py purely about argument handling."""

from __future__ import annotations

from pathlib import Path

import typer

from docgen.config import DocgenConfig


def run_parse(solution_zip: Path, out_dir: Path) -> None:
    typer.secho("`docgen parse` is not implemented yet (milestone 2).", fg=typer.colors.YELLOW, err=True)
    raise typer.Exit(code=3)


def run_render(
    snapshot_path: Path,
    doc_keys: list[str],
    formats: list[str],
    out_dir: Path,
    cfg: DocgenConfig,
    *,
    no_llm: bool,
) -> None:
    typer.secho("`docgen render` is not implemented yet (milestone 3).", fg=typer.colors.YELLOW, err=True)
    raise typer.Exit(code=3)


def run_diff(old_path: Path, new_path: Path, formats: list[str], out_dir: Path, cfg: DocgenConfig) -> None:
    typer.secho("`docgen diff` is not implemented yet (milestone 5).", fg=typer.colors.YELLOW, err=True)
    raise typer.Exit(code=3)


def run_check(snapshot_path: Path, out_dir: Path, cfg: DocgenConfig) -> None:
    typer.secho("`docgen check` is not implemented yet (milestone 4).", fg=typer.colors.YELLOW, err=True)
    raise typer.Exit(code=3)


def run_all(
    solution_zip: Path,
    doc_keys: list[str],
    formats: list[str],
    out_dir: Path,
    cfg: DocgenConfig,
    *,
    no_llm: bool,
) -> None:
    typer.secho("`docgen all` is not implemented yet (milestone 6).", fg=typer.colors.YELLOW, err=True)
    raise typer.Exit(code=3)
