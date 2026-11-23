"""Чистые русские текстовые утилиты блока 2 (§8.4, §12)."""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Sequence
from functools import lru_cache
from typing import Literal

from pymorphy3 import MorphAnalyzer
from rapidfuzz import fuzz

from gamebox.common.engines import MatchResult

Gender = Literal["masc", "fem", "neut", "plural"]
NUMBER_MIN = 0
NUMBER_MAX = 1_000_000
_UNITS = (
    ("ноль", "нулевой", "нулевая", "нулевое", "нулевые"),
    ("один", "первый", "первая", "первое", "первые"),
    ("два", "второй", "вторая", "второе", "вторые"),
    ("три", "третий", "третья", "третье", "третьи"),
    ("четыре", "четвертый", "четвертая", "четвертое", "четвертые"),
    ("пять", "пятый", "пятая", "пятое", "пятые"),
    ("шесть", "шестой", "шестая", "шестое", "шестые"),
    ("семь", "седьмой", "седьмая", "седьмое", "седьмые"),
    ("восемь", "восьмой", "восьмая", "восьмое", "восьмые"),
    ("девять", "девятый", "девятая", "девятое", "девятые"),
)
_TEENS = [
    "десять",
    "одиннадцать",
    "двенадцать",
    "тринадцать",
    "четырнадцать",
    "пятнадцать",
    "шестнадцать",
    "семнадцать",
    "восемнадцать",
    "девятнадцать",
]
_TEEN_ORDINAL = [
    "десятый",
    "одиннадцатый",
    "двенадцатый",
    "тринадцатый",
    "четырнадцатый",
    "пятнадцатый",
    "шестнадцатый",
    "семнадцатый",
    "восемнадцатый",
    "девятнадцатый",
]
_TENS = (
    "",
    "",
    "двадцать",
    "тридцать",
    "сорок",
    "пятьдесят",
    "шестьдесят",
    "семьдесят",
    "восемьдесят",
    "девяносто",
)
_TENS_ORDINAL = (
    "",
    "",
    "двадцатый",
    "тридцатый",
    "сороковой",
    "пятидесятый",
    "шестидесятый",
    "семидесятый",
    "восьмидесятый",
    "девяностый",
)
_HUNDREDS = (
    "",
    "сто",
    "двести",
    "триста",
    "четыреста",
    "пятьсот",
    "шестьсот",
    "семьсот",
    "восемьсот",
    "девятьсот",
)
_HUNDREDS_ORDINAL = (
    "",
    "сотый",
    "двухсотый",
    "трехсотый",
    "четырехсотый",
    "пятисотый",
    "шестисотый",
    "семисотый",
    "восьмисотый",
    "девятисотый",
)
_WORD_VALUES = {row[0]: index for index, row in enumerate(_UNITS)}
_WORD_VALUES.update({word: 10 + index for index, word in enumerate(_TEENS)})
_WORD_VALUES.update({word: index * 10 for index, word in enumerate(_TENS) if word})
_WORD_VALUES.update({word: index * 100 for index, word in enumerate(_HUNDREDS) if word})
_WORD_VALUES.update({"одна": 1, "две": 2})
_ORDINAL_VALUES: dict[str, int] = {}


def _ordinal_stem(word: str) -> str:
    if word == "сороковой":
        return "сороков"
    if word == "девяностый":
        return "девяност"
    return word[:-2]


for _i, _row in enumerate(_UNITS):
    for _form in _row[1:]:
        _ORDINAL_VALUES[_form] = _i
for _i, _word in enumerate(_TEEN_ORDINAL):
    _ORDINAL_VALUES[_word] = 10 + _i
    _ORDINAL_VALUES[_ordinal_stem(_word) + "ая"] = 10 + _i
    _ORDINAL_VALUES[_ordinal_stem(_word) + "ое"] = 10 + _i
    _ORDINAL_VALUES[_ordinal_stem(_word) + "ые"] = 10 + _i
for _i, _word in enumerate(_TENS_ORDINAL):
    if _word:
        _ORDINAL_VALUES[_word] = _i * 10
        _ORDINAL_VALUES[_ordinal_stem(_word) + "ая"] = _i * 10
        _ORDINAL_VALUES[_ordinal_stem(_word) + "ое"] = _i * 10
        _ORDINAL_VALUES[_ordinal_stem(_word) + "ые"] = _i * 10
