import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot.service import process_incoming
from bot.storage import set_setting
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
