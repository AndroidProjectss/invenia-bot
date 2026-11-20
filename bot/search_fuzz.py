"""Нечёткий поиск rapidfuzz по вопросам и разговорным формулировкам."""

from __future__ import annotations

from rapidfuzz import fuzz

from bot.corpus import search_documents
from bot.textutil import normalize_search


def _score(query: str, document: str) -> float:
    if not query or not document:
        return 0.0
    token_set = fuzz.token_set_ratio(query, document)
    token_sort = fuzz.token_sort_ratio(query, document)
    return (0.75 * token_set + 0.25 * token_sort) / 100.0


def rank(text: str) -> list[tuple[int, float]]:
    """Темы от лучшей к худшей. Оценка от 0 до 1."""
    query = normalize_search(text)
    best: dict[int, float] = {}
    for faq_id, document in search_documents():
        score = _score(query, document)
        if score > best.get(faq_id, 0.0):
            best[faq_id] = score
    ranked = sorted(best.items(), key=lambda item: (-item[1], item[0]))
    return [(faq_id, float(score)) for faq_id, score in ranked]
