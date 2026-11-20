"""Telegram: прямой ответ, три кнопки или отказ. Токен только из окружения."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from bot.answer import resolve
from bot.corpus import ROOT, faq_by_id
from bot.dialog import reset, set_topic
from bot.stats import log_unanswered, summary

_REFUSE = {
    "ru": "В базе FAQ нет ответа на этот вопрос. Я не буду его выдумывать.",
    "ky": "Бул суроого FAQ базасында жооп жок. Мен жоопту ойлоп таппайм.",
}
_BUTTONS = {
    "ru": "Я не уверен. Выберите близкий вопрос:",
    "ky": "Ишенбей жатам. Жакын суроону тандаңыз:",
}
_HELLO = (
    "Напишите вопрос о связи на русском или кыргызском.\n"
    "Байланыш боюнча суроону орусча же кыргызча жазыңыз.\n"
    "/stats — неотвеченные вопросы, /reset — забыть тему этого чата."
)


def _load_dotenv() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def phrase(faq_id: int, lang: str, field: str) -> str:
    item = faq_by_id()[faq_id]
    suffix = "ky" if lang == "ky" else "ru"
    return item[f"{field}_{suffix}"]


def render(full: dict) -> tuple[str, list[dict]]:
    """Текст сообщения и ряды кнопок. Сеть не нужна."""
    lang = full["lang"] if full["lang"] in ("ru", "ky") else "ru"
    if full["mode"] == "refuse" or full["faq_id"] is None:
        return _REFUSE[lang], []
    if full["mode"] == "buttons":
        rows = []
        for faq_id in full["candidates"]:
            label = phrase(faq_id, lang, "question")
            if len(label) > 60:
                label = label[:57] + "..."
            rows.append([{"text": label, "callback_data": f"{faq_id}:{lang}"}])
        return _BUTTONS[lang], rows
    return phrase(full["faq_id"], lang, "answer"), []


def _api(token: str, method: str, payload: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.loads(response.read().decode("utf-8"))


def _send(token: str, chat_id: int | str, text: str, buttons: list[dict]) -> None:
    payload: dict = {"chat_id": chat_id, "text": text}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    _api(token, "sendMessage", payload)


def _handle_text(token: str, chat_id: int, text: str) -> None:
    if text.startswith("/start"):
        _send(token, chat_id, _HELLO, [])
        return
    if text.startswith("/reset"):
        reset(str(chat_id))
        _send(token, chat_id, "Тема этого чата забыта. Задайте вопрос заново.", [])
        return
    if text.startswith("/stats"):
        _send(token, chat_id, summary(), [])
        return
    full = resolve(text, chat_id=str(chat_id))
    if full["mode"] != "direct":
        log_unanswered(text, full["lang"], full["mode"])
    message, buttons = render(full)
    _send(token, chat_id, message, buttons)


def _handle_callback(token: str, callback: dict) -> None:
    data = callback.get("data") or ""
    callback_id = callback.get("id")
    message = callback.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    _api(token, "answerCallbackQuery", {"callback_query_id": callback_id})
    if chat_id is None or ":" not in data:
        return
    raw_id, lang = data.split(":", 1)
    try:
        faq_id = int(raw_id)
    except ValueError:
        return
    if lang not in ("ru", "ky"):
        lang = "ru"
    if faq_id not in faq_by_id():
        return
    set_topic(str(chat_id), faq_id)
    _send(token, chat_id, phrase(faq_id, lang, "answer"), [])


def run_bot() -> None:
    _load_dotenv()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "Нет TELEGRAM_BOT_TOKEN. Проверка answer() работает без него: python main.py ask \"текст\""
        )
    offset = 0
    print("Бот слушает Telegram. Остановка: Ctrl+C.")
    while True:
        try:
            payload = _api(token, f"getUpdates?timeout=25&offset={offset}")
        except KeyboardInterrupt:
            print("Остановка.")
            return
        except urllib.error.URLError as error:
            print(f"Сеть Telegram недоступна: {error}")
            time.sleep(2)
            continue
        if not payload.get("ok", False):
            print(payload.get("description") or "Telegram вернул ошибку")
            time.sleep(2)
            continue
        for update in payload.get("result", []):
            offset = int(update["update_id"]) + 1
            if "message" in update and update["message"].get("text"):
                chat_id = update["message"]["chat"]["id"]
                _handle_text(token, chat_id, update["message"]["text"])
            elif "callback_query" in update:
                _handle_callback(token, update["callback_query"])
