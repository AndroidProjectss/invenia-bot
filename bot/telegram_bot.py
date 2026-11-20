"""Telegram: прямой ответ, три кнопки, отказ или передача оператору."""

from __future__ import annotations

import json
import os
import time
import traceback
import urllib.error
import urllib.request

from bot.answer import resolve
from bot.lang import detect_lang
from bot.corpus import faq_by_id
from bot.dialog import (
    is_handed_off,
    keep_for_operator,
    reset,
    set_topic,
    start_handoff,
)
from bot.envfile import load_dotenv
from bot.gemini import rephrase as gemini_rephrase
from bot.stats import log_unanswered, summary
from bot.textutil import basic_normalize

_REFUSE = {
    "ru": "С этим не помогу. Я отвечаю только по связи: баланс, интернет, роуминг, тариф и SIM.",
    "ky": "Буга жардам бере албайм. Мен байланыш боюнча гана жооп берем: баланс, интернет, роуминг, тариф жана SIM.",
}
_BUTTONS = {
    "ru": "Уточните, пожалуйста, о чём вопрос:",
    "ky": "Сурооңузду тактап коюңузчу:",
}
_HANDOFF = {
    "ru": "Сейчас подключу оператора. Напишите /reset, если хотите снова говорить со мной.",
    "ky": "Азыр операторду кошом. Кайра мен менен сүйлөшкүңүз келсе, /reset деп жазыңыз.",
}
_HELLO = (
    "Здравствуйте. Напишите вопрос по связи на русском или кыргызском.\n"
    "Саламатсызбы. Байланыш боюнча суроону орусча же кыргызча жазыңыз."
)
_RESET = "Тема этого чата забыта. Бот снова отвечает."


def phrase(faq_id: int, lang: str, field: str) -> str:
    item = faq_by_id()[faq_id]
    suffix = "ky" if lang == "ky" else "ru"
    return item[f"{field}_{suffix}"]


def operator_requested(text: str) -> bool:
    folded = basic_normalize(text)
    return "оператор" in folded or "operator" in folded


def render(full: dict) -> tuple[str, list[dict]]:
    """Текст сообщения и ряды кнопок. Сеть не нужна, нейросеть не вызывается."""
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


def compose(chat_id: str, text: str, *, rephrase=None, log=None) -> list[tuple[str, list]]:
    """Что отправить в чат. Пустой список значит «бот молчит»."""
    say = rephrase or gemini_rephrase
    record = log or log_unanswered
    if text.startswith("/start"):
        return [(_HELLO, [])]
    if text.startswith("/reset"):
        reset(chat_id)
        return [(_RESET, [])]
    if text.startswith("/stats"):
        return [(summary(), [])]
    if is_handed_off(chat_id):
        keep_for_operator(chat_id, text)
        return []
    if operator_requested(text):
        full = resolve(text, chat_id=chat_id)
        lang = full["lang"] if full["lang"] in ("ru", "ky") else "ru"
        official = phrase(14, lang, "answer")
        spoken = say(text, official, lang)
        start_handoff(chat_id)
        set_topic(chat_id, 14)
        return [(spoken, []), (_HANDOFF[lang], [])]

    full = resolve(text, chat_id=chat_id)
    if full["mode"] != "direct":
        record(text, full["lang"], full["mode"])
    message, buttons = render(full)
    if full["mode"] == "direct" and full["faq_id"] is not None:
        message = say(text, message, full["lang"])
    return [(message, buttons)]


_STATIC = {_HELLO, _RESET, *_REFUSE.values(), *_BUTTONS.values(), *_HANDOFF.values()}


def _api(token: str, method: str, payload: dict | None = None, timeout: float = 15) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _send(token: str, chat_id: int | str, text: str, buttons: list[dict]) -> int | None:
    payload: dict = {"chat_id": chat_id, "text": text}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    result = _api(token, "sendMessage", payload, timeout=15)
    return (result.get("result") or {}).get("message_id")


def _should_rephrase(message: str, buttons: list, index: int) -> bool:
    if index != 0 or buttons or message in _STATIC:
        return False
    return not (message.startswith("Не закрыто") or message.startswith("Неотвеченных"))


def _deliver(token: str, chat_id: int, question: str, message: str, buttons: list, index: int) -> None:
    message_id = _send(token, chat_id, message, buttons)
    print("ответ отправлен", flush=True)
    if not _should_rephrase(message, buttons, index) or not message_id:
        return
    rewritten = gemini_rephrase(question, message, detect_lang(question))
    if not rewritten or rewritten == message:
        return
    try:
        _api(
            token,
            "editMessageText",
            {"chat_id": chat_id, "message_id": message_id, "text": rewritten},
            timeout=15,
        )
        print("пересказ обновлён", flush=True)
    except urllib.error.URLError as error:
        print(f"пересказ не заменил сообщение: {error}", flush=True)


def _official(question: str, official: str, lang: str) -> str:
    return official


def _handle_text(token: str, chat_id: int, text: str) -> None:
    print(f"вопрос: {text}", flush=True)
    drafts = compose(str(chat_id), text, rephrase=_official)
    if not drafts:
        print("бот молчит: диалог у оператора", flush=True)
        return
    for index, (message, buttons) in enumerate(drafts):
        _deliver(token, chat_id, text, message, buttons, index)


def _handle_callback(token: str, callback: dict) -> None:
    data = callback.get("data") or ""
    callback_id = callback.get("id")
    message = callback.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    _api(token, "answerCallbackQuery", {"callback_query_id": callback_id})
    if chat_id is None or ":" not in data or is_handed_off(str(chat_id)):
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
    official = phrase(faq_id, lang, "answer")
    _deliver(token, int(chat_id), "", official, [], 0)


def bot_username(token: str) -> str:
    payload = _api(token, "getMe")
    if not payload.get("ok"):
        raise RuntimeError(payload.get("description") or "Telegram не принял токен")
    return payload["result"].get("username") or ""


def run_bot() -> None:
    load_dotenv()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "Нет TELEGRAM_BOT_TOKEN. Запишите его в .env. "
            "Проверка answer() работает без него: python main.py ask \"текст\""
        )
    try:
        username = bot_username(token)
    except (urllib.error.URLError, RuntimeError, json.JSONDecodeError) as error:
        raise SystemExit(f"Telegram не ответил на getMe: {error}") from error
    offset = 0
    print(f"Бот @{username} слушает Telegram. Остановка: Ctrl+C.")
    while True:
        try:
            payload = _api(token, "getUpdates", {"timeout": 10, "offset": offset}, timeout=20)
        except KeyboardInterrupt:
            print("Остановка.", flush=True)
            return
        except urllib.error.URLError as error:
            print(f"Сеть Telegram недоступна: {error}", flush=True)
            time.sleep(2)
            continue
        if not payload.get("ok", False):
            print(payload.get("description") or "Telegram вернул ошибку", flush=True)
            time.sleep(2)
            continue
        for update in payload.get("result", []):
            offset = int(update["update_id"]) + 1
            try:
                if "message" in update and update["message"].get("text"):
                    chat_id = update["message"]["chat"]["id"]
                    _handle_text(token, chat_id, update["message"]["text"])
                elif "callback_query" in update:
                    _handle_callback(token, update["callback_query"])
            except Exception:
                print("Не удалось ответить:", flush=True)
                traceback.print_exc()
