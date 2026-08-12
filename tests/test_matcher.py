from parser_tg.config import FilterRule
from parser_tg.matcher import Matcher, normalize


def test_normalize_unicode_punctuation_and_model_boundaries() -> None:
    assert normalize("  ВИДЕОКАРТА — RTX4070-Ti, 16GB! ") == "видеокарта rtx 4070 ti 16 gb"
    assert normalize("Ёж") == "еж"


def test_exact_and_fuzzy_match() -> None:
    matcher = Matcher(
        (
            FilterRule("gpu", ("видеокарта", "rtx 4070 ti"), 88),
            FilterRule("cpu", ("процессор",), 88),
        )
    )
    results = matcher.match("Скидка на ВИДЕОКАРТУ RTX4070-Ti")
    assert [result.filter_id for result in results] == ["gpu"]
    assert results[0].exact is True

    fuzzy = matcher.match("Новый процесор поступил в продажу")
    assert [result.filter_id for result in fuzzy] == ["cpu"]
    assert fuzzy[0].exact is False


def test_numbers_must_match_exactly() -> None:
    matcher = Matcher((FilterRule("gpu", ("rtx 4070 ti",), 80),))
    assert matcher.match("GeForce RTX 4070 Ti Super")
    assert not matcher.match("GeForce RTX 5070 Ti")
    assert not matcher.match("GeForce RTX Ti")


def test_exclusion_disables_filter_and_boundaries_are_respected() -> None:
    matcher = Matcher((FilterRule("cpu", ("cpu", "процессор"), 90, ("чехол",)),))
    assert matcher.match("Новый CPU в наличии")
    assert not matcher.match("Чехол для процессора")
    assert not matcher.match("cpuid utility")


def test_empty_text_does_not_match() -> None:
    matcher = Matcher((FilterRule("cpu", ("cpu",), 90),))
    assert matcher.match("") == ()


def test_empty_rules_match_everything_including_empty_text() -> None:
    matcher = Matcher(())
    assert matcher.match("любой пост")[0].filter_id == "all"
    assert matcher.match("")[0].filter_id == "all"


def test_require_any_needs_category_and_allowed_brand() -> None:
    matcher = Matcher(
        (
            FilterRule(
                "keyboard",
                ("клавиатура", "keyboard"),
                90,
                (),
                ("atk", "cidoo"),
            ),
        )
    )
    assert matcher.match("Механическая клавиатура ATK акция")
    assert not matcher.match("Механическая клавиатура Keychron акция")
    assert not matcher.match("Игровая мышь ATK акция")
