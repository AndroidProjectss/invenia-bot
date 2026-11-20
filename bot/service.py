"""Единая обработка сообщений независимо от канала доставки."""

from __future__ import annotations

from bot.answer import resolve
from bot.corpus import faq_by_id
from bot.dialog import set_topic
from bot.storage import add_message, ensure_chat, update_chat

REFUSE = {
    "ru": "В базе Invenia пока нет ответа на этот вопрос. Я передал диалог оператору.",
    "ky": "Invenia базасында бул суроого азырынча жооп жок. Диалог операторго өткөрүлдү.",
}
BUTTONS = {
    "ru": "Уточните, какой вопрос вы имели в виду:",
    "ky": "Кайсы суроону айтканыңызды тактаңыз:",
}


def phrase(faq_id: int, lang: str, field: str) -> str:
    item = faq_by_id()[faq_id]
    suffix = "ky" if lang == "ky" else "ru"
    return item[f"{field}_{suffix}"]


def render_response(full: dict) -> tuple[str, list[dict]]:
    lang = full["lang"] if full["lang"] in ("ru", "ky") else "ru"
    if full["mode"] == "refuse" or full["faq_id"] is None:
        return REFUSE[lang], []
    if full["mode"] == "buttons":
        buttons = [
            {
                "id": faq_id,
                "text": phrase(faq_id, lang, "question")[:60],
                "lang": lang,
            }
            for faq_id in full["candidates"][:3]
        ]
        return BUTTONS[lang], buttons
    return phrase(full["faq_id"], lang, "answer"), []


def process_incoming(
    channel: str,
    external_id: str,
    text: str,
    *,
    display_name: str = "",
    username: str = "",
    external_message_id: str | None = None,
    transform=None,
) -> dict:
    """Сохраняет входящее сообщение, запускает FAQ и готовит автоответ."""
    chat = ensure_chat(channel, external_id, display_name, username)
    saved = add_message(
        chat["id"],
        "inbound",
        "customer",
        text,
        external_message_id=external_message_id,
    )
    if saved is None:
        return {"duplicate": True, "chat": chat}

    memory_key = f"{channel}:{external_id}"
    if chat.get("current_topic") is not None:
        set_topic(memory_key, int(chat["current_topic"]))
    full = resolve(text, chat_id=memory_key)
    message, buttons = render_response(full)
    if transform is not None and full["mode"] == "direct" and full["faq_id"] is not None:
        message = transform(text, message, full["lang"])

    status = "needs_human" if full["mode"] == "refuse" else "open"
    changes = {"language": full["lang"], "status": status}
    if full["mode"] == "direct" and full["faq_id"] is not None:
        changes["current_topic"] = full["faq_id"]
    update_chat(chat["id"], **changes)

    if not chat["bot_enabled"]:
        update_chat(chat["id"], status="needs_human")
        return {"duplicate": False, "chat": chat, "send": False, "full": full}

    add_message(chat["id"], "outbound", "bot", message, mode=full["mode"])
    return {
        "duplicate": False,
        "chat": chat,
        "send": True,
        "full": full,
        "message": message,
        "buttons": buttons,
    }


def select_faq(
    channel: str,
    external_id: str,
    faq_id: int,
    lang: str,
    transform=None,
) -> dict:
    chat = ensure_chat(channel, external_id, language=lang)
    if faq_id not in faq_by_id():
        raise ValueError("Неизвестная тема FAQ")
    memory_key = f"{channel}:{external_id}"
    set_topic(memory_key, faq_id)
    update_chat(chat["id"], current_topic=faq_id, language=lang, status="open")
    message = phrase(faq_id, lang, "answer")
    if transform is not None:
        message = transform("", message, lang)
    add_message(chat["id"], "outbound", "bot", message, mode="selected")
    return {"chat": chat, "message": message}
