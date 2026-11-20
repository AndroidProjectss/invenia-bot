"""Telegram: прямой ответ, три кнопки, отказ или передача оператору."""

from __future__ import annotations

import json
import os
import re
import time
import traceback
import urllib.error
import urllib.request

from bot.answer import resolve
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
from bot.media import UNREADABLE, question_from_file, telegram_attachment
from bot.service import process_incoming, select_faq
from bot.stats import log_unanswered, summary
from bot.storage import add_message, ensure_chat, update_chat
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
    "ru": "Сейчас подключу оператора. Если хотите снова писать мне, отправьте /reset.",
    "ky": "Азыр операторду кошом. Кайра мага жазгыңыз келсе, /reset деп жазыңыз.",
}
_OPERATOR_NOTE = (
    "Человек уже просит живого оператора. Скажи, что соединяешь его с оператором. "
    "Часы работы возьми из официального текста. Не проси написать слово «оператор». "
    "В конце коротко скажи, что команда /reset возвращает к этому боту."
)
_HELLO = (
    "Здравствуйте! Это поддержка Invenia. Напишите вопрос на русском или кыргызском.\n"
    "Саламатсызбы! Бул Invenia колдоо кызматы. Суроону орусча же кыргызча жазыңыз.\n"
    "/reset — забыть тему текущего диалога."
)
_RESET = "Тема этого чата забыта. Бот снова отвечает."


def phrase(faq_id: int, lang: str, field: str) -> str:
    item = faq_by_id()[faq_id]
    suffix = "ky" if lang == "ky" else "ru"
    return item[f"{field}_{suffix}"]


def _hours_sentence(official: str) -> str:
    for part in re.split(r"(?<=[.!])\s+", official):
        if re.search(r"\d{1,2}:\d{2}", part):
            return part.strip()
    return ""


def _operator_fallback(lang: str, official: str) -> str:
    hours = _hours_sentence(official)
    if hours:
        return f"{_HANDOFF[lang]} {hours}"
    return _HANDOFF[lang]


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
    if operator_requested(text) and not any(word in basic_normalize(text) for word in ("другого", "другой", "башка")):
        full = resolve(text, chat_id=chat_id)
        lang = full["lang"] if full["lang"] in ("ru", "ky") else "ru"
        official = phrase(14, lang, "answer")
        if say is gemini_rephrase:
            spoken = gemini_rephrase(text, official, lang, note=_OPERATOR_NOTE)
        else:
            spoken = say(text, official, lang)
        if spoken.strip() == official.strip():
            spoken = _operator_fallback(lang, official)
        start_handoff(chat_id)
        set_topic(chat_id, 14)
        return [(spoken, [])]

    full = resolve(text, chat_id=chat_id)
    if full["mode"] != "direct":
        record(text, full["lang"], full["mode"])
    message, buttons = render(full)
    if full["mode"] == "direct" and full["faq_id"] is not None:
        message = say(text, message, full["lang"])
    return [(message, buttons)]


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


def _send(token: str, chat_id: int | str, text: str, buttons: list[dict]) -> None:
    payload: dict = {"chat_id": chat_id, "text": text}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    _api(token, "sendMessage", payload, timeout=15)


def _handle_text(
    token: str,
    chat_id: int,
    text: str,
    display_name: str = "",
    username: str = "",
    message_id: str | None = None,
) -> None:
    print(f"вопрос: {text}", flush=True)
    chat = ensure_chat("telegram", str(chat_id), display_name, username)
    if text.startswith("/start"):
        add_message(chat["id"], "inbound", "customer", text, external_message_id=message_id)
        add_message(chat["id"], "outbound", "bot", _HELLO, mode="command")
        _send(token, chat_id, _HELLO, [])
        return
    if text.startswith("/reset"):
        reset(str(chat_id))
        reset(f"telegram:{chat_id}")
        add_message(chat["id"], "inbound", "customer", text, external_message_id=message_id)
        add_message(chat["id"], "outbound", "bot", _RESET, mode="command")
        update_chat(chat["id"], status="open", bot_enabled=1, current_topic=None)
        _send(token, chat_id, _RESET, [])
        return
    if text.startswith("/stats"):
        admins = {item.strip() for item in os.environ.get("TELEGRAM_ADMIN_IDS", "").split(",") if item.strip()}
        if str(chat_id) not in admins:
            _send(token, chat_id, "Команда доступна только оператору.", [])
            return
        _send(token, chat_id, summary(), [])
        return

    if not chat["bot_enabled"]:
        add_message(
            chat["id"], "inbound", "customer", text,
            external_message_id=message_id,
        )
        update_chat(chat["id"], status="needs_human")
        keep_for_operator(f"telegram:{chat_id}", text)
        print("бот молчит: диалог у оператора", flush=True)
        return

    if operator_requested(text) and not any(word in basic_normalize(text) for word in ("другого", "другой", "башка")):
        saved = add_message(
            chat["id"], "inbound", "customer", text,
            external_message_id=message_id,
        )
        if saved is None:
            return
        drafts = compose(f"telegram:{chat_id}", text)
        for message, buttons in drafts:
            add_message(chat["id"], "outbound", "bot", message, mode="handoff")
            _send(token, chat_id, message, buttons)
            print(f"ответ: {message}", flush=True)
        update_chat(chat["id"], status="needs_human", bot_enabled=0, current_topic=14)
        return

    result = process_incoming(
        "telegram",
        str(chat_id),
        text,
        display_name=display_name,
        username=username,
        external_message_id=message_id,
        transform=gemini_rephrase,
    )
    if result.get("duplicate") or not result.get("send"):
        return
    if result["full"]["mode"] == "refuse":
        log_unanswered(text, result["full"]["lang"], result["full"]["mode"])
    rows = [
        [{"text": item["text"], "callback_data": f"{item['id']}:{item['lang']}"}]
        for item in result["buttons"]
    ]
    _send(token, chat_id, result["message"], rows)
    print(f"ответ: {result['message']}", flush=True)


