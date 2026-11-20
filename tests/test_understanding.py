import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot.service import process_incoming
from bot.storage import set_setting
from bot.understanding import understand


class UnderstandingTest(unittest.TestCase):
    def test_valid_kyrgyz_normalization(self):
        with patch.dict(os.environ, {"AI_UNDERSTANDING_ENABLED": "1"}):
            result = understand("акчам канча калды", transport=lambda _: json.dumps(
                {"lang": "ky", "kind": "question", "query": "Как проверить баланс?"}))
        self.assertEqual(result["lang"], "ky")
        self.assertEqual(result["query"], "Как проверить баланс?")

    def test_failure_and_invalid_model_output_fall_back(self):
        for raw in ("not json", '[]', '{"faq_id":1}', '{"lang":"en","kind":"question","query":"hi"}'):
            self.assertIsNone(understand("вопрос", transport=lambda _, value=raw: value))

    def test_search_chooses_topic_and_original_language_selects_answer(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"BOT_DB_PATH": str(Path(folder)/"test.db")}):
            set_setting("rag_enabled", False)
            with patch("bot.service.understand", return_value={
                "lang": "ky", "kind": "question", "query": "Как проверить баланс?"
            }):
                result = process_incoming("telegram", "ky-user", "акчам канча калды")
            self.assertEqual(result["full"]["faq_id"], 1)
            self.assertEqual(result["message"], "*100# териңиз. Текшерүү акысыз.")

    def test_model_outside_never_returns_guessed_topic(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"BOT_DB_PATH": str(Path(folder)/"test.db")}):
            with patch("bot.service.understand", return_value={
                "lang": "ru", "kind": "outside", "query": "Какая погода?"
            }):
                result = process_incoming("whatsapp", "weather", "Какая погода?")
            self.assertIsNone(result["full"]["faq_id"])
            self.assertEqual(result["full"]["mode"], "refuse")