for _i, _word in enumerate(_HUNDREDS_ORDINAL):
    if _word:
        _ORDINAL_VALUES[_word] = _i * 100
        _ORDINAL_VALUES[_ordinal_stem(_word) + "ая"] = _i * 100
        _ORDINAL_VALUES[_ordinal_stem(_word) + "ое"] = _i * 100
        _ORDINAL_VALUES[_ordinal_stem(_word) + "ые"] = _i * 100
_THOUSAND_GENITIVE_UNITS = (
    "",
    "одно",
    "двух",
    "трех",
    "четырех",
    "пяти",
    "шести",
    "семи",
    "восьми",
    "девяти",
)
_THOUSAND_GENITIVE_TEENS = (
    "десяти",
    "одиннадцати",
    "двенадцати",
    "тринадцати",
    "четырнадцати",
    "пятнадцати",
    "шестнадцати",
    "семнадцати",
    "восемнадцати",
    "девятнадцати",
)
_THOUSAND_GENITIVE_TENS = (
    "",
    "",
    "двадцати",
    "тридцати",
    "сорока",
    "пятидесяти",
    "шестидесяти",
    "семидесяти",
    "восьмидесяти",
    "девяноста",
)
_THOUSAND_GENITIVE_HUNDREDS = (
    "",
    "сто",
    "двухсот",
    "трехсот",
    "четырехсот",
    "пятисот",
    "шестисот",
    "семисот",
    "восьмисот",
    "девятисот",
)


def _thousand_ordinal_stem(count: int) -> str:
    if count == 1:
        return "тысячн"
    hundreds, rest = divmod(count, 100)
    tens, units = divmod(rest, 10)
    parts: list[str] = []
    if hundreds:
        parts.append(_THOUSAND_GENITIVE_HUNDREDS[hundreds])
    if 10 <= rest <= 19:
        parts.append(_THOUSAND_GENITIVE_TEENS[rest - 10])
    else:
        if tens:
            parts.append(_THOUSAND_GENITIVE_TENS[tens])
        if units:
            parts.append(_THOUSAND_GENITIVE_UNITS[units])
    return "".join(parts) + "тысячн"


def _parse_thousand_prefix(prefix: str) -> int:
    if not prefix:
        return 1
    value = 0
    for index, word in enumerate(_THOUSAND_GENITIVE_HUNDREDS):
        if word and prefix.startswith(word):
            value += index * 100
            prefix = prefix[len(word) :]
            break
    for index, word in enumerate(_THOUSAND_GENITIVE_TEENS):
        if prefix == word:
            return value + 10 + index
    for index, word in enumerate(_THOUSAND_GENITIVE_TENS):
        if word and prefix.startswith(word):
            value += index * 10
            prefix = prefix[len(word) :]
            break
    for index, word in enumerate(_THOUSAND_GENITIVE_UNITS):
        if word and prefix == word:
            return value + index
    raise ValueError(f"Некорректная приставка порядкового тысяч: {prefix}")


for _count in range(1, 1000):
    _stem = _thousand_ordinal_stem(_count)
    for _ending in ("ый", "ая", "ое", "ые"):
        _ORDINAL_VALUES[_stem + _ending] = _count * 1000
_ORDINAL_VALUES.update(
    {
        "миллионный": 1_000_000,
        "миллионная": 1_000_000,
        "миллионное": 1_000_000,
        "миллионные": 1_000_000,
    }
)
_GENDER_INDEX = {"masc": 1, "fem": 2, "neut": 3, "plural": 4}
_MORPH = MorphAnalyzer()


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold().replace("ё", "е")
    text = "".join(char if char.isalnum() or char.isspace() else " " for char in text)
    return " ".join(text.split())


def tokens(text: str) -> tuple[str, ...]:
    return tuple(normalize(text).split())


def _check_range(number: int) -> None:
    if (
        not isinstance(number, int)
        or isinstance(number, bool)
        or not NUMBER_MIN <= number <= NUMBER_MAX
    ):
        raise ValueError(f"Поддерживаются целые {NUMBER_MIN}–{NUMBER_MAX}")


def _under_thousand(number: int, feminine: bool = False) -> list[str]:
    words: list[str] = []
    hundreds, rest = divmod(number, 100)
    if hundreds:
        words.append(_HUNDREDS[hundreds])
    if 10 <= rest <= 19:
        words.append(_TEENS[rest - 10])
    else:
        tens, units = divmod(rest, 10)
        if tens:
            words.append(_TENS[tens])
        if units:
            if units == 1:
                words.append("одна" if feminine else "один")
            elif units == 2:
                words.append("две" if feminine else "два")
            else:
                words.append(_UNITS[units][0])
    return words


