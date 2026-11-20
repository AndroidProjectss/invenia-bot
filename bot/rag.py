"""Поиск по проверенной полной базе знаний Beeline Кыргызстан."""

from __future__ import annotations

import json
import os
import re
from datetime import date
from functools import lru_cache
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from bot.corpus import DATA
from bot.textutil import normalize_search

DEFAULT_PATH = DATA / "Beeline_KG_RAG_verified.jsonl"
DEFAULT_THRESHOLD = 0.30


def price_answer(text: str) -> dict | None:
    """Запрос цены требует ценовой записи, а не описания бонуса."""
    folded = text.lower()
    folded = re.sub(r"(?:каком|какой|не нужен|не про).{0,18}бонус\w*", "", folded)
    if not re.search(r"цен[аыуе]|стоимост|сколько.{0,12}стои|баа|канча.{0,12}тур", folded):
        return None
    if not re.search(r"цен[аыуе]|тариф|связь|подключ|баа", folded):
        return None
    # Конкретные услуги обрабатываются обычным поиском с фильтром цены.
    if re.search(r"роуминг|сим|sim|номер|бонус|роутер|router|сеники|укмуш|безлимит|30\s*(?:gb|гб)|70\s*(?:gb|гб)", folded):
        return None
    rows = [row for row in load_knowledge()
            if str(row["category"]).startswith("Тарифы:")
            and re.search(r"сколько стоит", row["question"].lower())]
    if not rows:
        return None
    answer = "Цены тарифов из загруженной базы:\n\n" + "\n\n".join(
        f"{row['category'].removeprefix('Тарифы:').strip()}: {row['answer']}\n{row.get('source_url', '')}"
        for row in rows
    ) + "\n\nУсловия указаны на дату проверки базы. Перед подключением уточните актуальность цены по ссылке."
    return {"lang": "ru", "faq_id": None, "confidence": 1.0, "candidates": [],
            "mode": "rag", "rag_id": "tariff-prices", "question": "Цены тарифов для подключения",
            "answer": answer, "sources": [row["id"] for row in rows]}


def knowledge_path() -> Path:
    configured = os.environ.get("RAG_KNOWLEDGE_PATH", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_PATH


def _active(row: dict, today: date | None = None) -> bool:
    if row.get("status") != "verified_from_official_page":
        return False
    raw_expiry = row.get("expires_at")
    if not raw_expiry:
        return True
    try:
        expiry = date.fromisoformat(str(raw_expiry))
    except ValueError:
        return False
    return expiry >= (today or date.today())


@lru_cache(maxsize=8)
def _load_cached(path_text: str, modified_ns: int, today_text: str) -> tuple[dict, ...]:
    del modified_ns  # часть ключа кэша: изменение файла автоматически создаёт новый индекс
    today = date.fromisoformat(today_text)
    path = Path(path_text)
    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Ошибка JSONL в строке {line_number}: {error}") from error
            required = {"id", "language", "category", "question", "answer"}
            missing = required - set(row)
            if missing:
                raise ValueError(
                    f"Запись {line_number} не содержит поля: {', '.join(sorted(missing))}"
                )
            if _active(row, today):
                rows.append(row)
    return tuple(rows)


def load_knowledge() -> tuple[dict, ...]:
    path = knowledge_path()
    if not path.exists():
        return ()
    stat = path.stat()
    return _load_cached(str(path.resolve()), stat.st_mtime_ns, date.today().isoformat())


@lru_cache(maxsize=8)
def _index(path_text: str, modified_ns: int, today_text: str):
    rows = _load_cached(path_text, modified_ns, today_text)
    documents = [
        normalize_search(
            " ".join(
                [
                    str(row["question"]),
                    str(row["category"]),
                    str(row["category"]),
                ]
            )
        )
        for row in rows
    ]
    if not documents:
        return rows, None, None
    vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        lowercase=False,
        sublinear_tf=True,
    )
    matrix = vectorizer.fit_transform(documents)
    return rows, vectorizer, matrix


def search(text: str, limit: int = 3) -> list[dict]:
    query = normalize_search(text)
    path = knowledge_path()
    if not query or not path.exists():
        return []
    stat = path.stat()
    rows, vectorizer, matrix = _index(
        str(path.resolve()), stat.st_mtime_ns, date.today().isoformat()
    )
    if not rows or vectorizer is None or matrix is None:
        return []
    vector = vectorizer.transform([query])
    scores = cosine_similarity(vector, matrix).ravel()
    order = scores.argsort()[::-1][: max(1, limit)]
    return [
        {**dict(rows[index]), "confidence": round(float(scores[index]), 4)}
        for index in order
    ]


def resolve(text: str, threshold: float | None = None) -> dict | None:
    prices = price_answer(text)
    if prices:
        return prices
    # Общий запрос об офисах ведёт на полную карту, а не в случайный офис.
    folded = text.lower()
    if re.search(r"офис|кеңсе|кенсе", folded) and not re.search(r"цум|вефа|vefa|парк|чуй|киев|горьк", folded):
        row = next((item for item in load_knowledge() if item["id"] == "BKG-0167"), None)
        if row:
            kyrgyz = bool(re.search(r"кай|жак|дарек|адреси|офиси", folded))
            return {"lang": "ky" if kyrgyz else "ru", "faq_id": None, "confidence": 1.0,
                    "candidates": [], "mode": "rag", "rag_id": row["id"],
                    "answer": "Beeline кеңселеринин даректери жана карта: https://www.beeline.kg/ru/map. Кайсы шаардан кеңсе издеп жатасыз?" if kyrgyz else "Адреса всех офисов Beeline и карта: https://www.beeline.kg/ru/map. В каком городе вам нужен офис?",
                    "source_url": row.get("source_url", "")}
    matches = search(text, limit=3)
    minimum = threshold
    if minimum is None:
        minimum = float(os.environ.get("RAG_MATCH_THRESHOLD", DEFAULT_THRESHOLD))
    if not matches or matches[0]["confidence"] < minimum:
        return None
    best = matches[0]
    if re.search(r"цен[аыуе]|стоимост|сколько.{0,12}стои|баа|канча.{0,12}тур", folded):
        # Не позволяем совпадению по слову «связь» ответить бонусом на вопрос о цене.
        if not re.search(r"сколько стоит|стоимость|цен[аыуе]", best["question"].lower()):
            return None
    if len(matches) > 1 and best["confidence"] < 0.65 and best["confidence"] - matches[1]["confidence"] < 0.05:
        return None
    return {
        "lang": best.get("language") or "ru",
        "faq_id": None,
        "confidence": best["confidence"],
        "candidates": [],
        "mode": "rag",
        "rag_id": best["id"],
        "question": best["question"],
        "answer": best["answer"],
        "category": best["category"],
        "source_url": best.get("source_url") or "",
        "checked_at": best.get("checked_at") or "",
    }


def summary() -> dict:
    rows = load_knowledge()
    return {
        "available": knowledge_path().exists(),
        "records": len(rows),
        "categories": len({row["category"] for row in rows}),
        "path": str(knowledge_path()),
    }
