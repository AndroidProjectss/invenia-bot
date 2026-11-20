"""Сравнение rapidfuzz и TF-IDF на открытых 40 фразах."""

from __future__ import annotations

from bot.answer import answer, rank_for
from bot.config import CONFIDENT_THRESHOLD, REJECT_THRESHOLD, SELECTED_METHOD
from bot.corpus import load_questions
from bot.lang import detect_lang

METHODS = ("fuzz", "tfidf")


def _rows(method: str) -> list[dict]:
    prepared = []
    for row in load_questions():
        ranked = rank_for(method, row["text"])
        top = ranked[:3]
        prepared.append(
            {
                **row,
                "lang_pred": detect_lang(row["text"]),
                "best_id": top[0][0] if top else None,
                "best_score": top[0][1] if top else 0.0,
                "top3": [faq_id for faq_id, _ in top],
            }
        )
    return prepared


def sweep_threshold(rows: list[dict]) -> float:
    """Порог, при котором верных первых номеров больше всего и вне FAQ — пусто."""
    scored = [row["best_score"] for row in rows]
    candidates = [0.0, *scored, 1.01]
    best_threshold = 0.0
    best_key = None
    for threshold in sorted(set(round(value, 4) for value in candidates)):
        top1 = 0
        top3 = 0
        for row in rows:
            predicted = None if row["best_score"] < threshold else row["best_id"]
            found = [] if predicted is None else row["top3"]
            gold = row["faq_id"]
            if predicted == gold:
                top1 += 1
            if gold is None:
                if predicted is None:
                    top3 += 1
            elif gold in found:
                top3 += 1
        # Сначала точность первого места, потом топ-3, потом более низкий порог:
        # так слабое, но верное совпадение на скрытом наборе не отрезается.
        key = (top1, top3, -threshold)
        if best_key is None or key > best_key:
            best_key = key
            best_threshold = threshold
    return best_threshold


def _metrics(rows: list[dict], threshold: float) -> dict:
    total = len(rows)
    lang_ok = top1 = top3 = 0
    misses = []
    for row in rows:
        predicted = None if row["best_score"] < threshold else row["best_id"]
        found = [] if predicted is None else row["top3"]
        gold = row["faq_id"]
        lang_hit = row["lang_pred"] == row["lang"]
        top1_hit = predicted == gold
        if gold is None:
            top3_hit = predicted is None
        else:
            top3_hit = gold in found
        lang_ok += int(lang_hit)
        top1 += int(top1_hit)
        top3 += int(top3_hit)
        if not (lang_hit and top1_hit and top3_hit):
            misses.append(
                {
                    "id": row["id"],
                    "text": row["text"],
                    "lang": row["lang"],
                    "lang_pred": row["lang_pred"],
                    "gold": gold,
                    "predicted": predicted,
                    "score": round(row["best_score"], 3),
                    "top3": found,
                }
            )
    return {
        "lang": lang_ok / total,
        "top1": top1 / total,
        "top3": top3 / total,
        "misses": misses,
        "threshold": threshold,
    }


def report() -> dict[str, dict]:
    summary = {}
    questions = load_questions()
    lang_ok = sum(1 for row in questions if detect_lang(row["text"]) == row["lang"])
    print(f"Язык на открытом наборе: {lang_ok}/{len(questions)}")
    print()
    for method in METHODS:
        rows = _rows(method)
        threshold = sweep_threshold(rows)
        metrics = _metrics(rows, threshold)
        summary[method] = metrics
        correct = [row["best_score"] for row in rows if row["faq_id"] is not None and row["best_id"] == row["faq_id"]]
        foreign = [row["best_score"] for row in rows if row["faq_id"] is None]
        gap = ""
        if correct and foreign:
            gap = f"  зазор {min(correct):.2f} против {max(foreign):.2f}"
        mark = "  <- в боте" if method == SELECTED_METHOD else ""
        print(
            f"{method:6}  лучший порог {threshold:.3f}  "
            f"первый {metrics['top1']:.0%}  топ-3 {metrics['top3']:.0%}{gap}{mark}"
        )
        for miss in metrics["misses"]:
            print(
                f"  {miss['id']} «{miss['text']}» "
                f"язык {miss['lang_pred']}/{miss['lang']} "
                f"тема {miss['predicted']}/{miss['gold']} "
                f"оценка {miss['score']} топ {miss['top3']}"
            )
    print()
    print(
        "При равной точности в боте оставлен tfidf: "
        "чужой вопрос и слабый верный ответ у него далеко друг от друга."
    )
    print(
        f"Пороги бота: отказ ниже {REJECT_THRESHOLD:.2f}, "
        f"сразу ответ от {CONFIDENT_THRESHOLD:.2f}, между ними — три кнопки."
    )
    print()
    live_misses = []
    for row in questions:
        predicted = answer(row["text"])
        if predicted["lang"] != row["lang"] or predicted["faq_id"] != row["faq_id"]:
            live_misses.append((row, predicted))
        elif row["faq_id"] is not None and row["faq_id"] not in predicted["candidates"]:
            live_misses.append((row, predicted))
    print(f"Функция answer() на открытом наборе, метод {SELECTED_METHOD}: ", end="")
    if live_misses:
        print(f"ошибок {len(live_misses)}")
        for row, predicted in live_misses:
            print(f"  {row['id']} {row['text']!r} -> {predicted}, ждали {row['lang']} {row['faq_id']}")
    else:
        print(f"все {len(questions)} фраз")
    return summary


def run() -> None:
    report()
