"""Память темы только внутри одного chat_id."""

from __future__ import annotations

_TOPICS: dict[str, int] = {}


def get_topic(chat_id: str) -> int | None:
    return _TOPICS.get(str(chat_id))


def set_topic(chat_id: str, faq_id: int | None) -> None:
    if faq_id is None:
        return
    _TOPICS[str(chat_id)] = int(faq_id)


def reset(chat_id: str | None = None) -> None:
    if chat_id is None:
        _TOPICS.clear()
        return
    _TOPICS.pop(str(chat_id), None)
