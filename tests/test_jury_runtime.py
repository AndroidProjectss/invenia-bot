import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot.answer import answer
from bot.dialog import reset
from bot.service import process_incoming
from bot.storage import set_setting


class JuryRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.env = patch.dict(os.environ, {"BOT_DB_PATH": str(Path(self.folder.name) / "test.db")})
        self.env.start()
        self.addCleanup(self.env.stop)
        reset()
        set_setting("rag_enabled", False)

    def test_uncertain_live_message_gets_three_buttons(self):
        result = process_incoming("telegram", "uncertain", "что с номером")
        self.assertEqual(result["full"]["mode"], "buttons")
        self.assertEqual(len(result["buttons"]), 3)

    def test_greeting_typos_and_kyrgyz(self):
        for text, lang in [("привкт", "ru"), ("превет", "ru"), ("Салам", "ky"), ("Salam", "ky")]:
            result = process_incoming("telegram", text, text)
            self.assertEqual(result["full"]["mode"], "greeting")
            self.assertEqual(result["full"]["lang"], lang)

    def test_kyrgyz_without_special_letters(self):
        for text, topic in [("Сим картам жоголуп кетти", 6), ("Akcha kotoruu", 9)]:
            result = answer(text)
            self.assertEqual(result["lang"], "ky")
            self.assertEqual(result["faq_id"], topic)

    def test_jury_response_never_uses_transform(self):
        def unexpected(*args):
            raise AssertionError("Конкурсный ответ должен идти прямо из FAQ")
        result = process_incoming("telegram", "balance", "Как проверить баланс?", transform=unexpected)
        self.assertEqual(result["message"], "Наберите *100#. Проверка бесплатная.")

    def test_latin_followup_keeps_roaming(self):
        answer("Роуминг канча турат?", chat_id="ky-dialog")
        self.assertEqual(answer("Kancha turat?", chat_id="ky-dialog")["faq_id"], 4)
