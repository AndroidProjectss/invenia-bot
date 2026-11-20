"""Вложение становится текстом вопроса. Ответ по теме потом ищет обычный FAQ."""

from __future__ import annotations

from bot.gemini import read_media

UNREADABLE = "Не разобрал вложение. Напишите вопрос текстом."


def question_from_file(data: bytes, mime: str, kind: str) -> str:
    return read_media(data, mime, kind)


def telegram_attachment(message: dict) -> tuple[str, str, str] | None:
    """file_id, mime, kind. kind: voice, image или document."""
    if message.get("voice"):
        voice = message["voice"]
        return voice["file_id"], voice.get("mime_type") or "audio/ogg", "voice"
    if message.get("audio"):
        audio = message["audio"]
        return audio["file_id"], audio.get("mime_type") or "audio/mpeg", "voice"
    if message.get("photo"):
        return message["photo"][-1]["file_id"], "image/jpeg", "image"
    document = message.get("document")
    if not document:
        return None
    mime = document.get("mime_type") or "application/octet-stream"
    kind = "image" if mime.startswith("image/") else "document"
    return document["file_id"], mime, kind


def whatsapp_attachment(message: dict) -> tuple[str, str, str] | None:
    """media id, mime, kind."""
    if message.get("audio"):
        audio = message["audio"]
        return audio.get("id", ""), audio.get("mime_type") or "audio/ogg", "voice"
    if message.get("image"):
        image = message["image"]
        return image.get("id", ""), image.get("mime_type") or "image/jpeg", "image"
    if message.get("document"):
        document = message["document"]
        mime = document.get("mime_type") or "application/octet-stream"
        kind = "image" if mime.startswith("image/") else "document"
        return document.get("id", ""), mime, kind
    return None
