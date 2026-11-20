"""Память темы только внутри одного chat_id."""

from __future__ import annotations

_TOPICS: dict[str, int] = {}
# Чат, который уже отдан человеку: список сообщений, которые бот промолчал.
_HANDOFF: dict[str, list[str]] = {}


def get_topic(chat_id: str) -> int | None:
    return _TOPICS.get(str(chat_id))


def set_topic(chat_id: str, faq_id: int | None) -> None:
    if faq_id is None:
        return
    _TOPICS[str(chat_id)] = int(faq_id)


def is_handed_off(chat_id: str) -> bool:
    return str(chat_id) in _HANDOFF


def start_handoff(chat_id: str) -> None:
    _HANDOFF.setdefault(str(chat_id), [])


def keep_for_operator(chat_id: str, text: str) -> None:
    _HANDOFF.setdefault(str(chat_id), []).append(text)


def kept_messages(chat_id: str) -> list[str]:
    return list(_HANDOFF.get(str(chat_id), []))


def reset(chat_id: str | None = None) -> None:
    if chat_id is None:
        _TOPICS.clear()
        _HANDOFF.clear()
        return
    key = str(chat_id)
    _TOPICS.pop(key, None)
    _HANDOFF.pop(key, None)
