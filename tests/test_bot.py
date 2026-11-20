import tempfile
import unittest
from pathlib import Path

from bot.answer import resolve
from bot.stats import log_unanswered, summary
from bot.telegram_bot import render


class StatsAndButtonsTest(unittest.TestCase):
    def test_stats_hide_chat_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "unanswered.jsonl"
            log_unanswered("Прогноз погоды", "ru", "refuse", path)
            log_unanswered("а может тариф", "ru", "buttons", path)
            text = summary(path)
            self.assertIn("Не закрыто ботом: 2", text)
            self.assertIn("Прогноз погоды", text)
            self.assertNotIn("chat", text.lower())
            raw = path.read_text(encoding="utf-8")
            self.assertNotIn("chat_id", raw)
            self.assertNotIn("996", raw)

    def test_refuse_has_no_buttons(self):
        full = resolve("Кредит на машину оформите")
        message, buttons = render(full)
        self.assertEqual(buttons, [])
        self.assertIn("не помогу", message.lower())

    def test_direct_answer_comes_from_faq(self):
        full = resolve("Скока денег на счету?")
        message, buttons = render(full)
        self.assertEqual(buttons, [])
        self.assertIn("*100#", message)

    def test_low_confidence_builds_three_buttons(self):
        full = {
            "lang": "ru",
            "faq_id": 1,
            "confidence": 0.4,
            "candidates": [1, 2, 11],
            "mode": "buttons",
        }
        message, buttons = render(full)
        self.assertIn("уточните", message.lower())
        self.assertEqual(len(buttons), 3)
        self.assertEqual(buttons[0][0]["callback_data"], "1:ru")


if __name__ == "__main__":
    unittest.main()
