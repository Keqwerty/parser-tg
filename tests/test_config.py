from pathlib import Path

import pytest

from parser_tg.config import ConfigError, Settings, load_rules


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


def test_recipient_must_be_positive_numeric_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TG_API_ID", "123")
    monkeypatch.setenv("TG_API_HASH", "hash")
    monkeypatch.setenv("TG_RECIPIENT", "456")
    assert Settings.from_env().recipient == 456

    for value in ("@username", "-100123", "0"):
        monkeypatch.setenv("TG_RECIPIENT", value)
        with pytest.raises(ConfigError, match="positive numeric"):
            Settings.from_env()

    monkeypatch.delenv("TG_RECIPIENT")
    assert Settings.from_env(require_recipient=False).recipient == 0


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
