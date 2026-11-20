"""Контракт жюри: answer(text) -> язык, номер темы, уверенность, кандидаты."""

from __future__ import annotations

from bot import config
from bot.dialog import get_topic, set_topic
from bot.lang import detect_lang
from bot.search_fuzz import rank as rank_fuzz
from bot.search_tfidf import rank as rank_tfidf
from bot.textutil import basic_normalize, tokenize

_FILLERS = {"а", "и", "ну", "же", "это", "то", "мне", "пожалуйста"}
# Слова продолжения без новой темы: «а сколько стоит?» после роуминга.
_FOLLOW = {
    "сколько",
    "скока",
    "стоит",
    "стоить",
    "цена",
    "почем",
    "канча",
    "турат",
    "баасы",
    "баа",
    "баасын",
    "стоимость",
    "как",
    "кантип",
    "сделать",
    "подключить",
    "включить",
    "кошуу",
}


def rank_for(method: str, text: str) -> list[tuple[int, float]]:
    if method == "fuzz":
        return rank_fuzz(text)
    if method == "tfidf":
        return rank_tfidf(text)
    raise ValueError(f"Неизвестный метод поиска: {method}")


def is_elliptical(text: str) -> bool:
    """Короткая реплика без своей темы. Её смысл берётся из прошлого вопроса чата."""
    tokens = [token for token in tokenize(text) if token not in _FILLERS]
    if not tokens or len(tokens) > 4:
        return False
    return all(token in _FOLLOW for token in tokens)


def _public(lang: str, faq_id: int | None, confidence: float, candidates: list[int]) -> dict:
    if faq_id is None:
        candidates = []
    else:
        ordered = [faq_id]
        for item in candidates:
            if item != faq_id and len(ordered) < 3:
                ordered.append(item)
        candidates = ordered
        if candidates and candidates[0] != faq_id:
            raise RuntimeError("Первый кандидат должен совпадать с faq_id")
    return {
        "lang": lang,
        "faq_id": faq_id,
        "confidence": round(max(0.0, min(1.0, confidence)), 2),
        "candidates": candidates,
    }


def resolve(text: str, chat_id: str | None = None, method: str | None = None) -> dict:
    """Полный разбор. Поле mode нужно боту: direct, buttons или refuse."""
    lang = detect_lang(text)
    if not (text or "").strip():
        return {**_public(lang, None, 0.0, []), "mode": "refuse"}

    method = method or config.SELECTED_METHOD
    ranked = rank_for(method, text)
    top3 = [faq_id for faq_id, _ in ranked[:3]]
    best_id, best_score = ranked[0] if ranked else (None, 0.0)

    topic = get_topic(chat_id) if chat_id is not None else None
    if topic is not None and is_elliptical(text):
        result = _public(lang, topic, max(best_score, config.CONTEXT_CONFIDENCE), top3)
        result["mode"] = "direct"
        set_topic(chat_id, topic)
        return result

    if best_id is None or best_score < config.REJECT_THRESHOLD:
        result = _public(lang, None, best_score, [])
        result["mode"] = "refuse"
        return result

    result = _public(lang, best_id, best_score, top3)
    result["mode"] = "direct" if best_score >= config.CONFIDENT_THRESHOLD else "buttons"
    # Тему запоминаем только когда ответили прямо. Кнопки ещё не подтверждены.
    if chat_id is not None and result["mode"] == "direct":
        set_topic(chat_id, best_id)
    return result


def answer(text: str, chat_id: str | None = None) -> dict:
    """Ответ для автопроверки. Без chat_id прошлая тема не используется."""
    full = resolve(text, chat_id=chat_id)
    return {
        "lang": full["lang"],
        "faq_id": full["faq_id"],
        "confidence": full["confidence"],
        "candidates": full["candidates"],
    }
