import pytest

from gamebox.common.text import (
    best_match,
    lemma_cache_info,
    lemmatize,
    normalize,
    number_to_ordinal,
    number_to_words,
    ordinal_to_number,
    parse_number,
    phonetic_key,
    pluralize,
    similarity,
    with_count,
    words_to_number,
)


def test_normalize() -> None:
    assert normalize("  Ёлка, БЭ-5! ") == "елка бэ 5"


@pytest.mark.parametrize(
    ("number", "words"),
    [
        (0, "ноль"),
        (1, "один"),
        (2, "два"),
        (5, "пять"),
        (11, "одиннадцать"),
        (21, "двадцать один"),
        (100, "сто"),
        (1000, "одна тысяча"),
        (1234, "одна тысяча двести тридцать четыре"),
        (1_000_000, "один миллион"),
    ],
)
def test_cardinal_roundtrip(number: int, words: str) -> None:
    assert number_to_words(number) == words
    assert words_to_number(words) == number
    assert parse_number(str(number)) == number


def test_cardinal_gender_and_invalid() -> None:
    assert number_to_words(2, "fem") == "две"
    assert number_to_words(21, "fem") == "двадцать одна"
    for text in ("два два", "тысяча тысяча", "миллион тысяч", ""):
        with pytest.raises(ValueError):
            words_to_number(text)
    with pytest.raises(ValueError):
        number_to_words(1_000_001)


@pytest.mark.parametrize(
    "number", [1, 2, 5, 10, 11, 21, 100, 101, 110, 120, 1000, 2000, 1234, 1_000_000]
)
def test_ordinal_roundtrip(number: int) -> None:
    for gender in ("masc", "fem", "neut", "plural"):
        words = number_to_ordinal(number, gender)
        assert ordinal_to_number(words) == number


def test_plurals() -> None:
    forms = ("очко", "очка", "очков")
    assert with_count(1, forms) == "1 очко"
    assert with_count(2, forms) == "2 очка"
    assert with_count(5, forms) == "5 очков"
    assert with_count(11, forms) == "11 очков"
    assert pluralize(21, forms) == "очко"


def test_lemmas_and_cache() -> None:
    assert lemmatize("Красивые корабли!") == ("красивый", "корабль")
    lemmatize("корабли")
    assert lemma_cache_info().hits >= 1  # type: ignore[attr-defined]


def test_fuzzy_and_phonetic() -> None:
    assert similarity("БЭ-5", "бэ 5") == 1.0
    match = best_match("бэ пять", ["бэ пять", "а один"], 0.8)
    assert match is not None and match.index == 0
    assert phonetic_key("дуб") == phonetic_key("дуп")
    assert phonetic_key("мороз") == phonetic_key("марос")
    assert phonetic_key("сдать") == phonetic_key("здат")
    assert phonetic_key("солнце") == phonetic_key("сонце")
    assert phonetic_key("мел") == phonetic_key("мил")


def test_cardinal_roundtrip_first_ten_thousand() -> None:
    for number in range(0, 10001):
        assert words_to_number(number_to_words(number)) == number