def _handle_callback(token: str, callback: dict) -> None:
    data = callback.get("data") or ""
    callback_id = callback.get("id")
    message = callback.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    _api(token, "answerCallbackQuery", {"callback_query_id": callback_id})
    if chat_id is None or ":" not in data or is_handed_off(str(chat_id)):
        return
    parts = data.split(":")
    if parts[0] == "faq" and len(parts) == 3:
        raw_id, lang = parts[1], parts[2]
    elif len(parts) == 2:
        raw_id, lang = parts
    else:
        return
    try:
        faq_id = int(raw_id)
    except ValueError:
        return
    if lang not in ("ru", "ky"):
        lang = "ru"
    if faq_id not in faq_by_id():
        return
    chat_row = ensure_chat("telegram", str(chat_id), language=lang)
    add_message(chat_row["id"], "inbound", "customer", phrase(faq_id, lang, "question"), mode="selection")
    result = select_faq(
        "telegram", str(chat_id), faq_id, lang,
        transform=gemini_rephrase,
    )
    _send(token, chat_id, result["message"], [])


def _download_telegram(token: str, file_id: str) -> bytes:
    meta = _api(token, "getFile", {"file_id": file_id}, timeout=20)
    path = (meta.get("result") or {}).get("file_path")
    if not path:
        raise RuntimeError("Telegram не отдал файл")
    with urllib.request.urlopen(f"https://api.telegram.org/file/bot{token}/{path}", timeout=30) as response:
        return response.read()


def _handle_attachment(token: str, message: dict, chat_id: int, display_name: str, username: str) -> None:
    caption = (message.get("caption") or "").strip()
    message_id = f"telegram:{chat_id}:{message.get('message_id')}"
    if caption:
        _handle_text(token, chat_id, caption, display_name=display_name, username=username, message_id=message_id)
        return
    found = telegram_attachment(message)
    if found is None:
        return
    file_id, mime, kind = found
    try:
        data = _download_telegram(token, file_id)
        text = question_from_file(data, mime, kind)
    except (urllib.error.URLError, RuntimeError, json.JSONDecodeError, TimeoutError, OSError):
        text = ""
    if not text:
        _send(token, chat_id, UNREADABLE, [])
        print(f"ответ: {UNREADABLE}", flush=True)
        return
    print(f"из вложения: {text}", flush=True)
    _handle_text(token, chat_id, text, display_name=display_name, username=username, message_id=message_id)


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
    print(f"Бот @{username} слушает Telegram. Остановка: Ctrl+C.", flush=True)
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
                if "message" in update:
                    message = update["message"]
                    chat_id = message["chat"]["id"]
                    sender = message.get("from") or {}
                    name = " ".join(
                        part for part in (sender.get("first_name", ""), sender.get("last_name", "")) if part
                    )
                    if message.get("text"):
                        _handle_text(
                            token,
                            chat_id,
                            message["text"],
                            display_name=name,
                            username=sender.get("username", ""),
                            message_id=f"telegram:{chat_id}:{message.get('message_id')}",
                        )
                    elif telegram_attachment(message):
                        _handle_attachment(token, message, chat_id, name, sender.get("username", ""))
                elif "callback_query" in update:
                    _handle_callback(token, update["callback_query"])
            except Exception:
                print("Не удалось ответить:", flush=True)
                traceback.print_exc()
