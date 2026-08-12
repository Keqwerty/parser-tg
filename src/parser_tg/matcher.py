from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

from parser_tg.config import FilterRule

_SEPARATOR_RE = re.compile(r"[^\w]+", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")
_NUMBER_RE = re.compile(r"\d+")
_LETTER_DIGIT_RE = re.compile(r"(?<=[^\W\d_])(?=\d)|(?<=\d)(?=[^\W\d_])", re.UNICODE)


def normalize(text: str) -> str:
    """Normalize natural-language product text while retaining model numbers."""
    text = (
        unicodedata.normalize("NFKC", text)
        .casefold()
        .replace("\N{CYRILLIC SMALL LETTER IO}", "\N{CYRILLIC SMALL LETTER IE}")
    )
    text = _LETTER_DIGIT_RE.sub(" ", text)
    text = _SEPARATOR_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()


@dataclass(frozen=True, slots=True)
class Match:
    filter_id: str
    alias: str
    score: float
    exact: bool


@dataclass(frozen=True, slots=True)
class _PreparedRule:
    source: FilterRule
    aliases: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...]
    excludes: tuple[str, ...]
    require_any: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...]


class Matcher:
    def __init__(self, rules: tuple[FilterRule, ...]) -> None:
        self._rules = tuple(self._prepare(rule) for rule in rules)

    def match(self, text: str) -> tuple[Match, ...]:
        if not self._rules:
            return (Match("all", "*", 100.0, True),)
        normalized = normalize(text)
        if not normalized:
            return ()
        tokens = tuple(normalized.split())
        padded = f" {normalized} "
        matches: list[Match] = []
        for rule in self._rules:
            if any(f" {excluded} " in padded for excluded in rule.excludes):
                continue
            best = self._best_match(
                rule.source.id,
                rule.aliases,
                tokens,
                padded,
                rule.source.fuzzy_threshold,
            )
            if best is not None:
                if (
                    rule.require_any
                    and self._best_match(
                        rule.source.id,
                        rule.require_any,
                        tokens,
                        padded,
                        rule.source.fuzzy_threshold,
                    )
                    is None
                ):
                    continue
                matches.append(best)
        return tuple(matches)

    @staticmethod
    def _prepare(rule: FilterRule) -> _PreparedRule:
        aliases = Matcher._prepare_phrases(rule.aliases)
        require_any = Matcher._prepare_phrases(rule.require_any)
        excludes = tuple(value for item in rule.exclude if (value := normalize(item)))
        return _PreparedRule(rule, aliases, excludes, require_any)

    @staticmethod
    def _prepare_phrases(
        phrases: tuple[str, ...],
    ) -> tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...]:
        prepared = []
        for phrase in phrases:
            normalized = normalize(phrase)
            if not normalized:
                continue
            tokens = tuple(normalized.split())
            prepared.append((phrase, tokens, tuple(_NUMBER_RE.findall(normalized))))
        return tuple(prepared)

    @staticmethod
    def _best_match(
        filter_id: str,
        phrases: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...],
        text_tokens: tuple[str, ...],
        padded_text: str,
        threshold: int,
    ) -> Match | None:
        best: Match | None = None
        for original, phrase_tokens, phrase_numbers in phrases:
            phrase = " ".join(phrase_tokens)
            if f" {phrase} " in padded_text:
                candidate = Match(filter_id, original, 100.0, True)
            else:
                score = Matcher._fuzzy_score(text_tokens, phrase_tokens, phrase_numbers)
                if score < threshold:
                    continue
                candidate = Match(filter_id, original, score, False)
            if best is None or candidate.score > best.score:
                best = candidate
        return best

    @staticmethod
    def _fuzzy_score(
        text_tokens: tuple[str, ...],
        alias_tokens: tuple[str, ...],
        alias_numbers: tuple[str, ...],
    ) -> float:
        if not text_tokens or not alias_tokens:
            return 0.0
        width = len(alias_tokens)
        best = 0.0
        # Equal-width windows keep fuzzy matching local and predictable. A typo may
        # alter letters, but numeric model components must remain exactly equal.
        for start in range(0, len(text_tokens) - width + 1):
            window_tokens = text_tokens[start : start + width]
            window = " ".join(window_tokens)
            window_numbers = tuple(_NUMBER_RE.findall(window))
            if window_numbers != alias_numbers:
                continue
            best = max(best, fuzz.ratio(" ".join(alias_tokens), window))
        return best
