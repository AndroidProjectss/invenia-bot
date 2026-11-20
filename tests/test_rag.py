import os
import tempfile
import unittest
from pathlib import Path

from bot.admin_app import create_app
from bot.rag import resolve as resolve_rag
from bot.rag import summary
from bot.service import process_incoming, resolve_knowledge
from bot.storage import get_setting_bool, set_setting


class FullKnowledgeBaseTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.previous_db = os.environ.get("BOT_DB_PATH")
        os.environ["BOT_DB_PATH"] = str(Path(self.folder.name) / "rag-test.sqlite3")

    def tearDown(self):
        if self.previous_db is None:
            os.environ.pop("BOT_DB_PATH", None)
        else:
            os.environ["BOT_DB_PATH"] = self.previous_db

    def test_verified_jsonl_is_loaded(self):
        info = summary()
        self.assertTrue(info["available"])
        self.assertEqual(info["records"], 167)
        self.assertEqual(info["categories"], 18)

    def test_rag_finds_verified_answer_and_rejects_foreign_question(self):
        result = resolve_rag("Как позвонить в поддержку с номера другого оператора?")
        self.assertIsNotNone(result)
        self.assertEqual(result["rag_id"], "BKG-0002")
        self.assertIn("+996 775 58 06 11", result["answer"])
        self.assertIsNone(resolve_rag("Какая погода завтра?"))

    def test_full_mode_keeps_strong_jury_answer(self):
        set_setting("rag_enabled", True)
        result = resolve_knowledge("Как проверить баланс?", "test:balance")
        self.assertEqual(result["mode"], "direct")
        self.assertEqual(result["faq_id"], 1)

    def test_full_mode_uses_extended_base(self):
        set_setting("rag_enabled", True)
        result = process_incoming(
            "telegram",
            "rag-user",
            "Где находится офис в Бишкек Парке?",
            external_message_id="rag:1",
        )
        self.assertEqual(result["full"]["mode"], "rag")
        self.assertEqual(result["full"]["rag_id"], "BKG-0165")
        self.assertIn("Киевская", result["message"])

    def test_admin_toggle_persists_global_mode(self):
        app = create_app({"TESTING": True, "ADMIN_PASSWORD": "secret", "SECRET_KEY": "test"})
        client = app.test_client()
        client.post("/login", data={"password": "secret"})

        page = client.get("/")
        self.assertIn("FAQ жюри".encode(), page.data)
        response = client.post(
            "/settings/knowledge-base",
            data={"enabled": "1"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(get_setting_bool("rag_enabled"))
        self.assertIn("Полная база".encode(), response.data)

        client.post("/settings/knowledge-base", data={"enabled": "0"})
        self.assertFalse(get_setting_bool("rag_enabled"))


if __name__ == "__main__":
    unittest.main()
