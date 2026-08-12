from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when application configuration is invalid."""


@dataclass(frozen=True, slots=True)
class FilterRule:
    id: str
    aliases: tuple[str, ...]
    fuzzy_threshold: int = 90
    exclude: tuple[str, ...] = ()
    require_any: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RulesConfig:
    sources: tuple[str | int, ...]
    filters: tuple[FilterRule, ...]


@dataclass(frozen=True, slots=True)
class Settings:
    api_id: int
    api_hash: str
    recipient: str | int
    session_path: Path
    config_path: Path
    state_path: Path
    health_path: Path
    log_level: str

    @classmethod
    def from_env(cls, *, require_recipient: bool = True) -> Settings:
        api_id_raw = _required_env("TG_API_ID")
        try:
            api_id = int(api_id_raw)
        except ValueError as exc:
            raise ConfigError("TG_API_ID must be an integer") from exc
        if api_id <= 0:
            raise ConfigError("TG_API_ID must be positive")

        recipient_raw = (
            _required_env("TG_RECIPIENT") if require_recipient else os.getenv("TG_RECIPIENT", "me")
        )
        recipient = _parse_peer(recipient_raw)
        session_path = Path(os.getenv("TG_SESSION_PATH", "/data/reader.session"))
        return cls(
            api_id=api_id,
            api_hash=_required_env("TG_API_HASH"),
            recipient=recipient,
            session_path=session_path,
            config_path=Path(os.getenv("CONFIG_PATH", "/app/config/rules.yaml")),
            state_path=Path(os.getenv("STATE_PATH", "/data/state.sqlite3")),
            health_path=Path(os.getenv("HEALTH_PATH", "/data/healthy")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )


def load_rules(path: Path) -> RulesConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read rules file {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("rules root must be a mapping")
    if raw.get("version") != 1:
        raise ConfigError("rules version must be 1")

    sources_raw = raw.get("sources")
    if not isinstance(sources_raw, list) or not sources_raw:
        raise ConfigError("sources must be a non-empty list")
    sources: list[str | int] = []
    for index, source in enumerate(sources_raw):
        if isinstance(source, int):
            sources.append(source)
        elif isinstance(source, str) and source.strip():
            sources.append(_parse_peer(source.strip()))
        else:
            raise ConfigError(f"sources[{index}] must be a username or numeric ID")
    if len(set(sources)) != len(sources):
        raise ConfigError("sources must not contain duplicates")

    filters_raw = raw.get("filters")
    if not isinstance(filters_raw, list):
        raise ConfigError("filters must be a list")
    filters = tuple(_parse_filter(value, index) for index, value in enumerate(filters_raw))
    ids = [rule.id for rule in filters]
    if len(set(ids)) != len(ids):
        raise ConfigError("filter ids must be unique")

    return RulesConfig(sources=tuple(sources), filters=filters)


def _parse_filter(raw: Any, index: int) -> FilterRule:
    label = f"filters[{index}]"
    if not isinstance(raw, dict):
        raise ConfigError(f"{label} must be a mapping")
    rule_id = raw.get("id")
    if not isinstance(rule_id, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", rule_id):
        raise ConfigError(f"{label}.id must match [a-z][a-z0-9_-]{{0,63}}")

    aliases = _string_list(raw.get("aliases"), f"{label}.aliases", required=True)
    excludes = _string_list(raw.get("exclude", []), f"{label}.exclude", required=False)
    require_any = _string_list(raw.get("require_any", []), f"{label}.require_any", required=False)
    threshold = raw.get("fuzzy_threshold", 90)
    if isinstance(threshold, bool) or not isinstance(threshold, int) or not 0 <= threshold <= 100:
        raise ConfigError(f"{label}.fuzzy_threshold must be an integer from 0 to 100")
    return FilterRule(rule_id, aliases, threshold, excludes, require_any)


def _string_list(raw: Any, label: str, *, required: bool) -> tuple[str, ...]:
    if not isinstance(raw, list) or (required and not raw):
        qualifier = "non-empty " if required else ""
        raise ConfigError(f"{label} must be a {qualifier}list")
    values: list[str] = []
    for index, value in enumerate(raw):
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"{label}[{index}] must be a non-empty string")
        values.append(value.strip())
    if len(set(values)) != len(values):
        raise ConfigError(f"{label} must not contain duplicates")
    return tuple(values)


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigError(f"environment variable {name} is required")
    return value


def _parse_peer(value: str) -> str | int:
    value = value.strip()
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value
