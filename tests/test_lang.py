import unittest

from bot.corpus import load_questions
from bot.lang import detect_lang


class LanguageTest(unittest.TestCase):
    def test_empty_is_russian(self):
        self.assertEqual(detect_lang(""), "ru")
        self.assertEqual(detect_lang("   "), "ru")

    def test_kyrgyz_letters_and_latin(self):
        self.assertEqual(detect_lang("Балансты кантип текшерем?"), "ky")
        self.assertEqual(detect_lang("Роуминг канча турат?"), "ky")
        self.assertEqual(detect_lang("Balansymdy kantip korom"), "ky")
        self.assertEqual(detect_lang("Internet ishtebei jatat"), "ky")
        self.assertEqual(detect_lang("Tarifti almashtyrgim kelet"), "ky")

    def test_russian_slang(self):
        self.assertEqual(detect_lang("Скока денег на счету?"), "ru")
        self.assertEqual(detect_lang("Инет не грузит, что делать"), "ru")

    def test_open_set(self):
        for row in load_questions():
            self.assertEqual(detect_lang(row["text"]), row["lang"], row["id"] + " " + row["text"])


if __name__ == "__main__":
    unittest.main()
