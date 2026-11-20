"""15 тем FAQ и разговорные формулировки, по которым ищут оба метода."""

from __future__ import annotations

import csv
import json
from functools import lru_cache
from pathlib import Path

from bot.textutil import normalize_search

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# Короткие тематические фразы, не копия проверочного списка.
# Официальные вопросы из faq.json добавляются отдельно.
ALIASES: dict[int, list[str]] = {
    1: [
        "сколько денег на счету",
        "скока денег",
        "проверка баланса",
        "акча канча бар",
        "балансым кантип кором",
    ],
    2: [
        "остаток минут",
        "остаток гигабайт",
        "остатки минут и гигов",
        "калдык мүнөт",
        "калдык гб",
        "где пакеты",
    ],
    3: [
        "интернет не работает",
        "интернет не грузит",
        "инет не грузит",
        "иштебей жатат",
        "что делать если нет интернета",
    ],
    4: [
        "подключить роуминг",
        "цена роуминга",
        "сколько стоит роуминг",
        "за границей связь",
        "еду за границу",
        "чет өлкөдө роуминг",
    ],
    5: [
        "сменить тариф",
        "другой тариф",
        "тарифти өзгөртүү",
        "хочу новый тариф",
    ],
    6: [
        "потерял сим",
        "новая сим карта",
        "восстановить сим",
        "сим жоголду",
        "симку потерял нужна новая",
    ],
    7: [
        "докупить гигабайты",
        "дополнительный пакет интернета",
        "кошумча гб",
        "кошумча интернет",
    ],
    8: [
        "отключить подписку",
        "платная подписка",
        "списывают за подписки",
        "жазылууну өчүрүү",
    ],
    9: [
        "перевод денег",
        "комиссия перевода",
        "перекинуть деньги другу",
        "акча которуу",
        "досумга акча",
    ],
    10: [
        "настроить apn",
        "точка доступа",
        "апн жөндөө",
        "какая apn",
    ],
    11: [
        "пополнить счет",
        "закинуть деньги на телефон",
        "эсепке акча салуу",
        "как пополнить",
    ],
    12: [
        "свой номер телефона",
        "узнать номер",
        "глянуть мой номер",
        "номерим кайсы",
    ],
    13: [
        "заблокировать сим",
        "украли сим",
        "блокируйте сим",
        "бөгөттөө сим",
        "уурдалган сим",
    ],
    14: [
        "позвать оператора",
        "живой оператор",
        "позовите оператора",
        "оператор чакыруу",
    ],
    15: [
        "детализация расходов",
        "список списаний",
        "чыгымдар тизмеси",
        "списания за месяц",
    ],
}


@lru_cache(maxsize=1)
def load_faq() -> tuple[dict, ...]:
    payload = json.loads((DATA / "faq.json").read_text(encoding="utf-8"))
    return tuple(payload)


@lru_cache(maxsize=1)
def faq_by_id() -> dict[int, dict]:
    return {int(item["id"]): item for item in load_faq()}


@lru_cache(maxsize=1)
def search_documents() -> tuple[tuple[int, str], ...]:
    docs: list[tuple[int, str]] = []
    for item in load_faq():
        faq_id = int(item["id"])
        texts = [item["question_ru"], item["question_ky"], *ALIASES.get(faq_id, [])]
        for text in texts:
            normalized = normalize_search(text)
            if normalized:
                docs.append((faq_id, normalized))
    return tuple(docs)


def load_questions() -> list[dict]:
    rows: list[dict] = []
    with (DATA / "questions_dev.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            raw_id = (row.get("faq_id") or "").strip()
            rows.append(
                {
                    "id": row["id"].strip(),
                    "text": row.get("text") or "",
                    "lang": (row.get("lang") or "").strip(),
                    "faq_id": int(raw_id) if raw_id else None,
                }
            )
    return rows


def load_dialogs() -> list[dict]:
    return json.loads((DATA / "dialogs_example.json").read_text(encoding="utf-8"))
