"""Состояние приёмника Telegram, общее для web и worker через SQLite."""

import json
import time

from bot.storage import get_setting, set_setting


def report(status: str, detail: str = "") -> None:
    set_setting("telegram_receiver", json.dumps({"status": status, "detail": detail,
                                                "updated_at": time.time()}))


def snapshot() -> dict:
    try:
        state = json.loads(get_setting("telegram_receiver", "{}"))
    except (ValueError, TypeError):
        state = {}
    if not state:
        return {"status": "unknown", "detail": "Приёмник ещё не сообщил о работе"}
    if time.time() - state.get("updated_at", 0) > 120:
        state["status"] = "stale"
        state["detail"] = "Нет сигнала от Telegram-приёмника более 2 минут"
    return state
