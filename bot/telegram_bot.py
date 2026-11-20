"""Telegram: прямой ответ, три кнопки или отказ. Токен только из окружения."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from bot.channels import send_telegram
from bot.corpus import ROOT, faq_by_id
from bot.dialog import reset
from bot.service import process_incoming, select_faq
from bot.stats import log_unanswered, summary
from bot.storage import add_message, ensure_chat

_REFUSE = {
    "ru": "В базе FAQ нет ответа на этот вопрос. Я не буду его выдумывать.",
    "ky": "Бул суроого FAQ базасында жооп жок. Мен жоопту ойлоп таппайм.",
}
_BUTTONS = {
    "ru": "Я не уверен. Выберите близкий вопрос:",
    "ky": "Ишенбей жатам. Жакын суроону тандаңыз:",
}
_HELLO = (
    "Здравствуйте! Это поддержка Invenia. Напишите вопрос на русском или кыргызском.\n"
    "Саламатсызбы! Бул Invenia колдоо кызматы. Суроону орусча же кыргызча жазыңыз.\n"
    "/reset — забыть тему текущего диалога."
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
    normalized = []
    for row in buttons:
        button = row[0]
        raw = button.get("callback_data", "")
        raw_id, lang = raw.split(":", 1) if ":" in raw else ("", "ru")
        if raw_id.isdigit():
            normalized.append({"id": int(raw_id), "lang": lang, "text": button["text"]})
    send_telegram(str(chat_id), text, normalized)


def _handle_text(
    token: str,
    chat_id: int,
    text: str,
    display_name: str = "",
    username: str = "",
    message_id: str | None = None,
) -> None:
    if text.startswith("/start"):
        _send(token, chat_id, _HELLO, [])
        return
    if text.startswith("/reset"):
        reset(str(chat_id))
        _send(token, chat_id, "Тема этого чата забыта. Задайте вопрос заново.", [])
        return
    if text.startswith("/stats"):
        admins = {item.strip() for item in os.environ.get("TELEGRAM_ADMIN_IDS", "").split(",") if item.strip()}
        if str(chat_id) not in admins:
            _send(token, chat_id, "Команда доступна только оператору.", [])
            return
        _send(token, chat_id, summary(), [])
        return
    result = process_incoming(
        "telegram",
        str(chat_id),
        text,
        display_name=display_name,
        username=username,
        external_message_id=message_id,
    )
    if result.get("duplicate") or not result.get("send"):
        return
    if result["full"]["mode"] != "direct":
        log_unanswered(text, result["full"]["lang"], result["full"]["mode"])
    rows = [
        [{"text": item["text"], "callback_data": f"{item['id']}:{item['lang']}"}]
        for item in result["buttons"]
    ]
    _send(token, chat_id, result["message"], rows)


def _handle_callback(token: str, callback: dict) -> None:
    data = callback.get("data") or ""
    callback_id = callback.get("id")
    message = callback.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    _api(token, "answerCallbackQuery", {"callback_query_id": callback_id})
    if chat_id is None or ":" not in data:
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
    result = select_faq("telegram", str(chat_id), faq_id, lang)
    _send(token, chat_id, result["message"], [])


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
                message = update["message"]
                chat_id = message["chat"]["id"]
                sender = message.get("from") or {}
                name = " ".join(
                    part for part in (sender.get("first_name", ""), sender.get("last_name", "")) if part
                )
                _handle_text(
                    token,
                    chat_id,
                    message["text"],
                    display_name=name,
                    username=sender.get("username", ""),
                    message_id=f"telegram:{chat_id}:{message.get('message_id')}",
                )
            elif "callback_query" in update:
                _handle_callback(token, update["callback_query"])
