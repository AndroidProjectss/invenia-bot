import json
import os
import unittest
from unittest.mock import patch

from bot.gemini import grounded, read_media, rephrase
from bot.media import telegram_attachment, whatsapp_attachment


_OFFICIAL = "Наберите *100#. Проверка бесплатная."


class GeminiRephraseTest(unittest.TestCase):
    def test_extra_price_is_rejected(self):
        self.assertEqual(grounded(_OFFICIAL, "Наберите *100#. Это стоит 50 сом."), _OFFICIAL)

    def test_extra_ussd_is_rejected(self):
        self.assertEqual(grounded(_OFFICIAL, "Наберите *102#."), _OFFICIAL)

    def test_dropped_transfer_code_is_rejected(self):
        source = "*145*номер*сумма#, комиссия 2%, от 10 до 5000 сом, лимит 10000 сом."
        self.assertEqual(grounded(source, "Комиссия за перевод составляет 2%."), source)

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

    def test_voice_file_becomes_question_text(self):
        def transport(parts):
            self.assertEqual(parts[0]["inline_data"]["mime_type"], "audio/ogg")
            self.assertIn("дословно", parts[1]["text"])
            return "Как проверить баланс?"

        text = read_media(b"ogg", "audio/ogg", "voice", transport=transport)
        self.assertEqual(text, "Как проверить баланс?")

    def test_unreadable_file_is_empty(self):
        self.assertEqual(read_media(b"png", "image/png", "image", transport=lambda parts: ""), "")
        self.assertEqual(read_media(b"", "image/png", "image"), "")

    def test_attachment_kinds(self):
        voice = telegram_attachment({"voice": {"file_id": "v1"}})
        photo = telegram_attachment({"photo": [{"file_id": "small"}, {"file_id": "big"}]})
        document = whatsapp_attachment({"document": {"id": "d1", "mime_type": "application/pdf"}})
        self.assertEqual(voice[2], "voice")
        self.assertEqual(photo[0], "big")
        self.assertEqual(document[2], "document")

    def test_bad_json_shape_returns_official(self):
        def model(prompt):
            raise json.JSONDecodeError("bad", "", 0)

        self.assertEqual(rephrase("баланс", _OFFICIAL, "ky", transport=model), _OFFICIAL)


if __name__ == "__main__":
    unittest.main()
