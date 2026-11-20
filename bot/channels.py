"""Отправка сообщений во внешние каналы."""

from __future__ import annotations

import json
import os
import urllib.request


def _json_request(url: str, payload: dict, headers: dict | None = None) -> dict:
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=request_headers,
    )
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.loads(response.read().decode("utf-8"))


def send_telegram(chat_id: str, text: str, buttons: list[dict] | None = None) -> dict:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Не настроен TELEGRAM_BOT_TOKEN")
    payload: dict = {"chat_id": chat_id, "text": text}
    if buttons:
        payload["reply_markup"] = {
            "inline_keyboard": [
                [{"text": button["text"], "callback_data": f"faq:{button['id']}:{button['lang']}"}]
                for button in buttons[:3]
            ]
        }
    return _json_request(f"https://api.telegram.org/bot{token}/sendMessage", payload)


def send_whatsapp(recipient: str, text: str, buttons: list[dict] | None = None) -> dict:
    token = os.environ.get("WHATSAPP_ACCESS_TOKEN", "").strip()
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    if not token or not phone_number_id:
        raise RuntimeError("Не настроены WHATSAPP_ACCESS_TOKEN и WHATSAPP_PHONE_NUMBER_ID")
    payload: dict = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
    }
    if buttons:
        payload.update(
            {
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": text},
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {
                                    "id": f"faq:{button['id']}:{button['lang']}",
                                    "title": button["text"][:20],
                                },
                            }
                            for button in buttons[:3]
                        ]
                    },
                },
            }
        )
    else:
        payload.update({"type": "text", "text": {"preview_url": False, "body": text}})
    version = os.environ.get("WHATSAPP_GRAPH_VERSION", "v21.0").strip()
    return _json_request(
        f"https://graph.facebook.com/{version}/{phone_number_id}/messages",
        payload,
        {"Authorization": f"Bearer {token}"},
    )


def send_channel(channel: str, recipient: str, text: str, buttons: list[dict] | None = None) -> dict:
    if channel == "telegram":
        return send_telegram(recipient, text, buttons)
    if channel == "whatsapp":
        return send_whatsapp(recipient, text, buttons)
    raise ValueError(f"Неподдерживаемый канал: {channel}")
