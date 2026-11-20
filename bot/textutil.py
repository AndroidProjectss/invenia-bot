"""Нормализация текста: латиница кыргызского и обрезка окончаний."""

from __future__ import annotations

import re

_DIGRAPHS = (
    ("sh", "ш"),
    ("ch", "ч"),
    ("zh", "ж"),
    ("ng", "ң"),
    ("kh", "х"),
    ("ts", "ц"),
    ("ei", "ей"),
    ("ay", "ай"),
    ("oy", "ой"),
    ("ya", "я"),
    ("yu", "ю"),
    ("yo", "ё"),
)

_SINGLES = {
    "a": "а",
    "b": "б",
    "c": "к",
    "d": "д",
    "e": "е",
    "f": "ф",
    "g": "г",
    "h": "х",
    "i": "и",
    "j": "ж",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "q": "к",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "v": "в",
    "w": "в",
    "x": "кс",
    "y": "ы",
    "z": "з",
}

# Длинные окончания раньше коротких, чтобы «ымды» не резалось как «ды».
_ENDINGS = tuple(
    sorted(
        (
            "ымды",
            "имди",
            "умду",
            "үмдү",
            "ымда",
            "имде",
            "ымдын",
            "имдин",
            "ым",
            "им",
            "ум",
            "үм",
            "өм",
            "дын",
            "дин",
            "дун",
            "дүн",
            "нын",
            "нин",
            "нун",
            "нүн",
            "дан",
            "ден",
            "дон",
            "дөн",
            "тан",
            "тен",
            "гон",
            "гөн",
            "ды",
            "ди",
            "ду",
            "дү",
            "ты",
            "ти",
            "ту",
            "тү",
            "га",
            "ге",
            "го",
            "гө",
            "ка",
            "ке",
            "да",
            "де",
            "до",
            "дө",
            "та",
            "те",
        ),
        key=len,
        reverse=True,
    )
)


def transliterate(token: str) -> str:
    """Неофициальная латиница кыргызского в кириллицу: balansymdy -> балансымды."""
    out: list[str] = []
    i = 0
    while i < len(token):
        pair = token[i : i + 2]
        hit = None
        for latin, cyr in _DIGRAPHS:
            if pair == latin:
                hit = cyr
                break
        if hit is not None:
            out.append(hit)
            i += 2
            continue
        out.append(_SINGLES.get(token[i], token[i]))
        i += 1
    return "".join(out)


def basic_normalize(text: str) -> str:
    text = (text or "").strip().lower().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-яөүң]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> list[str]:
    """Слова фразы. Латинские слова переводятся в кириллицу."""
    tokens: list[str] = []
    for token in basic_normalize(text).split():
        if re.fullmatch(r"[a-z]+", token):
            tokens.append(transliterate(token))
        else:
            tokens.append(token)
    return tokens


def stem_token(token: str) -> str:
    for ending in _ENDINGS:
        if token.endswith(ending) and len(token) - len(ending) >= 4:
            return token[: -len(ending)]
    return token


def normalize_search(text: str) -> str:
    """Текст для обоих поисков: одна письменность и без падежных хвостов."""
    return " ".join(stem_token(token) for token in tokenize(text))
