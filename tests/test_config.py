from pathlib import Path

import pytest

from parser_tg.config import ConfigError, load_rules


def test_load_rules(tmp_path: Path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text(
        """
version: 1
sources: ["@one", -100123]
filters:
  - id: gpu
    aliases: ["видеокарта", "rtx 4070"]
    require_any: ["nvidia", "amd"]
    fuzzy_threshold: 91
    exclude: ["чехол"]
""",
        encoding="utf-8",
    )
    rules = load_rules(path)
    assert rules.sources == ("@one", -100123)
    assert rules.filters[0].fuzzy_threshold == 91
    assert rules.filters[0].require_any == ("nvidia", "amd")


def test_empty_filters_enable_match_all_configuration(tmp_path: Path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text("version: 1\nsources: ['@one']\nfilters: []\n", encoding="utf-8")
    rules = load_rules(path)
    assert rules.filters == ()


@pytest.mark.parametrize(
    "body, error",
    [
        ("version: 2\nsources: ['@one']\nfilters: []\n", "version"),
        ("version: 1\nsources: []\nfilters: []\n", "sources"),
        (
            "version: 1\nsources: ['@one']\nfilters:\n  - id: Bad ID\n    aliases: [cpu]\n",
            "id",
        ),
    ],
)
def test_reject_invalid_rules(tmp_path: Path, body: str, error: str) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(ConfigError, match=error):
        load_rules(path)
