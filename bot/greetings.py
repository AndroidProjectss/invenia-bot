"""Короткие приветствия с опечатками; не участвуют в выборе темы FAQ."""

from rapidfuzz.fuzz import ratio

from bot.textutil import basic_normalize


def greeting(text: str) -> dict | None:
    normalized = basic_normalize(text)
    if not normalized or len(normalized.split()) > 3:
        return None
    forms = {
        "ru": ("привет", "здравствуйте", "добрый день", "hello", "hi"),
        "ky": ("салам", "саламатсызбы", "саламатсыздарбы", "salam", "salamatsyzby"),
    }
    for lang, words in forms.items():
        if any(normalized == word or (len(word) >= 5 and ratio(normalized, word) >= 80) for word in words):
            return {"lang": lang, "faq_id": None, "confidence": 1.0, "candidates": [],
                    "mode": "greeting", "answer": "Саламатсызбы! Байланыш боюнча кандай сурооңуз бар?" if lang == "ky" else "Здравствуйте! Чем могу помочь по услугам связи?"}
    return None
