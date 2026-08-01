from pathlib import Path

import pytest

from docgen.config import ConfigError, DocgenConfig, load_config
from docgen.constants import ALL_DOC_KEYS


def test_defaults_when_no_file(tmp_path: Path):
    cfg = load_config(None, cwd=tmp_path)
    assert cfg == DocgenConfig()
    assert cfg.output_dir == Path("out")
    assert cfg.default_docs == list(ALL_DOC_KEYS)
    assert cfg.formats == ["md", "docx"]
    assert cfg.llm.model == "claude-sonnet-4-6"


def test_discovers_docgen_yaml_in_cwd(tmp_path: Path):
    (tmp_path / "docgen.yaml").write_text("output_dir: docs-out\nformats: [md]\n", encoding="utf-8")
    cfg = load_config(None, cwd=tmp_path)
    assert cfg.output_dir == Path("docs-out")
    assert cfg.formats == ["md"]
    # untouched keys keep defaults
    assert cfg.llm.enabled is True


def test_explicit_path_wins_over_cwd(tmp_path: Path):
    (tmp_path / "docgen.yaml").write_text("output_dir: from-cwd\n", encoding="utf-8")
    explicit = tmp_path / "other.yaml"
    explicit.write_text("output_dir: from-explicit\n", encoding="utf-8")
    cfg = load_config(explicit, cwd=tmp_path)
    assert cfg.output_dir == Path("from-explicit")


def test_explicit_missing_file_raises(tmp_path: Path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml", cwd=tmp_path)


def test_unknown_key_raises(tmp_path: Path):
    (tmp_path / "docgen.yaml").write_text("outptu_dir: typo\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="Invalid config"):
        load_config(None, cwd=tmp_path)


def test_empty_file_gives_defaults(tmp_path: Path):
    (tmp_path / "docgen.yaml").write_text("", encoding="utf-8")
    assert load_config(None, cwd=tmp_path) == DocgenConfig()


def test_non_mapping_yaml_raises(tmp_path: Path):
    (tmp_path / "docgen.yaml").write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="mapping"):
        load_config(None, cwd=tmp_path)


def test_example_config_in_repo_is_valid():
    repo_root = Path(__file__).parent.parent
    cfg = load_config(repo_root / "docgen.yaml")
    assert cfg.default_docs == list(ALL_DOC_KEYS)