def number_to_words(number: int, gender: Literal["masc", "fem"] = "masc") -> str:
    _check_range(number)
    if number == 0:
        return "ноль"
    if number == NUMBER_MAX:
        return "один миллион"
    millions, rest = divmod(number, 1_000_000)
    thousands, units = divmod(rest, 1000)
    words: list[str] = []
    if millions:
        words.extend(_under_thousand(millions))
        words.append("миллион")
    if thousands:
        words.extend(_under_thousand(thousands, feminine=True))
        words.append(
            "тысяча"
            if thousands % 10 == 1 and thousands % 100 != 11
            else "тысячи"
            if 2 <= thousands % 10 <= 4 and not 12 <= thousands % 100 <= 14
            else "тысяч"
        )
    words.extend(_under_thousand(units, feminine=gender == "fem"))
    return " ".join(words)


def words_to_number(text: str) -> int:
    words = tokens(text)
    if not words:
        raise ValueError("Пустое числительное")
    total = 0
    group = 0
    last_scale = math.inf
    seen: set[str] = set()
    for word in words:
        if word in ("тысяча", "тысячи", "тысяч", "миллион", "миллиона", "миллионов"):
            scale = 1000 if word.startswith("тысяч") else 1_000_000
            if scale >= last_scale or not 1 <= group <= 999:
                raise ValueError(f"Некорректный разряд: {word}")
            total += group * scale
            group = 0
            last_scale = scale
            seen = set()
            continue
        if word not in _WORD_VALUES or word in seen:
            raise ValueError(f"Неизвестное или повторное числительное: {word}")
        value = _WORD_VALUES[word]
        if value == 0 and (len(words) != 1 or total or group):
            raise ValueError("Ноль должен быть один")
        if value >= 100:
            if group % 100 or group >= 100:
                raise ValueError("Повторные сотни")
            group += value
        elif value >= 10:
            if group % 100:
                raise ValueError("Порядок числительных нарушен")
            group += value
        else:
            if group % 10:
                raise ValueError("Повторные единицы")
            group += value
        seen.add(word)
    result = total + group
    _check_range(result)
    return result


def parse_number(text: str) -> int:
    cleaned = normalize(text)
    if cleaned.isdigit():
        return int(cleaned)
    return words_to_number(cleaned)


