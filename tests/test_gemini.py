import json
import os
import unittest
from unittest.mock import patch

from bot.gemini import grounded, rephrase


_OFFICIAL = "Наберите *100#. Проверка бесплатная."


class GeminiRephraseTest(unittest.TestCase):
    def test_extra_price_is_rejected(self):
        self.assertEqual(grounded(_OFFICIAL, "Наберите *100#. Это стоит 50 сом."), _OFFICIAL)

    def test_extra_ussd_is_rejected(self):
        self.assertEqual(grounded(_OFFICIAL, "Наберите *102#."), _OFFICIAL)

    def test_same_facts_are_kept(self):
        rewritten = "Проверка баланса бесплатная: наберите *100#."
        self.assertEqual(grounded(_OFFICIAL, rewritten), rewritten)

    def test_missing_key_returns_official(self):
        with patch("bot.gemini.load_dotenv"):
            with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
                self.assertEqual(rephrase("баланс", _OFFICIAL, "ru"), _OFFICIAL)

    def test_network_error_returns_official(self):
        def broken(prompt):
            raise TimeoutError("нет сети")

        self.assertEqual(rephrase("баланс", _OFFICIAL, "ru", transport=broken), _OFFICIAL)

    def test_invented_price_from_model_returns_official(self):
        def model(prompt):
            self.assertIn("*100#", prompt)
            return "Баланс смотрите по *100#. Комиссия 15 сом."

        self.assertEqual(rephrase("баланс", _OFFICIAL, "ru", transport=model), _OFFICIAL)

    def test_clean_model_text_is_used(self):
        def model(prompt):
            return "Баланс проверяется бесплатно, наберите *100#."

        text = rephrase("баланс", _OFFICIAL, "ru", transport=model)
        self.assertIn("*100#", text)
        self.assertNotEqual(text, _OFFICIAL)

    def test_bad_json_shape_returns_official(self):
        def model(prompt):
            raise json.JSONDecodeError("bad", "", 0)

        self.assertEqual(rephrase("баланс", _OFFICIAL, "ky", transport=model), _OFFICIAL)


if __name__ == "__main__":
    unittest.main()
