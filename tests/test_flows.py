import unittest

from bot.dialog import get_topic, reset
from bot.telegram_bot import compose


def _quiet(question, official, lang):
    return official


class TelegramFlowTest(unittest.TestCase):
    def setUp(self):
        reset()

    def test_direct_answer_refusal_and_dialog(self):
        direct = compose("flow", "Скока денег на счету?", rephrase=_quiet, log=lambda *args: None)
        self.assertIn("*100#", direct[0][0])
        self.assertEqual(direct[0][1], [])

        refused = compose("flow", "Прогноз погоды на завтра", rephrase=_quiet, log=lambda *args: None)
        self.assertIn("не помогу", refused[0][0].lower())
        self.assertEqual(refused[0][1], [])

        reset("roam")
        first = compose("roam", "Как подключить роуминг?", rephrase=_quiet, log=lambda *args: None)
        self.assertIn("15 сом", first[0][0])
        second = compose("roam", "А сколько стоит?", rephrase=_quiet, log=lambda *args: None)
        self.assertIn("15 сом", second[0][0])
        self.assertEqual(get_topic("roam"), 4)

    def test_low_confidence_message_has_three_buttons(self):
        # «что с номером» похоже сразу на несколько тем, прямого ответа нет.
        vague = compose("flow", "что с номером", rephrase=_quiet, log=lambda *args: None)
        self.assertEqual(len(vague[0][1]), 3)
        self.assertIn("уточните", vague[0][0].lower())


if __name__ == "__main__":
    unittest.main()
