"""Одна точка входа.

python main.py check
python main.py ask "текст вопроса"
python main.py ask --chat demo "А сколько стоит?"
python main.py bot
"""

from __future__ import annotations

import json
import sys

HELP = """\
invenia-bot — поддержка RU/KY по базе FAQ.

  python main.py check                 сравнить два поиска на открытых 40 фразах
  python main.py ask "текст"           напечатать JSON для жюри
  python main.py ask --chat ИМЯ "текст" тот же чат помнит прошлую тему
  python main.py bot                   запустить Telegram

Функция для автопроверки, из корня репозитория:

  python -c "from bot.answer import answer; print(answer('Балансымда канча акча бар?'))"
"""


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help", "help"}:
        print(HELP)
        return 0
    command = args[0]
    if command == "check":
        from bot.compare import run

        run()
        return 0
    if command == "ask":
        from bot.answer import answer

        rest = args[1:]
        chat_id = None
        if rest and rest[0] == "--chat":
            if len(rest) < 3:
                print("Формат: python main.py ask --chat ИМЯ \"текст\"")
                return 1
            chat_id = rest[1]
            rest = rest[2:]
        if not rest:
            print("Нужен текст вопроса.")
            return 1
        text = " ".join(rest)
        print(json.dumps(answer(text, chat_id=chat_id), ensure_ascii=False))
        return 0
    if command == "bot":
        from bot.telegram_bot import run_bot

        run_bot()
        return 0
    print(f"Неизвестная команда: {command}\n")
    print(HELP)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
