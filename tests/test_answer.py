import unittest

from bot.answer import answer
from bot.corpus import load_questions


class AnswerContractTest(unittest.TestCase):
    def test_shape_and_open_set(self):
        for row in load_questions():
            result = answer(row["text"])
            self.assertEqual(set(result), {"lang", "faq_id", "confidence", "candidates"}, row["id"])
            self.assertEqual(result["lang"], row["lang"], row["text"])
            self.assertEqual(result["faq_id"], row["faq_id"], row["text"])
            self.assertGreaterEqual(result["confidence"], 0.0)
            self.assertLessEqual(result["confidence"], 1.0)
            if row["faq_id"] is None:
                self.assertEqual(result["candidates"], [], row["text"])
            else:
                self.assertEqual(result["candidates"][0], result["faq_id"], row["text"])
                self.assertIn(row["faq_id"], result["candidates"], row["text"])
                self.assertLessEqual(len(result["candidates"]), 3)

    def test_out_of_scope_does_not_invent(self):
        result = answer("Прогноз погоды на завтра")
        self.assertEqual(result["lang"], "ru")
        self.assertIsNone(result["faq_id"])
        self.assertEqual(result["candidates"], [])

    def test_empty_question(self):
        result = answer("")
        self.assertEqual(result, {"lang": "ru", "faq_id": None, "confidence": 0.0, "candidates": []})


if __name__ == "__main__":
    unittest.main()
