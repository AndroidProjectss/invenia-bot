import unittest

from bot.answer import answer
from bot.corpus import load_dialogs
from bot.dialog import get_topic, reset


class DialogTest(unittest.TestCase):
    def setUp(self):
        reset()

    def test_example_dialog(self):
        dialog = load_dialogs()[0]
        chat_id = dialog["id"]
        for turn in dialog["turns"]:
            result = answer(turn["text"], chat_id=chat_id)
            self.assertEqual(result["lang"], turn["lang"], turn["text"])
            self.assertEqual(result["faq_id"], turn["faq_id"], turn["text"])

    def test_followup_stays_on_chat_topic(self):
        answer("Хочу другой тариф", chat_id="tariff")
        follow = answer("А сколько стоит?", chat_id="tariff")
        self.assertEqual(follow["faq_id"], 5)

        answer("Как подключить роуминг?", chat_id="roam")
        follow = answer("А сколько стоит?", chat_id="roam")
        self.assertEqual(follow["faq_id"], 4)
        self.assertEqual(follow["candidates"][0], 4)

    def test_clear_new_topic_overrides_context(self):
        answer("Как подключить роуминг?", chat_id="mix")
        result = answer("Сколько комиссия за перевод?", chat_id="mix")
        self.assertEqual(result["faq_id"], 9)

    def test_new_chat_does_not_inherit_topic(self):
        answer("Хочу другой тариф", chat_id="one")
        self.assertIsNone(get_topic("two"))
        # Полный вопрос в новом чате задаёт свою тему, а не тариф из чужого чата.
        result = answer("Как подключить роуминг?", chat_id="two")
        self.assertEqual(result["faq_id"], 4)
        self.assertEqual(get_topic("two"), 4)

    def test_stateless_call_ignores_saved_topic(self):
        answer("Хочу другой тариф", chat_id="saved")
        self.assertEqual(get_topic("saved"), 5)
        # Без chat_id «а сколько стоит?» не обязана угадать тариф.
        answer("А сколько стоит?")
        self.assertEqual(get_topic("saved"), 5)


if __name__ == "__main__":
    unittest.main()
