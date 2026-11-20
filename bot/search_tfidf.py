"""Второй поиск: TF-IDF по символьным n-граммам и косинус."""

from __future__ import annotations

from functools import lru_cache

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from bot.corpus import search_documents
from bot.textutil import normalize_search


@lru_cache(maxsize=1)
def _index():
    pairs = search_documents()
    ids = [faq_id for faq_id, _ in pairs]
    texts = [document for _, document in pairs]
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), lowercase=False)
    matrix = vectorizer.fit_transform(texts)
    return vectorizer, matrix, tuple(ids)


def rank(text: str) -> list[tuple[int, float]]:
    """Темы от лучшей к худшей. Оценка — косинус, от 0 до 1."""
    query = normalize_search(text)
    vectorizer, matrix, ids = _index()
    if not query:
        return [(faq_id, 0.0) for faq_id in sorted(set(ids))]
    vector = vectorizer.transform([query])
    scores = cosine_similarity(vector, matrix).ravel()
    best: dict[int, float] = {}
    for faq_id, score in zip(ids, scores):
        value = float(score)
        if value > best.get(faq_id, 0.0):
            best[faq_id] = value
    ranked = sorted(best.items(), key=lambda item: (-item[1], item[0]))
    return [(faq_id, score) for faq_id, score in ranked]
