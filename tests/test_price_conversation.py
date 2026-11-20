import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot.service import process_incoming
from bot.storage import set_setting, get_messages, update_chat, add_message
from bot.rag import load_knowledge


class PriceConversationTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        env = patch.dict(os.environ, {"BOT_DB_PATH": str(Path(folder.name)/"test.db"),
                                      "AI_UNDERSTANDING_ENABLED": "0"})
        env.start()
        self.addCleanup(env.stop)
        set_setting("rag_enabled", True)

    def test_screenshot_dialog_without_ai_returns_actual_price_records(self):
        for text in (
            "Мне цены скажи, я же тебе говорю, только приехал хочу связь себе",
            "КАКОМ НАХУЙ БОНУСЕ, ДАЙ МНЕ ЦЕНЫ. ЦИФЕРКИ ТАКИЕ В СОМАХ ЗНАЕШЬ",
        ):
            result = process_incoming("telegram", "new-customer", text)
            self.assertEqual(result["full"]["rag_id"], "tariff-prices")
            self.assertIn("250 сомов", result["message"])
            self.assertNotIn("Tigrow", result["message"])
            for source_id in result["full"]["sources"]:
                record = next(row for row in load_knowledge() if row["id"] == source_id)
                self.assertIn(record["answer"], result["message"])

    def test_explicit_price_request_survives_wrong_ai_query(self):
        with patch("bot.service.understand", return_value={
            "lang": "ru", "kind": "question", "query": "Что такое бонус Связь при нуле?"
        }):
            result = process_incoming("telegram", "new-customer", "Мне цены скажи, хочу связь себе")
        self.assertEqual(result["full"]["rag_id"], "tariff-prices")

    def test_context_includes_previous_turns_from_same_chat_only(self):
        process_incoming("telegram", "other", "Привет")
        process_incoming("telegram", "customer", "Мне цены тарифов")
        with patch("bot.service.understand", return_value=None) as understand:
            process_incoming("telegram", "customer", "И на сколько дней?")
        context = understand.call_args.args[1]
        self.assertIn("Мне цены тарифов", context)
        self.assertNotIn("Привет", context)

    def test_paused_bot_does_not_call_ai(self):
        first = process_incoming("telegram", "operator-chat", "Привет")
        update_chat(first["chat"]["id"], bot_enabled=0)
        with patch("bot.service.understand", side_effect=AssertionError("ИИ не нужен")):
            result = process_incoming("telegram", "operator-chat", "Подскажите цены")
        self.assertFalse(result["send"])

    def test_answer_diagnostics_are_saved(self):
        result = process_incoming("telegram", "diagnostics", "Мне цены тарифов")
        message = get_messages(result["chat"]["id"])[-1]
        self.assertEqual(message["answer_details"]["rag_id"], "tariff-prices")
        self.assertEqual(message["answer_details"]["understanding"], "local")

    def test_reset_excludes_earlier_context(self):
        first = process_incoming("telegram", "reset-chat", "Мне цены тарифов")
        add_message(first["chat"]["id"], "inbound", "customer", "/reset")
        with patch("bot.service.understand", return_value=None) as understand:
            process_incoming("telegram", "reset-chat", "Как подключиться?")
        self.assertNotIn("Мне цены тарифов", understand.call_args.args[1])
