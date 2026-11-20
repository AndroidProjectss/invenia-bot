"""Локальный журнал вопросов, которые бот не закрыл, без идентификатора чата."""

from __future__ import annotations

import json
from pathlib import Path

from bot.corpus import DATA

DEFAULT_PATH = DATA / "unanswered.jsonl"


def log_unanswered(text: str, lang: str, reason: str, path: Path | None = None) -> None:
    target = path or DEFAULT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "text": (text or "").strip(),
        "lang": lang,
        "reason": reason,
    }
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_unanswered(path: Path | None = None) -> list[dict]:
    target = path or DEFAULT_PATH
    if not target.exists():
        return []
    rows = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def summary(path: Path | None = None) -> str:
    rows = load_unanswered(path)
    if not rows:
        return "Неотвеченных вопросов нет."
    refused = sum(1 for row in rows if row.get("reason") == "refuse")
    uncertain = sum(1 for row in rows if row.get("reason") == "buttons")
    lines = [
        f"Не закрыто ботом: {len(rows)}",
        f"Отказ, темы в базе нет: {refused}",
        f"Показаны три похожих вопроса: {uncertain}",
        "Последние формулировки:",
    ]
    seen: set[str] = set()
    for row in reversed(rows):
        text = row.get("text") or "(пустой вопрос)"
        if text in seen:
            continue
        seen.add(text)
        lines.append(f"- {text}")
        if len(seen) >= 15:
            break
    return "\n".join(lines)