def number_to_ordinal(number: int, gender: Gender = "masc") -> str:
    _check_range(number)
    if number == 0:
        raise ValueError("Порядковые начинаются с 1")
    if number == NUMBER_MAX:
        prefix, last = "", "миллионный"
    elif number >= 1000 and number % 1000 == 0:
        prefix, last = "", _thousand_ordinal_stem(number // 1000) + "ый"
    else:
        remainder = number % 100
        if number % 10 and not 10 <= remainder <= 19:
            last_number = number % 10
        elif remainder:
            last_number = remainder
        else:
            last_number = number % 1000
        prefix_number = number - last_number
        prefix = number_to_words(prefix_number) if prefix_number else ""
        last = _ordinal_under_thousand(last_number)
    index = _GENDER_INDEX[gender]
    if last == "миллионный":
        forms = ("миллионный", "миллионная", "миллионное", "миллионные")
        last = forms[index - 1]
    elif "тысячн" in last:
        stem = last[: last.index("тысячн") + len("тысячн")]
        last = stem + ("ый", "ая", "ое", "ые")[index - 1]
    elif last in _ORDINAL_VALUES:
        value = _ORDINAL_VALUES[last]
        if value < 10:
            last = _UNITS[value][index]
        elif value < 20:
            stem = _ordinal_stem(_TEEN_ORDINAL[value - 10])
            last = stem + ("ый", "ая", "ое", "ые")[index - 1]
        elif value < 100:
            stem = _ordinal_stem(_TENS_ORDINAL[value // 10])
            endings = ("ой", "ая", "ое", "ые") if value == 40 else ("ый", "ая", "ое", "ые")
            last = stem + endings[index - 1]
        else:
            stem = _ordinal_stem(_HUNDREDS_ORDINAL[value // 100])
            last = stem + ("ый", "ая", "ое", "ые")[index - 1]
    return f"{prefix} {last}".strip()


def _ordinal_under_thousand(number: int) -> str:
    if number < 10:
        return _UNITS[number][1]
    if number < 20:
        return _TEEN_ORDINAL[number - 10]
    if number < 100 and number % 10 == 0:
        return _TENS_ORDINAL[number // 10]
    if number % 100 == 0:
        return _HUNDREDS_ORDINAL[number // 100]
    return _ordinal_under_thousand(number % 100 if number > 100 else number % 10)


def ordinal_to_number(text: str) -> int:
    words = list(tokens(text))
    if not words:
        raise ValueError("Пустое порядковое")
    last = words.pop()
    if last not in _ORDINAL_VALUES:
        raise ValueError(f"Неизвестное порядковое: {last}")
    prefix = words_to_number(" ".join(words)) if words else 0
    result = prefix + _ORDINAL_VALUES[last]
    _check_range(result)
    return result


def pluralize(count: int, forms: tuple[str, str, str]) -> str:
    if len(forms) != 3:
        raise ValueError("Нужны три формы: 1 / 2 / 5")
    n = abs(count) % 100
    if 11 <= n <= 14:
        return forms[2]
    n %= 10
    return forms[0] if n == 1 else forms[1] if 2 <= n <= 4 else forms[2]


def with_count(count: int, forms: tuple[str, str, str]) -> str:
    return f"{count} {pluralize(count, forms)}"


@lru_cache(maxsize=8192)
def lemma(word: str) -> str:
    parsed = _MORPH.parse(normalize(word))
    return parsed[0].normal_form.replace("ё", "е") if parsed else normalize(word)


def lemmatize(text: str) -> tuple[str, ...]:
    return tuple(lemma(word) for word in tokens(text))


def lemma_cache_info() -> object:
    return lemma.cache_info()


def similarity(left: str, right: str) -> float:
    return float(fuzz.ratio(normalize(left), normalize(right)) / 100.0)


def best_match(text: str, candidates: Sequence[str], threshold: float) -> MatchResult | None:
    if not 0 <= threshold <= 1:
        raise ValueError("threshold должен быть в [0, 1]")
    scored = [(similarity(text, candidate), index) for index, candidate in enumerate(candidates)]
    if not scored:
        return None
    score, index = max(scored, key=lambda pair: (pair[0], -pair[1]))
    return MatchResult(candidates[index], index, score) if score >= threshold else None


_PAIRED = {"б": "п", "в": "ф", "г": "к", "д": "т", "ж": "ш", "з": "с"}
_REVERSE = {value: key for key, value in _PAIRED.items()}
_VOICELESS = set(_PAIRED.values())
_VOICED = set(_PAIRED) | {"л", "м", "н", "р", "й"}
_VOWELS = set("аеёиоуыэюя")
_REDUCE = {"о": "а", "я": "а", "е": "и", "э": "и", "ы": "и", "ю": "у"}


def phonetic_key(text: str, stress: int | None = None) -> str:
    """Эвристический ключ для нечёткого сравнения, не полноценная фонетическая транскрипция.

    Оглушение на конце и в кластерах, упрощение сочетаний, сближение гласных.
    Без ударения редукция консервативно применяется ко всем гласным; `stress` —
    необязательный индекс гласной в слове, которую нужно сохранить.
    """
    words = normalize(text).replace("ъ", "").replace("ь", "").split()
    result: list[str] = []
    for word in words:
        word = word.replace("тся", "ца").replace("ться", "ца")
        for old, new in (("стн", "сн"), ("здн", "зн"), ("лнц", "нц"), ("ндц", "нц")):
            word = word.replace(old, new)
        chars = list(word)
        for index in range(len(chars) - 1, -1, -1):
            char = chars[index]
            if char not in _PAIRED and char not in _REVERSE:
                continue
            following = chars[index + 1] if index + 1 < len(chars) else None
            if following is None or following in _VOICELESS:
                chars[index] = _PAIRED.get(char, char)
            elif following in _VOICED and char != "в":
                chars[index] = _REVERSE.get(char, char)
        vowel_index = 0
        reduced: list[str] = []
        for char in chars:
            if char in _VOWELS:
                if stress is not None and vowel_index == stress:
                    reduced.append(char)
                else:
                    reduced.append(_REDUCE.get(char, char))
                vowel_index += 1
            else:
                reduced.append(char)
        result.append("".join(reduced))
    return " ".join(result)
