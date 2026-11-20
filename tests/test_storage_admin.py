import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot.admin_app import create_app
from bot.dialog import reset
from bot.service import process_incoming
from bot.storage import get_messages, list_chats, update_chat
from bot.telegram_bot import _handle_text


class StorageAndAdminTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.folder.cleanup)
        self.previous_db = os.environ.get("BOT_DB_PATH")
        os.environ["BOT_DB_PATH"] = str(Path(self.folder.name) / "test.sqlite3")
        reset()

    def tearDown(self):
        if self.previous_db is None:
            os.environ.pop("BOT_DB_PATH", None)
        else:
            os.environ["BOT_DB_PATH"] = self.previous_db

    def test_incoming_message_is_saved_with_bot_answer(self):
        result = process_incoming(
            "telegram",
            "42",
            "Как проверить баланс?",
            display_name="Тестовый клиент",
            external_message_id="tg:42:1",
        )
        self.assertTrue(result["send"])
        self.assertEqual(result["full"]["faq_id"], 1)
        chats = list_chats()
        self.assertEqual(len(chats), 1)
        messages = get_messages(chats[0]["id"])
        self.assertEqual([item["sender"] for item in messages], ["customer", "bot"])
        self.assertIn("*100#", messages[1]["text"])

    def test_disabled_bot_collects_message_without_autoanswer(self):
        first = process_incoming("whatsapp", "996500000000", "Как проверить баланс?")
        update_chat(first["chat"]["id"], bot_enabled=0)
        second = process_incoming("whatsapp", "996500000000", "А сколько стоит?")
        self.assertFalse(second["send"])
        self.assertEqual(list_chats()[0]["status"], "needs_human")

    def test_admin_requires_login_and_renders_conversation(self):
        process_incoming("telegram", "77", "Как проверить баланс?", display_name="Айбек")
        app = create_app({"TESTING": True, "ADMIN_PASSWORD": "secret", "SECRET_KEY": "test"})
        client = app.test_client()
        self.assertEqual(client.get("/").status_code, 302)
        response = client.post("/login", data={"password": "secret"}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Айбек".encode(), response.data)
        self.assertIn("*100#".encode(), response.data)

    def test_operator_reply_uses_chat_channel(self):
        process_incoming("telegram", "88", "Как проверить баланс?")
        chat = list_chats()[0]
        app = create_app({"TESTING": True, "ADMIN_PASSWORD": "secret", "SECRET_KEY": "test"})
        client = app.test_client()
        client.post("/login", data={"password": "secret"})
        with patch("bot.admin_app.send_channel", return_value={"ok": True}) as send:
            response = client.post(
                f"/chats/{chat['id']}/reply",
                data={"text": "Ответ оператора"},
                follow_redirects=True,
            )
        self.assertEqual(response.status_code, 200)
        send.assert_called_once_with("telegram", "88", "Ответ оператора")
        self.assertEqual(get_messages(chat["id"])[-1]["sender"], "operator")

    def test_live_telegram_handler_sends_and_saves_only_once(self):
        with (
            patch("bot.telegram_bot._send") as send,
            patch("bot.telegram_bot.gemini_rephrase", side_effect=lambda _q, answer, _lang: answer),
        ):
            _handle_text(
                "token",
                901,
                "Как проверить баланс?",
                display_name="Telegram User",
                message_id="telegram:901:1",
            )
        send.assert_called_once()
        chat = list_chats()[0]
        messages = get_messages(chat["id"])
        self.assertEqual([row["sender"] for row in messages], ["customer", "bot"])

    def test_live_telegram_operator_request_is_handed_off_once(self):
        with (
            patch("bot.telegram_bot._send") as send,
            patch("bot.telegram_bot.gemini_rephrase", side_effect=lambda _q, answer, _lang, **_kw: answer),
        ):
            _handle_text(
                "token",
                902,
                "Позовите оператора",
                display_name="Telegram User",
                message_id="telegram:902:1",
            )
        send.assert_called_once()
        chat = list_chats()[0]
        self.assertEqual(chat["status"], "needs_human")
        self.assertEqual(chat["bot_enabled"], 0)
        self.assertEqual(len(get_messages(chat["id"])), 2)

    def test_whatsapp_webhook_verification(self):
        previous = os.environ.get("WHATSAPP_VERIFY_TOKEN")
        os.environ["WHATSAPP_VERIFY_TOKEN"] = "verify-me"
        self.addCleanup(
            lambda: os.environ.pop("WHATSAPP_VERIFY_TOKEN", None)
            if previous is None
            else os.environ.__setitem__("WHATSAPP_VERIFY_TOKEN", previous)
        )
        app = create_app({"TESTING": True, "SECRET_KEY": "test"})
        client = app.test_client()
        response = client.get(
            "/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=verify-me&hub.challenge=12345"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "12345")

    def test_whatsapp_message_is_answered_and_collected(self):
        app = create_app({"TESTING": True, "SECRET_KEY": "test"})
        client = app.test_client()
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "contacts": [
                                    {"wa_id": "996555000000", "profile": {"name": "Нурбек"}}
                                ],
                                "messages": [
                                    {
                                        "id": "wamid.1",
                                        "from": "996555000000",
                                        "type": "text",
                                        "text": {"body": "Как проверить баланс?"},
                                    }
                                ],
                            },
                        }
                    ]
                }
            ]
        }
        with patch("bot.admin_app.send_whatsapp", return_value={"messages": [{"id": "out.1"}]}) as send:
            response = client.post("/webhooks/whatsapp", json=payload)
        self.assertEqual(response.status_code, 200)
        send.assert_called_once()
        self.assertEqual(list_chats()[0]["display_name"], "Нурбек")
        self.assertEqual(len(get_messages(list_chats()[0]["id"])), 2)


if __name__ == "__main__":
    unittest.main()
