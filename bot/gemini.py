"""Пересказ уже найденного ответа. Номер темы эта функция не выбирает."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from bot.envfile import load_dotenv

_MODEL = "gemini-2.5-flash"
_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{_MODEL}:generateContent"
_USSD = re.compile(r"\*\d[\d*]*#")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _facts(text: str) -> tuple[set[str], set[str]]:
    return set(_USSD.findall(text)), set(_NUMBER.findall(text))


def grounded(source: str, rewritten: str) -> str:
    """Если в пересказе новое число или USSD-код, остаётся официальный текст."""
    source = (source or "").strip()
    rewritten = (rewritten or "").strip().strip('"').strip()
    if not rewritten:
        return source
    source_codes, source_numbers = _facts(source)
    new_codes, new_numbers = _facts(rewritten)
    if not new_codes <= source_codes or not new_numbers <= source_numbers:
        return source
    return rewritten


def _prompt(question: str, official: str, lang: str) -> str:
    language = "кыргызском" if lang == "ky" else "русском"
    return (
        "Ответь абоненту как сотрудник поддержки: коротко, спокойно и по делу, на "
        f"{language} языке.\n"
        "Смысл, цены и коды бери только из официального текста. Ничего от себя не добавляй.\n"
        "Не пиши про базу, FAQ и про то, что ты не выдумываешь. Верни только сам ответ.\n\n"
        f"Вопрос абонента:\n{question}\n\n"
        f"Официальный текст:\n{official}"
    )


def _text_from_payload(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        return ""
    parts = ((candidates[0].get("content") or {}).get("parts") or [])
    chunks = [part.get("text", "") for part in parts if part.get("text") and not part.get("thought")]
    return "\n".join(chunks).strip()


def _call(key: str, prompt: str) -> str:
    body = json.dumps(
        {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        _URL,
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    with urllib.request.urlopen(request, timeout=4) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return _text_from_payload(payload)


def rephrase(question: str, official: str, lang: str, transport=None) -> str:
    """Без ключа, при ошибке сети и при лишнем факте возвращает official."""
    source = (official or "").strip()
    if not source:
        return source
    load_dotenv()
    if transport is None:
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            return source

        def transport(prompt: str) -> str:
            return _call(key, prompt)

    try:
        rewritten = transport(_prompt(question, source, lang))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return source
    except Exception:
        return source
    return grounded(source, rewritten if isinstance(rewritten, str) else "")
