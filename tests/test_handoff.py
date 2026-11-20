import unittest

from bot.answer import answer
from bot.dialog import is_handed_off, kept_messages, reset
from bot.telegram_bot import compose, operator_requested


def _quiet(question, official, lang):
    return official


class HandoffTest(unittest.TestCase):
    def setUp(self):
        reset()

    def test_jury_still_gets_faq_14(self):
        result = answer("Позовите живого оператора")
        self.assertEqual(result["faq_id"], 14)
        self.assertEqual(result["lang"], "ru")
        self.assertFalse(is_handed_off("jury"))

    def test_word_hands_chat_to_human_and_then_bot_is_silent(self):
        self.assertTrue(operator_requested("Позовите оператора"))
        self.assertTrue(operator_requested("operator"))
        messages = compose("live", "Позовите оператора", rephrase=_quiet, log=lambda *args: None)
        self.assertEqual(len(messages), 1)
        self.assertIn("оператор", messages[0][0].lower())
        self.assertIn("/reset", messages[0][0])
        self.assertIn("09:00", messages[0][0])
        self.assertTrue(is_handed_off("live"))

        silent = compose("live", "А сколько стоит роуминг?", rephrase=_quiet, log=lambda *args: None)
        self.assertEqual(silent, [])
        self.assertIn("А сколько стоит роуминг?", kept_messages("live"))

        again = compose("live", "/reset", rephrase=_quiet, log=lambda *args: None)
        self.assertIn("снова отвечает", again[0][0])
        self.assertFalse(is_handed_off("live"))
        back = compose("live", "Скока денег на счету?", rephrase=_quiet, log=lambda *args: None)
        self.assertIn("*100#", back[0][0])

    def test_stats_do_not_receive_the_chat_id(self):
        compose("996555000111", "operator", rephrase=_quiet, log=lambda *args: None)
        text = compose("996555000111", "/stats", rephrase=_quiet, log=lambda *args: None)[0][0]
        self.assertNotIn("996555000111", text)
        self.assertNotIn("chat", text.lower())


if __name__ == "__main__":
    unittest.main()
